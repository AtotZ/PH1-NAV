import sys
from pathlib import Path
import textwrap
import pytest

# Add the OnisAI Bot directory to import path
ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "OnisAI" / "Bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

import store


def test_latest_summary_functions_use_latest_header(tmp_path):
    tripdb = tmp_path / "TripDB"
    tripdb.mkdir()
    summary_path = tripdb / "TripLog-2024-01-01-SUMMARY.txt"

    content = textwrap.dedent(
        """
        ==== Monday, 01 January 2024 ====
        🕓 Trip 1 Runtime: 0:25:20
        💰 Uber Price: £12.50

        🕓 Trip 2 Runtime: 0:10:40
        💰 Uber Price: £7.50

        ==== Tuesday, 02 January 2024 ====
        🕓 Trip 1 Runtime: 1:05:20
        💰 Uber Price: £20.00

        🕓 Trip 2 Runtime: 0:15:40
        💰 Uber Price: £5.25
        """
    ).strip() + "\n"

    summary_path.write_text(content, encoding="utf-8")

    scope = store.latest_summary_scope(tripdb)

    # The scope should only include the latest day section (after the final header)
    assert "Monday" not in scope
    assert "0:25:20" not in scope
    assert scope.lstrip().startswith("🕓 Trip 1 Runtime: 1:05:20")

    # Totals should come from the latest section only
    assert store.latest_summary_total(tripdb) == pytest.approx(25.25)

    # Drive minutes should round seconds >=30 up to the next minute
    assert store.latest_summary_drive_minutes(tripdb) == 81
    assert store.latest_summary_drive_minutes(tripdb, round_secs=False) == 80


def test_latest_summary_functions_handle_missing_files(tmp_path):
    tripdb = tmp_path / "TripDB"
    tripdb.mkdir()

    assert store.latest_summary_scope(tripdb) == ""
    assert store.latest_summary_total(tripdb) == 0.0
    assert store.latest_summary_drive_minutes(tripdb) == 0
