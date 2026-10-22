#!/usr/bin/env python3
"""Command-line interface for the mortgage market dashboard."""

import argparse
import os
import sys
from datetime import date

from mortgage_dashboard import (load_all, align, attach_delinquency, spread_stats,
                                delinquency_trend, market_summary, rate_volatility, build_html,
                                write_aligned_csv, curve_spread, curve_stats, build_note)
from mortgage_dashboard.note import STALE_DAYS


def build_parser():
    p = argparse.ArgumentParser(description="Mortgage market dashboard from public FRED data")
    p.add_argument("--data-dir", default="data", help="cache directory for downloaded CSVs")
    p.add_argument("--out", default="out", help="output directory for report.html and aligned.csv")
    p.add_argument("--offline", action="store_true", help="use cached CSVs only; no network")
    p.add_argument("--window-years", type=float, help="z-score history window in years (default: all)")
    p.add_argument("--note", metavar="FILE.html", help="also write the one-page Morning Note to this file")
    p.add_argument("--chart-years", type=int, default=5, help="years shown in the rates chart")
    return p


def main(argv=None):
    parser = build_parser()
    a = parser.parse_args(argv)
    if a.window_years is not None and a.window_years < 0.5:
        parser.error("--window-years must be at least 0.5")
    if a.chart_years < 1:
        parser.error("--chart-years must be at least 1")
    try:
        data = load_all(a.data_dir, a.offline)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for sid in ("MORTGAGE30US", "DGS10"):
        age = (date.today() - data[sid][-1][0]).days
        if age > STALE_DAYS:
            print(f"warning: latest {sid} observation is {age} days old; data may be stale", file=sys.stderr)
    rows = align(data["MORTGAGE30US"], data["MORTGAGE15US"], data["DGS10"])
    attach_delinquency(rows, data["DRSFRMACBS"])
    stats = spread_stats(rows, a.window_years)
    dq = delinquency_trend(data["DRSFRMACBS"])
    curve = curve_spread(data["DGS10"], data["DGS2"])
    cv = curve_stats(curve, a.window_years)
    curve3m = curve_spread(data["DGS10"], data["DGS3MO"])
    cv3m = curve_stats(curve3m, a.window_years)
    vol = rate_volatility(data["DGS10"])
    label = f"in the trailing {a.window_years:g} years" if a.window_years else None
    os.makedirs(a.out, exist_ok=True)
    html_path, csv_path = os.path.join(a.out, "report.html"), os.path.join(a.out, "aligned.csv")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html(rows, data["DRSFRMACBS"], stats, dq, label, a.chart_years,
                            generated=date.today().isoformat(), curve=curve, cv=cv, curve3m=curve3m, cv3m=cv3m, vol=vol))
    write_aligned_csv(csv_path, rows)
    if a.note:
        with open(a.note, "w", encoding="utf-8") as fh:
            fh.write(build_note(rows, stats, cv, cv3m, curve, curve3m, dq))
    print(market_summary(stats, dq, label, cv, cv3m))
    if vol is not None:
        print(f"10Y yield volatility: {vol:.1f} bp std dev of daily changes over the last 63 days")
    print(f"\nAligned weeks: {len(rows):,} ({rows[0]['date']} to {rows[-1]['date']})")
    print(f"Wrote {html_path}\nWrote {csv_path}")
    if a.note:
        print(f"Wrote {a.note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
