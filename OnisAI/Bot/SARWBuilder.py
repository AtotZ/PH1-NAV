# Builds per-day RAW and SUMMARY files from ~/Documents/OnisAI/UnifiedDB.txt,
# then prunes UnifiedDB to keep the last N trips by pure count (no status logic).
# If the boundary (Nth) trip is UNACCEPTED, it is stamped as ACCEPTED.
# Finally triggers the pickup/dropoff grid builder via PUDOUpdater.

import sys
from pathlib import Path

# Ensure Bot dir is importable (robust under Pythonista / CWD variance)
BOT_DIR = Path.home() / "Documents" / "OnisAI" / "Bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

import re
import datetime
import hashlib

# ---- bring in shared parsing + metrics (synergy with Push/Main) ----
from parse import extract_pickup_address, extract_dropoff_address, pickup_status_ctx
from metrics import calc_metrics

# --- Paths ---
DOCS = Path.home() / "Documents"
ONIS_ROOT = DOCS / "OnisAI"
ONIS_ROOT.mkdir(parents=True, exist_ok=True)

MAIN_LOG  = ONIS_ROOT / "UnifiedDB.txt"  # central source-of-truth
TRIP_DB   = ONIS_ROOT / "TripDB"         # per-day summaries
UBER_DB   = ONIS_ROOT / "UberDB"         # per-day raw (OCR + enriched)
TRIP_DB.mkdir(parents=True, exist_ok=True)
UBER_DB.mkdir(parents=True, exist_ok=True)

# ---- constants ----
FUEL_MILES_PER_KWH = 4.1
ELECTRICITY_PRICE_PER_KWH = 0.40
PRUNE_KEEP_LAST = 50  # <-- numeric window

# ---------- Utilities ----------
def to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def to_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def extract_value(pattern: str, text: str, group: int = 1):
    m = re.search(pattern, text)
    return m.group(group).strip() if m else ''

def extract_timestamp(text: str, label: str, base_date=None):
    """
    Accepts either:
      - '🕓 ACCEPTED AT: 2025-09-11 12:34:56'
      - '🕓 ACCEPTED AT: 12:34:56'
    If only time is present, combine with base_date (or today if None).
    """
    m = re.search(
        rf'{re.escape(label)}\s*AT:\s*(?:(\d{{4}}-\d{{2}}-\d{{2}})\s+)?(\d{{2}}:\d{{2}}:\d{{2}})',
        text
    )
    if not m:
        return None
    dpart, tpart = m.groups()
    if dpart:
        return datetime.datetime.strptime(f'{dpart} {tpart}', '%Y-%m-%d %H:%M:%S')
    if base_date is None:
        base_date = datetime.date.today()
    hh, mm, ss = map(int, tpart.split(':'))
    return datetime.datetime(base_date.year, base_date.month, base_date.day, hh, mm, ss)

def extract_estimated_trip_minutes(trip_text: str) -> int:
    m = re.search(r'⏱ Trip Time Estimate:\s*(\d+)\s*min', trip_text)
    return int(m.group(1)) if m else 0

def extract_price(trip_text: str) -> float:
    m = re.search(r'Price \(highest\): £\s*([\d\.]+)', trip_text)
    return float(m.group(1)) if m else 0.0

def format_delta_color(delta_min: int) -> str:
    if delta_min <= -10:
        return f'🟢 {delta_min:+d} min'
    if delta_min >= 10:
        return f'🔴 {delta_min:+d} min'
    return f'⚪ {delta_min:+d} min'

def assign_traffic_level(delta_min, est_min):
    if est_min >= 20 and abs(delta_min) <= est_min * 0.1:
        return 2
    if delta_min <= 1:
        return 1
    if delta_min <= 3:
        return 3
    if delta_min <= 5:
        return 5
    if delta_min <= 8:
        return 6
    if delta_min <= 12:
        return 8
    return 10

# ---------- de-dupe helpers for SUMMARY ----------
TRIP_START = re.compile(r'^——————\s*$')

