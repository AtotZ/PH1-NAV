# Capture screenshot → OCR → quick metrics+push → append a TRIP block into UnifiedDB.txt

import sys, time, datetime, re
from pathlib import Path

# Ensure Bot dir is importable (robust under Pythonista / CWD variance)
BOT_DIR = Path.home() / "Documents" / "OnisAI" / "Bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

# Helpers from your modules
from ocr_ios import wait_fresh_asset, cgimage_from_asset, run_ocr
from parse import sanity_basic, parse_card, pickup_status_ctx
from metrics import calc_metrics
from notify import open_uber, push_local
from utils import created_str, sha1_hex, today_heading  # <-- shared heading
from store import latest_summary_total, latest_summary_drive_minutes  # <-- NEW: pulls from SUMMARY

# === Paths ===
DOCS       = Path.home() / "Documents"
ONIS_ROOT  = DOCS / "OnisAI"
UNIFIED    = ONIS_ROOT / "UnifiedDB.txt"
STATE_DIR  = ONIS_ROOT / "State"
STATE_FILE = STATE_DIR / ".uber_triplogger_state.json"
TRIPDB_DIR = ONIS_ROOT / "TripDB"   # for latest total + drive minutes

ONIS_ROOT.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)
TRIPDB_DIR.mkdir(parents=True, exist_ok=True)
if not UNIFIED.exists():
    UNIFIED.write_text("", encoding="utf-8")

# === tiny state I/O ===
import json
def _load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
def _save_state(d):
    try:
        STATE_FILE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass

# === day header ===
def _ensure_today_header():
    t = UNIFIED.read_text(encoding="utf-8", errors="ignore")
    h = today_heading()
    if h not in t:
        with UNIFIED.open("a", encoding="utf-8") as f:
            f.write(h)

def _next_trip_num_for_today():
    txt = UNIFIED.read_text(encoding="utf-8", errors="ignore")
    h   = today_heading()
    m   = re.search(re.escape(h) + r"(.*?)(?:\n==== |\Z)", txt, flags=re.S)
    body = (m.group(1) if m else "")
    nums = [int(m2.group(1)) for m2 in re.finditer(r'(?m)^TRIP\s+(\d+)\s*$', body)]
    return (max(nums) + 1) if nums else 1

# === run ===
t0 = time.perf_counter()
print(f"[T0] Entered Pythonista at {time.strftime('%H:%M:%S')}")

state = _load_state()
prev_asset_id = state.get('last_asset_id')
prev_created  = state.get('last_created')
prev_ocr_sha1 = state.get('last_ocr_sha1')

# fetch image & OCR (light retry until sanity passes)
asset   = wait_fresh_asset(prev_asset_id, prev_created, poll=0.08)
cgimage = cgimage_from_asset(asset)

MAX_OCR_RETRIES = 4
for attempt in range(1, MAX_OCR_RETRIES + 1):
    ocr_text, ocr_time = run_ocr(cgimage)
    sane, *_ = sanity_basic(ocr_text)
    if sane:
        if attempt > 1:
            print(f"[sanity] OCR passed on retry #{attempt}")
        break
    else:
        print(f"[sanity] OCR incomplete on attempt #{attempt}; re-running...")
else:
    # Record failed OCR hash to prevent loops, then exit quietly
    _save_state({
        "last_asset_id": getattr(asset, 'local_id', None),
        "last_created":  created_str(getattr(asset, 'creation_date', None)),
        "last_ocr_sha1": sha1_hex(ocr_text)
    })
    raise SystemExit(0)

print(f"[⏱ OCR Scan Time] {ocr_time:.3f} seconds")
print(f"OCR result:\n{ocr_text}")

ocr_sha1 = sha1_hex(ocr_text)
if prev_ocr_sha1 and ocr_sha1 == prev_ocr_sha1:
    print("[guard] Duplicate OCR text detected; skipping.")
    raise SystemExit(0)

