import os
import re
import shutil
import tempfile
import unittest
import urllib.error
from datetime import date

from mortgage_dashboard import (
    SERIES,
    align,
    attach_delinquency,
    build_html,
    change_over_days,
    curve_spread,
    curve_stats,
    delinquency_trend,
    load_series,
    market_summary,
    parse_fred_csv,
    percentile_rank,
    rate_volatility,
    rolling_mean,
    spread_stats,
    weekly_last,
    write_aligned_csv,
    zscore,
)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def raw(name):
    with open(os.path.join(FIX, name + ".csv")) as fh:
        return fh.read()


def fx(name):
    return parse_fred_csv(raw(name))


class TestParse(unittest.TestCase):
    def test_drops_missing_and_handles_both_headers(self):
        for hdr in ("DATE,X", "observation_date,X"):
            got = parse_fred_csv(f"{hdr}\n2024-01-02,1.5\n2024-01-03,.\n2024-01-04,\n2024-01-05,2.0\n")
            self.assertEqual(got, [(date(2024, 1, 2), 1.5), (date(2024, 1, 5), 2.0)])

    def test_sorted(self):
        got = parse_fred_csv("DATE,X\n2024-01-05,2\n2024-01-02,1\n")
        self.assertEqual([d for d, _ in got], [date(2024, 1, 2), date(2024, 1, 5)])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            parse_fred_csv("")

    def test_maintenance_html_page_gets_clear_error(self):
        # FRED served this (HTTP 200) during maintenance
        page = "<!doctype html>\n<html lang=\"en\"><head><title>Site Maintenance | St. Louis Fed<</title>"
        with self.assertRaisesRegex(ValueError, "HTML page"):
            parse_fred_csv(page)

    def test_utf8_bom_is_tolerated(self):
        self.assertEqual(parse_fred_csv("\ufeffDATE,X\n2024-01-02,1.5\n"), [(date(2024, 1, 2), 1.5)])


class TestAlign(unittest.TestCase):
    def setUp(self):
        self.rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        self.by = {r["date"]: r for r in self.rows}

    def test_weeks_without_treasury_data_are_skipped(self):
        self.assertEqual(len(self.rows), 8)
        self.assertNotIn(date(2024, 1, 4), self.by)

    def test_weekly_average_window(self):
        r = self.by[date(2024, 10, 10)]
        self.assertAlmostEqual(r["dgs10_avg"], 4.00)
        self.assertEqual(r["dgs10_obs"], 5)
        # 2024-10-11 (after the date) and 2023-10-05 (7 days before) must be excluded
        self.assertAlmostEqual(self.by[date(2023, 10, 12)]["dgs10_avg"], 4.70)

    def test_holiday_gap_averages_available_prints(self):
        r = self.by[date(2024, 9, 5)]
        self.assertEqual(r["dgs10_obs"], 4)
        self.assertAlmostEqual(r["dgs10_avg"], (3.70 + 3.80 + 3.85 + 3.90) / 4)

    def test_spread_math(self):
        r = self.by[date(2024, 10, 10)]
        self.assertAlmostEqual(r["spread"], 6.32 - 4.00)
        self.assertAlmostEqual(self.by[date(2024, 9, 5)]["spread"], 6.35 - 3.8125)
        self.assertEqual(r["mortgage15"], 5.63)

    def test_missing_15y_is_none(self):
        rows = align(fx("MORTGAGE30US"), [], fx("DGS10"))
        self.assertTrue(all(r["mortgage15"] is None for r in rows))

    def test_attach_delinquency_forward_fills_by_quarter(self):
        rows = attach_delinquency(self.rows, fx("DRSFRMACBS"))
        self.assertEqual(self.by[date(2024, 10, 10)]["delinquency"], 1.66)   # Q2 2024 start 04-01
        self.assertEqual(self.by[date(2024, 8, 29)]["delinquency"], 1.66)
        self.assertEqual(self.by[date(2023, 10, 12)]["delinquency"], 1.56)


