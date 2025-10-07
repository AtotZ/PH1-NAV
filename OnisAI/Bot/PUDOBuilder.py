# Builds:
#   ~/Documents/OnisAI/GridZoneDB/pickup_grid_db.json
#   ~/Documents/OnisAI/GridZoneDB/dropoff_grid_db.json
#   ~/Documents/OnisAI/GridZoneDB/pickup_zone_summary.txt
#   ~/Documents/OnisAI/GridZoneDB/dropoff_zone_summary.txt
#   ~/Documents/OnisAI/GridZoneDB/grid_guardrail_log.txt
#
# FAST MODE: scans ONLY the latest SUMMARY in:
#   ~/Documents/OnisAI/TripDB/TripLog-YYYY-MM-DD-SUMMARY.txt

import re, json
from pathlib import Path
from datetime import datetime, timedelta

# ===== Paths (OnisAI layout) =====
ROOT     = Path.home() / "Documents" / "OnisAI"
TRIP_DB  = ROOT / "TripDB"          # summaries live here
GRID_DB  = ROOT / "GridZoneDB"      # outputs go here
GRID_DB.mkdir(parents=True, exist_ok=True)

PICK_JSON   = GRID_DB / "pickup_grid_db.json"
DROP_JSON   = GRID_DB / "dropoff_grid_db.json"
PICK_SUMMARY= GRID_DB / "pickup_zone_summary.txt"
DROP_SUMMARY= GRID_DB / "dropoff_zone_summary.txt"
GUARD_LOG   = GRID_DB / "grid_guardrail_log.txt"

# ===== Regex (unchanged) =====
HDR_DATE_RE   = re.compile(r'^====\s+([A-Za-z]+),\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*====', re.M)
RUNTIME_RE    = re.compile(r'^🕓 Trip\s+\d+\s+Runtime:\s*([\d:]+)\s*\((\d+)\s*min Uber estimate\)', re.M)
COMPLETED_RE  = re.compile(r'^⌛ Completed At:\s*([0-9]{2}:[0-9]{2}:[0-9]{2})', re.M)
PICK_RE       = re.compile(r'^📍 Pickup Address:\s*(.+)$', re.M)
DROP_RE       = re.compile(r'^🏁 Dropoff Address:\s*(.+)$', re.M)
PRICE_RE      = re.compile(r'^💰 Uber Price:\s*£\s*([\d.]+)', re.M)
DIST_RE       = re.compile(r'^🛣\s*Distance:\s*([\d.]+)\s*mi', re.M)  # optional
PICKUP_EST_RE = re.compile(r'^⏱\s*Pickup Estimate:\s*(\d+)\s*min', re.M)
PICKUP_DIST_RE= re.compile(r'^📏\s*Pickup Distance:\s*([\d.]+)\s*mi', re.M)  # optional

