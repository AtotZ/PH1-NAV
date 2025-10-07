# 1-tap: ACCEPT, 2-tap: COMPLETE — smartly stamps the most recent PENDING trip first.

import re, datetime
from pathlib import Path

DOCS      = Path.home() / "Documents"
ROOT      = DOCS / "OnisAI"
UNIFIED   = ROOT / "UnifiedDB.txt"

ROOT.mkdir(parents=True, exist_ok=True)
if not UNIFIED.exists():
    UNIFIED.write_text("", encoding="utf-8")

HDR_RE     = re.compile(r'(==== .*? ====\n)(.*?)(?=\n==== |\Z)', re.S)
TRIP_HDR   = re.compile(r'(?m)^TRIP\s+\d+\s*$')
STAMP_ACC  = re.compile(r'(?m)^🕓 ACCEPTED AT:\s*\d{2}:\d{2}:\d{2}\s*$')
STAMP_COM  = re.compile(r'(?m)^✅ COMPLETED AT:\s*\d{2}:\d{2}:\d{2}\s*$')
DT_LINE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*$')

def _today_header():
    n = datetime.datetime.now()
    return f"==== {n.strftime('%A')}, {n.strftime('%d')} {n.strftime('%B')} {n.strftime('%Y')} ====\n"

def _ensure_today_header():
    t = UNIFIED.read_text(encoding="utf-8", errors="ignore")
    h = _today_header()
    if h not in t:
        with UNIFIED.open("a", encoding="utf-8") as f:
            f.write(h)

def _split_today_blocks(txt: str):
    """Return list of (start_idx, end_idx, block_text) for today's trips."""
    h = _today_header()
    m = re.search(re.escape(h) + r"(.*?)(?:\n==== |\Z)", txt, flags=re.S)
    if not m:
        return h, []
    body = m.group(1)
    starts = [s.start() for s in TRIP_HDR.finditer(body)]
    if not starts:
        return h, []
    starts.append(len(body))
    blocks = [(starts[i], starts[i+1], body[starts[i]:starts[i+1]]) for i in range(len(starts)-1)]
    return h, blocks

def _find_latest(blocks):
    return len(blocks) - 1 if blocks else None

def _has_acc(block: str): return bool(STAMP_ACC.search(block))
def _has_com(block: str): return bool(STAMP_COM.search(block))

def _find_latest_pending(blocks):
    """Most recent block that is ACCEPTED but not COMPLETED."""
    for i in range(len(blocks)-1, -1, -1):
        if _has_acc(blocks[i][2]) and not _has_com(blocks[i][2]):
            return i
    return None

def _insert_stamp(block: str, line: str, kind: str):
    """Insert ACCEPTED/COMPLETED line in a stable position."""
    lines = block.splitlines()
    insert_at = 1
    if len(lines) >= 2 and DT_LINE_RE.match(lines[1]):  # timestamp line present
        insert_at = 2
    if kind == "complete":
        # if already has ACCEPTED, put COMPLETED right after it
        for i, ln in enumerate(lines):
            if STAMP_ACC.match(ln):
                insert_at = i + 1
                break
    lines.insert(insert_at, line)
    return "\n".join(lines)

def _edit_latest_trip(mode: str):
    _ensure_today_header()
    txt = UNIFIED.read_text(encoding="utf-8", errors="ignore")
    h, blocks = _split_today_blocks(txt)
    if not blocks:
        print("No trips today to stamp."); return

    # indexes within today's body
    latest_idx  = _find_latest(blocks)
    pending_idx = _find_latest_pending(blocks)

    now_hms = datetime.datetime.now().strftime("%H:%M:%S")
    acc_line = f"🕓 ACCEPTED AT: {now_hms}"
    com_line = f"✅ COMPLETED AT: {now_hms}"

    # Decide target block and operation
    if mode == "accept":
        if pending_idx is not None:
            # complete the most recent pending trip (desired behavior)
            target_idx = pending_idx
            kind = "complete"
            line = com_line
            action = "✅ Completed PENDING at "
        else:
            # no pending → accept the latest block
            target_idx = latest_idx
            kind = "accept"
            line = acc_line
            action = "🕓 Marked as ACCEPTED at "
    else:  # explicit complete
        if pending_idx is not None:
            target_idx = pending_idx
        else:
            target_idx = latest_idx
        kind = "complete"
        line = com_line
        action = "✅ Marked as COMPLETED at "

    # Rebuild today's body with the stamped block
    start0 = blocks[0][0]
    end_last = blocks[-1][1]
    body = txt.split(h, 1)[1]
    body = body[:body.find('\n==== ')] if '\n==== ' in body else body

    rel_start, rel_end, block = blocks[target_idx]
    # Prevent double-stamping
    if kind == "accept" and _has_acc(block):
        print("Already ACCEPTED; no change.")
        return
    if kind == "complete" and _has_com(block):
        print("Already COMPLETED; no change.")
        return

    new_block = _insert_stamp(block, line, kind)
    new_body = body[:rel_start] + new_block + body[rel_end:]

    UNIFIED.write_text(txt.replace(body, new_body, 1), encoding="utf-8")
    print(action + now_hms + " → UnifiedDB.txt")

if __name__ == "__main__":
    import sys
    arg = (sys.argv[1].strip().lower() if len(sys.argv) > 1 else "accept")
    if arg in ("accept", "accepted", "a"):
        _edit_latest_trip("accept")
    else:
        _edit_latest_trip("complete")
