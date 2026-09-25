"""Privately download August 2026 source samples and report coverage without values.

This is an exploratory data audit, not the published diagnosis snapshot.
Raw responses live only under the Git-ignored data/raw/ directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.net import load_env, open_direct  # noqa: E402

OUTPUT = ROOT / "data" / "raw" / "experiment-2026-08"
START = datetime(2026, 8, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
END = datetime(2026, 8, 31, 23, 59, 59, 999000, tzinfo=ZoneInfo("Asia/Shanghai"))
START_MS = int(START.timestamp() * 1000)
END_MS = int(END.timestamp() * 1000)

FUYAO = [
    ("stock_daily", "/api/a-share/prices/historical", {"thscode": "002466.SZ", "interval": "1d", "adjust": "forward", "start": START_MS, "end": END_MS}),
    ("peer_daily", "/api/a-share/prices/historical", {"thscode": "002460.SZ", "interval": "1d", "adjust": "forward", "start": START_MS, "end": END_MS}),
    ("income_quarters", "/api/a-share/financials/income-statements", {"thscode": "002466.SZ", "period": "quarterly", "limit": 8}),
    ("balance_quarters", "/api/a-share/financials/balance-sheets", {"thscode": "002466.SZ", "period": "quarterly", "limit": 8}),
    ("cash_flow_quarters", "/api/a-share/financials/cash-flow-statements", {"thscode": "002466.SZ", "period": "quarterly", "limit": 8}),
    ("indicators_2026_h1", "/api/a-share/financials/indicators", {"thscode": "002466.SZ", "report": "2026-2"}),
    ("indicators_2025_h1", "/api/a-share/financials/indicators", {"thscode": "002466.SZ", "report": "2025-2"}),
]

IFIND = [
    ("company_info", "stock", "get_stock_info", {"query": "天齐锂业002466.SZ截至2026年8月31日的主营产品、行业分类、可比公司"}),
    ("stock_valuation_daily", "stock", "get_stock_performance", {"query": "天齐锂业002466.SZ在2026年8月1日至8月31日逐交易日的市盈率TTM和市净率"}),
    ("financial_2026_h1", "stock", "get_stock_financials", {"query": "天齐锂业002466.SZ 2026年6月30日的单季度归母净利润、扣非归母净利润、存货、资产减值损失"}),
    ("financial_2025_h1", "stock", "get_stock_financials", {"query": "天齐锂业002466.SZ 2025年6月30日的单季度归母净利润、扣非归母净利润、存货、资产减值损失"}),
    ("peer_financial_2026_h1", "stock", "get_stock_financials", {"query": "赣锋锂业002460.SZ 2026年6月30日的营业收入、销售毛利率、ROE、资产负债率"}),
    ("peer_valuation_2026_08_31", "stock", "get_stock_performance", {"query": "天齐锂业002466.SZ和赣锋锂业002460.SZ在2026年8月31日的市盈率TTM、市净率"}),
    ("shareholders", "stock", "get_stock_shareholders", {"query": "天齐锂业002466.SZ截至2026年8月31日的控股股东持股及股权质押比例"}),
    ("events", "stock", "get_stock_events", {"query": "天齐锂业002466.SZ在2026年8月1日至8月31日的股权质押、限售股解禁及分红日期和数量"}),
    ("risk", "stock", "get_risk_indicators", {"query": "天齐锂业002466.SZ截至2026年8月31日近20个交易日波动率和最大回撤"}),
    ("sector", "index", "sector_data", {"query": "申万有色金属板块2026年8月1日至8月31日的区间涨跌幅、成分股个数"}),
    ("lithium_carbonate", "edb", "get_edb_data", {"query": "工业级碳酸锂现货价2026年8月1日至8月31日逐日数据，元每吨"}),
    ("lithium_hydroxide", "edb", "get_edb_data", {"query": "氢氧化锂现货价格2026年8月1日至8月31日逐日数据"}),
    ("spodumene", "edb", "get_edb_data", {"query": "化工级Li2O 6%-6.5%锂精矿均价2026年8月1日至8月31日逐日数据"}),
    ("lithium_futures", "edb", "get_edb_data", {"query": "广州期货交易所碳酸锂期货活跃合约收盘价2026年8月1日至8月31日逐日数据"}),
    ("notices", "news", "search_notice", {"query": "天齐锂业002466.SZ 半年度报告 项目进展 股权质押 解禁", "time_start": "2026-08-01", "time_end": "2026-08-31", "size": 20}),
    ("notices_broad", "news", "search_notice", {"query": "天齐锂业002466.SZ", "time_start": "2026-08-01", "time_end": "2026-08-31", "size": 50}),
    ("news", "news", "search_news", {"query": "天齐锂业002466.SZ", "time_start": "2026-08-01", "time_end": "2026-08-31", "size": 20}),
]

MCP_SERVICES = {
    "stock": "hexin-ifind-ds-stock-mcp", "index": "hexin-ifind-ds-index-mcp",
    "edb": "hexin-ifind-ds-edb-mcp", "news": "hexin-ifind-ds-news-mcp",
}

OFFICIAL_2026_H1 = "https://disc.static.szse.cn/disc/disk03/finalpage/2026-08-28/8e2a0f8d-1d4e-4676-b8a4-ac57c06021ef.PDF"


def _publish_private(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _dates_in_fuyao(items: list[dict]) -> list[str]:
    dates = []
    for item in items:
        for key in ("timestamp", "trade_date_ms", "date_ms", "period_end_ms"):
            value = item.get(key)
            if isinstance(value, (int, float)) and 1500000000000 < value < 2000000000000:
                dates.append(datetime.fromtimestamp(value / 1000, ZoneInfo("Asia/Shanghai")).date().isoformat())
                break
    return sorted(set(dates))


def _ifind_dates(value: object) -> list[str]:
    serialized = json.dumps(value, ensure_ascii=False)
    matches = re.findall(r"(?<!\d)20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?!\d)|(?<!\d)20\d{6}(?!\d)", serialized)
    dates = set()
    for match in matches:
        digits = re.findall(r"\d+", match)
        parts = [int(digits[0][:4]), int(digits[0][4:6]), int(digits[0][6:])] if len(digits) == 1 else [int(x) for x in digits[:3]]
        try:
            dates.add(date(*parts).isoformat())
        except ValueError:
            pass
    return sorted(dates)


def _fuyao_job(name: str, endpoint: str, params: dict, key: str) -> dict:
    path = OUTPUT / f"fuyao_{name}.json"
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        status = "saved_existing"
    else:
        request = Request(f"https://fuyao.aicubes.cn{endpoint}?{urlencode(params)}", headers={"X-api-key": key})
        with open_direct(request, timeout=45) as response:
            document = {"source": "fuyao", "endpoint": endpoint, "params": params,
                        "http_status": response.status, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                        "body": json.load(response)}
        _publish_private(path, document)
        status = "downloaded"
    body = document.get("body", {})
    data = body.get("data") or {}
    items = data.get("item") if isinstance(data, dict) else None
    dates = _dates_in_fuyao(items) if isinstance(items, list) else []
    if isinstance(items, list):
        count = len(items)
    elif isinstance(data, dict) and isinstance(data.get("abilities"), list):
        count = sum(len(x.get("indicators", [])) for x in data["abilities"] if isinstance(x, dict))
    else:
        count = None
    return {"name": name, "source": "fuyao", "status": status,
            "http_status": document.get("http_status"), "business_code": body.get("code"),
            "item_count": count, "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None, "distinct_dates": len(dates),
            "sample_fields": sorted(items[0])[:60] if isinstance(items, list) and items else [],
            "file": path.name}


def _mcp_post(url: str, token: str, payload: dict, session: str | None = None) -> tuple[int, str | None, dict | None]:
    headers = {"Authorization": token, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    with open_direct(request, timeout=70) as response:
        raw = response.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            events = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
            parsed = json.loads(events[-1]) if events else None
        return response.status, response.headers.get("Mcp-Session-Id"), parsed


def _mcp_session(service: str, token: str) -> tuple[str, str]:
    url = f"https://api-mcp.51ifind.com:8643/ds-mcp-servers/{MCP_SERVICES[service]}"
    status, session, _ = _mcp_post(url, token, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                                   "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                                              "clientInfo": {"name": "stock-diagnosis-experiment", "version": "0.1.0"}}})
    if status != 200 or not session:
        raise RuntimeError("iFinD initialize failed")
    _mcp_post(url, token, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    return url, session


def _ifind_job(name: str, service: str, tool: str, params: dict, token: str,
               sessions: dict[str, tuple[str, str]], request_id: int) -> dict:
    path = OUTPUT / f"ifind_{name}.json"
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        status = "saved_existing"
    else:
        if service not in sessions:
            sessions[service] = _mcp_session(service, token)
        url, session = sessions[service]
        http_status, _, response = _mcp_post(url, token, {"jsonrpc": "2.0", "id": request_id,
                                                         "method": "tools/call", "params": {"name": tool, "arguments": params}}, session)
        document = {"source": "ifind", "service": service, "tool": tool, "params": params,
                    "http_status": http_status, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "response": response}
        _publish_private(path, document)
        status = "downloaded"
    response = document.get("response") or {}
    result = response.get("result") if isinstance(response, dict) else None
    content = result.get("content") if isinstance(result, dict) else None
    parsed = None
    if isinstance(content, list) and content and isinstance(content[0], dict):
        try:
            parsed = json.loads(content[0].get("text", ""))
        except (TypeError, json.JSONDecodeError):
            pass
    data = parsed.get("data") if isinstance(parsed, dict) else None
    records = None
    if isinstance(data, dict) and isinstance(data.get("datas"), list):
        records = sum(len(item.get("data", {}).get("data", [])) for item in data["datas"] if isinstance(item, dict))
    elif isinstance(data, dict) and isinstance(data.get("answer"), str):
        records = max(0, sum(line.lstrip().startswith("|") for line in data["answer"].splitlines()) - 2)
    elif isinstance(data, dict) and isinstance(data.get("data"), str):
        try:
            records = sum("日期" in row for row in json.loads(data["data"]))
        except (TypeError, json.JSONDecodeError):
            pass
    elif isinstance(data, str):
        try:
            records = sum("日期" in row for row in json.loads(data))
        except (TypeError, json.JSONDecodeError):
            pass
    dates = _ifind_dates(data) if data is not None else []
    return {"name": name, "source": "ifind", "status": status,
            "http_status": document.get("http_status"),
            "mcp_error": bool(response.get("error")) if isinstance(response, dict) else True,
            "tool_error": result.get("isError") if isinstance(result, dict) else None,
            "api_code": parsed.get("code") if isinstance(parsed, dict) else None,
            "record_count": records, "content_blocks": len(content) if isinstance(content, list) else None,
            "text_date_examples": dates[:8], "text_date_token_count": len(dates), "file": path.name}


def _official_report_job() -> dict:
    path = OUTPUT / "szse_2026_h1_report.pdf"
    if path.exists():
        encoded = path.read_bytes()
        status = "saved_existing"
    else:
        request = Request(OFFICIAL_2026_H1)
        with open_direct(request, timeout=70) as response:
            encoded = response.read(20_000_001)
        if not encoded.startswith(b"%PDF-") or len(encoded) > 20_000_000:
            raise ValueError("official report is not a bounded PDF")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(encoded)
        status = "downloaded"
    if not encoded.startswith(b"%PDF-") or len(encoded) > 20_000_000:
        raise ValueError("saved official report is not a bounded PDF")
    return {"name": "official_2026_h1_report", "source": "szse", "status": status,
            "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest(), "file": path.name}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("all", "fuyao", "ifind", "official"), default="all")
    args = parser.parse_args()
    env = load_env(ROOT / ".env") if args.source != "official" else {}
    if args.source in ("all", "fuyao") and not env.get("FUYAO_API_KEY"):
        raise ValueError("FUYAO_API_KEY missing")
    if args.source in ("all", "ifind"):
        url = urlparse(env.get("IFIND_MCP_URL", ""))
        if not env.get("IFIND_MCP_AUTH_TOKEN") or url.scheme != "https" or url.hostname != "api-mcp.51ifind.com" or url.port != 8643:
            raise ValueError("official iFinD MCP configuration missing")
    jobs = []
    sessions: dict[str, tuple[str, str]] = {}
    if args.source in ("all", "fuyao"):
        for name, endpoint, params in FUYAO:
            try:
                result = _fuyao_job(name, endpoint, params, env["FUYAO_API_KEY"])
            except Exception as error:
                result = {"name": name, "source": "fuyao", "status": "failed", "error_type": type(error).__name__}
            jobs.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    if args.source in ("all", "ifind"):
        for index, (name, service, tool, params) in enumerate(IFIND, start=2):
            try:
                result = _ifind_job(name, service, tool, params, env["IFIND_MCP_AUTH_TOKEN"], sessions, index)
            except Exception as error:
                result = {"name": name, "source": "ifind", "status": "failed", "error_type": type(error).__name__}
            jobs.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            time.sleep(0.6)  # Default free-tier limit: at most two requests per second.
    if args.source in ("all", "official"):
        try:
            result = _official_report_job()
        except Exception as error:
            result = {"name": "official_2026_h1_report", "source": "szse", "status": "failed",
                      "error_type": type(error).__name__}
        jobs.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    audit = {"requested_window": ["2026-08-01", "2026-08-31"],
             "disclaimer": "Experimental coverage only; not validated product evidence or the frozen product snapshot.",
             "checked_at": datetime.now(timezone.utc).isoformat(), "jobs": jobs}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _publish_private(OUTPUT / f"audit_{args.source}_{stamp}.json", audit)
    return 0 if all(job["status"] != "failed" for job in jobs) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
