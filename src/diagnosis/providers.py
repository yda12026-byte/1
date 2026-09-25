from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode, urlparse
from urllib.request import Request
from zoneinfo import ZoneInfo

from .net import open_direct

SUBJECT = "002466.SZ"
ENDPOINTS = {
    "net_profit": ("/api/a-share/financials/income-statements", "net_profit"),
    "operating_cash_flow": ("/api/a-share/financials/cash-flow-statements", "act_cash_flow_net"),
}


def _official_base(value: str) -> str:
    parsed = urlparse(value or "https://fuyao.aicubes.cn")
    if parsed.scheme != "https" or parsed.netloc != "fuyao.aicubes.cn":
        raise ValueError("FUYAO_BASE_URL must be the official HTTPS host")
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_statement(base: str, api_key: str, endpoint: str) -> list[dict]:
    query = urlencode({"thscode": SUBJECT, "period": "annual", "limit": 4})
    request = Request(f"{base}{endpoint}?{query}", headers={"X-api-key": api_key})
    # The machine's default Python proxy is unavailable; direct access to this
    # allowlisted official host has been verified and matches the Node probes.
    with open_direct(request, timeout=15) as response:
        body = json.load(response)
    items = body.get("data", {}).get("item")
    if body.get("code") != 0 or not isinstance(items, list):
        raise ValueError("Fuyao business response is invalid")
    return items


def _date_from_ms(value: object) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, ZoneInfo("Asia/Shanghai")).date().isoformat()


def _normalize(row: dict | None, endpoint: str, field: str, *, failed: bool = False) -> dict:
    query_ref = f"{SUBJECT};period=annual;limit=4"
    if row is None:
        return {"status": "error" if failed else "missing", "reason": "接口失败" if failed else "未取得对应年报字段",
                "endpoint": endpoint, "query_ref": query_ref, "period_basis": "annual"}
    value = row.get(field)
    return {
        "status": "missing" if value is None else "valid", "value": value,
        "period_end": _date_from_ms(row.get("period_end_ms")), "unit": row.get("currency"),
        "period_basis": "annual" if row.get("period") == "annual" and row.get("fiscal_period") == "FY" else "unverified",
        "consolidation": "consolidated", "endpoint": endpoint,
        "query_ref": f"{query_ref};period_end_ms={row.get('period_end_ms')}",
        # report_date_ms is not promoted to published_at without filing verification.
    }


def fetch_fuyao_profit_cash(api_key: str, base_url: str = "https://fuyao.aicubes.cn") -> dict:
    if not api_key:
        raise ValueError("FUYAO_API_KEY is required")
    base = _official_base(base_url)
    results: dict[str, list[dict]] = {}
    failures: set[str] = set()
    for name, (endpoint, _) in ENDPOINTS.items():
        try:
            results[name] = _get_statement(base, api_key, endpoint)
        except Exception:
            results[name] = []
            failures.add(name)
    profits, cashes = results["net_profit"], results["operating_cash_flow"]
    common_ends = {row.get("period_end_ms") for row in cashes}
    matching = sorted((row for row in profits if row.get("period_end_ms") in common_ends),
                      key=lambda row: row.get("period_end_ms") or 0, reverse=True)
    profit_row = matching[0] if matching else max(profits, key=lambda row: row.get("period_end_ms") or 0, default=None)
    cash_row = next((row for row in cashes if row.get("period_end_ms") == profit_row.get("period_end_ms")), None) \
        if matching else max(cashes, key=lambda row: row.get("period_end_ms") or 0, default=None)
    return {
        "net_profit": _normalize(profit_row, *ENDPOINTS["net_profit"], failed="net_profit" in failures),
        "operating_cash_flow": _normalize(cash_row, *ENDPOINTS["operating_cash_flow"], failed="operating_cash_flow" in failures),
    }
