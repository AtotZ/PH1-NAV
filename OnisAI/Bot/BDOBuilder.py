# Refresh latest SUMMARY/RAW (via SARWBuilder if available), then export BAD drop-offs:
# Criteria: has "⚠️ FLAGGED: ... Δ +N min" with N >= MIN_OVER_EST_MIN AND "🚦 Traffic Level: 10/10"
#
# Output: ~/Documents/OnisAI/bad_dropoffs.json
# {
#   "bad_dropoffs": {
#     "<dropoff address>": {
#       "status": "BAD",
#       "max_delay_min": 38,
#       "times": ["HH:MM:SS", ...]   # completed times only
#     }
#   }
# }

import re, json, importlib, runpy, sys
from pathlib import Path

# Ensure Bot dir is importable (robust under Pythonista / CWD variance)
BOT_DIR = Path.home() / "Documents" / "OnisAI" / "Bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

# ====== CONFIG ======
MIN_OVER_EST_MIN = 5
DOCS       = Path.home() / "Documents"
ONISAI     = DOCS / "OnisAI"
TRIPDB     = ONISAI / "TripDB"
UBERDB     = ONISAI / "UberDB"
OUT_JSON   = ONISAI / "bad_dropoffs.json"   # moved inside project

# ====== REGEX ======
R_RUNTIME    = re.compile(r"^🕓 Trip\s+(\d+)\s+Runtime:", re.I)
R_DROPOFF    = re.compile(r"^🏁 Dropoff Address:\s*(.+)$", re.I)
R_FLAGGED    = re.compile(r"^⚠️ FLAGGED:.*Δ\s*\+?(\d+)\s*min", re.I)
R_TRAFFIC10  = re.compile(r"^🚦 Traffic Level:\s*10/10")

# RAW file extraction (match TRIP sections inside RAW)
R_TRIP_HDR   = re.compile(r"^TRIP\s+(\d+)\b")
# Accept both styles and optional date:
R_COMPLETED1 = re.compile(r"^✅ COMPLETED AT:\s*(?:(\d{4}-\d{2}-\d{2})\s+)?(\d{2}:\d{2}:\d{2})")
R_COMPLETED2 = re.compile(r"^⌛ Completed At:\s*(\d{2}:\d{2}:\d{2})")

def try_refresh_with_sarw():
    """
    Execute OnisAI/Bot/SARWBuilder.py (if present) to rebuild latest RAW/SUMMARY
    from UnifiedDB.txt. Works even if SARWBuilder is a plain script.
    """
    sarw = ONISAI / "Bot" / "SARWBuilder.py"
    if not sarw.exists():
        print("i️ SARWBuilder not found; using existing files.")
        return
    try:
        runpy.run_path(str(sarw), run_name="__main__")
        print("🔄 SARWBuilder: refreshed latest RAW/SUMMARY.")
    except SystemExit:
        pass
    except Exception as e:
        print(f"i️ SARWBuilder failed to run ({e}). Using existing files.")

def latest_summary_in_tripdb() -> Path | None:
    """Newest TripLog-*-SUMMARY.txt from OnisAI/TripDB by filename (date)."""
    if not TRIPDB.exists():
        return None
    cands = sorted(TRIPDB.glob("TripLog-*-SUMMARY.txt"), key=lambda p: p.name, reverse=True)
    return cands[0] if cands else None

def raw_for_summary(summary_path: Path) -> Path | None:
    """
    Map TripDB/TripLog-YYYY-MM-DD-SUMMARY.txt -> UberDB/TripLog-YYYY-MM-DD-RAW.txt
    Fallback to UberDB/TripLogLegacy-YYYY-MM-DD-RAW.txt if the primary is missing.
    """
    if not summary_path:
        return None
    name = summary_path.name
    if "-SUMMARY" not in name:
        return None
    date_part = name.replace("TripLog-", "").replace("-SUMMARY.txt", "")
    primary = UBERDB / f"TripLog-{date_part}-RAW.txt"
    if primary.exists():
        return primary
    legacy = UBERDB / f"TripLogLegacy-{date_part}-RAW.txt"
    return legacy if legacy.exists() else None

def is_sep(line: str) -> bool:
    s = line.strip()
    return (
        s.startswith("————") or
        s.startswith("───")  or
        s.startswith("---")  or
        s.startswith("___")  or
        s.startswith("===")
    )

