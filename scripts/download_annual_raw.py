"""Resume a private, one-year source download for the 72-field candidate catalog.

This is raw acquisition, not a validated or published diagnosis snapshot.
Each successful response is saved once under Git-ignored data/raw/. Failures stay
in the audit and may be retried by running the command again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from diagnosis.net import load_env, open_direct  # noqa: E402

# Reuse the already exercised MCP transport and bounded private-file writer.
from scripts import experiment_august_data as transport  # noqa: E402

OUTPUT = ROOT / "data" / "raw" / "annual-2025-08-31_2026-08-31"
WINDOW_START = date(2025, 8, 31)
WINDOW_END = date(2026, 8, 31)
SHANGHAI = ZoneInfo("Asia/Shanghai")
OFFICIAL_REPORTS = {
    "stock_2025_h1": "https://static.cninfo.com.cn/finalpage/2025-08-30/1224628837.PDF",
    "stock_2025_q3": "https://static.cninfo.com.cn/finalpage/2025-10-30/1224762331.PDF",
    "stock_2025_fy": "https://static.cninfo.com.cn/finalpage/2026-03-28/1225044817.PDF",
    "stock_2026_q1": "https://static.cninfo.com.cn/finalpage/2026-04-28/1225206465.PDF",
    "stock_2026_h1": "https://static.cninfo.com.cn/finalpage/2026-08-28/1225522276.PDF",
}


def month_windows():
    start = WINDOW_START
    while start <= WINDOW_END:
        next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        end = min(next_month - timedelta(days=1), WINDOW_END)
        yield start, end
        start = end + timedelta(days=1)


def ms(day: date, *, end: bool = False) -> int:
    instant = datetime(day.year, day.month, day.day, tzinfo=SHANGHAI)
    if end:
        instant += timedelta(days=1)
        instant -= timedelta(milliseconds=1)
    return int(instant.timestamp() * 1000)


def jobs():
    start, end = ms(WINDOW_START), ms(WINDOW_END, end=True)
    for symbol, stem in (("002466.SZ", "stock"), ("002460.SZ", "peer")):
        yield ("fuyao", f"{stem}_daily", "/api/a-share/prices/historical",
               {"thscode": symbol, "interval": "1d", "adjust": "forward", "start": start, "end": end})
        for statement, endpoint in (("income", "income-statements"), ("balance", "balance-sheets"),
                                    ("cash_flow", "cash-flow-statements")):
            yield ("fuyao", f"{stem}_{statement}_quarters", f"/api/a-share/financials/{endpoint}",
                   {"thscode": symbol, "period": "quarterly", "limit": 12})
        for report in ("2025-2", "2025-3", "2025-4", "2026-1", "2026-2"):
            yield ("fuyao", f"{stem}_indicators_{report}", "/api/a-share/financials/indicators",
                   {"thscode": symbol, "report": report})
    yield ("fuyao", "stock_corporate_actions", "/api/a-share/corporate-actions/adjustment-factors",
           {"thscode": "002466.SZ", "from": WINDOW_START.isoformat(), "to": WINDOW_END.isoformat()})

    for name, url in OFFICIAL_REPORTS.items():
        yield ("official", name, url)

    fixed_ifind = [
        ("company_info", "stock", "get_stock_info", "天齐锂业002466.SZ截至2026年8月31日的主营产品、行业分类、可比公司、主营业务构成"),
        ("financial_2025_h1", "stock", "get_stock_financials", "天齐锂业002466.SZ 2025年6月30日的单季度归母净利润、扣非归母净利润、存货、资产减值损失"),
        ("financial_2025_fy", "stock", "get_stock_financials", "天齐锂业002466.SZ 2025年12月31日的投资收益、分产品收入、分产品成本、分产品毛利率"),
        ("financial_2026_h1", "stock", "get_stock_financials", "天齐锂业002466.SZ 2026年6月30日的单季度归母净利润、扣非归母净利润、存货、资产减值损失"),
        ("peer_financial_2026_h1", "stock", "get_stock_financials", "赣锋锂业002460.SZ 2026年6月30日的营业收入、销售毛利率、ROE、资产负债率"),
        ("peer_valuation_cutoff", "stock", "get_stock_performance", "天齐锂业002466.SZ和赣锋锂业002460.SZ在2026年8月31日的市盈率TTM、市净率"),
        ("stock_valuation_cutoff", "stock", "get_stock_performance", "天齐锂业002466.SZ在2026年8月31日的市盈率TTM、市盈率MRQ、市净率MRQ、市销率TTM、市现率TTM"),
        ("shareholders_cutoff", "stock", "get_stock_shareholders", "天齐锂业002466.SZ截至2026年8月31日的控股股东持股及股权质押比例"),
        ("events_cutoff", "stock", "get_stock_events", "天齐锂业002466.SZ在2025年8月31日至2026年8月31日的股权质押、限售股解禁及分红日期和数量"),
        ("risk_cutoff", "stock", "get_risk_indicators", "天齐锂业002466.SZ截至2026年8月31日近20个交易日波动率和最大回撤"),
        ("business_2026_h1", "stock", "get_stock_financials", "天齐锂业002466.SZ 2026年6月30日的分产品收入、分产品成本、分产品毛利率"),
    ]
    for name, service, tool, query in fixed_ifind:
        yield ("ifind", name, service, tool, {"query": query})

    for first, last in month_windows():
        label = first.strftime("%Y_%m")
        span = f"{first.isoformat()}至{last.isoformat()}"
        yield ("ifind", f"valuation_{label}", "stock", "get_stock_performance",
               {"query": f"天齐锂业002466.SZ在{span}逐交易日的市盈率TTM和市净率"})
        yield ("ifind", f"sector_{label}", "index", "sector_data",
               {"query": f"申万有色金属板块{span}逐交易日的收盘价、区间涨跌幅和成分股数"})
        for stem, query in (
            ("lithium_carbonate", "工业级碳酸锂现货价"),
            ("lithium_hydroxide", "氢氧化锂现货价格"),
            ("spodumene", "化工级Li2O 6%-6.5%锂精矿均价"),
            ("lithium_futures", "广州期货交易所碳酸锂期货活跃合约收盘价"),
        ):
            yield ("ifind", f"{stem}_{label}", "edb", "get_edb_data",
                   {"query": f"{query}{span}逐日数据"})
        for stem, tool, query in (
            ("notices", "search_notice", "天齐锂业002466.SZ"),
            ("project_notices", "search_notice", "天齐锂业002466.SZ 项目进展 产能 减值 海外资产"),
            ("news", "search_news", "天齐锂业002466.SZ"),
        ):
            yield ("ifind", f"{stem}_{label}", "news", tool,
                   {"query": query, "time_start": first.isoformat(), "time_end": last.isoformat(), "size": 50})


def save(path: Path, document: dict) -> str:
    return transport._publish_private(path, document)


def fuyao_job(name: str, endpoint: str, params: dict, key: str) -> dict:
    path = OUTPUT / f"fuyao_{name}.json"
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("source") != "fuyao" or document.get("endpoint") != endpoint or document.get("params") != params:
            raise ValueError("saved Fuyao response does not match this request")
        status = "no_records" if name == "stock_corporate_actions" and document.get("body", {}).get("code") == 3002 else "saved_existing"
    else:
        request = Request(f"https://fuyao.aicubes.cn{endpoint}?{urlencode(params)}",
                          headers={"X-api-key": key})
        with open_direct(request, timeout=70) as response:
            document = {"source": "fuyao", "endpoint": endpoint, "params": params,
                        "http_status": response.status, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                        "body": json.load(response)}
        body = document["body"]
        data = body.get("data") if isinstance(body, dict) else None
        no_records = name == "stock_corporate_actions" and body.get("code") == 3002
        if document["http_status"] != 200 or not (body.get("code") == 0 and isinstance(data, dict) or no_records):
            raise ValueError("Fuyao HTTP or business response failed")
        save(path, document)
        status = "no_records" if no_records else "downloaded"
    body = document.get("body") or {}
    raw_data = body.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}
    if document.get("http_status") != 200 or not (body.get("code") == 0 and isinstance(raw_data, dict) or
                                                   name == "stock_corporate_actions" and body.get("code") == 3002):
        raise ValueError("saved Fuyao response has invalid business status")
    items = data.get("item") if isinstance(data, dict) else None
    count = len(items) if isinstance(items, list) else (0 if body.get("code") == 3002 else None)
    if count is None and isinstance(data.get("abilities"), list):
        count = sum(len(a.get("indicators", [])) for a in data["abilities"] if isinstance(a, dict))
    dates = transport._dates_in_fuyao(items) if isinstance(items, list) else []
    return {"name": name, "source": "fuyao", "status": status, "http_status": document.get("http_status"),
            "business_code": body.get("code"), "item_count": count, "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None, "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def ifind_job(name: str, service: str, tool: str, params: dict, token: str,
              sessions: dict, request_id: int) -> dict:
    path = OUTPUT / f"ifind_{name}.json"
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        if (document.get("source") != "ifind" or document.get("service") != service or
                document.get("tool") != tool or document.get("params") != params or
                document.get("http_status") != 200 or parsed_ifind(document).get("code") != 1):
            raise ValueError("saved iFinD response does not match this request")
        status = "saved_existing"
    else:
        if service not in sessions:
            sessions[service] = transport._mcp_session(service, token)
        url, session = sessions[service]
        http_status, _, response = transport._mcp_post(
            url, token, {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                         "params": {"name": tool, "arguments": params}}, session)
        document = {"source": "ifind", "service": service, "tool": tool, "params": params,
                    "http_status": http_status, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "response": response}
        parsed = parsed_ifind(document)
        if http_status != 200 or parsed.get("code") != 1 or parsed.get("data") is None:
            raise ValueError("iFinD HTTP, MCP or business response failed")
        save(path, document)
        status = "downloaded"
    parsed = parsed_ifind(document)
    dates = transport._ifind_dates(parsed.get("data"))
    return {"name": name, "source": "ifind", "status": status, "http_status": document.get("http_status"),
            "business_code": parsed.get("code"), "date_token_count": len(dates),
            "first_date_token": dates[0] if dates else None, "last_date_token": dates[-1] if dates else None,
            "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def parsed_ifind(document: dict) -> dict:
    response = document.get("response") or {}
    if not isinstance(response, dict) or response.get("error"):
        return {}
    result = response.get("result") or {}
    if not isinstance(result, dict) or result.get("isError"):
        return {}
    content = result.get("content") or []
    if not isinstance(content, list):
        return {}
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            try:
                value = json.loads(block["text"])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
    return {}


def official_job(name: str, url: str) -> dict:
    path = OUTPUT / f"official_{name}.pdf"
    if path.exists():
        payload = path.read_bytes()
        status = "saved_existing"
    else:
        with open_direct(Request(url), timeout=70) as response:
            payload = response.read(25_000_001)
        if not payload.startswith(b"%PDF-") or len(payload) > 25_000_000:
            raise ValueError("official report is not a bounded PDF")
        with path.open("xb") as handle:
            handle.write(payload)
        status = "downloaded"
    if not payload.startswith(b"%PDF-") or len(payload) > 25_000_000:
        raise ValueError("saved official report is not a bounded PDF")
    return {"name": name, "source": "official", "status": status, "url": url,
            "bytes": len(payload), "file": path.name, "sha256": hashlib.sha256(payload).hexdigest()}


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
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sessions = {}
    completed = []
    for index, job in enumerate(jobs(), start=2):
        source, name, *rest = job
        if args.source != "all" and source != args.source:
            continue
        try:
            if source == "fuyao":
                result = fuyao_job(name, *rest, env["FUYAO_API_KEY"])
            elif source == "official":
                result = official_job(name, *rest)
            else:
                result = ifind_job(name, *rest, env["IFIND_MCP_AUTH_TOKEN"], sessions, index)
        except Exception as error:
            result = {"name": name, "source": source, "status": "failed", "error_type": type(error).__name__}
        completed.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        # Audit is always resumable, including if the process is interrupted.
        (OUTPUT / f"audit_{args.source}.json").write_text(json.dumps({
            "window": [WINDOW_START.isoformat(), WINDOW_END.isoformat()],
            "state": "raw_download_only_unvalidated", "checked_at": datetime.now(timezone.utc).isoformat(),
            "jobs": completed}, ensure_ascii=False, indent=2), encoding="utf-8")
        if source == "ifind" and result["status"] != "saved_existing":
            time.sleep(0.6)
    return 0 if completed and all(x["status"] != "failed" for x in completed) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
