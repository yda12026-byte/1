"""Probe Fuyao access without printing keys or source values."""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.net import load_env, open_direct  # noqa: E402


def probe(base: str, key: str, name: str, path: str, params: dict) -> dict:
    started = time.monotonic()
    request = Request(f"{base}{path}?{urlencode(params)}", headers={"X-api-key": key})
    try:
        with open_direct(request, timeout=20) as response:
            http_status = response.status
            body = json.load(response)
        data = body.get("data") or {}
        items = data.get("item")
        abilities = data.get("abilities")
        count = len(items) if isinstance(items, list) else sum(
            len(ability.get("indicators", [])) for ability in abilities if isinstance(ability, dict)
        ) if isinstance(abilities, list) else None
        first = items[0] if isinstance(items, list) and items else None
        return {
            "name": name, "http_status": http_status, "business_code": body.get("code"),
            "status": "http_error" if http_status != 200 else "api_error" if body.get("code") != 0 else
            "empty" if not count else "ok",
            "message": str(body.get("message") or "").replace(key, "[redacted]")[:160],
            "item_count": count,
            "data_shape": "item" if isinstance(items, list) else "abilities" if isinstance(abilities, list) else "other",
            "data_timestamp_ms": data.get("timestamp"), "report_period": data.get("report"),
            "first_period_end_ms": first.get("period_end_ms") if isinstance(first, dict) else None,
            "first_item_fields": list(first)[:40] if isinstance(first, dict) else [],
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except Exception as error:
        return {"name": name, "status": "request_failed", "error_type": type(error).__name__,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}


def main() -> int:
    env = load_env(ROOT / ".env")
    key = env.get("FUYAO_API_KEY", "")
    base = urlparse(env.get("FUYAO_BASE_URL") or "https://fuyao.aicubes.cn")
    stock = sys.argv[1] if len(sys.argv) > 1 else "600519.SH"
    if not key or base.scheme != "https" or base.netloc != "fuyao.aicubes.cn" or not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", stock):
        print("Missing key, unofficial Fuyao URL, or invalid A-share code", file=sys.stderr)
        return 2
    end = round(time.time() * 1000)
    start = end - 60 * 24 * 60 * 60 * 1000
    requests = [
        ("snapshot", "/api/a-share/prices/snapshot", {"thscodes": stock}),
        ("historical", "/api/a-share/prices/historical", {"thscode": stock, "interval": "1d", "adjust": "forward", "start": start, "end": end}),
        ("income", "/api/a-share/financials/income-statements", {"thscode": stock, "period": "quarterly", "limit": 4}),
        ("balance", "/api/a-share/financials/balance-sheets", {"thscode": stock, "period": "quarterly", "limit": 4}),
        ("cash_flow", "/api/a-share/financials/cash-flow-statements", {"thscode": stock, "period": "quarterly", "limit": 4}),
        ("indicators", "/api/a-share/financials/indicators", {"thscode": stock, "report": "2026-2"}),
        ("valuation", "/api/a-share/valuations/snapshot", {"thscodes": stock}),
    ]
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        origin = f"{base.scheme}://{base.netloc}"
        results = list(pool.map(lambda item: probe(origin, key, *item), requests))
    print(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "sample_stock": stock,
                      "results": results}, ensure_ascii=False, indent=2))
    return 1 if all(item["status"] != "ok" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
