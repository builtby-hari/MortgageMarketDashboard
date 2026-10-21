"""Mortgage market dashboard: FRED rates, mortgage-Treasury spread, HTML report."""

from .fred import SERIES, parse_fred_csv, load_series, load_all
from .analytics import (align, change_over_days, zscore, percentile_rank,
                        spread_stats, delinquency_trend, attach_delinquency,
                        curve_spread, curve_stats, weekly_last)
from .summary import market_summary
from .report import build_html, write_aligned_csv