class TestStats(unittest.TestCase):
    def test_zscore_known(self):
        self.assertAlmostEqual(zscore(5, [1, 2, 3, 4, 5]), 2 / (2.5 ** 0.5))
        self.assertAlmostEqual(zscore(3, [1, 2, 3, 4, 5]), 0.0)
        with self.assertRaises(ValueError):
            zscore(1, [2, 2, 2])

    def test_percentile(self):
        self.assertEqual(percentile_rank(5, [1, 2, 3, 4, 5]), 90.0)
        self.assertEqual(percentile_rank(0, [1, 2, 3]), 0.0)
        self.assertEqual(percentile_rank(9, [1, 2, 3]), 100.0)
        self.assertEqual(percentile_rank(2, [1, 2, 3]), 50.0)

    def test_change_over_days(self):
        s = [(date(2023, 10, 12), 7.63), (date(2024, 10, 10), 6.32)]
        chg, prior = change_over_days(s, 364)
        self.assertAlmostEqual(chg, -1.31)
        self.assertEqual(prior, date(2023, 10, 12))
        self.assertEqual(change_over_days(s, 100), (None, None))
        self.assertEqual(change_over_days([], 364), (None, None))

    def test_spread_stats_on_fixture(self):
        rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        s = spread_stats(rows)
        self.assertAlmostEqual(s["spread"], 2.32)
        self.assertAlmostEqual(s["mortgage30_wk_chg"], 0.20)
        self.assertAlmostEqual(s["mortgage30_52w_chg"], -1.31)
        self.assertAlmostEqual(s["spread_52w_chg"], 2.32 - 2.93)
        self.assertAlmostEqual(s["dgs10_52w_chg"], 4.00 - 4.70)
        hist = [r["spread"] for r in rows]
        self.assertAlmostEqual(s["spread_z"], zscore(2.32, hist))
        self.assertEqual(s["hist_n"], 8)
        self.assertLess(s["spread_z"], 0)

    def test_five_year_view_ignores_window_arg(self):
        rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        s = spread_stats(rows, window_years=0.5)
        full = spread_stats(rows)
        self.assertAlmostEqual(s["spread_z_5y"], full["spread_z_5y"])
        self.assertAlmostEqual(s["spread_z_5y"], zscore(2.32, [r["spread"] for r in rows]))  # all 8 rows within 5y
        self.assertAlmostEqual(s["spread_pctile_5y"], full["spread_pctile"])

    def test_window_limits_history(self):
        rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        self.assertEqual(spread_stats(rows, window_years=0.5)["hist_n"], 7)

    def test_delinquency_trend(self):
        dq = delinquency_trend(fx("DRSFRMACBS"))
        self.assertEqual(dq["value"], 1.66)
        self.assertAlmostEqual(dq["qoq"], 0.06)
        self.assertAlmostEqual(dq["yoy"], 0.14)   # vs 2023-04-01 (1.52)
        self.assertEqual(dq["direction"], "rising")
        self.assertEqual(dq["streak"], 3)         # 1.50 -> 1.56 -> 1.60 -> 1.66
        self.assertEqual(dq["pctile"], 100 * 5.5 / 6)
        flat = delinquency_trend([(date(2020 + i // 4, 1 + 3 * (i % 4), 1), 2.0) for i in range(6)])
        self.assertEqual(flat["direction"], "flat")
        with self.assertRaises(ValueError):
            delinquency_trend(fx("DRSFRMACBS")[:3])


class TestCurve(unittest.TestCase):
    def setUp(self):
        self.curve = curve_spread(fx("DGS10"), fx("DGS2"))
        self.by = dict(self.curve)

    def test_inner_join_drops_dates_missing_from_either_leg(self):
        # DGS10 has a '.' on 2024-09-02 (dropped by the parser) and DGS2 lacks 2023-10-09
        self.assertNotIn(date(2024, 9, 2), self.by)
        self.assertNotIn(date(2023, 10, 9), self.by)
        self.assertEqual(len(self.curve), 40)

    def test_spread_is_long_minus_short_in_percentage_points(self):
        self.assertAlmostEqual(self.by[date(2024, 10, 11)], 4.10 - 3.90)     # +0.20, upward sloping
        self.assertAlmostEqual(self.by[date(2023, 10, 12)], -0.30)            # inverted
        self.assertAlmostEqual(self.by[date(2024, 8, 23)], 0.40)

    def test_sorted(self):
        self.assertEqual([d for d, _ in self.curve], sorted(d for d, _ in self.curve))

    def test_stats_latest_change_and_inversion_share(self):
        cv = curve_stats(self.curve)
        self.assertEqual(cv["date"], date(2024, 10, 11))
        self.assertAlmostEqual(cv["value"], 0.20)
        self.assertAlmostEqual(cv["yoy"], 0.20 - (-0.30))     # vs 2023-10-12, one day before the 52-week target
        # inverted days: 2023-10-05/06/10/11/12 (5) and 2024-09-06/09/10/11/12/13 (6) = 11 of 40
        self.assertAlmostEqual(cv["inverted_pct"], 100 * 11 / 40)
        self.assertEqual(cv["hist_n"], 40)
        self.assertEqual(cv["hist_start"], date(2023, 10, 5))

    def test_last_inverted_date(self):
        cv = curve_stats(self.curve)
        self.assertFalse(cv["inverted_now"])
        self.assertEqual(cv["last_inverted"], date(2024, 9, 13))
        # trimming the series to a never-inverted stretch leaves no inversion date
        cv2 = curve_stats([x for x in self.curve if x[0] >= date(2024, 10, 1)])
        self.assertIsNone(cv2["last_inverted"])
        cv3 = curve_stats([(date(2024, 1, 1), 0.5), (date(2024, 1, 2), -0.1)])
        self.assertTrue(cv3["inverted_now"])

    def test_window_trims_history(self):
        cv = curve_stats(self.curve, window_years=0.5)
        self.assertEqual(cv["hist_start"], date(2024, 8, 23))
        self.assertAlmostEqual(cv["inverted_pct"], 100 * 6 / 35)   # only the 2024 stretch remains

    def test_no_prior_year_gives_none(self):
        self.assertIsNone(curve_stats(self.curve[5:])["yoy"])

    def test_empty_curve_rejected(self):
        with self.assertRaises(ValueError):
            curve_stats([])

    def test_weekly_last_keeps_last_print_of_each_iso_week(self):
        series = [(date(2024, 10, 7), 1.0), (date(2024, 10, 8), 2.0), (date(2024, 10, 11), 3.0),
                  (date(2024, 10, 14), 4.0)]
        self.assertEqual(weekly_last(series), [(date(2024, 10, 11), 3.0), (date(2024, 10, 14), 4.0)])


class TestCurve3M(unittest.TestCase):
    def setUp(self):
        self.curve = curve_spread(fx("DGS10"), fx("DGS3MO"))
        self.by = dict(self.curve)

    def test_inner_join_drops_dates_missing_from_either_leg(self):
        self.assertNotIn(date(2024, 9, 17), self.by)   # absent from the 3M file
        self.assertNotIn(date(2024, 9, 3), self.by)    # '.' in the 3M file
        self.assertEqual(len(self.curve), 39)

    def test_spread_is_long_minus_short(self):
        self.assertAlmostEqual(self.by[date(2023, 10, 5)], 4.60 - 5.40)
        self.assertAlmostEqual(self.by[date(2024, 10, 11)], 4.10 - 3.90)

    def test_stats_and_last_inverted(self):
        cv = curve_stats(self.curve)
        self.assertAlmostEqual(cv["value"], 0.20)
        self.assertAlmostEqual(cv["yoy"], 0.20 - (-0.60))   # vs 2023-10-12
        self.assertAlmostEqual(cv["inverted_pct"], 100 * 20 / 39)
        self.assertEqual(cv["last_inverted"], date(2024, 10, 3))
        self.assertFalse(cv["inverted_now"])

    def test_summary_sentence_only_when_given(self):
        rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        stats = spread_stats(rows)
        cv3 = curve_stats(self.curve)
        t = market_summary(stats, None, None, None, cv3)
        self.assertIn("10-year minus 3-month Treasury spread was +20 bp", t)
        self.assertIn("it last closed inverted on October 3, 2024", t)
        self.assertNotIn("3-month", market_summary(stats, None))

    def test_html_tile_chart_and_volatility(self):
        rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        stats = spread_stats(rows)
        c2 = curve_spread(fx("DGS10"), fx("DGS2"))
        kw = dict(curve=c2, cv=curve_stats(c2), curve3m=self.curve, cv3m=curve_stats(self.curve))
        html = build_html(rows, [], stats, None, **kw, vol=12.3)
        self.assertIn("10Y - 3M curve", html)
        self.assertIn("10Y minus 3M", html)
        self.assertIn("10Y volatility", html)
        self.assertIn("12.3 bp", html)
        self.assertNotIn("10Y volatility", build_html(rows, [], stats, None, **kw))


class TestRollingMean(unittest.TestCase):
    def test_trailing_window_values(self):
        s = [(date(2024, 1, i), float(i)) for i in range(1, 6)]
        out = rolling_mean(s, 3)
        self.assertEqual([v for _, v in out], [2.0, 3.0, 4.0])
        self.assertEqual(out[0][0], date(2024, 1, 3))

    def test_window_longer_than_series_gives_empty(self):
        self.assertEqual(rolling_mean([(date(2024, 1, 1), 1.0)], 3), [])


class TestRateVol(unittest.TestCase):
    def _daily(self, values, start=date(2024, 6, 1)):
        return [(date.fromordinal(start.toordinal() + i), v) for i, v in enumerate(values)]

    def test_constant_series_has_zero_vol(self):
        self.assertEqual(rate_volatility(self._daily([4.0] * 10)), 0.0)

    def test_alternating_moves_match_hand_value(self):
        # six changes of +10, -10, ... bp: mean 0, sample variance 600 / 5 = 120
        vals = [4.00, 4.10] * 3 + [4.00]
        self.assertAlmostEqual(rate_volatility(self._daily(vals)), 120 ** 0.5)

    def test_too_few_changes_returns_none(self):
        self.assertIsNone(rate_volatility(self._daily([4.0, 4.1, 4.0, 4.1, 4.0])))  # 4 changes
        self.assertIsNone(rate_volatility([]))

    def test_window_excludes_old_moves(self):
        # a 400 bp jump 60+ days before the last print must not count
        old = self._daily([1.0, 5.0], start=date(2024, 1, 1))
        recent = self._daily([4.0] * 7, start=date(2024, 6, 1))
        self.assertEqual(rate_volatility(old + recent, days=63), 0.0)
        self.assertGreater(rate_volatility(old + recent, days=400), 0.0)


class TestSummary(unittest.TestCase):
    def setUp(self):
        self.rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        self.stats = spread_stats(self.rows)
        self.dq = delinquency_trend(fx("DRSFRMACBS"))
        self.text = market_summary(self.stats, self.dq)

    def test_contains_levels_and_changes(self):
        t = self.text
        self.assertIn("October 10, 2024", t)
        self.assertIn("30-year fixed mortgage rate was 6.32%", t)
        self.assertIn("up 20 bp on the week", t)
        self.assertIn("down 131 bp over 52 weeks", t)
        self.assertIn("15-year was 5.63%", t)
        self.assertIn("10-year Treasury averaged 4.00%", t)
        self.assertIn("spread was 232 bp", t)
        self.assertIn("down 61 bp over 52 weeks", t)

    def test_contains_zscore_percentile_delinquency(self):
        t = self.text
        self.assertRegex(t, r"\d\.\d standard deviations below the average of \d+ bp \(8 weekly observations since 2023\)")
        self.assertRegex(t, r"at the \d+(st|nd|rd|th) percentile of the range 228 to 293 bp")
        self.assertIn("delinquency rate was 1.66% in Q2 2024", t)
        self.assertIn("up 0.06 pp on the quarter and up 0.14 pp on the year (rising trend)", t)

    def test_no_delinquency_is_fine(self):
        self.assertNotIn("delinquency", market_summary(self.stats, None))

    def test_curve_sentence_only_when_curve_given(self):
        self.assertNotIn("2-year", self.text)
        cv = curve_stats(curve_spread(fx("DGS10"), fx("DGS2")))
        t = market_summary(self.stats, self.dq, None, cv)
        self.assertIn("10-year minus 2-year Treasury spread was +20 bp (up 50 bp over 52 weeks)", t)
        self.assertIn("inverted on 28% of 40 daily readings since 2023", t)
        self.assertIn("it last closed inverted on September 13, 2024", t)

    def test_five_year_sentence_only_for_full_history(self):
        self.assertIn("trailing five years alone", self.text)
        self.assertNotIn("trailing five years alone", market_summary(self.stats, self.dq, "in the trailing 2 years"))


class TestIOAndReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_offline_requires_cache(self):
        with self.assertRaises(FileNotFoundError):
            load_series("DGS10", self.tmp, offline=True)

    def test_online_writes_cache_then_offline_reads_it(self):
        text = raw("DGS10")
        got = load_series("DGS10", self.tmp, fetch=lambda sid: text)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "DGS10.csv")))
        self.assertEqual(load_series("DGS10", self.tmp, offline=True), got)

    def test_download_failure_falls_back_to_cache(self):
        text = raw("DGS10")
        load_series("DGS10", self.tmp, fetch=lambda sid: text)

        def boom(sid):
            raise urllib.error.URLError("no network")
        msgs = []
        got = load_series("DGS10", self.tmp, fetch=boom, log=msgs.append)
        self.assertEqual(len(got), len(parse_fred_csv(text)))
        self.assertTrue(msgs and "using cache" in msgs[0])

    def test_offline_without_cache_uses_snapshot(self):
        text = raw("DGS10")
        os.makedirs(os.path.join(self.tmp, "snapshot"))
        with open(os.path.join(self.tmp, "snapshot", "DGS10.csv"), "w") as fh:
            fh.write(text)
        msgs = []
        got = load_series("DGS10", self.tmp, offline=True, log=msgs.append)
        self.assertEqual(got, parse_fred_csv(text))
        self.assertTrue(msgs and "snapshot" in msgs[0])
        # an online refresh writes the normal cache and leaves the snapshot untouched
        load_series("DGS10", self.tmp, fetch=lambda sid: "DATE,DGS10\n2030-01-02,9.99\n")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "DGS10.csv")))
        with open(os.path.join(self.tmp, "snapshot", "DGS10.csv")) as fh:
            self.assertEqual(fh.read(), text)

    def test_committed_snapshot_covers_every_series(self):
        snap = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "snapshot")
        for sid in SERIES:
            with open(os.path.join(snap, f"{sid}.csv"), newline="") as fh:
                self.assertTrue(parse_fred_csv(fh.read()))

    def test_download_failure_without_cache_raises(self):
        def boom(sid):
            raise urllib.error.URLError("no network")
        with self.assertRaises(RuntimeError):
            load_series("DGS10", self.tmp, fetch=boom)

    def test_garbage_download_does_not_clobber_cache(self):
        text = raw("DGS10")
        load_series("DGS10", self.tmp, fetch=lambda sid: text)
        load_series("DGS10", self.tmp, fetch=lambda sid: "<html>blocked</html>", log=lambda m: None)
        with open(os.path.join(self.tmp, "DGS10.csv")) as fh:
            self.assertEqual(fh.read(), text)

    def _build(self):
        rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
        dl = fx("DRSFRMACBS")
        attach_delinquency(rows, dl)
        return rows, dl, spread_stats(rows), delinquency_trend(dl)

    def test_csv_output(self):
        rows, *_ = self._build()
        path = os.path.join(self.tmp, "a.csv")
        write_aligned_csv(path, rows)
        with open(path) as fh:
            lines = fh.read().strip().splitlines()
        self.assertEqual(lines[0], "date,mortgage30,mortgage15,dgs10_avg,dgs10_obs,spread,spread_bp,delinquency")
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[-1], "2024-10-10,6.32,5.63,4.0000,5,2.3200,232.0,1.66")

    def test_html_is_self_contained(self):
        rows, dl, stats, dq = self._build()
        html = build_html(rows, dl, stats, dq)
        self.assertEqual(html.count("<svg"), 3)
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertNotRegex(html, r"<script|<link|src=|@import|url\(")
        self.assertEqual([u for u in re.findall(r"https?://[^\"' <]+", html)
                          if "w3.org" not in u], [])
        self.assertIn("30-year fixed mortgage rate was 6.32%", html)

    def test_html_with_curve_adds_section_tile_and_chart(self):
        rows, dl, stats, dq = self._build()
        curve = curve_spread(fx("DGS10"), fx("DGS2"))
        html = build_html(rows, dl, stats, dq, curve=curve, cv=curve_stats(curve))
        self.assertEqual(html.count("<svg"), 4)
        self.assertIn("Treasury Curve", html)
        self.assertIn("10Y - 2Y curve", html)
        self.assertIn("+20 bp", html)
        self.assertNotRegex(html, r"<script|<link|src=|@import|url\(")

    def test_html_without_curve_is_unchanged(self):
        rows, dl, stats, dq = self._build()
        html = build_html(rows, dl, stats, dq)
        self.assertNotIn("Treasury Curve", html)

    def test_default_series_include_two_year(self):
        from mortgage_dashboard import SERIES
        self.assertIn("DGS2", SERIES)
        self.assertIn("DGS3MO", SERIES)


