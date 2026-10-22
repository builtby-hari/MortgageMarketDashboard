#!/usr/bin/env python3
"""Draw the README graphics as hand-written SVG, light and dark, from the cached FRED data.

Run `python3 cli.py` once to fill data/, then `python3 charts.py`. Writes
docs/<name>.svg and docs/<name>-dark.svg. Standard library only.
"""

import argparse
import contextlib
import io
import math
import os
import statistics
import sys
import textwrap
from datetime import timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mortgage_dashboard import load_all, align, spread_stats, curve_spread, weekly_last  # noqa: E402
from mortgage_dashboard.charts import nice_ticks  # noqa: E402

NAME = "Mortgage Market Dashboard"
TAGLINE = "Mortgage Rates, Treasuries and the Spread Between Them, from FRED"
COMMAND = "python3 cli.py --offline"
FONT = 'font-family="Helvetica, Arial, sans-serif"'
MONO = 'font-family="Menlo, Consolas, Courier New, monospace"'
THEMES = {
    "light": {"navy": "#1f3a5f", "teal": "#14b8a6", "grid": "#cbd5e1", "text": "#334155",
              "halo": "#ffffff", "lo": "#e2e8f0", "hi": "#1f3a5f",
              "win": "#f8fafc", "win_line": "#cbd5e1"},
    "dark": {"navy": "#60a5fa", "teal": "#2dd4bf", "grid": "#475569", "text": "#e2e8f0",
             "halo": "#0d1117", "lo": "#1e293b", "hi": "#60a5fa",
             "win": "#161b22", "win_line": "#475569"},
}
W, H = 760, 380          # line and bar charts
L, R, T, B = 64, 24, 66, 46
DOTS = ("#ef4444", "#f59e0b", "#22c55e")


def _f(x):
    return f"{x:.1f}"


