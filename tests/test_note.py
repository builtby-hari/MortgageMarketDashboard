import re
import unittest
from datetime import date
from unittest import mock

from mortgage_dashboard import (align, curve_spread, curve_stats, spread_stats, delinquency_trend,
                                build_note, note)
from tests.test_dashboard import fx

TODAY = date(2024, 10, 14)


def inputs():
    rows = align(fx("MORTGAGE30US"), fx("MORTGAGE15US"), fx("DGS10"))
    c2, c3 = curve_spread(fx("DGS10"), fx("DGS2")), curve_spread(fx("DGS10"), fx("DGS3MO"))
    return rows, spread_stats(rows), c2, curve_stats(c2), c3, curve_stats(c3)


def stats(**kw):
    s = {"date": date(2024, 10, 10), "mortgage30": 6.3, "dgs10_avg": 4.1, "spread": 2.2, "hist_start": date(1971, 4, 2),
         "mortgage30_wk_chg": 0.0, "mortgage30_52w_chg": None, "dgs10_52w_chg": None, "spread_52w_chg": None,
         "spread_mean": 1.7, "spread_z": 0.0, "spread_pctile": 50.0, "spread_z_5y": None}
    s.update(kw)
    return s


def cvx(value, inverted=None):
    return {"date": date(2024, 10, 10), "value": value, "yoy": None, "inverted_now": value < 0 if inverted is None else inverted}


class TestNote(unittest.TestCase):
    def render(self, today=TODAY):
        rows, st, c2, cv, c3, cv3 = inputs()
        return note.build_note(rows, st, cv, cv3, c2, c3, None, today=today)

    def test_renders_from_fixtures(self):
        html = self.render()
        for part in ("Mortgage and Rates Morning Note", "Headline Numbers", "Curve", "What Moved", "Read Across",
                     "not advice", "FRED", "@page", "8.5in 11in"):
            self.assertIn(part, html)
        self.assertEqual(html.count("<svg"), 5)
        self.assertNotIn("Stale data", html)

    def test_as_of_date_shown(self):
        self.assertIn("As of October 10, 2024", self.render())

    def test_no_external_urls(self):
        html = self.render()
        self.assertNotRegex(html, r"https?://|//[a-z]|src=|href=|@import|url\(")

    def test_escapes_text(self):
        bad = "<script>alert(1)</script>"
        rows, st, c2, cv, c3, cv3 = inputs()
        with mock.patch.object(note, "what_moved", return_value=[bad]), \
                mock.patch.object(note, "read_across", return_value=[("FIG", bad)]):
            html = note.build_note(rows, st, cv, cv3, c2, c3, None, today=TODAY)
        self.assertNotIn(bad, html)
        self.assertEqual(html.count("&lt;script&gt;"), 2)

    def test_stale_warning_only_when_old(self):
        self.assertNotIn("Stale data", self.render(date(2024, 10, 24)))
        self.assertRegex(self.render(date(2025, 3, 1)), r"Stale data warning: .* 142 days old")

    def test_one_page_letter_css(self):
        self.assertRegex(note.CSS, r"width:7\.5in")


class TestRules(unittest.TestCase):
    def test_weekly_movers_ranked_and_capped_at_three(self):
        moves = [("A", 0.01), ("B", -0.30), ("C", 0.05), ("D", 0.10), ("E", 0.0)]
        out = note.what_moved(moves, stats(), [])
        self.assertEqual(out[0], "B fell 30 bp on the week.")
        self.assertEqual(len(out), 3)

    def test_spread_outside_one_sd(self):
        self.assertTrue(any("above its average" in t for t in note.what_moved([], stats(spread_z=1.5), [])))
        self.assertTrue(any("below its average" in t for t in note.what_moved([], stats(spread_z=-1.2), [])))
        self.assertFalse(any("standard" in t for t in note.what_moved([], stats(spread_z=0.9), [])))

    def test_curve_sign_change(self):
        ser = [(date(2024, 10, 3), -0.05), (date(2024, 10, 10), 0.10)]
        out = note.what_moved([], stats(), [("10Y-2Y", cvx(0.10), ser)])
        self.assertTrue(any("change of sign over the week" in t for t in out))
        same = [(date(2024, 10, 3), 0.05), (date(2024, 10, 10), 0.10)]
        self.assertFalse(any("sign" in t for t in note.what_moved([], stats(), [("10Y-2Y", cvx(0.10), same)])))

    def tags(self, **kw):
        a = dict(stats=stats(), cv=cvx(0.5), cv3m=cvx(0.4), dq=None, wk10=None)
        a.update(kw)
        return " ".join(t for _, t in note.read_across(a["stats"], a["cv"], a["cv3m"], a["dq"], a["wk10"]))

    def test_read_across_rules(self):
        self.assertIn("mortgage rates sit wide of Treasuries", self.tags(stats=stats(spread_z_5y=1.4)))
        self.assertIn("mortgage rates sit tight to Treasuries", self.tags(stats=stats(spread_z_5y=-1.4)))
        self.assertNotIn("to Treasuries", self.tags(stats=stats(spread_z_5y=0.5)))
        self.assertIn("net interest margin faces pressure", self.tags(cv=cvx(-0.2)))
        self.assertIn("positive carry", self.tags())
        self.assertIn("refinancing incentive is lower", self.tags(stats=stats(mortgage30_52w_chg=0.30)))
        self.assertIn("refinancing incentive is higher", self.tags(stats=stats(mortgage30_52w_chg=-0.30)))
        self.assertNotIn("refinancing", self.tags(stats=stats(mortgage30_52w_chg=0.10)))
        self.assertIn("higher all-in coupon", self.tags(wk10=0.12))
        self.assertIn("lower all-in coupon", self.tags(wk10=-0.12))
        self.assertIn("upward pressure", self.tags(dq={"direction": "rising", "yoy": 0.2}))
        self.assertIn("downward pressure", self.tags(dq={"direction": "falling", "yoy": -0.2}))


if __name__ == "__main__":
    unittest.main()
