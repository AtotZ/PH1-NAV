# Called by SARWBuilder AFTER building RAW + SUMMARY. Runs your grid builder.

import sys
from pathlib import Path

# Ensure Bot dir is importable (robust under Pythonista / CWD variance)
BOT_DIR = Path.home() / "Documents" / "OnisAI" / "Bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

def main():
    try:
        import importlib
        pudo = importlib.import_module("PUDOBuilder")
        pudo = importlib.reload(pudo)
        # prefer explicit entrypoint
        if hasattr(pudo, "build_pickup_dropoff"):
            pudo.build_pickup_dropoff()
        elif hasattr(pudo, "main"):
            pudo.main()
        elif hasattr(pudo, "run"):
            pudo.run()
        print("✅ Pickup/Dropoff grids updated.")
    except Exception as e:
        print(f"⚠️ PUDOBuilder not available or failed: {e}")

if __name__ == "__main__":
    main()