def _open(w, h, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{escape_attr(title)}"><title>{escape_attr(title)}</title>']


def escape_attr(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _text(th, x, y, s, size=11, anchor="start", weight=None, fill=None, extra=""):
    bold = f' font-weight="{weight}"' if weight else ""
    color = fill or th["text"]
    return (f'<text x="{_f(x)}" y="{_f(y)}" fill="{color}" font-size="{size}" '
            f'text-anchor="{anchor}"{bold} {FONT}{extra}>{escape_attr(s)}</text>')


def _legend(th, items, y=46):
    """items: (kind, label, color, opacity) with kind line, dash or box."""
    out, x = [], L
    for kind, label, color, op in items:
        if kind == "line":
            out.append(f'<line x1="{x}" x2="{x + 16}" y1="{y - 4}" y2="{y - 4}" stroke="{color}" stroke-width="2.5"/>')
        elif kind == "dash":
            out.append(f'<line x1="{x}" x2="{x + 16}" y1="{y - 4}" y2="{y - 4}" stroke="{color}" '
                       f'stroke-width="1.2" stroke-dasharray="5 4"/>')
        else:
            out.append(f'<rect x="{x}" y="{y - 10}" width="16" height="11" fill="{color}" '
                       f'fill-opacity="{op}" stroke="{color}" stroke-width="0.6"/>')
        out.append(_text(th, x + 22, y, label, size=12))
        x += 22 + 7 * len(label) + 18
    return out


def _year_ticks(x0, x1):
    step = next(s for s in (1, 2, 5, 10, 20) if (x1 - x0) / s <= 8)
    yr = math.ceil(x0 / step) * step
    years = []
    while yr <= x1 + 1e-9:
        years.append(int(yr))
        yr += step
    return years


def _yr(d):
    return d.year + (d.timetuple().tm_yday - 1) / 366.0


def _line_chart(th, title, series, ylabel, *, band=None, hline=None, shade=False, marker=None,
                yfmt="{:.1f}", extra_legend=()):
    """series: [(label, color_key, [(date, value), ...])], color_key navy or teal.

    band: (lo, hi, label) shaded range. hline: (value, label) dashed reference line.
    shade: fill the first series wherever it is below zero. marker: (date, value, label).
    """
    pts = [p for _, _, s in series for p in s]
    x0 = min(_yr(d) for d, _ in pts)
    x1 = max(_yr(d) for d, _ in pts)
    vals = [v for _, v in pts]
    if band:
        vals += [band[0], band[1]]
    if hline:
        vals.append(hline[0])
    ticks = nice_ticks(min(vals), max(vals))
    y0, y1 = ticks[0], ticks[-1]

    def XY(yf):
        return L + (yf - x0) / ((x1 - x0) or 1) * (W - L - R)

    def X(d):
        return XY(_yr(d))

    def Y(v):
        return H - B - (v - y0) / ((y1 - y0) or 1) * (H - T - B)

    out = _open(W, H, title)
    out.append(_text(th, W / 2, 26, title, size=15, anchor="middle", weight="bold"))
    legend = [("line", lab, th[ck], 1) for lab, ck, _ in series]
    if band:
        legend.append(("box", band[2], th["teal"], 0.18))
    if hline:
        legend.append(("dash", hline[1], th["text"], 1))
    out += _legend(th, legend + list(extra_legend))
    for v in ticks:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{_f(Y(v))}" y2="{_f(Y(v))}" stroke="{th["grid"]}" stroke-width="0.8"/>')
        out.append(_text(th, L - 8, Y(v) + 4, yfmt.format(v), anchor="end"))
    for yr in _year_ticks(x0, x1):
        x = XY(yr)
        out.append(f'<line x1="{_f(x)}" x2="{_f(x)}" y1="{H - B}" y2="{H - B + 5}" stroke="{th["text"]}" stroke-opacity="0.6"/>')
        out.append(_text(th, x, H - B + 19, str(yr), anchor="middle"))
    if band:
        out.append(f'<rect x="{L}" y="{_f(Y(band[1]))}" width="{W - L - R}" '
                   f'height="{_f(Y(band[0]) - Y(band[1]))}" fill="{th["teal"]}" fill-opacity="0.18"/>')
    if shade:
        run, polys = [], []
        for p in series[0][2] + [None]:
            if p is not None and p[1] < 0:
                run.append(p)
                continue
            if run:
                pts_xy = ([f"{_f(X(run[0][0]))},{_f(Y(0))}"] + [f"{_f(X(d))},{_f(Y(v))}" for d, v in run]
                          + [f"{_f(X(run[-1][0]))},{_f(Y(0))}"])
                polys.append(" ".join(pts_xy))
                run = []
        for poly in polys:
            out.append(f'<polygon points="{poly}" fill="{th["text"]}" fill-opacity="0.14"/>')
    if hline:
        y = Y(hline[0])
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{_f(y)}" y2="{_f(y)}" stroke="{th["text"]}" '
                   f'stroke-opacity="0.7" stroke-width="1.2" stroke-dasharray="5 4"/>')
    out.append(f'<line x1="{L}" x2="{L}" y1="{T}" y2="{H - B}" stroke="{th["text"]}" stroke-opacity="0.6"/>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{th["text"]}" stroke-opacity="0.6"/>')
    for _, ck, s in series:
        path = " ".join(f"{_f(X(d))},{_f(Y(v))}" for d, v in s)
        out.append(f'<polyline points="{path}" fill="none" stroke="{th[ck]}" stroke-width="1.8" stroke-linejoin="round"/>')
    if marker:
        d, v, label = marker
        cx, cy = X(d), Y(v)
        out.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="4" fill="{th["navy"]}" stroke="{th["halo"]}" stroke-width="1.5"/>')
        halo = f' stroke="{th["halo"]}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"'
        out.append(_text(th, cx - 8, cy - 10, label, anchor="end", weight="bold", extra=halo))
    out.append(f'<text transform="translate(16 {_f((T + H - B) / 2)}) rotate(-90)" text-anchor="middle" '
               f'font-size="12" fill="{th["text"]}" {FONT}>{escape_attr(ylabel)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _year_box_chart(th, title, yearly, ylabel="Basis Points"):
    """yearly: [(year, min, p25, median, p75, max)] in bp. Box = middle 50% of weeks."""
    vals = [v for row in yearly for v in row[1:]]
    ticks = nice_ticks(min(vals), max(vals))
    y0, y1 = ticks[0], ticks[-1]

    def Y(v):
        return H - B - (v - y0) / ((y1 - y0) or 1) * (H - T - B)

    n = len(yearly)
    slot = (W - L - R) / n
    bw = max(1.0, slot * 0.6)
    out = _open(W, H, title)
    out.append(_text(th, W / 2, 26, title, size=15, anchor="middle", weight="bold"))
    out += _legend(th, [("box", "Middle 50% of Weeks", th["teal"], 0.35),
                        ("line", "Median", th["navy"], 1),
                        ("line", "Min to Max", th["text"], 1)])
    for v in ticks:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{_f(Y(v))}" y2="{_f(Y(v))}" stroke="{th["grid"]}" stroke-width="0.8"/>')
        out.append(_text(th, L - 8, Y(v) + 4, f"{v:,.0f}", anchor="end"))
    for i, (yr, lo, p25, med, p75, hi) in enumerate(yearly):
        cx = L + (i + 0.5) * slot
        out.append(f'<line x1="{_f(cx)}" x2="{_f(cx)}" y1="{_f(Y(hi))}" y2="{_f(Y(lo))}" stroke="{th["text"]}" '
                   f'stroke-opacity="0.6" stroke-width="1"/>')
        for v in (lo, hi):
            out.append(f'<line x1="{_f(cx - bw / 4)}" x2="{_f(cx + bw / 4)}" y1="{_f(Y(v))}" y2="{_f(Y(v))}" '
                       f'stroke="{th["text"]}" stroke-opacity="0.6"/>')
        out.append(f'<rect x="{_f(cx - bw / 2)}" y="{_f(Y(p75))}" width="{_f(bw)}" '
                   f'height="{_f(max(0.6, Y(p25) - Y(p75)))}" fill="{th["teal"]}" fill-opacity="0.35" '
                   f'stroke="{th["teal"]}" stroke-width="0.8"/>')
        out.append(f'<line x1="{_f(cx - bw / 2)}" x2="{_f(cx + bw / 2)}" y1="{_f(Y(med))}" y2="{_f(Y(med))}" '
                   f'stroke="{th["navy"]}" stroke-width="2"/>')
        if yr % 5 == 0:
            out.append(_text(th, cx, H - B + 19, str(yr), anchor="middle"))
    out.append(f'<line x1="{L}" x2="{L}" y1="{T}" y2="{H - B}" stroke="{th["text"]}" stroke-opacity="0.6"/>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{th["text"]}" stroke-opacity="0.6"/>')
    out.append(f'<text transform="translate(16 {_f((T + H - B) / 2)}) rotate(-90)" text-anchor="middle" '
               f'font-size="12" fill="{th["text"]}" {FONT}>{escape_attr(ylabel)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _heatmap_chart(th, title, years, values):
    """years: row labels (ints). values: {(year, month): bp}. Missing cells are outlined."""
    cell_h, cols = 13, 12
    cw = (W - L - R) / cols
    h = T + len(years) * cell_h + 62
    vals = list(values.values())
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
    span = (hi - lo) or 1.0
    out = _open(W, h, title)
    out.append(_text(th, W / 2, 26, title, size=15, anchor="middle", weight="bold"))
    for m, ch in enumerate("JFMAMJJASOND"):
        out.append(_text(th, L + (m + 0.5) * cw, T - 10, ch, anchor="middle"))
    for r, yr in enumerate(years):
        cy = T + r * cell_h
        out.append(_text(th, L - 8, cy + cell_h - 3, str(yr), size=10, anchor="end"))
        for m in range(cols):
            x, key = L + m * cw, (yr, m + 1)
            if key in values:
                fill = _mix(th["lo"], th["hi"], (values[key] - lo) / span)
                out.append(f'<rect x="{_f(x)}" y="{cy}" width="{_f(cw - 2)}" height="{cell_h - 2}" fill="{fill}"/>')
            else:
                out.append(f'<rect x="{_f(x)}" y="{cy}" width="{_f(cw - 2)}" height="{cell_h - 2}" fill="none" '
                           f'stroke="{th["grid"]}" stroke-width="0.6"/>')
    ky = h - 34
    for i in range(20):
        out.append(f'<rect x="{L + i * 10}" y="{ky}" width="10" height="10" fill="{_mix(th["lo"], th["hi"], i / 19)}"/>')
    out.append(_text(th, L, ky + 24, f"{lo:,.0f} bp", size=11))
    out.append(_text(th, L + 200, ky + 24, f"{hi:,.0f} bp", size=11, anchor="end"))
    out.append(_text(th, L + 218, ky + 9, "Mean Spread in the Month (Blank = No Data)", size=11))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _banner(th, name, tagline):
    out = _open(1200, 240, name)
    out.append(f'<text x="80" y="118" fill="{th["navy"]}" font-size="56" font-weight="bold" {FONT}>{escape_attr(name)}</text>')
    out.append(f'<text x="80" y="162" fill="{th["text"]}" font-size="24" {FONT}>{escape_attr(tagline)}</text>')
    out.append(f'<line x1="80" x2="300" y1="190" y2="190" stroke="{th["teal"]}" stroke-width="4" stroke-linecap="round"/>')
    out.append(f'<line x1="300" x2="1120" y1="190" y2="190" stroke="{th["teal"]}" stroke-opacity="0.35" stroke-width="1"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _terminal(th, command, lines, title="Sample Output"):
    w, lh = 920, 19
    h = 38 + 26 + len(lines) * lh + 24
    out = _open(w, h, "Sample Terminal Output")
    out.append(f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="{th["win"]}" stroke="{th["win_line"]}"/>')
    out.append(f'<line x1="1" x2="{w - 1}" y1="38" y2="38" stroke="{th["win_line"]}"/>')
    for i, color in enumerate(DOTS):
        out.append(f'<circle cx="{22 + i * 20}" cy="20" r="6" fill="{color}"/>')
    out.append(_text(th, w / 2, 24, title, size=12, anchor="middle"))
    y = 38 + 26
    out.append(f'<text x="22" y="{y}" fill="{th["navy"]}" font-size="13" {MONO} xml:space="preserve">$ {escape_attr(command)}</text>')
    for line in lines:
        y += lh
        out.append(f'<text x="22" y="{y}" fill="{th["text"]}" font-size="13" {MONO} xml:space="preserve">{escape_attr(line)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def yearly_stats(rows):
    """Per calendar year: (year, min, p25, median, p75, max) of the weekly spread, in bp."""
    by = {}
    for r in rows:
        by.setdefault(r["date"].year, []).append(r["spread"] * 100)
    out = []
    for yr in sorted(by):
        v = sorted(by[yr])
        if len(v) >= 2:
            p25, med, p75 = statistics.quantiles(v, n=4, method="inclusive")
        else:
            p25 = med = p75 = v[0]
        out.append((yr, v[0], p25, med, p75, v[-1]))
    return out


def monthly_means(rows, since):
    """{(year, month): mean weekly spread in bp} for years from `since`."""
    acc = {}
    for r in rows:
        if r["date"].year >= since:
            acc.setdefault((r["date"].year, r["date"].month), []).append(r["spread"] * 100)
    return {k: statistics.mean(v) for k, v in acc.items()}


def render_all(rows, stats, curve, sample_lines, chart_years=5, curve3m=None):
    """Return {name: {"light": svg, "dark": svg}} for every README graphic."""
    last = rows[-1]["date"]
    recent = [r for r in rows if r["date"] >= last - timedelta(days=round(365.25 * chart_years))]
    yearly = yearly_stats(rows)
    heat_since = 2000
    heat_years = list(range(heat_since, last.year + 1))
    heat_vals = monthly_means(rows, heat_since)
    mean, sd = stats["spread_mean"] * 100, stats["spread_stdev"] * 100
    spread_bp = stats["spread"] * 100

    def spread(th):
        series = [("Mortgage-Treasury Spread", "navy", [(r["date"], r["spread"] * 100) for r in rows])]
        return _line_chart(
            th, "Mortgage-Treasury Spread, Weekly (bp)", series, "Basis Points",
            band=(mean - sd, mean + sd, "Mean ± 1 sd"), hline=(mean, f"Mean {mean:,.0f} bp"),
            marker=(last, spread_bp, f"{spread_bp:,.0f} bp, z = {stats['spread_z']:+.1f}"), yfmt="{:,.0f}")

    def rates(th):
        series = [("30Y Mortgage (PMMS)", "navy", [(r["date"], r["mortgage30"]) for r in recent]),
                  ("10Y Treasury, Weekly Average", "teal", [(r["date"], r["dgs10_avg"]) for r in recent])]
        return _line_chart(th, f"30Y Mortgage vs 10Y Treasury, Last {chart_years} Years", series, "Percent")

    def curve_chart(th):
        series = [("10Y Minus 2Y, Weekly", "navy", [(d, v * 100) for d, v in curve])]
        title = "10Y Minus 2Y Treasury Spread, Weekly (bp)"
        if curve3m:
            series.append(("10Y Minus 3M, Weekly", "teal", [(d, v * 100) for d, v in curve3m]))
            title = "10Y Minus 2Y and 10Y Minus 3M Treasury Spreads, Weekly (bp)"
        return _line_chart(th, title, series, "Basis Points",
                           shade=True, hline=(0.0, "0 bp = Flat"), yfmt="{:,.0f}",
                           extra_legend=[("box", "Inverted (Below Zero)", th["text"], 0.14)])

    builders = {
        "spread": spread,
        "rates": rates,
        "curve": curve_chart,
        "spread-by-year": lambda th: _year_box_chart(th, "Mortgage-Treasury Spread by Year (bp)", yearly),
        "spread-heatmap": lambda th: _heatmap_chart(
            th, f"Mortgage-Treasury Spread by Month, {heat_since} to {last.year} (bp)", heat_years, heat_vals),
        "banner": lambda th: _banner(th, NAME, TAGLINE),
        "sample-output": lambda th: _terminal(th, COMMAND, sample_lines),
    }
    return {name: {key: fn(THEMES[key]) for key in THEMES} for name, fn in builders.items()}


def write_all(rendered, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, variants in rendered.items():
        for key, suffix in (("light", ""), ("dark", "-dark")):
            path = os.path.join(out_dir, f"{name}{suffix}.svg")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(variants[key])
            paths.append(path)
    return paths


def load_inputs(data_dir="data"):
    """Aligned weekly rows, spread stats, and the weekly 10Y-2Y and 10Y-3M curves. Cache only."""
    data = load_all(data_dir, offline=True)
    rows = align(data["MORTGAGE30US"], data["MORTGAGE15US"], data["DGS10"])
    stats = spread_stats(rows)
    curve = weekly_last(curve_spread(data["DGS10"], data["DGS2"]))
    curve3m = weekly_last(curve_spread(data["DGS10"], data["DGS3MO"]))
    return rows, stats, curve, curve3m


def sample_output_lines(width=90):
    """Run the real CLI (offline) and return its output, wrapped for the terminal picture."""
    import cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["--offline"])
    if code != 0:
        raise SystemExit(f"cli.py exited with {code}")
    lines = []
    for line in buf.getvalue().splitlines():
        lines.extend(textwrap.wrap(line, width) or [""])
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(description="Draw the README charts (light and dark SVG)")
    p.add_argument("--out", default="docs", help="output directory, relative to the repo")
    p.add_argument("--chart-years", type=int, default=5, help="years shown in the rates chart")
    a = p.parse_args(argv)
    os.chdir(ROOT)
    try:
        rows, stats, curve, curve3m = load_inputs("data")
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}. Run python3 cli.py first to fill data/.", file=sys.stderr)
        return 1
    rendered = render_all(rows, stats, curve, sample_output_lines(), a.chart_years, curve3m)
    for path in write_all(rendered, os.path.join(ROOT, a.out)):
        print("wrote " + os.path.relpath(path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
