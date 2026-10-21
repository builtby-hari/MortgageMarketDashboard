"""Template-based market summary. States levels, changes and percentiles only."""


def _bp(x):
    return f"{abs(x) * 100:,.0f} bp"


def _move(x, up="up", down="down", flat="unchanged"):
    if x is None:
        return None
    if round(x * 100) == 0:
        return flat
    return f"{up if x > 0 else down} {_bp(x)}"


def _pp(x):
    if round(x, 2) == 0:
        return "unchanged"
    return f"{'up' if x > 0 else 'down'} {abs(x):.2f} pp"


def _ordinal(n):
    n = int(round(n))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _quarter(d):
    return f"Q{(d.month - 1) // 3 + 1} {d.year}"


def market_summary(s, dq=None, window_label=None, cv=None):
    """Return a short factual paragraph from spread_stats `s`, delinquency_trend `dq` and curve_stats `cv`."""
    parts = []
    wk = _move(s["mortgage30_wk_chg"], flat="unchanged")
    yr = _move(s["mortgage30_52w_chg"], flat="unchanged")
    first = f"For the week of {s['date']:%B} {s['date'].day}, {s['date'].year}, the 30-year fixed mortgage rate was {s['mortgage30']:.2f}%"
    chg = []
    if wk:
        chg.append(f"{wk} on the week" if wk != "unchanged" else "unchanged on the week")
    if yr:
        chg.append(f"{yr} over 52 weeks" if yr != "unchanged" else "unchanged over 52 weeks")
    parts.append(first + (f" ({', '.join(chg)})" if chg else "") + ".")
    if s.get("mortgage15") is not None:
        parts[-1] = parts[-1][:-1] + f"; the 15-year was {s['mortgage15']:.2f}%."
    sp = (f"The 10-year Treasury averaged {s['dgs10_avg']:.2f}% over the same week, so the "
          f"mortgage-Treasury spread was {s['spread'] * 100:,.0f} bp")
    if s["spread_52w_chg"] is not None:
        m = _move(s["spread_52w_chg"], flat="unchanged")
        sp += f" ({m} over 52 weeks)" if m != "unchanged" else " (unchanged over 52 weeks)"
    sp += "."
    parts.append(sp)
    z = s["spread_z"]
    rel = "above" if z > 0 else "below"
    window = window_label or f"since {s['hist_start']:%Y}"
    parts.append(f"That is {abs(z):.1f} standard deviations {rel} the average of {s['spread_mean'] * 100:,.0f} bp "
                 f"({s['hist_n']:,} weekly observations {window}), at the {_ordinal(s['spread_pctile'])} "
                 f"percentile of the range {s['spread_min'] * 100:,.0f} to {s['spread_max'] * 100:,.0f} bp.")
    if cv:
        slope = cv["value"] * 100
        sentence = (f"The 10-year minus 2-year Treasury spread was {slope:+,.0f} bp")
        m = _move(cv["yoy"], flat="unchanged") if cv["yoy"] is not None else None
        if m:
            sentence += f" ({m} over 52 weeks)" if m != "unchanged" else " (unchanged over 52 weeks)"
        sentence += (f"; the curve was inverted on {cv['inverted_pct']:.0f}% of "
                     f"{cv['hist_n']:,} daily readings since {cv['hist_start']:%Y}.")
        parts.append(sentence)
    if dq:
        parts.append(f"The single-family mortgage delinquency rate was {dq['value']:.2f}% in {_quarter(dq['date'])}, "
                     f"{_pp(dq['qoq'])} on the quarter and {_pp(dq['yoy'])} on the year ({dq['direction']} trend), "
                     f"at the {_ordinal(dq['pctile'])} percentile of quarterly readings since {dq['hist_start'].year}.")
    return " ".join(parts)
