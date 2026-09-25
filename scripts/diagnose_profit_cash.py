"""Run the first live backend slice. Raw provider responses are not stored."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.deepseek import DeepSeek  # noqa: E402
from diagnosis.net import load_env  # noqa: E402
from diagnosis.pipeline import diagnose_profit_cash  # noqa: E402
from diagnosis.snapshot import load_snapshot  # noqa: E402

SNAPSHOT_PATH = ROOT / "data" / "cache" / "profit_cash_002466.json"


def main() -> int:
    env = load_env(ROOT / ".env")
    question = " ".join(sys.argv[1:]) or "天齐锂业的利润和经营现金流匹配吗？"
    configured_path = env.get("DIAGNOSIS_SNAPSHOT_PATH", "")
    snapshot_path = Path(configured_path) if configured_path else SNAPSHOT_PATH
    if not snapshot_path.is_absolute():
        snapshot_path = ROOT / snapshot_path
    llm = DeepSeek(env["DEEPSEEK_API_KEY"], env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                   env.get("DEEPSEEK_MODEL", "deepseek-flash")) if env.get("DEEPSEEK_API_KEY") else None
    result = diagnose_profit_cash(
        question,
        lambda: load_snapshot(snapshot_path),
        llm,
    )
    print(json.dumps(result.to_dict() if hasattr(result, "to_dict") else result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError:
        print(json.dumps({"status": "snapshot_missing", "next": "py scripts/download_data.py"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        # Do not print credentials, raw responses, or provider exception bodies.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