class TestCliStaleWarning(unittest.TestCase):
    def test_old_cache_warns_on_stderr_but_still_runs(self):
        import contextlib, io

        import cli
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        for sid in ("MORTGAGE30US", "MORTGAGE15US", "DGS10", "DGS2", "DGS3MO", "DRSFRMACBS"):
            shutil.copy(os.path.join(FIX, sid + ".csv"), tmp)
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = cli.main(["--offline", "--data-dir", tmp, "--out", os.path.join(tmp, "out")])
        self.assertEqual(rc, 0)
        self.assertIn("days old; data may be stale", err.getvalue())
        self.assertTrue(os.path.exists(os.path.join(tmp, "out", "report.html")))

    def test_bad_window_years_is_a_clean_error(self):
        import contextlib, io

        import cli
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main(["--window-years", "0"])

    def test_empty_cached_series_is_a_clean_error(self):
        import contextlib, io

        import cli
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        for sid in ("MORTGAGE30US", "MORTGAGE15US", "DGS10", "DGS2", "DGS3MO", "DRSFRMACBS"):
            shutil.copy(os.path.join(FIX, sid + ".csv"), tmp)
        with open(os.path.join(tmp, "DGS10.csv"), "w") as fh:
            fh.write("observation_date,DGS10\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["--offline", "--data-dir", tmp, "--out", os.path.join(tmp, "o")])
        self.assertEqual(rc, 1)
        self.assertIn("no observations", err.getvalue())

    def test_offline_with_old_cache_missing_dgs3mo_gives_clear_error(self):
        import contextlib, io

        import cli
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        for sid in ("MORTGAGE30US", "MORTGAGE15US", "DGS10", "DGS2", "DRSFRMACBS"):
            shutil.copy(os.path.join(FIX, sid + ".csv"), tmp)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["--offline", "--data-dir", tmp, "--out", os.path.join(tmp, "o")])
        self.assertEqual(rc, 1)
        self.assertIn("DGS3MO.csv", err.getvalue())
        self.assertIn("run once without --offline", err.getvalue())


if __name__ == "__main__":
    unittest.main()