# --- parse & metrics ---
main_price, star_rating, pickup_min, pickup_miles, trip_min, trip_miles = parse_card(ocr_text)
pickup_status = pickup_status_ctx(pickup_miles, pickup_min, trip_miles, trip_min)
met = calc_metrics(
    price=main_price, trip_mi=trip_miles, trip_min=trip_min,
    pickup_mi=pickup_miles, pickup_min=pickup_min,
    star=star_rating, ocr_time=ocr_time
)

# --- quick push: match your desired layout ---
headline_parts = []
if star_rating and star_rating < 4.50:
    headline_parts.append(f"❌ DECLINE (⭐ {star_rating:.2f})")
headline_parts.append(pickup_status)
headline_parts.append(met["status_str"])
if not any(s.startswith("❌ DECLINE") for s in headline_parts):
    headline_parts.append(f"⭐ {star_rating:.2f}")
line1 = " | ".join(headline_parts)

# Line 2 — paper £/min vs pickup-included £/min (exact text)
line2 = f"£/min £{met['per_min']:.2f} | £{met['per_min_adj']:.2f} incl"

# Lines 3–4 — pull from newest SUMMARY so Push matches SARW/Reveal
today_total = latest_summary_total(TRIPDB_DIR)
drive_min   = latest_summary_drive_minutes(TRIPDB_DIR)
left_min    = max(0, 10 * 60 - drive_min)
def _fmt_hm(m: int) -> str:
    h, r = divmod(m, 60)
    return f"{h}h {r}m"
line3 = f"Total so far: £{today_total:.2f}"
line4 = f"Drive: {_fmt_hm(drive_min)} of 10h | Left: {_fmt_hm(left_min)}"

# Fire push + open Uber
try:
    open_uber()
except Exception:
    pass
push_local("Push01", f"{line1}\n{line2}\n{line3}\n{line4}", delay=0.5)

# --- append to UnifiedDB.txt (central ledger) ---
_ensure_today_header()
trip_num = _next_trip_num_for_today()
now = datetime.datetime.now()
stamp = now.strftime('%Y-%m-%d %H:%M:%S')

raw_block = f"""TRIP {trip_num}
==============================
{stamp}

[⏱ OCR Scan Time] {ocr_time:.3f} seconds

{ocr_text.strip()}

Pickup: {pickup_miles:.2f} mi | {pickup_min} min
Trip: {trip_miles:.2f} mi | {trip_min} min
Star Rating: {star_rating:.2f}
Price (highest): £{main_price:.2f}
£ per mile: £{main_price:.2f} ÷ {trip_miles:.2f} = £{met['per_mile']:.2f}
£ per min: £{main_price:.2f} ÷ {trip_min} = £{met['per_min']:.2f}
# Base raw / adj-delta (for audit)
Base: £{met['base_raw']:.2f} / {met['base_adj_delta']:+.2f}
Effective £/hour (0m wait): £{met['hourly_nominal']:.2f}
Effective £/hour (+{met['OVERHEAD_MINUTES']}m wait): £{met['hourly_adj']:.2f}
Fuel for pickup: £{met['fuel_pickup']:.2f}
Fuel for trip: £{met['fuel_trip']:.2f}
Total fuel cost: £{met['fuel_total']:.2f}

STATUS: {met['status_str']}
"""

# Enforce separators: newline at EOF + exactly one blank line before TRIP header
with UNIFIED.open("ab+") as fb:
    fb.seek(0, 2)
    try:
        fb.seek(-1, 2)
        last = fb.read(1)
    except OSError:
        last = b""
    need_trailing_newline = (last != b"\n")

with UNIFIED.open("a", encoding="utf-8") as f:
    if need_trailing_newline:
        f.write("\n")
    f.write("\n")  # one blank line between blocks
    f.write(raw_block.rstrip() + "\n")

# persist state
_save_state({
    "last_asset_id": getattr(asset, 'local_id', None),
    "last_created":  created_str(getattr(asset, 'creation_date', None)),
    "last_ocr_sha1": ocr_sha1
})

t1 = time.perf_counter()
print(f"[T1] Leaving Pythonista at {time.strftime('%H:%M:%S')} (Exec time: {t1 - t0:.3f}s)")
