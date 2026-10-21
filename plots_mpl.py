#!/usr/bin/env python3
"""Optional richer versions of the main README charts, drawn with matplotlib.

The core project is standard library only. This script needs matplotlib
(`pip install -r requirements-extra.txt`); without it, it prints a note and exits.
Writes docs/mpl/<name>.png from the cached FRED data (run `python3 cli.py` first).
"""

import os
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import charts  # noqa: E402

NAVY, TEAL, GRID, TEXT = "#1f3a5f", "#14b8a6", "#cbd5e1", "#334155"
THEME_LO = "#e2e8f0"


def make_pngs(out_dir, rows, stats, curve, chart_years=5):
    """Draw the five main charts with matplotlib and return the written paths."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    plt.rcParams.update({
        "axes.edgecolor": TEXT, "axes.labelcolor": TEXT, "xtick.color": TEXT, "ytick.color": TEXT,
        "axes.titlecolor": TEXT, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    })
    os.makedirs(out_dir, exist_ok=True)
    written = []

    def save(fig, name):
        path = os.path.join(out_dir, name + ".png")
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)

    last = rows[-1]["date"]
    recent = [r for r in rows if r["date"] >= last - timedelta(days=round(365.25 * chart_years))]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.plot([r["date"] for r in recent], [r["mortgage30"] for r in recent], color=NAVY, lw=1.6,
            label="30Y Mortgage (PMMS)")
    ax.plot([r["date"] for r in recent], [r["dgs10_avg"] for r in recent], color=TEAL, lw=1.6,
            label="10Y Treasury, Weekly Average")
    ax.set_title(f"30Y Mortgage vs 10Y Treasury, Last {chart_years} Years")
    ax.set_ylabel("Percent")
    ax.legend()
    save(fig, "rates")

    dates = [r["date"] for r in rows]
    spread = [r["spread"] * 100 for r in rows]
    mean, sd = stats["spread_mean"] * 100, stats["spread_stdev"] * 100
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.plot(dates, spread, color=NAVY, lw=1.1, label="Mortgage-Treasury Spread")
    ax.axhspan(mean - sd, mean + sd, color=TEAL, alpha=0.18, lw=0, label="Mean ± 1 sd")
    ax.axhline(mean, color=TEXT, ls="--", lw=1, label=f"Mean {mean:,.0f} bp")
    ax.set_title("Mortgage-Treasury Spread, Weekly (bp)")
    ax.set_ylabel("Basis Points")
    ax.legend(loc="upper left")
    save(fig, "spread")

    fig, ax = plt.subplots(figsize=(9, 4.4))
    cd = [d for d, _ in curve]
    cv = [v * 100 for _, v in curve]
    ax.plot(cd, cv, color=NAVY, lw=1.1, label="10Y Minus 2Y, Weekly")
    ax.fill_between(cd, cv, 0, where=[v < 0 for v in cv], color=TEXT, alpha=0.18, lw=0,
                    interpolate=True, label="Inverted (Below Zero)")
    ax.axhline(0, color=TEXT, lw=1)
    ax.set_title("10Y Minus 2Y Treasury Spread, Weekly (bp)")
    ax.set_ylabel("Basis Points")
    ax.legend(loc="upper left")
    save(fig, "curve")

    yearly = charts.yearly_stats(rows)
    yrs = [y[0] for y in yearly]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.vlines(yrs, [y[1] for y in yearly], [y[5] for y in yearly], color=TEXT, alpha=0.5, lw=0.8)
    ax.bar(yrs, [y[4] - y[2] for y in yearly], bottom=[y[2] for y in yearly], width=0.7,
           color=TEAL, alpha=0.35, edgecolor=TEAL, lw=0.6, label="Middle 50% of Weeks")
    ax.hlines([y[3] for y in yearly], [y - 0.35 for y in yrs], [y + 0.35 for y in yrs],
              color=NAVY, lw=2, label="Median")
    ax.set_title("Mortgage-Treasury Spread by Year (bp)")
    ax.set_ylabel("Basis Points")
    ax.legend(loc="upper left")
    save(fig, "spread-by-year")

    since = 2000
    years = list(range(since, last.year + 1))
    monthly = charts.monthly_means(rows, since)
    grid = [[monthly.get((y, m), float("nan")) for m in range(1, 13)] for y in years]
    cmap = LinearSegmentedColormap.from_list("spread", [THEME_LO, NAVY])
    cmap.set_bad(alpha=0)
    fig, ax = plt.subplots(figsize=(7.5, 8))
    im = ax.imshow(grid, aspect="auto", cmap=cmap, interpolation="nearest")
    ax.grid(False)
    ax.set_xticks(range(12))
    ax.set_xticklabels(list("JFMAMJJASOND"))
    ax.set_yticks(range(0, len(years), 2))
    ax.set_yticklabels([str(y) for y in years[::2]])
    ax.set_title(f"Mortgage-Treasury Spread by Month, {since} to {last.year} (bp)")
    fig.colorbar(im, ax=ax, label="Mean Spread in the Month (bp)")
    save(fig, "spread-heatmap")
    return written



def main():
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib is not installed. It is optional: pip install -r requirements-extra.txt")
        print("The core charts (python3 charts.py) need nothing extra.")
        return 0
    rows, stats, curve = charts.load_inputs("data")
    for path in make_pngs(os.path.join(ROOT, "docs", "mpl"), rows, stats, curve):
        print("wrote " + os.path.relpath(path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
