"""Publish the fixed product snapshot once from the Git-ignored annual raw download.

Usage: py scripts/build_product_snapshot.py [--output PATH]
The output defaults to data/cache/product_snapshot_002466.json and is never
overwritten. Only counts and the snapshot ID are printed, not restricted values.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.product_snapshot import build_product_snapshot, load_product_snapshot, publish_product_snapshot  # noqa: E402

RAW = ROOT / "data" / "raw" / "annual-2025-08-31_2026-08-31"
DEFAULT = ROOT / "data" / "cache" / "product_snapshot_002466.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.output.exists():
        document = load_product_snapshot(args.output)
        print(json.dumps({"status": "already_prepared", "snapshot_id": document["snapshot_id"]}))
        return 0
    payload = build_product_snapshot(RAW)
    result = publish_product_snapshot(args.output, payload)
    print(json.dumps({"status": "published", **result, "raw_files": len(payload["raw_manifest"]),
                      "trading_days": payload["trading_calendar"]["count"],
                      "notice_clues": len(payload["clues"]["notices"]), "news_clues": len(payload["clues"]["news"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
