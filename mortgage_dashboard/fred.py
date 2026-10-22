"""Download, cache and parse FRED series via the public no-key CSV endpoint."""

import csv
import io
import os
import time
import urllib.error
import urllib.request
from datetime import date

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
SERIES = {
    "MORTGAGE30US": "30-year fixed mortgage rate, Freddie Mac PMMS (weekly, %)",
    "MORTGAGE15US": "15-year fixed mortgage rate, Freddie Mac PMMS (weekly, %)",
    "DGS10": "10-year Treasury constant maturity yield (daily, %)",
    "DGS2": "2-year Treasury constant maturity yield (daily, %)",
    "DGS3MO": "3-month Treasury constant maturity yield (daily, %)",
    "DRSFRMACBS": "Delinquency rate on single-family residential mortgages (quarterly, %)",
}


def parse_fred_csv(text):
    """Parse FRED CSV text into a sorted list of (date, value); '.' and blanks are dropped."""
    text = text.strip().lstrip("\ufeff")
    if text[:15].lower().startswith(("<!doctype", "<html")):
        raise ValueError("FRED returned an HTML page instead of CSV (site maintenance or blocked request?)")
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)  # name is DATE or observation_date depending on FRED's era; not used
    if not header or len(header) < 2:
        raise ValueError("not a FRED CSV: missing header")
    out = []
    for row in rd:
        if len(row) < 2:
            continue
        raw = row[1].strip()
        if raw in ("", "."):
            continue
        out.append((date.fromisoformat(row[0].strip()), float(raw)))
    if not out:
        raise ValueError("FRED CSV has no observations")
    out.sort()
    return out


def cache_path(series_id, data_dir):
    return os.path.join(data_dir, f"{series_id}.csv")


def download(series_id, timeout=30, retries=3):
    """GET the series CSV with a few retries (FRED's CSV endpoint is occasionally slow)."""
    # Default urllib User-Agent on purpose: FRED's edge stalls requests with custom/browser-like agents.
    req = urllib.request.Request(URL.format(series_id))
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def load_series(series_id, data_dir="data", offline=False, fetch=download, log=print):
    """Return parsed observations, refreshing the cache unless offline.

    Online failures fall back to a cached file when one exists.
    """
    path = cache_path(series_id, data_dir)
    if not offline:
        try:
            text = fetch(series_id)
            data = parse_fred_csv(text)          # validate before overwriting the cache
            os.makedirs(data_dir, exist_ok=True)
            with open(path + ".tmp", "w", newline="") as fh:   # replace atomically: no truncated cache on crash
                fh.write(text)
            os.replace(path + ".tmp", path)
            return data
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if not os.path.exists(path):
                raise RuntimeError(f"could not download {series_id} ({exc}) and no cache at {path}") from exc
            log(f"warning: download of {series_id} failed ({exc}); using cache {path}")
    elif not os.path.exists(path):
        raise FileNotFoundError(f"--offline requested but no cached file at {path}; run once without --offline to download it")
    with open(path, newline="") as fh:
        return parse_fred_csv(fh.read())


def load_all(data_dir="data", offline=False, fetch=download, log=print):
    return {sid: load_series(sid, data_dir, offline, fetch, log) for sid in SERIES}
