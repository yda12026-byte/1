"""Inspect a question's planned dimensions and fields without reading data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from diagnosis.routing import route_question  # noqa: E402


def main() -> None:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('usage: py scripts/route_question.py "用户问题"')
    print(json.dumps(route_question(question), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
