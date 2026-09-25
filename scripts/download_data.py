"""Download and atomically publish the current normalized Fuyao data slice."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.net import load_env  # noqa: E402
from diagnosis.providers import fetch_fuyao_profit_cash  # noqa: E402
from diagnosis.snapshot import publish_snapshot  # noqa: E402

SNAPSHOT_PATH = ROOT / "data" / "cache" / "profit_cash_002466.json"


def main() -> int:
    if SNAPSHOT_PATH.exists():
        from diagnosis.snapshot import load_snapshot
        existing = load_snapshot(SNAPSHOT_PATH)["_snapshot"]
        print(json.dumps({"status": "already_prepared", "snapshot_id": existing["id"],
                          "created_at": existing["created_at"]}, ensure_ascii=False))
        return 0
    env = load_env(ROOT / ".env")
    inputs = fetch_fuyao_profit_cash(env.get("FUYAO_API_KEY", ""), env.get("FUYAO_BASE_URL", "https://fuyao.aicubes.cn"))
    result = publish_snapshot(SNAPSHOT_PATH, inputs)
    print(json.dumps({"status": "published", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "download_failed", "error_type": type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
