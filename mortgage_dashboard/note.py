"""One-page "Mortgage and Rates Morning Note". Every sentence is filled from computed numbers by rules."""

from datetime import date, timedelta
from html import escape

from .analytics import change_over_days, weekly_last
from .summary import _ordinal

STALE_DAYS = 14  # weekly PMMS plus a holiday week still stays under this
BIG_MOVE_BP = 25  # a 52-week move at least this large triggers the rate-level Read Across rules
WEEK_MOVE_BP = 10  # a weekly 10Y move at least this large triggers the benchmark rule
SPARK_POINTS = 52

CSS = """
@page{size:8.5in 11in;margin:.5in}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:#111;font:10pt/1.4 Georgia,'Times New Roman',serif}
main{width:7.5in;max-width:100%;margin:0 auto;padding:.3in 0}
h1{font-size:17pt;margin:0;border-bottom:2px solid #1f3a5f;padding-bottom:3px}
h2{font-size:10.5pt;margin:12px 0 4px;color:#1f3a5f;text-transform:uppercase;letter-spacing:.04em}
.sub{margin:3px 0 6px;color:#444;font-size:9pt}
.warn{border:1px solid #9a3412;background:#fff7ed;color:#7c2d12;padding:4px 8px;margin:6px 0;font-size:9pt}
table{border-collapse:collapse;width:100%;font-size:9pt;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:3px 6px;border-bottom:1px solid #ccc}
th{border-bottom:1px solid #111}th:first-child,td:first-child{text-align:left}
ul{margin:2px 0;padding-left:16px}li{margin:2px 0}
.box{border:1px solid #1f3a5f;padding:4px 10px 6px;margin-top:10px}
.sparks{display:flex;flex-wrap:wrap;gap:6px 14px}
.sp{width:1.4in;font-size:8pt;color:#444}.sp svg{display:block;width:100%;height:30px}
footer{margin-top:12px;border-top:1px solid #999;padding-top:4px;font-size:8pt;color:#444}
@media print{main{padding:0}}
"""


def _bp(x, sign=True):
    return "n/a" if x is None else f"{x * 100:{'+' if sign else ''},.0f} bp"


def _week(series):
    return change_over_days(series, 7, 3)[0]