def split_blocks(text_lines):
    """
    Split a list of lines into trip blocks. Ignore separator-only fragments.
    """
    blocks, cur = [], []
    for ln in text_lines:
        if TRIP_START.match(ln):
            if cur and any(l.startswith('🕓 Trip ') for l in cur):
                blocks.append(cur)
            cur = [ln]
        else:
            if cur:
                cur.append(ln)
    if cur and any(l.startswith('🕓 Trip ') for l in cur):
        blocks.append(cur)
    return blocks

def _completed_line(block_lines):
    return next((ln for ln in block_lines if ln.startswith('⌛ Completed At:')), '')

def _accepted_line(block_lines):
    return next((ln for ln in block_lines if ln.startswith('🕓 ACCEPTED AT:')), '')

def _line_value(block_lines, prefix):
    for ln in block_lines:
        if ln.startswith(prefix):
            return ln[len(prefix):].strip()
    return ''

def _normalize_addr(s: str) -> str:
    s = s.strip().rstrip(' ,.;-')
    s = re.sub(r'\s+', ' ', s)
    return s

def block_signature(block_lines):
    """
    Strong, normalized signature to prevent duplicates across runs.
    Uses accepted time, completed time, pickup, dropoff, price, est minutes, distance.
    """
    accepted = _line_value(block_lines, '🕓 ACCEPTED AT: ')
    completed = _line_value(block_lines, '⌛ Completed At: ')
    dropoff = _normalize_addr(_line_value(block_lines, '🏁 Dropoff Address: '))
    pickup  = _normalize_addr(_line_value(block_lines, '📍 Pickup Address: '))
    price   = _line_value(block_lines, '💰 Uber Price: ')
    estmin  = _line_value(block_lines, '⏱ Trip Time Estimate: ')
    miles   = _line_value(block_lines, '🛣 Distance: ')

    price = re.sub(r'\s+', '', price)
    estmin = re.sub(r'[^0-9]', '', estmin)
    miles  = re.sub(r'[^0-9\.]', '', miles)

    sig = f"{accepted}|{completed}|{pickup}|{dropoff}|{price}|{estmin}|{miles}"
    return hashlib.sha1(sig.encode('utf-8', errors='ignore')).hexdigest()[:20]

def block_key(block_lines):
    runtime = next((ln for ln in block_lines if ln.startswith('🕓 Trip ')), '')
    completed = _completed_line(block_lines)
    drop = next((ln for ln in block_lines if ln.startswith('🏁 Dropoff Address:')), '')
    core = (runtime + '|' + completed + '|' + drop).strip() or '\n'.join(block_lines)
    return hashlib.sha1(core.encode('utf-8', errors='ignore')).hexdigest()[:16]

RE_COMPLETED = re.compile(r'^⌛ Completed At:\s*([0-9]{2}:[0-9]{2}:[0-9]{2})')

def _completed_time_tuple(block_lines, fallback='99:99:99'):
    m = RE_COMPLETED.match(_completed_line(block_lines))
    return tuple(map(int, (m.group(1) if m else fallback).split(':')))

def sort_blocks_by_completed_time(blocks):
    return sorted(blocks, key=lambda b: _completed_time_tuple(b, '99:99:99'))

def renumber_blocks(blocks):
    out = []
    pat = re.compile(r'^(🕓\s*Trip\s+)(\d+)(\s+Runtime:.*)$')
    idx = 1
    for b in blocks:
        new_block, changed = [], False
        for ln in b:
            if not changed:
                m = pat.match(ln)
                if m:
                    new_block.append(f'{m.group(1)}{idx}{m.group(3)}')
                    changed = True
                    continue
            new_block.append(ln)
        out.append(new_block)
        idx += 1
    return out

RE_ARROW = re.compile(r'→ .*? →\s*([🟢🔴⚪])\s*£([\d\.]+)\s*\(fuel:\s*£([\d\.]+)\)')

