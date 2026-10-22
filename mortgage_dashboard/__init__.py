"""Mortgage market dashboard: FRED rates, mortgage-Treasury spread, HTML report."""

from .fred import SERIES, load_all, load_series, parse_fred_csv
from .analytics import (align, change_over_days, zscore, percentile_rank,
                        spread_stats, delinquency_trend, attach_delinquency,
                        curve_spread, curve_stats, weekly_last, rate_volatility, rolling_mean)
from .summary import market_summary
from .report import build_html, write_aligned_csv
from .note import build_note