# Postcode regexes: prefer full postcode; fall back to OUTCODE only
OC_FULL_RE     = re.compile(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*\d[A-Z]{2}\b', re.I)
OC_OUTCODE_RE  = re.compile(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b', re.I)

# ======================== Zone Groups ========================
# NOTE: Deduped memberships: EC* & WC* solely under City/Central; EN* solely North London.
ZONE_GROUPS = {
    "North West London": set('NW1 NW2 NW3 NW4 NW5 NW6 NW7 NW8 NW9 NW10 NW11 HA0 HA1 HA2 HA3 HA4 HA5 HA6 HA7 HA8 HA9'.split()),
    "West London": set('W1 W2 W3 W4 W5 W6 W7 W8 W9 W10 W11 W12 W13 W14 WD3 WD4 WD6 WD7 WD17 WD18 WD19 WD23 WD24 WD25'.split()),
    "South West London": set('SW1 SW2 SW3 SW4 SW5 SW6 SW7 SW8 SW9 SW10 SW11 SW12 SW13 SW14 SW15 SW16 SW17 SW18 SW19 TW1 TW2 TW3 TW4 TW5 TW6 TW7 TW8 TW9 TW10 TW18 TW20 KT1 KT2 KT3 KT4 KT10 KT16 SM4 CR9 GU16'.split()),
    "North London": set('N1 N2 N3 N4 N5 N6 N7 N8 N9 N10 N11 N12 N13 N14 N15 N16 N17 N18 N19 N20 N21 N22 EN1 EN2 EN3 EN4 EN5 EN6 EN7'.split()),
    "Outer West London": set('UB1 UB2 UB3 UB4 UB5 UB6 UB7 UB8 UB9 UB10 UB11 SL2 SL3 SL4 SL6'.split()),
    "North East London": set('E1 E2 E3 E8 E9 E10 E11 E12 E13 E14 E15 E16 E17 E18 E20 IG1 IG6 IG9'.split()),
    "City/Central": set('EC1 EC2 EC3 EC4 WC1 WC2 W1J WC2A WC2E WC2H WC2N EC2M EC2N EC2Y EC3M EC3N EC3V EC4A EC4V WC1B'.split()),
    "South East London": set('SE1 SE2 SE3 SE4 SE5 SE6 SE7 SE8 SE9 SE10 SE11 SE12 SE13 SE14 SE15 SE16 SE17 SE18 SE19 SE20 SE21 SE22 SE23 SE24'.split()),
    "Outer East London": set('IG1 IG6 IG9 RM1 RM10'.split()),
    "Outer North London": set('AL1 AL2 AL8 LU2'.split()),
    "Other UK": set('CB2 CM13 CM24 HP13 OX2 OX7 OX26 RG1 RG14 BL8'.split()),
}

# ---------- Special Areas (airports & rail hubs) ----------
SPECIAL_AREAS = [
    # Major rail hubs
    ("@PAD", ["PADDINGTON"]),
    ("@KGX", ["KING'S CROSS","KINGS CROSS","KING S CROSS","KGX"]),
    ("@STP", ["ST PANCRAS","ST. PANCRAS","STPANCRAS"]),
    ("@EUS", ["EUSTON"]),
    ("@VIC", ["VICTORIA STATION","VICTORIA LONDON"]),
    ("@WAT", ["WATERLOO"]),
    ("@LST", ["LIVERPOOL STREET","LIVERPOOL ST"]),
    # Heathrow (LHR)
    ("@LHR", [
        "HEATHROW","LHR","TERMINAL 2","TERMINAL 3","TERMINAL 4","TERMINAL 5"," T2"," T3"," T4"," T5",
        "SHORT STAY","SHORT-STAY","SHORTSTAY","POD PARKING","HEATHROW EXPRESS","CENTRAL TERMINAL AREA",
        "ARRIVALS","DEPARTURES","PICK UP","PICK-UP","PICKUP","DROP OFF","DROP-OFF","DROPOFF"
    ]),
    # Gatwick (LGW)
    ("@LGW", [
        "GATWICK","LGW","NORTH TERMINAL","SOUTH TERMINAL",
        "FORECOURT","LONG STAY","SHORT STAY","CAR PARK","PICK UP","PICK-UP","DROP OFF","DROP-OFF","DROPOFF"
    ]),
    # Luton (LTN)
    ("@LTN", [
        "LUTON AIRPORT","LTN","LONDON LUTON","TERMINAL CAR PARK","TERMINAL CAR PARK 1","TERMINAL CAR PARK 2",
        "DROP OFF","DROP-OFF","DROPOFF","PICK UP","PICK-UP","SHORT STAY","SHORT-STAY"
    ]),
    # Stansted (STN)
    ("@STN", [
        "STANSTED","STN","LONDON STANSTED","SHORT STAY","SHORT-STAY","SHORT STAY CAR PARK","PREMIUM",
        "PREMIUM SHORT STAY","ORANGE ZONE","SHORT STAY ORANGE","PREMIUM ORANGE","ORANGE CAR PARK",
        "BLUE ZONE","GREEN ZONE","RED ZONE","YELLOW ZONE","PICK UP","PICK-UP","DROP OFF","DROP-OFF","DROPOFF"
    ]),
    # London City (LCY)
    ("@LCY", ["LONDON CITY AIRPORT","CITY AIRPORT","LCY","PICK UP","PICK-UP","DROP OFF","DROP-OFF","SHORT STAY","CAR PARK"]),
    # Optional
    ("@SEN", ["SOUTHEND AIRPORT","SEN"]),
    ("@BQH", ["BIGGIN HILL","BQH"]),
]

def detect_zone_group(outcode: str) -> str:
    if outcode and outcode.startswith("@"):
        return "Special Areas"
    for name, codes in ZONE_GROUPS.items():
        if outcode in codes:
            return name
    return "Other/Unassigned"

# ======================== Helpers ========================
def _iter_summary_files():
    """
    FAST mode:
      - Only scan ~/Documents/OnisAI/TripDB
      - Return just the newest SUMMARY (by filename; tie-break by mtime)
    """
    TRIP_DB.mkdir(parents=True, exist_ok=True)
    files = list(TRIP_DB.glob("TripLog-*-SUMMARY*.txt"))
    if not files:
        return []
    files.sort(key=lambda p: (p.name, p.stat().st_mtime))
    return [files[-1]]  # only the latest

# -------- OCR normaliser for postcode digit/letter swaps --------
_DIGIT_FIX = {'I':'1','L':'1','O':'0','S':'5','B':'8','Z':'2','G':'6'}
def _normalize_pc_noise(text: str) -> str:
    if not text:
        return text
    t = text.upper()

    def _fix_inward(m):
        return m.group(1) + _DIGIT_FIX.get(m.group(2), m.group(2)) + m.group(3)
    t = re.sub(r'(\s)([ILOSBZG])([A-Z]{2})\b', _fix_inward, t)

    def _fix_outcode(m):
        return m.group(1) + _DIGIT_FIX.get(m.group(2), m.group(2)) + m.group(3)
    t = re.sub(r'\b([A-Z]{1,2})([ILOSBZG])([A-Z])\b', _fix_outcode, t)

    return t

def _outcode_from(text: str) -> str | None:
    if not text:
        return None
    t = _normalize_pc_noise(text)
    m = OC_FULL_RE.search(t)
    if m:
        return m.group(1).upper()
    m2 = OC_OUTCODE_RE.search(t)
    return m2.group(1).upper() if m2 else None

def _detect_special(text: str) -> str | None:
    if not text:
        return None
    T = text.upper()
    for code, keys in SPECIAL_AREAS:
        if any(k in T for k in keys):
            return code
    return None

def _area_or_outcode(text: str) -> str | None:
    oc = _outcode_from(text)
    return oc if oc else _detect_special(text)

def _hhmmss_to_seconds(hms: str) -> int:
    hh, mm, ss = (hms.split(':') + ["0","0","0"])[:3]
    return int(hh)*3600 + int(mm)*60 + int(ss)

def _parse_summary_file(p: Path):
    text = p.read_text(encoding="utf-8", errors="ignore")
    mh = HDR_DATE_RE.search(text)
    if not mh:
        return []
    _, d_str, m_name, y_str = mh.groups()
    months = {m: i for i, m in enumerate(
        ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1)}
    y, m, d = int(y_str), months.get(m_name, 1), int(d_str)

    day_key = f"{y:04d}-{m:02d}-{d:02d}"
    file_id = str(p.resolve())
    seq = 0

    # split into blocks
    lines = text.splitlines()
    blocks, cur = [], []
    for ln in lines:
        if ln.strip().startswith("————"):
            if cur:
                blocks.append("\n".join(cur))
            cur = [ln]
        else:
            if cur:
                cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))

    out = []
    for b in blocks:
        mr = RUNTIME_RE.search(b)
        mc = COMPLETED_RE.search(b)
        mp = PRICE_RE.search(b)
        mpick = PICK_RE.search(b)
        mdrop = DROP_RE.search(b)
        if not (mr and mc and mp and mpick and mdrop):
            continue

        runtime_hms = mr.group(1)
        try:
            est_min = int(mr.group(2))
        except:
            continue
        comp_hms = mc.group(1)
        try:
            price = float(mp.group(1))
        except:
            continue

        try:
            comp_dt = datetime(y, m, d, *map(int, comp_hms.split(':')))
        except Exception:
            continue

        runtime_sec = _hhmmss_to_seconds(runtime_hms)
        if runtime_sec <= 0:
            continue

        runtime_min = runtime_sec / 60.0
        delay_min = runtime_min - est_min

        ac_dt = comp_dt - timedelta(seconds=runtime_sec)
        per_hr = (price / runtime_min) * 60 if runtime_min else 0.0

        _ = DIST_RE.search(b)
        m_pick_est  = PICKUP_EST_RE.search(b)
        m_pick_dist = PICKUP_DIST_RE.search(b)

        pickup_est_min = int(m_pick_est.group(1)) if m_pick_est else 0
        pickup_dist_mi = float(m_pick_dist.group(1)) if m_pick_dist else 0.0  # parsed (unused here)

        pickup  = mpick.group(1)
        dropoff = mdrop.group(1)

        out.append({
            "pickup_oc": _area_or_outcode(pickup),
            "dropoff_oc": _area_or_outcode(dropoff),
            "hour": ac_dt.hour,
            "dow": ac_dt.strftime("%A"),
            "per_hr": per_hr,
            "runtime_min": runtime_min,
            "uber_est_min": est_min,
            "delay_min": delay_min,
            "pickup_est_min": pickup_est_min,
            "accepted_dt": ac_dt,
            "completed_dt": comp_dt,
            "day_key": day_key,
            "file_id": file_id,
            "seq": seq
        })
        seq += 1
    return out

