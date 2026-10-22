"""Build the self-contained HTML report and the aligned-data CSV."""

import csv
from datetime import timedelta
from html import escape

from .analytics import rolling_mean, weekly_last
from .charts import line_chart
from .summary import market_summary

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c1e22;--mut:#5b6068;--line:#e2e4e8}
@media (prefers-color-scheme: dark){:root{--bg:#0f1115;--card:#16181d;--fg:#ececec;--mut:#9aa0a8;--line:#2a2d34}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,Helvetica,Arial,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 2px}h2{font-size:1.1rem;margin:28px 0 10px}
.sub{color:var(--mut);margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.kpi .v{font-size:1.5rem;font-weight:600}.kpi .l{color:var(--mut);font-size:.82rem}.kpi .d{font-size:.85rem;color:var(--mut)}
table{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}
.wrap{overflow-x:auto}.note{color:var(--mut);font-size:.85rem}
"""


def _signed(x, unit="bp", scale=100, dec=0):
    if x is None:
        return "n/a"
    return f"{x * scale:+,.{dec}f} {unit}"


def write_aligned_csv(path, rows):
    cols = ["date", "mortgage30", "mortgage15", "dgs10_avg", "dgs10_obs", "spread", "spread_bp", "delinquency"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            def f(k, nd):
                v = r.get(k)
                return "" if v is None else f"{v:.{nd}f}"
            w.writerow([r["date"].isoformat(), f("mortgage30", 2), f("mortgage15", 2), f("dgs10_avg", 4),
                        r["dgs10_obs"], f("spread", 4), f"{r['spread'] * 100:.1f}", f("delinquency", 2)])


def charts_for(rows, delinq, stats, chart_years=5, standalone=False, curve=None, curve3m=None):
    """Return {name: svg} for the dashboard charts (a fourth, the curve slope, when `curve` is given)."""
    last = rows[-1]["date"]
    recent = [r for r in rows if r["date"] >= last - timedelta(days=round(365.25 * chart_years))]
    spread = [(r["date"], r["spread"]) for r in rows]
    out = {
        "rates": line_chart(
            f"Mortgage rates vs 10Y Treasury, last {chart_years} years (%)",
            [("30Y mortgage", "c1", [(r["date"], r["mortgage30"]) for r in recent]),
             ("15Y mortgage", "c3", [(r["date"], r["mortgage15"]) for r in recent if r["mortgage15"] is not None]),
             ("10Y Treasury (weekly avg)", "c2", [(r["date"], r["dgs10_avg"]) for r in recent])],
            "Percent", standalone=standalone),
        "spread": line_chart(
            "30Y mortgage - 10Y Treasury spread (percentage points)",
            [("Spread", "c1", spread)] + ([("52-week average", "c2", rolling_mean(spread, 52))] if len(spread) >= 52 else []),
            "Percentage points",
            band=(stats["spread_mean"] - stats["spread_stdev"], stats["spread_mean"] + stats["spread_stdev"]),
            hline=(stats["spread_mean"], f"mean {stats['spread_mean']*100:,.0f} bp (band = +/-1 sd)"),
            marker=(last, stats["spread"], f"{stats['spread']*100:,.0f} bp, z = {stats['spread_z']:+.1f}"),
            yfmt="{:.1f}", standalone=standalone),
    }
    if curve:
        lines = [("10Y minus 2Y", "c3", weekly_last(curve))]
        if curve3m:
            lines.append(("10Y minus 3M", "c2", weekly_last(curve3m)))
        out["curve"] = line_chart(
            "10Y - 2Y and 10Y - 3M Treasury spreads (percentage points, weekly)" if curve3m
            else "10Y - 2Y Treasury spread (percentage points, weekly)",
            lines, "Percentage points",
            hline=(0.0, "inverted below zero"), yfmt="{:.1f}", standalone=standalone)
    if delinq:
        out["delinquency"] = line_chart(
            "Single-family mortgage delinquency rate (%, quarterly)",
            [("", "c2", delinq)], "Percent", yfmt="{:.1f}", standalone=standalone)
    return out


def build_html(rows, delinq, stats, dq, window_label=None, chart_years=5, generated=None,
               curve=None, cv=None, curve3m=None, cv3m=None, vol=None):
    svgs = charts_for(rows, delinq, stats, chart_years, curve=curve if cv else None,
                      curve3m=curve3m if cv3m else None)
    summary = market_summary(stats, dq, window_label, cv, cv3m)
    kp = [("30Y mortgage", f"{stats['mortgage30']:.2f}%", f"{_signed(stats['mortgage30_52w_chg'])} vs 52 wks"),
          ("10Y Treasury (wk avg)", f"{stats['dgs10_avg']:.2f}%", f"{_signed(stats['dgs10_52w_chg'])} vs 52 wks"),
          ("Spread", f"{stats['spread']*100:,.0f} bp", f"{_signed(stats['spread_52w_chg'])} vs 52 wks"),
          ("Spread z-score", f"{stats['spread_z']:+.2f}", f"{stats['spread_pctile']:.0f}th percentile")]
    if cv:
        kp.append(("10Y - 2Y curve", f"{cv['value']*100:+,.0f} bp",
                   f"{_signed(cv['yoy'])} vs 52 wks" if cv["yoy"] is not None else f"inverted {cv['inverted_pct']:.0f}% of days"))
    if cv3m:
        kp.append(("10Y - 3M curve", f"{cv3m['value']*100:+,.0f} bp",
                   f"{_signed(cv3m['yoy'])} vs 52 wks" if cv3m["yoy"] is not None
                   else f"inverted {cv3m['inverted_pct']:.0f}% of days"))
    if vol is not None:
        kp.append(("10Y volatility", f"{vol:.1f} bp", "daily-change std dev, 63 days"))
    if dq:
        kp.append(("Delinquency rate", f"{dq['value']:.2f}%", f"{dq['direction']}, {dq['yoy']:+.2f} pp YoY"))
    tiles = "".join(f'<div class="card kpi"><div class="l">{escape(l)}</div><div class="v">{escape(v)}</div>'
                    f'<div class="d">{escape(d)}</div></div>' for l, v, d in kp)
    body = "".join(
        f"<tr><td>{r['date']}</td><td>{r['mortgage30']:.2f}</td>"
        f"<td>{'' if r['mortgage15'] is None else format(r['mortgage15'], '.2f')}</td>"
        f"<td>{r['dgs10_avg']:.2f}</td><td>{r['spread']*100:,.0f}</td></tr>" for r in reversed(rows[-12:]))
    gen = f" Generated {generated}." if generated else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mortgage Market Dashboard</title><style>{CSS}</style></head>
<body><main>
<h1>Mortgage Market Dashboard</h1>
<p class="sub">Data through {stats['date']} &middot; Source: FRED (Freddie Mac PMMS; Federal Reserve H.15 and Board of Governors data).{gen}</p>
<div class="card"><p style="margin:0">{escape(summary)}</p></div>
<div class="kpis">{tiles}</div>
<h2>Rates</h2><div class="card">{svgs['rates']}</div>
<h2>Mortgage-Treasury Spread</h2><div class="card">{svgs['spread']}</div>
{'<h2>Treasury Curve</h2><div class="card">' + svgs['curve'] + '</div>' if 'curve' in svgs else ''}
{'<h2>Delinquency</h2><div class="card">' + svgs['delinquency'] + '</div>' if 'delinquency' in svgs else ''}
<h2>Latest 12 Weeks</h2><div class="card wrap"><table>
<tr><th>Week</th><th>30Y %</th><th>15Y %</th><th>10Y avg %</th><th>Spread bp</th></tr>{body}</table></div>
<p class="note">Method: each weekly mortgage rate is paired with the mean of all DGS10 prints dated in the 7 calendar days ending on that date.
Spread = 30Y mortgage rate minus that average. The z-score uses the sample standard deviation of the spread over the stated history, including the current week.
Informational only; not investment advice.</p>
</main></body></html>
"""