def metrics_from_block(block_lines):
    comp = None
    net_signed = 0.0
    fuel = 0.0
    for ln in block_lines:
        m = RE_COMPLETED.match(ln)
        if m:
            comp = m.group(1)
        m2 = RE_ARROW.search(ln)
        if m2:
            sign, net_str, fuel_str = m2.groups()
            val = to_float(net_str, 0.0)
            net_signed += (val if sign == '🟢' else -val if sign == '🔴' else 0.0)
            fuel += to_float(fuel_str, 0.0)
    return comp, net_signed, fuel

def merged_shift_summary_from_blocks(header_line, merged_blocks):
    times, net_total, fuel_total = [], 0.0, 0.0
    for b in merged_blocks:
        t, n, fu = metrics_from_block(b)
        if t:
            times.append(t)
        net_total += n
        fuel_total += fu

    dm = re.search(r'==== \w+, (\d{2}) (\w+) (\d{4}) ====', header_line)
    if dm:
        d = int(dm.group(1))
        mname = dm.group(2)
        y = int(dm.group(3))
        month_map = {
            "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
            "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
        }
        m = month_map.get(mname, 1)
    else:
        now = datetime.datetime.now()
        y, m, d = now.year, now.month, now.day

    if times:
        def to_dt(hms):
            hh, mm, ss = map(int, hms.split(':'))
            return datetime.datetime(y, m, d, hh, mm, ss)
        start_dt = min(to_dt(t) for t in times)
        end_dt   = max(to_dt(t) for t in times)
        duration = end_dt - start_dt
        trend = '🟢' if net_total > 0 else '🔴' if net_total < 0 else '⚪'
        return (
            f"\n=== SHIFT SUMMARY ===\n"
            f"Start: {start_dt.strftime('%H:%M:%S')}\n"
            f"End: {end_dt.strftime('%H:%M:%S')}\n"
            f"Duration: {duration}\n"
            f"🔋 Fuel Total: £{fuel_total:.2f}\n"
            f"📊 Daily Net Impact: {trend} £{abs(net_total):.2f}\n"
        )
    else:
        return "\n=== SHIFT SUMMARY ===\nNo valid trips found.\n"

