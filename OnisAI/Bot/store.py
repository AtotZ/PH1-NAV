# File/folder paths, RAW/SUMMARY writing, state I/O, daily totals

import os
import re
import json
from pathlib import Path
import datetime

# Public API:
# - ensure_dirs(base_dir) -> dict with paths (tripdb, uberdb, state)
# - load_state(state_file) / save_state(state_file, data)
# - append_raw(uberdb_dir, now_dt, text_block)
# - append_summary(tripdb_dir, now_dt, text_block)
# - latest_summary_total(tripdb_dir) -> float
# - latest_summary_scope(tripdb_dir) -> str
# - latest_summary_drive_minutes(tripdb_dir) -> int


def ensure_dirs(base_dir: str | Path):
    base = Path(base_dir)
    tripdb = base / "TripDB"
    uberdb = base / "UberDB"
    state_dir = base / "State"
    for d in (tripdb, uberdb, state_dir):
        d.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / ".uber_triplogger_state.json"
    return {
        "tripdb": tripdb,
        "uberdb": uberdb,
        "state": state_file,
    }


def load_state(state_file: str | Path) -> dict:
    p = Path(state_file)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state_file: str | Path, data: dict):
    p = Path(state_file)
    try:
        p.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _day_key(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _summary_path(tripdb_dir: str | Path, dt: datetime.datetime) -> Path:
    return Path(tripdb_dir) / f"TripLog-{_day_key(dt)}-SUMMARY.txt"


def _raw_path(uberdb_dir: str | Path, dt: datetime.datetime) -> Path:
    return Path(uberdb_dir) / f"TripLog-{_day_key(dt)}-RAW.txt"


_TRIP_HDR_RE = re.compile(r'^TRIP\s+(\d+)\s*$', re.M)


def _next_trip_num(file_path: Path) -> int:
    if not file_path.exists():
        return 1
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        nums = [int(m.group(1)) for m in _TRIP_HDR_RE.finditer(text)]
        return (max(nums) + 1) if nums else 1
    except Exception:
        return 1


def append_raw(uberdb_dir: str | Path, now_dt: datetime.datetime, text_block: str):
    """
    Append a TRIP block (prefixed with 'TRIP N') to the daily RAW file.
    """
    p = _raw_path(uberdb_dir, now_dt)
    trip_num = _next_trip_num(p)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\nTRIP {trip_num}\n")
        f.write(text_block)
        f.flush()
        os.fsync(f.fileno())


def append_summary(tripdb_dir: str | Path, now_dt: datetime.datetime, text_block: str):
    """
    Append a TRIP block (prefixed with 'TRIP N') to the daily SUMMARY file.
    Day headers and runtime/summaries are later added by SARW/Reveal.
    """
    p = _summary_path(tripdb_dir, now_dt)
    trip_num = _next_trip_num(p)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\nTRIP {trip_num}\n")
        f.write(text_block)
        f.flush()
        os.fsync(f.fileno())


# ---------- Readers used by Main/SARW/Notify ----------

_HEADER_RE   = re.compile(r"^==== .+?====\s*$", re.MULTILINE)
_PRICE_RE    = re.compile(r"💰\s*Uber Price:\s*£\s*([\d.]+)")
_RUNTIME_RE  = re.compile(r"^🕓\s*Trip\s+\d+\s+Runtime:\s*(\d+):(\d+):(\d+)", re.MULTILINE)

def _newest_summary_path(tripdb_dir: str | Path) -> Path | None:
    tripdb = Path(tripdb_dir)
    cands = sorted(tripdb.glob("TripLog-*-SUMMARY.txt"), key=lambda p: p.name)
    return cands[-1] if cands else None

def latest_summary_scope(tripdb_dir: str | Path) -> str:
    """
    Return the latest day-section text from the newest SUMMARY file.
    If no header is present, return the whole file. If no file, return ''.
    """
    p = _newest_summary_path(tripdb_dir)
    if not p:
        return ""
    text = p.read_text(encoding="utf-8", errors="ignore")
    headers = list(_HEADER_RE.finditer(text))
    return text[headers[-1].end():] if headers else text

def latest_summary_total(tripdb_dir: str | Path) -> float:
    """
    Sum all '💰 Uber Price: £X' values from the latest day-section
    of the newest SUMMARY file.
    """
    scope = latest_summary_scope(tripdb_dir)
    prices = _PRICE_RE.findall(scope)
    try:
        return round(sum(float(x) for x in prices), 2)
    except Exception:
        return 0.0

def latest_summary_drive_minutes(tripdb_dir: str | Path, round_secs: bool = True) -> int:
    """
    Sum completed runtimes in minutes from the latest day-section of the newest SUMMARY.
    If round_secs=True, seconds ≥30 are rounded up to the next minute.
    """
    scope = latest_summary_scope(tripdb_dir)
    total = 0
    for hh, mm, ss in _RUNTIME_RE.findall(scope):
        h, m, s = int(hh), int(mm), int(ss)
        mins = h * 60 + m
        if round_secs and s >= 30:
            mins += 1
        total += mins
    return total
