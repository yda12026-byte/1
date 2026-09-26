"""Record human spot-check results for announcement excerpts (decision 0022).

Usage: py scripts/record_event_spotcheck.py 1224956916:range=consistent 1224674868=inconsistent
Only IDs in the sample list are accepted; results are "consistent" or "inconsistent".
Rebuild the product snapshot afterwards so the page shows the checked status.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "annual-2025-08-31_2026-08-31" / "cninfo_event_spotcheck.json"


def main(args: list[str]) -> int:
    document = json.loads(PATH.read_text(encoding="utf-8"))
    for arg in args:
        key, _, result = arg.partition("=")
        if key not in document["sample"] or result not in ("consistent", "inconsistent"):
            raise SystemExit(f"not a sampled ID or invalid result: {arg}")
        document["results"][key] = {"status": result, "checked_at": datetime.now(timezone.utc).isoformat()}
    PATH.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    pending = [key for key in document["sample"] if key not in document["results"]]
    print(json.dumps({"recorded": len(args), "pending": pending}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
