#!/usr/bin/env python3
"""Command-line interface for the mortgage market dashboard."""

import argparse
import os
import sys
from datetime import date

from mortgage_dashboard import (load_all, align, attach_delinquency, spread_stats,
                                delinquency_trend, market_summary, build_html,
                                write_aligned_csv, curve_spread, curve_stats)


def build_parser():
    p = argparse.ArgumentParser(description="Mortgage market dashboard from public FRED data")
    p.add_argument("--data-dir", default="data", help="cache directory for downloaded CSVs")
    p.add_argument("--out", default="out", help="output directory for report.html and aligned.csv")
    p.add_argument("--offline", action="store_true", help="use cached CSVs only; no network")
    p.add_argument("--window-years", type=float, help="z-score history window in years (default: all)")
    p.add_argument("--chart-years", type=int, default=5, help="years shown in the rates chart")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        data = load_all(a.data_dir, a.offline)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    rows = align(data["MORTGAGE30US"], data["MORTGAGE15US"], data["DGS10"])
    attach_delinquency(rows, data["DRSFRMACBS"])
    stats = spread_stats(rows, a.window_years)
    dq = delinquency_trend(data["DRSFRMACBS"])
    curve = curve_spread(data["DGS10"], data["DGS2"])
    cv = curve_stats(curve, a.window_years)
    label = f"in the trailing {a.window_years:g} years" if a.window_years else None
    os.makedirs(a.out, exist_ok=True)
    html_path, csv_path = os.path.join(a.out, "report.html"), os.path.join(a.out, "aligned.csv")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html(rows, data["DRSFRMACBS"], stats, dq, label, a.chart_years,
                            generated=date.today().isoformat(), curve=curve, cv=cv))
    write_aligned_csv(csv_path, rows)
    print(market_summary(stats, dq, label, cv))
    print(f"\nAligned weeks: {len(rows):,} ({rows[0]['date']} to {rows[-1]['date']})")
    print(f"Wrote {html_path}\nWrote {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