def _spark(label, series, now):
    pts = series[-SPARK_POINTS:]
    if len(pts) < 2:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    w, h = 100.0, 30.0
    xy = [(i * w / (len(vals) - 1), h - 3 - (v - lo) / rng * (h - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    return (f'<div class="sp"><svg viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none" role="img" '
            f'aria-label="{escape(label)} sparkline">'
            f'<polyline points="{line}" fill="none" stroke="#1f3a5f" stroke-width="1.2" '
            f'vector-effect="non-scaling-stroke"/></svg>{escape(label)}: {escape(now)}</div>')


def what_moved(moves, stats, curves):
    """Rule-based bullets.

    W1 the three largest absolute weekly changes (bp) among the 30Y rate, 10Y weekly average, spread and curve slopes.
    W2 the spread is more than 1 standard deviation from its mean.
    W3 a curve slope changed sign over the week or over 52 weeks.
    """
    out = []
    ranked = sorted((m for m in moves if m[1] is not None and round(m[1] * 100) != 0), key=lambda m: -abs(m[1]))
    for name, chg in ranked[:3]:
        out.append(f"{name} {'rose' if chg > 0 else 'fell'} {_bp(abs(chg), False)} on the week.")
    if not ranked:
        out.append("No tracked series moved by 1 bp or more on the week.")
    z = stats["spread_z"]
    if abs(z) > 1:
        out.append(f"The mortgage-Treasury spread of {_bp(stats['spread'], False)} is {abs(z):.1f} standard "
                   f"deviations {'above' if z > 0 else 'below'} its average of {_bp(stats['spread_mean'], False)}.")
    for name, cv, ser in curves:
        for days, label in ((7, "the week"), (364, "52 weeks")):
            chg = change_over_days(ser, days, 7)[0] if ser else None
            if chg is None:
                continue
            before, now = cv["value"] - chg, cv["value"]
            if before * now < 0:
                out.append(f"The {name} slope moved from {_bp(before)} to {_bp(now)}, a change of sign over {label}.")
    return out


def read_across(stats, cv, cv3m, dq, wk10):
    """Rule-based FIG and DCM implications, each phrased as a conditional fact.

    R1 spread z-score vs its trailing 5 years >= +1 or <= -1.
    R2 either curve slope below zero (inverted).
    R3 both curve slopes above zero.
    R4 30Y rate up or down at least 25 bp over 52 weeks.
    R5 10Y weekly average up or down at least 10 bp on the week.
    R6 bank mortgage delinquency trend rising or falling (4 quarter change beyond 0.10 pp).
    """
    out = []
    z5 = stats.get("spread_z_5y")
    if z5 is not None and z5 >= 1:
        out.append(("FIG", f"Spread {z5:.1f} standard deviations above its 5-year average: originations face wider primary-secondary spreads."))
    elif z5 is not None and z5 <= -1:
        out.append(("FIG", f"Spread {abs(z5):.1f} standard deviations below its 5-year average: originations face tighter primary-secondary spreads."))
    inv = [n for n, c in (("10Y-2Y", cv), ("10Y-3M", cv3m)) if c and c["inverted_now"]]
    if inv:
        out.append(("FIG", f"With the {' and '.join(inv)} curve inverted, funding costs sit above long asset yields: net interest margin faces pressure."))
    elif cv and cv3m and cv["value"] > 0 and cv3m["value"] > 0:
        out.append(("FIG", "With the curve upward sloping on both measures, term lending earns a positive carry over short funding."))
    chg = stats["mortgage30_52w_chg"]
    if chg is not None and chg * 100 >= BIG_MOVE_BP:
        out.append(("FIG", f"With the 30Y rate up {_bp(chg, False)} over 52 weeks: refinancing incentive is lower and origination volumes face pressure."))
    elif chg is not None and chg * 100 <= -BIG_MOVE_BP:
        out.append(("FIG", f"With the 30Y rate down {_bp(chg, False)} over 52 weeks: refinancing incentive is higher and origination volumes have support."))
    if wk10 is not None and wk10 * 100 >= WEEK_MOVE_BP:
        out.append(("DCM", f"With the 10Y benchmark up {_bp(wk10, False)} on the week: fixed-rate issuers face a higher all-in coupon at the same spread."))
    elif wk10 is not None and wk10 * 100 <= -WEEK_MOVE_BP:
        out.append(("DCM", f"With the 10Y benchmark down {_bp(wk10, False)} on the week: fixed-rate issuers face a lower all-in coupon at the same spread."))
    if dq and dq["direction"] == "rising":
        out.append(("FIG", f"With bank mortgage delinquency rising ({dq['yoy']:+.2f} pp on the year): provisioning needs for mortgage books face upward pressure."))
    elif dq and dq["direction"] == "falling":
        out.append(("FIG", f"With bank mortgage delinquency falling ({dq['yoy']:+.2f} pp on the year): provisioning needs for mortgage books face downward pressure."))
    return out


def build_note(rows, stats, cv, cv3m, curve=None, curve3m=None, dq=None, today=None):
    """Return the one-page note as a self-contained HTML string. `today` sets the stale-data check."""
    today = today or date.today()
    asof = stats["date"]
    if cv:
        asof = min(asof, cv["date"])
    age = (today - asof).days
    dg = [(r["date"], r["dgs10_avg"]) for r in rows]
    sp = [(r["date"], r["spread"]) for r in rows]
    m30 = [(r["date"], r["mortgage30"]) for r in rows]
    wk10, wksp = _week(dg), _week(sp)
    curves = [(n, c, ser) for n, c, ser in (("10Y-2Y", cv, curve), ("10Y-3M", cv3m, curve3m)) if c]
    curve_wk = {n: change_over_days(ser, 7, 3)[0] if ser else None for n, _, ser in curves}
    moves = [("The 30Y mortgage rate", stats["mortgage30_wk_chg"]), ("The 10Y Treasury weekly average", wk10),
             ("The mortgage-Treasury spread", wksp)]
    moves += [(f"The {n} slope", curve_wk[n]) for n, _, _ in curves]
    heads = [("30Y Mortgage Rate", f"{stats['mortgage30']:.2f}%", stats["mortgage30_wk_chg"], stats["mortgage30_52w_chg"]),
             ("10Y Treasury (Week Avg)", f"{stats['dgs10_avg']:.2f}%", wk10, stats["dgs10_52w_chg"]),
             ("Spread", _bp(stats["spread"], False), wksp, stats["spread_52w_chg"])]
    trs = "".join(f"<tr><td>{escape(n)}</td><td>{escape(v)}</td><td>{_bp(w)}</td><td>{_bp(y)}</td></tr>" for n, v, w, y in heads)
    trs += (f"<tr><td>Spread Z-Score / Percentile</td><td>{stats['spread_z']:+.2f}</td>"
            f"<td colspan=\"2\">{_ordinal(stats['spread_pctile'])} percentile since {stats['hist_start']:%Y}</td></tr>")
    ctr = "".join(
        f"<tr><td>{escape(n)}</td><td>{_bp(c['value'])}</td><td>{_bp(curve_wk[n])}</td>"
        f"<td>{_bp(c['yoy'])}</td><td>{'Inverted' if c['inverted_now'] else 'Not inverted'}</td></tr>" for n, c, _ in curves)
    sparks = "".join(s for s in (
        _spark("30Y Rate", m30, f"{stats['mortgage30']:.2f}%"), _spark("10Y Avg", dg, f"{stats['dgs10_avg']:.2f}%"),
        _spark("Spread", sp, _bp(stats["spread"], False)),
        *(_spark(f"{n} Slope", weekly_last(ser), _bp(c["value"])) for n, c, ser in curves if ser)))
    moved = "".join(f"<li>{escape(t)}</li>" for t in what_moved(moves, stats, curves))
    ra = read_across(stats, cv, cv3m, dq, wk10)
    rat = "".join(f"<li><b>{tag}</b>: {escape(t)}</li>" for tag, t in ra) or "<li>No Read Across rule fired on the latest data.</li>"
    warn = (f'<div class="warn">Stale data warning: the latest observation is {age} days old as of {today:%B} {today.day}, {today.year}.</div>'
            if age > STALE_DAYS else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mortgage and Rates Morning Note</title><style>{CSS}</style></head>
<body><main>
<h1>Mortgage and Rates Morning Note</h1>
<p class="sub">As of {asof:%B} {asof.day}, {asof.year}</p>
{warn}
<h2>Headline Numbers</h2>
<table><tr><th>Measure</th><th>Latest</th><th>Week</th><th>52 Weeks</th></tr>{trs}</table>
<h2>Curve</h2>
<table><tr><th>Slope</th><th>Latest</th><th>Week</th><th>52 Weeks</th><th>Status</th></tr>{ctr}</table>
<h2>Trend, Last 52 Weeks</h2><div class="sparks">{sparks}</div>
<h2>What Moved</h2><ul>{moved}</ul>
<div class="box"><h2 style="margin-top:2px">Read Across</h2><ul>{rat}</ul></div>
<footer>Source: FRED, Federal Reserve Bank of St. Louis (Freddie Mac PMMS; Treasury constant maturity yields). As of {asof:%Y-%m-%d}. Rule-based text from computed figures. Informational only; not advice.</footer>
</main></body></html>
"""