def parse_bad_blocks_from_summary(summary_path: Path):
    """
    Yield (trip_num, dropoff_address, delta_min) for each BAD trip:
      - has ⚠️ FLAGGED with Δ >= MIN_OVER_EST_MIN
      - has 🚦 Traffic Level: 10/10
    """
    lines = summary_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out = []
    i, N = 0, len(lines)

    while i < N:
        m_rt = R_RUNTIME.search(lines[i])
        if not m_rt:
            i += 1
            continue

        # Parse trip number from the runtime line
        try:
            trip_num = int(re.search(r"Trip\s+(\d+)\s+Runtime:", lines[i]).group(1))
        except Exception:
            trip_num = None

        # Collect block until next separator
        start = i
        j = i + 1
        while j < N and not is_sep(lines[j]):
            j += 1
        block = lines[start:j]

        drop, delta, t10 = None, None, False
        for ln in block:
            if drop is None:
                md = R_DROPOFF.search(ln)
                if md:
                    drop = md.group(1).strip()
            if delta is None:
                mf = R_FLAGGED.search(ln)
                if mf:
                    try:
                        delta = int(mf.group(1))
                    except ValueError:
                        delta = None
            if not t10 and R_TRAFFIC10.search(ln):
                t10 = True

        if trip_num is not None and drop and t10 and (delta is not None and delta >= MIN_OVER_EST_MIN):
            out.append((trip_num, drop, delta))

        # advance past trailing separators
        i = j + 1
        while i < N and is_sep(lines[i]):
            i += 1

    return out

def completed_time_for_trip(raw_path: Path, trip_num: int) -> str | None:
    """
    Return HH:MM:SS from RAW's completed line within TRIP <num> block.
    Accepts both '✅ COMPLETED AT:' (with optional date) and '⌛ Completed At:'.
    """
    if not raw_path or not raw_path.exists():
        return None
    lines = raw_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    idxs = [k for k, ln in enumerate(lines) if R_TRIP_HDR.search(ln)]
    idxs.append(len(lines))
    for k in range(len(idxs) - 1):
        start, end = idxs[k], idxs[k+1]
        m = R_TRIP_HDR.search(lines[start])
        if not m:
            continue
        if int(m.group(1)) != trip_num:
            continue
        for ln in lines[start:end]:
            m1 = R_COMPLETED1.search(ln)
            if m1:
                return m1.group(2)  # HH:MM:SS
            m2 = R_COMPLETED2.search(ln)
            if m2:
                return m2.group(1)
    return None

def load_store():
    if OUT_JSON.exists():
        try:
            return json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {"bad_dropoffs": {}}
    return {"bad_dropoffs": {}}

def save_store(store):
    OUT_JSON.write_text(json.dumps(store, indent=2), encoding="utf-8")

def main():
    # 1) Refresh RAW/SUMMARY from UnifiedDB.txt (non-fatal if missing)
    try_refresh_with_sarw()

    # 2) Pick latest SUMMARY (+ RAW) from OnisAI stores
    summ = latest_summary_in_tripdb()
    if not summ:
        print("No SUMMARY found yet in OnisAI/TripDB.")
        return
    raw = raw_for_summary(summ)

    # 3) Parse all BAD drop-offs
    bads = parse_bad_blocks_from_summary(summ)
    if not bads:
        print("No BAD drop-offs found.")
        return

    # 4) Merge into store
    store = load_store()
    bucket = store.setdefault("bad_dropoffs", {})
    added = 0

    for trip_num, drop_addr, delta_min in bads:
        rec = bucket.get(drop_addr, {"status": "BAD", "max_delay_min": 0, "times": []})
        if delta_min > rec.get("max_delay_min", 0):
            rec["max_delay_min"] = delta_min

        t_completed = completed_time_for_trip(raw, trip_num)
        if t_completed and t_completed not in rec["times"]:
            rec["times"].append(t_completed)
            rec["times"].sort()

        bucket[drop_addr] = rec
        added += 1

    save_store(store)
    print(f"{summ.name}: recorded {added} BAD drop-off(s).")
    print(f"Output → {OUT_JSON}")

if __name__ == "__main__":
    main()