# ---------- core trip labeling ----------
def label_and_summarize_trips(body: str, base_date: datetime.date):
    summary_lines = []
    trip_blocks = re.findall(r'(TRIP\s+\d+)(.*?)(?=(?:TRIP\s+\d+|\Z))', body, re.DOTALL)
    new_body = ''
    daily_net_impact = 0.0
    daily_fuel_cost = 0.0

    for trip_header, trip_body in trip_blocks:
        trip_num = re.search(r'TRIP\s+(\d+)', trip_header).group(1)
        accepted  = extract_timestamp(trip_body, '🕓 ACCEPTED', base_date)
        completed = extract_timestamp(trip_body, '✅ COMPLETED', base_date)
        est_min   = extract_estimated_trip_minutes(trip_body)
        price     = extract_price(trip_body)

        rating       = to_float(extract_value(r'Star Rating:\s*([\d.]+)', trip_body), 0.0)
        trip_miles   = to_float(extract_value(r'Trip:\s*([\d.]+)\s*mi', trip_body), 0.0)
        est_pickup   = to_int(  extract_value(r'Pickup:\s*[\d.]+\s*mi\s*\|\s*(\d+)\s*min', trip_body), 0)
        pickup_miles = to_float(extract_value(r'Pickup:\s*([\d.]+)\s*mi\s*\|\s*\d+\s*min', trip_body), 0.0)

        vehicle = extract_value(r'Vehicle Type: (.+)', trip_body) or extract_value(r'• ([A-Za-z]+)\n• Exclusive', trip_body)

        # Old per-min fallback (kept for compatibility if needed)
        m_permin = re.search(r'£\s*per\s*min:\s*£\s*[\d.]+\s*[÷/]\s*\d+\s*=\s*£\s*([\d.]+)', trip_body, re.I)
        per_min_legacy = to_float(m_permin.group(1), 0.0) if m_permin else (round(price / est_min, 2) if est_min else 0.0)

        pickup_addr = extract_pickup_address(trip_body)
        drop_addr   = extract_dropoff_address(trip_body)

        # ---------- SYNERGY: compute the same metrics as Push/Main ----------
        pickup_status = pickup_status_ctx(pickup_miles, est_pickup, trip_miles, est_min)

        met = calc_metrics(
            price=price,
            trip_mi=trip_miles, trip_min=est_min,
            pickup_mi=pickup_miles, pickup_min=est_pickup,
            star=rating,
            ocr_time=0.0
        )
        per_mile        = met["per_mile"]
        per_min         = met["per_min"] if met["per_min"] else per_min_legacy
        per_min_incl    = met["per_min_adj"]
        hourly_nominal  = met["hourly_nominal"]
        hourly_adj      = met["hourly_adj"]
        overhead_mins   = int(met["OVERHEAD_MINUTES"])

        # ---------- existing net/fuel math (unchanged) ----------
        label = 'REJECTED'
        if accepted and completed:
            label = 'COMPLETED'
            delta = completed - accepted
            delta_min = int(delta.total_seconds() / 60) if delta.total_seconds() >= 0 else 0
            diff = delta_min - est_min
            color = format_delta_color(diff)

            total_miles = (trip_miles or 0.0) + (pickup_miles or 0.0)
            fuel_kwh = round(total_miles / FUEL_MILES_PER_KWH, 2)
            fuel_cost = round(fuel_kwh * ELECTRICITY_PRICE_PER_KWH, 2)
            daily_fuel_cost += fuel_cost

            time_factor = (delta_min / est_min) if est_min else 1.0
            net = round(price - (price * time_factor) - fuel_cost, 2)
            daily_net_impact += net
            sign = '🟢' if net > 0 else '🔴' if net < 0 else '⚪'
            after_cost_price = round(price + net, 2)

            block = [
                f'——————',
                f'🕓 Trip {trip_num} Runtime: {str(delta)} ({est_min} min Uber estimate)',
            ]
            if accepted:
                block.append(f'🕓 ACCEPTED AT: {accepted.strftime("%H:%M:%S")}')
            if completed:
                block.append(f'⌛ Completed At: {completed.strftime("%H:%M:%S")}')
            block.extend([
                f'→ {color} → {sign} £{abs(net):.2f} (fuel: £{fuel_cost:.2f})',
                f'🔋 Fuel Used: {fuel_kwh:.2f} kWh → £{fuel_cost:.2f}',
                f'📍 Pickup Address: {pickup_addr}',
                f'🏁 Dropoff Address: {drop_addr}',
                f'🚗 Vehicle Type: {vehicle}',
                f'💰 Uber Price: £{price:.2f}',
                f'💰 After Costs: £{after_cost_price:.2f}',
                f'⭐ Rating: {rating:.2f}',
                f'🛣 Distance: {trip_miles:.2f} mi',
                f'⏱ Trip Time Estimate: {est_min} min',
                f'📏 Pickup Distance: {pickup_miles:.2f} mi',
                f'⏱ Pickup Estimate: {est_pickup} min',
                f'💸 £/mi: £{per_mile:.2f}' if trip_miles else '',
                f'💸 £/min: £{per_min:.2f}',
                f'£/min incl pickup: £{per_min_incl:.2f}',
                f'💸 £/hr: £{hourly_nominal:.2f}',
                f'💸 £/hr (+{overhead_mins}m wait): £{hourly_adj:.2f}',
                f'Pickup status: {pickup_status}',
                extract_value(r'STATUS: (.*?)\n', trip_body),
            ])
            if abs(diff) >= 2:
                block.append(f'⚠️ FLAGGED: Runtime {delta_min} min vs Uber {est_min} min (Δ {diff:+} min)')
            traffic_level = assign_traffic_level(diff, est_min)
            block.append(f'🚦 Traffic Level: {traffic_level}/10')
            block.append('——————')
            summary_lines.extend(block)

        elif accepted and not completed:
            label = 'INCOMPLETE'
        else:
            label = 'REJECTED'

        new_body += f'{trip_header} {label}\n{trip_body}\n'

    return new_body, summary_lines, daily_net_impact, daily_fuel_cost

