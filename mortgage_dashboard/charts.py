"""Hand-written SVG line charts with light/dark styling (no external CSS or JS)."""

import math
from datetime import date
from xml.sax.saxutils import escape

W, H = 760, 380
L, R, T, B = 62, 24, 46, 48
STYLE = """<style>
.bg{fill:#ffffff}.t{fill:#222}.ax{stroke:#444}.gr{stroke:#dcdcdc}.lb{fill:#444}
.c1{stroke:#2563c9;fill:#2563c9}.c2{stroke:#c9700f;fill:#c9700f}.c3{stroke:#1f8a5b;fill:#1f8a5b}
polyline{fill:none!important}.halo{paint-order:stroke;stroke-width:3px;stroke-linejoin:round;stroke:#fff}.band{fill:#2563c9;fill-opacity:.10;stroke:none}.ref{stroke:#777}
@media (prefers-color-scheme: dark){
.bg{fill:#16181d}.t{fill:#eee}.ax{stroke:#aaa}.gr{stroke:#3a3d44}.lb{fill:#bbb}
.c1{stroke:#6ea8ff;fill:#6ea8ff}.c2{stroke:#f0a04b;fill:#f0a04b}.c3{stroke:#5fd0a0;fill:#5fd0a0}
.halo{stroke:#16181d}.band{fill:#6ea8ff;fill-opacity:.14}.ref{stroke:#999}}
</style>"""
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def nice_ticks(lo, hi, n=5):
    raw = (hi - lo) / n or 1
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    t, out = math.floor(lo / step + 1e-9) * step, []
    while True:
        out.append(round(t, 10))
        if t >= hi - 1e-9 * step:
            return out
        t += step


def _yr(d):
    return d.year + (d.timetuple().tm_yday - 1) / 366.0


def line_chart(title, series, ylabel, band=None, hline=None, marker=None,
               yfmt="{:.1f}", standalone=False):
    """series: list of (label, css_class c1|c2|c3, [(date, value), ...]).

    band: (lo, hi) shaded range; hline: (value, label) dashed reference;
    marker: (date, value, label) highlighted point.
    """
    pts = [(d, v) for _, _, s in series for d, v in s]
    x0, x1 = min(_yr(d) for d, _ in pts), max(_yr(d) for d, _ in pts)
    vals = [v for _, v in pts] + ([band[0], band[1]] if band else [])
    ticks = nice_ticks(min(vals), max(vals))
    y0, y1 = ticks[0], ticks[-1]

    def X(d):
        return L + (_yr(d) - x0) / ((x1 - x0) or 1) * (W - L - R)

    def Y(v):
        return H - B - (v - y0) / ((y1 - y0) or 1) * (H - T - B)

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'role="img" aria-label="{escape(title)}" style="max-width:100%;height:auto">', STYLE]
    if standalone:
        p.append(f'<rect class="bg" width="{W}" height="{H}"/>')
    p.append(f'<text class="t" x="{W/2}" y="26" text-anchor="middle" font-size="15" font-weight="bold" {FONT}>{escape(title)}</text>')
    for v in ticks:
        y = Y(v)
        p.append(f'<line class="gr" x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}"/>')
        p.append(f'<text class="lb" x="{L-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" {FONT}>{yfmt.format(v)}</text>')
    span = x1 - x0
    step = next(s for s in (1, 2, 5, 10, 20) if span / s <= 8)
    yr = math.ceil(x0 / step) * step
    while yr <= x1 + 1e-9:
        x = X(date(int(yr), 1, 1))
        if L - 1 <= x <= W - R + 1:
            p.append(f'<line class="ax" x1="{x:.1f}" x2="{x:.1f}" y1="{H-B}" y2="{H-B+5}"/>')
            p.append(f'<text class="lb" x="{x:.1f}" y="{H-B+19}" text-anchor="middle" font-size="11" {FONT}>{int(yr)}</text>')
        yr += step
    if band:
        p.append(f'<rect class="band" x="{L}" y="{Y(band[1]):.1f}" width="{W-L-R}" height="{Y(band[0])-Y(band[1]):.1f}"/>')
    if hline:
        y = Y(hline[0])
        p.append(f'<line class="ref" x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" stroke-dasharray="5 4"/>')
        p.append(f'<text class="lb halo" x="{L+8}" y="{y+15:.1f}" text-anchor="start" font-size="11" {FONT}>{escape(hline[1])}</text>')
    p.append(f'<line class="ax" x1="{L}" x2="{L}" y1="{T}" y2="{H-B}"/>')
    p.append(f'<line class="ax" x1="{L}" x2="{W-R}" y1="{H-B}" y2="{H-B}"/>')
    for _, cls, s in series:
        path = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in s)
        p.append(f'<polyline class="{cls}" fill="none" stroke-width="1.8" stroke-linejoin="round" points="{path}"/>')
    if marker:
        d, v, label = marker
        p.append(f'<circle class="c1" cx="{X(d):.1f}" cy="{Y(v):.1f}" r="4.5"/>')
        p.append(f'<text class="t halo" x="{X(d)-8:.1f}" y="{Y(v)-9:.1f}" text-anchor="end" font-size="11" {FONT}>{escape(label)}</text>')
    if len(series) > 1 or series[0][0]:
        for i, (label, cls, _) in enumerate(series):
            yy = T + 6 + i * 17
            p.append(f'<rect class="{cls}" x="{L+12}" y="{yy}" width="14" height="4"/>')
            p.append(f'<text class="lb" x="{L+32}" y="{yy+6}" font-size="12" {FONT}>{escape(label)}</text>')
    p.append(f'<text class="lb" transform="translate(15 {(T+H-B)/2}) rotate(-90)" text-anchor="middle" font-size="12" {FONT}>{escape(ylabel)}</text>')
    p.append("</svg>")
    return "\n".join(p) + "\n"
