"""Alignment, spread math and statistics. Pure functions, no I/O."""

import bisect
import statistics
from datetime import timedelta

WINDOW_DAYS = 7  # the 7 calendar days ending on the mortgage observation date


def _lookup(series):
    return dict(series)


def align(mort30, mort15, dgs10, window=WINDOW_DAYS):
    """Join weekly mortgage rates to the average 10Y Treasury yield for the same week.

    For each 30Y mortgage observation on date d, the Treasury figure is the mean
    of all DGS10 observations dated d-6 .. d (7 calendar days; holidays and
    missing prints simply drop out). Weeks with no Treasury print are skipped.
    Returns a list of dicts sorted by date, spread in percentage points.
    """
    t_dates = [d for d, _ in dgs10]
    t_vals = [v for _, v in dgs10]
    m15 = _lookup(mort15)
    rows = []
    for d, m in mort30:
        lo = bisect.bisect_left(t_dates, d - timedelta(days=window - 1))
        hi = bisect.bisect_right(t_dates, d)
        if hi <= lo:
            continue
        avg = sum(t_vals[lo:hi]) / (hi - lo)
        rows.append({"date": d, "mortgage30": m, "mortgage15": m15.get(d),
                     "dgs10_avg": avg, "dgs10_obs": hi - lo, "spread": m - avg})
    return rows


def curve_spread(long_leg, short_leg):
    """Long minus short Treasury yield, in percentage points, on dates where both legs have a print.

    An inner join on date: a holiday that affects only one leg drops out instead of being filled.
    Returns a sorted list of (date, spread).
    """
    short = dict(short_leg)
    return [(d, v - short[d]) for d, v in long_leg if d in short]


def curve_stats(curve, window_years=None):
    """Latest curve slope, 52-week change, and how often the curve has been inverted.

    `curve` is a sorted list of (date, spread in pp). With `window_years` the history is trimmed
    to that many trailing years. Inverted means a negative slope (short rates above long rates).
    """
    if not curve:
        raise ValueError("no curve observations")
    d, v = curve[-1]
    hist = curve
    if window_years:
        cutoff = d - timedelta(days=round(365.25 * window_years))
        hist = [x for x in curve if x[0] >= cutoff]
    chg, _ = change_over_days(curve, 364)
    vals = [x for _, x in hist]
    return {"date": d, "value": v, "yoy": chg,
            "inverted_pct": 100.0 * sum(1 for x in vals if x < 0) / len(vals),
            "pctile": percentile_rank(v, vals),
            "hist_start": hist[0][0], "hist_n": len(vals)}


def weekly_last(series):
    """Keep the last observation in each ISO week (for lighter charts of daily data)."""
    last = {}
    for d, v in series:
        iso = d.isocalendar()
        last[(iso[0], iso[1])] = (d, v)
    return [last[k] for k in sorted(last)]


def attach_delinquency(rows, delinq):
    """Add 'delinquency' to each row: the quarter whose start date is the latest <= row date.

    Quarters are matched by their label date, not by publication date, so the
    value is not a point-in-time series (FRED publishes with a lag).
    """
    q_dates = [d for d, _ in delinq]
    for r in rows:
        i = bisect.bisect_right(q_dates, r["date"]) - 1
        r["delinquency"] = delinq[i][1] if i >= 0 else None
    return rows


def change_over_days(series, days=364, tolerance=7):
    """Change between the latest point and the latest point on/before (latest - days).

    `series` is a sorted list of (date, value). Returns (change, prior_date) or
    (None, None) if no observation lies within `tolerance` days of the target.
    """
    if not series:
        return None, None
    d, v = series[-1]
    target = d - timedelta(days=days)
    dates = [x for x, _ in series]
    i = bisect.bisect_right(dates, target) - 1
    if i < 0 or (target - dates[i]).days > tolerance:
        return None, None
    return v - series[i][1], dates[i]


def zscore(value, history):
    """Standard score of `value` against `history` (sample standard deviation)."""
    if len(history) < 2:
        raise ValueError("need at least two observations")
    sd = statistics.stdev(history)
    if sd == 0:
        raise ValueError("history has zero variance")
    return (value - statistics.mean(history)) / sd


def percentile_rank(value, history):
    """Mid-rank percentile (0-100): share below plus half the share equal."""
    below = sum(1 for h in history if h < value)
    equal = sum(1 for h in history if h == value)
    return 100.0 * (below + 0.5 * equal) / len(history)


def spread_stats(rows, window_years=None):
    """Latest spread, changes and z-score/percentile against history (current included)."""
    if not rows:
        raise ValueError("no aligned rows")
    last = rows[-1]
    hist_rows = rows
    if window_years:
        cutoff = last["date"] - timedelta(days=round(365.25 * window_years))
        hist_rows = [r for r in rows if r["date"] >= cutoff]
    hist = [r["spread"] for r in hist_rows]
    wk, _ = change_over_days([(r["date"], r["mortgage30"]) for r in rows], 7, 0)
    yr, _ = change_over_days([(r["date"], r["mortgage30"]) for r in rows], 364)
    sp_yr, _ = change_over_days([(r["date"], r["spread"]) for r in rows], 364)
    t_yr, _ = change_over_days([(r["date"], r["dgs10_avg"]) for r in rows], 364)
    return {
        "date": last["date"], "mortgage30": last["mortgage30"], "mortgage15": last["mortgage15"],
        "dgs10_avg": last["dgs10_avg"], "spread": last["spread"],
        "mortgage30_wk_chg": wk, "mortgage30_52w_chg": yr,
        "dgs10_52w_chg": t_yr, "spread_52w_chg": sp_yr,
        "spread_mean": statistics.mean(hist), "spread_stdev": statistics.stdev(hist) if len(hist) > 1 else 0.0,
        "spread_z": zscore(last["spread"], hist), "spread_pctile": percentile_rank(last["spread"], hist),
        "spread_min": min(hist), "spread_max": max(hist),
        "hist_n": len(hist), "hist_start": hist_rows[0]["date"],
    }


def delinquency_trend(delinq, flat_band=0.10):
    """Latest delinquency rate, QoQ and YoY change, direction and history percentile.

    Direction compares the year-over-year change to +/- `flat_band` (pp).
    """
    if len(delinq) < 5:
        raise ValueError("need at least five quarterly observations")
    d, v = delinq[-1]
    qoq = v - delinq[-2][1]
    yoy = v - delinq[-5][1]
    direction = "rising" if yoy > flat_band else "falling" if yoy < -flat_band else "flat"
    # consecutive quarters moving in the same direction as the latest quarter
    run, sign = 0, (qoq > 0) - (qoq < 0)
    for i in range(len(delinq) - 1, 0, -1):
        s = (delinq[i][1] > delinq[i - 1][1]) - (delinq[i][1] < delinq[i - 1][1])
        if s != sign or s == 0:
            break
        run += 1
    return {"date": d, "value": v, "qoq": qoq, "yoy": yoy, "direction": direction,
            "streak": run, "streak_sign": sign,
            "pctile": percentile_rank(v, [x for _, x in delinq]),
            "hist_start": delinq[0][0], "hist_n": len(delinq)}