# ---------- NUMERIC WINDOW PRUNE (keep last N trips globally) ----------
def _iter_day_blocks(text: str):
    parts = re.split(r'(==== .*? ====\n)', text)
    for i in range(1, len(parts), 2):
        header = parts[i]
        body   = parts[i+1] if i+1 < len(parts) else ''
        yield header, body

def _split_trips_in_body(body: str):
    starts = [m.start() for m in re.finditer(r'(?m)^TRIP\s+\d+.*$', body)]
    if not starts:
        return []
    starts.append(len(body))
    return [body[starts[i]:starts[i+1]] for i in range(len(starts)-1)]

def _header_date(header: str):
    m = re.search(r'==== (\w+), (\d{2}) (\w+) (\d{4}) ====', header)
    if not m:
        return None
    year  = int(m.group(4))
    month = datetime.datetime.strptime(m.group(3), '%B').month
    day   = int(m.group(2))
    return datetime.date(year, month, day)

def _extract_any_iso_dt(block: str, base_date: datetime.date):
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', block)
    if m:
        return datetime.datetime.strptime(m.group(0), "%Y-%m-%d %H:%M:%S")
    m2 = re.search(r'\b(\d{2}:\d{2}:\d{2})\b', block)
    if m2 and base_date:
        hh, mm, ss = map(int, m2.group(1).split(':'))
        return datetime.datetime(base_date.year, base_date.month, base_date.day, hh, mm, ss)
    return None

def _is_accepted(block: str) -> bool:
    return "🕓 ACCEPTED AT:" in block

def _stamp_accepted(block: str, when_dt: datetime.datetime):
    """Insert an ACCEPTED line if missing, directly under TRIP header."""
    if _is_accepted(block):
        return block
    hhmmss = when_dt.strftime("%H:%M:%S")
    lines = block.splitlines()
    insert_at = 1 if (lines and lines[0].startswith("TRIP ")) else 0
    lines.insert(insert_at, f"🕓 ACCEPTED AT: {hhmmss}")
    return "\n".join(lines)

def prune_unified_keep_last(text: str, keep_last: int = PRUNE_KEEP_LAST) -> str:
    days = []
    for header, body in _iter_day_blocks(text):
        d = _header_date(header)
        blocks = _split_trips_in_body(body)
        days.append((header, d, blocks))

    flat = []
    for di, (header, d, blocks) in enumerate(days):
        for bi, b in enumerate(blocks):
            flat.append((di, bi, header, d, b))

    total = len(flat)
    if total <= keep_last:
        return text

    kept = flat[-keep_last:]
    kept_indices = set((di, bi) for di, bi, _h, _d, _b in kept)

    boundary_di, boundary_bi, _bh, boundary_date, boundary_block = kept[0]
    if not _is_accepted(boundary_block):
        when = _extract_any_iso_dt(boundary_block, boundary_date) or datetime.datetime.now()
        stamped = _stamp_accepted(boundary_block, when)
        hdr, d, blks = days[boundary_di]
        blks[boundary_bi] = stamped
        days[boundary_di] = (hdr, d, blks)

    out_chunks = []
    for di, (header, _d, blocks) in enumerate(days):
        kept_blocks = [blocks[bi] for bi in range(len(blocks)) if (di, bi) in kept_indices]
        if kept_blocks:
            out_chunks.append(header + "".join(kept_blocks))
    return "".join(out_chunks)

