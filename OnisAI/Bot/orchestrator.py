# Align "accept / complete" behavior with your old runner logic:
# - If any ACCEPTED-but-not-COMPLETED exists => stamp COMPLETED first, run SARW.
# - Else, if latest block is fresh (no 🕓/✅) => stamp ACCEPTED.
# - Else, do nothing.
#
# Safe/Idempotent, and normalizes separators to prevent glued titles like "...LOWTRIP 2".

import sys, re, datetime
from pathlib import Path

# Ensure Bot dir is importable (Pythonista-safe)
BOT_DIR = Path.home() / "Documents" / "OnisAI" / "Bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from utils import today_heading  # use the same day header generator

DOCS      = Path.home() / "Documents"
ONIS_ROOT = DOCS / "OnisAI"
UNIFIED   = ONIS_ROOT / "UnifiedDB.txt"

# ---------- tiny helpers ----------
TRIP_HDR_RE   = re.compile(r'(?m)^TRIP\s+\d+\s*$')
ACCEPTED_RE   = re.compile(r'(?m)^🕓 ACCEPTED AT:\s*(\d{2}:\d{2}:\d{2})\s*$')
COMPLETED_RE  = re.compile(r'(?m)^✅ COMPLETED AT:\s*(\d{2}:\d{2}:\d{2})\s*$')

def _now_hms():
    return datetime.datetime.now().strftime('%H:%M:%S')

def _normalize_trip_separators(text: str) -> str:
    # 1) If a "TRIP N" header is glued after content, force a newline before it.
    t = re.sub(r'(?<!\n)(TRIP\s+\d+\b)', r'\n\1', text)
    # 2) Collapse 3+ newlines before headers to exactly two (one blank line).
    t = re.sub(r'\n{3,}(TRIP\s+\d+\b)', r'\n\n\1', t)
    # 3) Ensure at least one blank line before headers (one extra if only one).
    t = re.sub(r'\n(TRIP\s+\d+\b)', r'\n\n\1', t)
    # 4) If file starts directly with TRIP, add a leading newline for consistency.
    if t.startswith("TRIP "):
        t = "\n" + t
    return t

def _extract_today_span(text: str):
    """Return (start, end) slice indices for today's section; if not present, (-1,-1)."""
    hdr = today_heading()
    m = re.search(re.escape(hdr), text)
    if not m:
        return -1, -1
    start = m.start()
    # next header or end
    m2 = re.search(r'\n==== .*? ====\n', text[m.end():])
    end = (m.end() + m2.start()) if m2 else len(text)
    return start, end

def _split_trips(day_body: str):
    """Return list of (start_idx, end_idx) for TRIP blocks inside a day's body."""
    starts = [m.start() for m in TRIP_HDR_RE.finditer(day_body)]
    if not starts:
        return []
    starts.append(len(day_body))
    return [(starts[i], starts[i+1]) for i in range(len(starts)-1)]

def _has_accepted(block: str) -> bool:
    return ACCEPTED_RE.search(block) is not None

def _has_completed(block: str) -> bool:
    return COMPLETED_RE.search(block) is not None

def _insert_after_trip_header(block: str, line: str) -> str:
    """Insert a line immediately after the 'TRIP N' header line."""
    lines = block.splitlines()
    if not lines:
        return block
    # 'TRIP N' header is the first line by format
    lines.insert(1, line)
    return "\n".join(lines)

def _stamp_accepted(block: str, when_hms: str) -> str:
    if _has_accepted(block):
        return block
    return _insert_after_trip_header(block, f"🕓 ACCEPTED AT: {when_hms}")

def _stamp_completed(block: str, when_hms: str) -> str:
    if _has_completed(block):
        return block
    # place '✅ COMPLETED AT:' after ACCEPTED if present, else directly after header
    lines = block.splitlines()
    if not lines:
        return block
    # try to insert after ACCEPTED line if it exists
    inserted = False
    for i, ln in enumerate(lines):
        if ln.startswith("🕓 ACCEPTED AT:"):
            lines.insert(i+1, f"✅ COMPLETED AT: {when_hms}")
            inserted = True
            break
    if not inserted:
        # fallback: insert as the second line (after TRIP header)
        lines.insert(1, f"✅ COMPLETED AT: {when_hms}")
    return "\n".join(lines)

# ---------- core policy ----------
def _apply_policy_to_today(text: str):
    """
    Returns (new_text, action_str)
    Policy:
      1) If any ACCEPTED && not COMPLETED exists (the most recent one), stamp COMPLETED (now) and run SARW.
      2) Else, if latest block has neither ACCEPTED nor COMPLETED, stamp ACCEPTED (now). No SARW yet.
      3) Else, no change.
    """
    t_start, t_end = _extract_today_span(text)
    if t_start == -1:
        return text, "No-today-header"

    before = text[:t_start]
    today  = text[t_start:t_end]
    after  = text[t_end:]

    # The body after the day header line
    day_lines = today.splitlines(True)  # keepends
    if not day_lines:
        return text, "No-today-body"

    # split header + body
    # header is first line (today_heading), rest is body
    header = day_lines[0]
    body   = "".join(day_lines[1:])

    trips = _split_trips(body)
    if not trips:
        return text, "No-trips"

    # Build list of blocks
    blocks = [body[s:e] for (s, e) in trips]

    # 1) Find latest ACCEPTED && not COMPLETED (scan from end)
    open_idx = None
    for idx in range(len(blocks) - 1, -1, -1):
        if _has_accepted(blocks[idx]) and not _has_completed(blocks[idx]):
            open_idx = idx
            break

    if open_idx is not None:
        # Stamp COMPLETED on that block
        hms = _now_hms()
        blocks[open_idx] = _stamp_completed(blocks[open_idx], hms)
        action = f"Stamped ✅ COMPLETED for TRIP@idx {open_idx}"
    else:
        # 2) Else, if latest block is fresh (no 🕓/✅), stamp ACCEPTED
        latest = len(blocks) - 1
        if (not _has_accepted(blocks[latest])) and (not _has_completed(blocks[latest])):
            hms = _now_hms()
            blocks[latest] = _stamp_accepted(blocks[latest], hms)
            action = "Stamped 🕓 ACCEPTED on latest fresh"
        else:
            return text, "No-change"

    # Reassemble day body, preserving original slices
    rebuilt = []
    for (s, e), new_block in zip(trips, blocks):
        rebuilt.append(new_block)
    new_body = "".join(rebuilt)

    # Put back together and normalize separators
    new_today = header + new_body
    new_text  = before + new_today + after
    new_text  = _normalize_trip_separators(new_text)
    return new_text, action

# ---------- public run ----------
def main():
    if not UNIFIED.exists():
        print("[orchestrator] UnifiedDB missing; nothing to do.")
        return

    txt = UNIFIED.read_text(encoding="utf-8", errors="ignore")
    new_txt, action = _apply_policy_to_today(txt)

    if action == "No-change":
        print("[orchestrator] Latest already stamped (🕓/✅). No action.")
        return
    if action in ("No-today-header","No-today-body","No-trips"):
        print(f"[orchestrator] {action}.")
        return

    UNIFIED.write_text(new_txt, encoding="utf-8")
    print(f"[orchestrator] {action}.", flush=True)

    # If we just stamped a COMPLETED, drive SARW once.
    if action.startswith("Stamped ✅ COMPLETED"):
        try:
            import importlib
            sarw = importlib.import_module("SARWBuilder")
            importlib.reload(sarw)
            sarw.main()
        except Exception as e:
            print(f"[orchestrator] SARW failed: {e}")

if __name__ == "__main__":
    main()