# ======================== Builder Core ========================
def build_pickup_dropoff():
    # 1) Parse latest SUMMARY only
    samples = []
    for f in _iter_summary_files():
        samples.extend(_parse_summary_file(f))

    from collections import defaultdict
    guard_events = []

    by_day = defaultdict(list)
    for s in samples:
        by_day[s["day_key"]].append(s)

    # init fields
    for s in samples:
        s["dead_min"] = 0.0
        s["next_pickup_est_min"] = 0.0

    MAX_GAP_MIN = 50  # cutoff; treat larger gaps as breaks (no penalty)

    for day, trips in by_day.items():
        trips.sort(key=lambda x: (x["accepted_dt"], x["completed_dt"], x["file_id"], x["seq"]))
        for i, s in enumerate(trips):
            next_acc = None
            next_pick_est = 0.0
            reason = "end-of-day"
            if i + 1 < len(trips):
                cand = trips[i+1]
                if cand["accepted_dt"] > s["completed_dt"]:
                    gap = (cand["accepted_dt"] - s["completed_dt"]).total_seconds() / 60.0
                    if gap > MAX_GAP_MIN:
                        reason = f"break-long-gap>{MAX_GAP_MIN}m ({gap:.1f}m)"
                    else:
                        next_acc = cand["accepted_dt"]
                        next_pick_est = float(cand.get("pickup_est_min", 0) or 0)
                        reason = f"linked gap {gap:.1f}m"
                else:
                    reason = "overlap/early-accept"
            if next_acc:
                dead_min = max(0.0, min(60.0, (next_acc - s["completed_dt"]).total_seconds() / 60.0))
            else:
                dead_min = 0.0

            s["dead_min"] = dead_min
            s["next_pickup_est_min"] = next_pick_est

            guard_events.append({
                "day": day,
                "completed": s["completed_dt"].strftime("%H:%M:%S"),
                "drop_outcode": s.get("dropoff_oc"),
                "next_accept": next_acc.strftime("%H:%M:%S") if next_acc else None,
                "dead_min": round(dead_min, 2),
                "next_pick_est": round(next_pick_est, 2),
                "reason": reason
            })

    # 3) Aggregate into pickup & dropoff buckets (plain and effective metrics)
    pickup, dropoff = {}, {}

    def _add_pick(oc, per_hr, runtime_min, pickup_est_min, delay_min):
        if not oc: return
        node = pickup.setdefault(oc, {"count":0,"sum_hr":0.0,"sum_pick_min":0.0,"sum_eff_hr":0.0,"sum_delay_min":0.0})
        node["count"] += 1
        node["sum_hr"] += per_hr
        node["sum_delay_min"] += (delay_min or 0.0)
        denom = max(1e-6, pickup_est_min + runtime_min)
        eff = per_hr * (runtime_min / denom)
        node["sum_eff_hr"] += eff
        node["sum_pick_min"] += pickup_est_min

    def _add_drop(oc, per_hr, runtime_min, dead_min, next_pick_est, delay_min):
        if not oc: return
        node = dropoff.setdefault(oc, {
            "count":0, "sum_hr":0.0, "sum_dead_min":0.0, "sum_eff_hr":0.0,
            "sum_dead_min_plus_next":0.0, "sum_eff_hr_plus_next":0.0, "sum_delay_min":0.0
        })
        node["count"] += 1
        node["sum_hr"] += per_hr
        node["sum_delay_min"] += (delay_min or 0.0)

        denom_a = max(1e-6, runtime_min + dead_min)
        eff_a = per_hr * (runtime_min / denom_a)
        node["sum_eff_hr"] += eff_a
        node["sum_dead_min"] += dead_min

        denom_b = max(1e-6, runtime_min + dead_min + (next_pick_est or 0.0))
        eff_b = per_hr * (runtime_min / denom_b)
        node["sum_eff_hr_plus_next"] += eff_b
        node["sum_dead_min_plus_next"] += (dead_min + (next_pick_est or 0.0))

    for s in samples:
        _add_pick(s["pickup_oc"], s["per_hr"], s["runtime_min"], s.get("pickup_est_min", 0), s.get("delay_min", 0.0))
        _add_drop(
            s["dropoff_oc"], s["per_hr"], s["runtime_min"],
            s.get("dead_min", 0.0), s.get("next_pickup_est_min", 0.0), s.get("delay_min", 0.0)
        )

    # 4) Collapse to averages
    def collapse_pick(b):
        out = {}
        for oc, d in b.items():
            c = d["count"]
            avg_hr = (d["sum_hr"]/c) if c else 0.0
            avg_pick_min = (d["sum_pick_min"]/c) if c else 0.0
            avg_eff = (d["sum_eff_hr"]/c) if c else 0.0
            avg_delay = (d["sum_delay_min"]/c) if c else 0.0
            out[oc] = {
                "count": c,
                "avg_hr": round(avg_hr, 2),
                "avg_pickup_min": round(avg_pick_min, 2),
                "avg_effective_pickup_hr": round(avg_eff, 2),
                "avg_delay_min": round(avg_delay, 2)
            }
        return out

    def collapse_drop(b):
        out = {}
        for oc, d in b.items():
            c = d["count"]
            avg_hr = (d["sum_hr"]/c) if c else 0.0
            avg_dead = (d["sum_dead_min"]/c) if c else 0.0
            avg_eff = (d["sum_eff_hr"]/c) if c else 0.0
            avg_dead_plus_next = (d["sum_dead_min_plus_next"]/c) if c else 0.0
            avg_eff_plus_next  = (d["sum_eff_hr_plus_next"]/c) if c else 0.0
            avg_delay = (d["sum_delay_min"]/c) if c else 0.0
            out[oc] = {
                "count": c,
                "avg_hr": round(avg_hr, 2),
                "avg_dead_min": round(avg_dead, 2),
                "avg_effective_dropoff_hr": round(avg_eff, 2),
                "avg_dead_min_with_next_pickup": round(avg_dead_plus_next, 2),
                "avg_effective_dropoff_hr_including_next_pickup": round(avg_eff_plus_next, 2),
                "avg_delay_min": round(avg_delay, 2)
            }
        return out

    pick = collapse_pick(pickup)
    drop = collapse_drop(dropoff)

    # -------- per-day effective totals (incl next pickup) for header line(s)
    daily_header_lines = []
    for day, trips in by_day.items():
        if not trips:
            continue
        total_price = sum((t["per_hr"] * t["runtime_min"] / 60.0) for t in trips)
        total_runtime = sum(t["runtime_min"] for t in trips)
        total_dead    = sum(t.get("dead_min", 0.0) for t in trips)
        total_next    = sum(t.get("next_pickup_est_min", 0.0) for t in trips)
        denom_hours   = (total_runtime + total_dead + total_next) / 60.0 if (total_runtime + total_dead + total_next) > 0 else 1e-6
        eff_hr_day    = total_price / denom_hours
        daily_header_lines.append(
            f"{day} → ~£{total_price:.2f} (eff £/hr incl next={eff_hr_day:.2f}; trips={len(trips)}; time R/D/N={total_runtime:.0f}/{total_dead:.0f}/{total_next:.0f} mins)"
        )

    # 5) Write battle-map summaries (text)
    def make_zone_summary(b):
        groups = {}
        for oc, d in b.items():
            z = detect_zone_group(oc)
            g = groups.setdefault(z, {"total":0,"sum_hr":0.0,"zones":[]})
            g["total"] += d["count"]
            g["sum_hr"] += d["avg_hr"] * d["count"]
            g["zones"].append((oc, d["count"], d["avg_hr"]))
        return groups

    def write_summary(groups, path, title, extra_header_lines=None):
        lines = []
        lines.append(f"=== {title} (Battle Map) ===")
        if extra_header_lines:
            for ln in extra_header_lines:
                lines.append(ln)
            lines.append("")
        total_zones = len({oc for g in groups.values() for oc,_,_ in g["zones"]})
        total_trips = sum(g["total"] for g in groups.values())
        lines.append(f"TOTAL ZONES: {total_zones}")
        lines.append(f"TOTAL TRIPS: {total_trips}")
        lines.append("")
        for z, data in sorted(groups.items(), key=lambda kv: kv[1]["total"], reverse=True):
            avg_hr = (data["sum_hr"]/data["total"]) if data["total"] else 0.0
            lines.append(f"ZONE: {z}")
            lines.append(f"  Trips: {data['total']} (avg £/hr: {avg_hr:.2f})")
            for oc, count, avg in sorted(data["zones"], key=lambda r:r[1], reverse=True):
                lines.append(f"    {oc}: {count} trips avg £/hr: {avg:.2f}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    write_summary(make_zone_summary(pick), PICK_SUMMARY, "PICKUP GRID SUMMARY")
    write_summary(make_zone_summary(drop), DROP_SUMMARY, "DROPOFF GRID SUMMARY", extra_header_lines=daily_header_lines)

    # 6) Write JSONs
    PICK_JSON.write_text(json.dumps({"meta":{"last_update":datetime.utcnow().isoformat()},"zones":pick}, indent=2), encoding="utf-8")
    DROP_JSON.write_text(json.dumps({"meta":{"last_update":datetime.utcnow().isoformat()},"zones":drop}, indent=2), encoding="utf-8")

    # 7) Guardrail log
    try:
        stamp = datetime.utcnow().isoformat()
        lines = [f"=== Guardrail Build {stamp} ==="]
        lines.append("Rules: per-day linking only; break link if gap > 50 min; cap counted dead time at 60 min.\n")
        for e in guard_events:
            lines.append(
                f"{e['day']} | completed {e['completed']} ({e.get('drop_outcode')}) "
                f"-> next {e['next_accept'] or '—'} | dead={e['dead_min']}m "
                f"+ nextPickEst={e['next_pick_est']}m | {e['reason']}"
            )
        lines.append("")
        with GUARD_LOG.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception:
        pass

    print("✅ pickup & dropoff DBs built (FAST latest-summary mode)")

if __name__ == "__main__":
    build_pickup_dropoff()