# --- normalize separators so each TRIP header is cleanly separated ---
def _normalize_trip_separators(text: str) -> str:
    t = re.sub(r'(?<!\n)(TRIP\s+\d+\b)', r'\n\1', text)
    t = re.sub(r'\n{3,}(TRIP\s+\d+\b)', r'\n\n\1', t)
    t = re.sub(r'\n(TRIP\s+\d+\b)', r'\n\n\1', t)
    if t.startswith("TRIP "):
        t = "\n" + t
    return t

# ---------- Main per-day processing ----------
def main():
    if not MAIN_LOG.exists():
        print("UnifiedDB not found; nothing to build.")
        return

    with MAIN_LOG.open('r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    day_blocks = re.split(r'(==== .*? ====\n)', content)
    grouped = [(day_blocks[i], day_blocks[i + 1] if i + 1 < len(day_blocks) else '')
               for i in range(1, len(day_blocks), 2)]

    for header, body in grouped:
        date_match = re.search(r'==== (\w+), (\d{2}) (\w+) (\d{4}) ====', header)
        if not date_match:
            continue

        year  = int(date_match.group(4))
        month = datetime.datetime.strptime(date_match.group(3), '%B').month
        day   = int(date_match.group(2))
        base_date = datetime.date(year, month, day)

        date_str = f"{year}-{month:02}-{day:02}"
        raw_path = UBER_DB / f'TripLog-{date_str}-RAW.txt'
        summary_path = TRIP_DB / f'TripLog-{date_str}-SUMMARY.txt'

        labeled_body, summary_lines, _net_total_run, _fuel_total_run = label_and_summarize_trips(body, base_date)

        with raw_path.open('w', encoding='utf-8') as raw_file:
            raw_file.write(header + labeled_body)

        # New blocks from this run
        new_trip_blocks = split_blocks(summary_lines)

        # Existing blocks (from file)
        existing_blocks = []
        if summary_path.exists():
            with summary_path.open('r', encoding='utf-8') as sf:
                existing_text = sf.read()
            core = existing_text.split("\n=== SHIFT SUMMARY ===")[0]
            if not core.startswith(header):
                if header.strip() not in core:
                    core = header + core
            existing_lines_after_header = core.split('\n')[1:]
            existing_blocks = split_blocks(existing_lines_after_header)

        # De-dupe using strong signature first; legacy key as secondary
        seen_sig = {block_signature(b) for b in existing_blocks}
        seen_key = {block_key(b) for b in existing_blocks}

        merged_blocks = list(existing_blocks)
        for nb in new_trip_blocks:
            sig = block_signature(nb)
            if sig in seen_sig:
                continue
            k = block_key(nb)
            if k in seen_key:
                continue
            merged_blocks.append(nb)
            seen_sig.add(sig)
            seen_key.add(k)

        merged_blocks = sort_blocks_by_completed_time(merged_blocks)
        merged_blocks = renumber_blocks(merged_blocks)

        out_lines = [header.rstrip('\n')]
        for b in merged_blocks:
            out_lines.extend(b)

        shift = merged_shift_summary_from_blocks(header, merged_blocks)
        out_text = '\n'.join(out_lines) + '\n' + shift + '\n'

        with summary_path.open('w', encoding='utf-8') as summary_file:
            summary_file.write(out_text)

    # Keep last PRUNE_KEEP_LAST trips; stamp boundary if needed
    new_unified = prune_unified_keep_last(content, keep_last=PRUNE_KEEP_LAST)
    new_unified = _normalize_trip_separators(new_unified)
    with MAIN_LOG.open('w', encoding='utf-8') as f:
        f.write(new_unified)

    # Trigger grid build (best-effort)
    try:
        import importlib
        updater = importlib.import_module("PUDOUpdater")
        importlib.reload(updater)
        if hasattr(updater, "main"):
            updater.main()
        elif hasattr(updater, "run"):
            updater.run()
        print("✅ Pickup/Dropoff grids updated.")
    except Exception as e:
        print(f"i️ SARWBuilder: PUDOUpdater not found; continuing. ({e})")

if __name__ == "__main__":
    main()
