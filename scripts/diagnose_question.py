"""General entry point for the supported fixed-snapshot financial questions."""

from __future__ import annotations

import json
import sys

from diagnose_profit_cash import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError:
        print(json.dumps({"status": "snapshot_missing", "next": "py scripts/download_data.py"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        # Keep credential and raw provider details out of CLI failures.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
