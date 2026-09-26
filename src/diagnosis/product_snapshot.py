"""Normalize the approved subset of the annual raw download into one fixed product snapshot.

The snapshot is built once from Git-ignored raw files, never overwritten, and
read-only at question time. Every block records its provider, tool/endpoint,
query and the raw file fingerprints it came from. Rules follow decisions 0013,
0014 and 0016: cumulative statement values, trading-day filtering of daily
series, iFinD valuation used as-is and never mixed with other market caps.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 2
SUBJECT = "002466.SZ"
PEERS = {"002460.SZ": ("peer", "赣锋锂业"), "002738.SZ": ("peer002738", "中矿资源"),
         "002756.SZ": ("peer002756", "永兴材料")}
NAMES = {SUBJECT: "天齐锂业", **{code: name for code, (_, name) in PEERS.items()}}
STEMS = {SUBJECT: "stock", **{code: stem for code, (stem, _) in PEERS.items()}}
WINDOW = {"start": "2025-08-31", "end": "2026-08-31"}
SHANGHAI = timezone(timedelta(hours=8))
INDICATOR_IDS = ("calculate_operating_income_yoy_growth_ratio", "calculate_parent_holder_net_profit_yoy_growth_ratio",
                 "sale_gross_margin", "index_weighted_avg_roe", "assets_debt_ratio", "inventory_turnover_ratio",
                 "current_ratio", "quick_ratio", "cash_ratio")
STATEMENT_FIELDS = {
    "income": ("operating_income", "net_profit", "parent_holder_net_profit"),
    "cash_flow": ("act_cash_flow_net", "pay_fixed_assets_etc_cash"),
    "balance": ("cash", "total_debt", "assets_total", "holder_equity_total"),
}
ENDPOINTS = {"income": "/api/a-share/financials/income-statements",
             "cash_flow": "/api/a-share/financials/cash-flow-statements",
             "balance": "/api/a-share/financials/balance-sheets"}
QUARTER_END = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class RawReader:
    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self.used: dict[str, str] = {}

    def load(self, name: str) -> dict:
        path = self.raw_dir / name
        data = path.read_bytes()
        self.used[name] = hashlib.sha256(data).hexdigest()[:16]
        document = json.loads(data)
        if document.get("http_status") != 200:
            raise ValueError(f"raw file is not a successful response: {name}")
        return document

    def fuyao(self, name: str):
        body = self.load(name)["body"]
        if body.get("code") != 0:
            raise ValueError(f"Fuyao business error in {name}")
        data = body["data"]
        return data.get("item", data) if isinstance(data, dict) and "item" in data else data

    def local_json(self, name: str):
        """Manual extraction files (not API responses): fingerprint and parse."""
        data = (self.raw_dir / name).read_bytes()
        self.used[name] = hashlib.sha256(data).hexdigest()[:16]
        return json.loads(data)

    def ifind(self, name: str) -> tuple[dict, dict]:
        document = self.load(name)
        text = document["response"]["result"]["content"][0]["text"]
        parsed = json.loads(text)
        if parsed.get("code") != 1:
            raise ValueError(f"iFinD business error in {name}")
        return document["params"], parsed["data"]


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, SHANGHAI).date().isoformat()


def _tables(answer: str) -> list[list[dict]]:
    tables, lines = [], []
    for line in answer.splitlines() + [""]:
        if line.startswith("|"):
            lines.append(line)
        elif lines:
            header = [cell.strip() for cell in lines[0].strip("|").split("|")]
            rows = [[cell.strip() for cell in row.strip("|").split("|")] for row in lines[2:]]
            tables.append([dict(zip(header, row)) for row in rows])
            lines = []
    return tables


def _ymd(text: str) -> str:
    text = text.replace("-", "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _number(text: str) -> float:
    match = re.fullmatch(r"(-?[\d.]+)(亿|万)?", text.strip())
    if not match:
        raise ValueError(f"unparseable number: {text}")
    return float(match.group(1)) * {"亿": 1e8, "万": 1e4, None: 1}[match.group(2)]


def _months() -> list[str]:
    start, end = date.fromisoformat(WINDOW["start"]), date.fromisoformat(WINDOW["end"])
    months, cursor = [], start.replace(day=1)
    while cursor <= end:
        months.append(f"{cursor.year}_{cursor.month:02d}")
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return months


def _statements(reader: RawReader, code: str) -> list[dict]:
    stem = STEMS[code]
    periods: dict[str, dict] = {}
    for statement, fields in STATEMENT_FIELDS.items():
        name = f"fuyao_{stem}_{statement}_quarters.json"
        for row in reader.fuyao(name):
            period_end = f"{row['fiscal_year']}-{QUARTER_END[row['fiscal_period']]}"
            entry = periods.setdefault(period_end, {"period_end": period_end, "fiscal_year": row["fiscal_year"],
                                                    "fiscal_period": row["fiscal_period"], "basis": "cumulative",
                                                    "values": {}, "sources": {}})
            if _day(row["period_end_ms"]) != period_end:
                raise ValueError(f"period_end_ms disagrees with fiscal period in {name}")
            for field in fields:
                value = row.get(field)
                entry["values"][field] = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
                entry["sources"][field] = {"provider": "Fuyao", "endpoint": ENDPOINTS[statement], "field": field,
                                           "raw_file": name}
    return sorted(periods.values(), key=lambda item: item["period_end"], reverse=True)


def _indicators(reader: RawReader, code: str) -> dict[str, dict]:
    out = {}
    for report in ("2025-2", "2025-3", "2025-4", "2026-1", "2026-2"):
        name = f"fuyao_{STEMS[code]}_indicators_{report}.json"
        year, quarter = report.split("-")
        period_end = f"{year}-{QUARTER_END['Q' + quarter]}"
        values = {}
        for ability in reader.fuyao(name)["abilities"]:
            for item in ability.get("indicators", []):
                if item["index_id"] in INDICATOR_IDS:
                    values[item["index_id"]] = float(item["value"]) if item.get("value") not in (None, "") else None
        out[period_end] = {"period_end": period_end, "basis": "cumulative", "unit": "%/次", "values": values,
                           "source": {"provider": "Fuyao", "endpoint": "/api/a-share/financials/indicators",
                                      "raw_file": name, "query": f"report={report}"}}
    return out


def _daily(reader: RawReader, code: str) -> dict:
    name = f"fuyao_{STEMS[code]}_daily.json"
    rows = [{"date": _day(row["date_ms"]), "open": row["open_price"], "high": row["high_price"],
             "low": row["low_price"], "close": row["close_price"], "volume": row["volume"],
             "turnover": row["turnover"]} for row in reader.fuyao(name)]
    rows.sort(key=lambda row: row["date"])
    if len({row["date"] for row in rows}) != len(rows):
        raise ValueError(f"duplicate trading dates in {name}")
    return {"adjust": "forward", "unit": {"price": "CNY", "volume": "股", "turnover": "CNY"}, "rows": rows,
            "source": {"provider": "Fuyao", "endpoint": "/api/a-share/prices/historical", "raw_file": name,
                       "query": f"thscode={code};interval=1d;adjust=forward"}}


def _series(reader: RawReader, stem: str, calendar: set[str], label: str, unit: str) -> dict:
    points: dict[str, float] = {}
    dropped = 0
    files = []
    for month in _months():
        name = f"ifind_{stem}_{month}.json"
        files.append(name)
        params, data = reader.ifind(name)
        rows = data["datas"][0]["data"]["data"] if data.get("datas") else []
        for day, value in rows:
            if day > WINDOW["end"] or day < WINDOW["start"]:
                continue
            if day not in calendar:
                dropped += 1
                continue
            if value is not None:
                points[day] = float(value)
    return {"label": label, "unit": unit, "points": sorted(points.items()), "dropped_non_trading_rows": dropped,
            "source": {"provider": "iFinD", "tool": "EDB", "raw_files": files, "query": params["query"]}}


def _valuation_series(reader: RawReader, calendar: set[str]) -> dict:
    points, files, dropped = {}, [], 0
    for month in _months():
        name = f"ifind_valuation_{month}.json"
        files.append(name)
        _, data = reader.ifind(name)
        for table in _tables(data["answer"]):
            for row in table:
                if "日期" not in row:
                    continue
                day = _ymd(row["日期"])
                if not WINDOW["start"] <= day <= WINDOW["end"]:
                    continue
                if day not in calendar:
                    dropped += 1
                    continue
                points[day] = {"pe_ttm": float(row["市盈率(PE,TTM)"]), "pb": float(row["市净率(PB,最新)"])}
    return {"points": sorted(points.items()), "dropped_non_trading_rows": dropped,
            "source": {"provider": "iFinD", "tool": "get_stock_performance", "raw_files": files,
                       "query": "天齐锂业逐交易日市盈率TTM、市净率（按月请求）"}}


def _sector(reader: RawReader, calendar: set[str]) -> dict:
    windows, files, constituents = [], [], {}
    for month in _months():
        name = f"ifind_sector_{month}.json"
        supplement = f"ifind_sector_{month}_capweighted.json"
        if (reader.raw_dir / supplement).exists():  # re-queried with explicit cap weighting (2026-05)
            _, cap = reader.ifind(supplement)
            cap_table = _tables(cap["answer"])[0][0]
            cap_key = next(key for key in cap_table if "区间涨跌幅" in key)
            files.append(supplement)
        else:
            cap_table = None
        files.append(name)
        params, data = reader.ifind(name)
        span = re.findall(r"(\d{4}-\d{2}-\d{2})", params["query"])
        tables = _tables(data["answer"])
        header_key = next(key for key in tables[0][0] if "区间涨跌幅" in key)
        if cap_table is not None:
            header_key, row = cap_key, cap_table
        else:
            row = tables[0][0]
        windows.append({"start": span[0], "end": span[1], "return_pct": float(row[header_key]),
                        "weighting": "总市值加权平均" if "总市值加权" in header_key else "算术平均" if "算术平均" in header_key else header_key,
                        "raw_file": supplement if cap_table is not None else name})
        for row in tables[1]:
            day = _ymd(row["日期"])
            if day in calendar:
                constituents[day] = int(row["成份股个数"])
    return {"name": "申万有色金属", "code": "001030005", "windows": windows,
            "constituents": sorted(constituents.items()),
            "source": {"provider": "iFinD", "tool": "sector_data", "raw_files": files,
                       "query": "申万有色金属板块逐月区间涨跌幅与成分股数"}}


def _valuation_cutoff(reader: RawReader) -> dict:
    params, data = reader.ifind("ifind_stock_valuation_cutoff.json")
    row = _tables(data["answer"])[0][0]
    pick = {"pe_ttm": "市盈率(PE,TTM)", "pe_mrq": "市盈率（PE，MRQ）", "pb_mrq": "市净率（PB，MRQ）",
            "ps_ttm": "市销率(PS,TTM)", "pcf_ttm": "市现率(PCF,经营现金流TTM)"}
    return {"date": "2026-08-31", "values": {key: float(row[column]) for key, column in pick.items()},
            "indicator_params": data.get("indicators_params"),
            "source": {"provider": "iFinD", "tool": "get_stock_performance",
                       "raw_file": "ifind_stock_valuation_cutoff.json", "query": params["query"]}}


def _peer_valuation(reader: RawReader) -> dict:
    params, data = reader.ifind("ifind_peer_valuation_cutoff_group.json")
    values = {row["证券代码"]: {"pe_ttm": float(row["市盈率(PE,TTM)"]), "pb": float(row["市净率(PB,最新)"])}
              for row in _tables(data["answer"])[0]}
    if set(values) != set(NAMES):
        raise ValueError("peer valuation file does not cover the formal peer group")
    return {"date": "2026-08-31", "values": values,
            "note": "PE(TTM) 元数据标“交易日期: 最新”，已用显式 20260831 查询复核数值一致（决策 0014 第三轮）",
            "source": {"provider": "iFinD", "tool": "get_stock_performance",
                       "raw_file": "ifind_peer_valuation_cutoff_group.json", "query": params["query"]}}


def _clues(reader: RawReader) -> dict:
    notices, news, empty = {}, {}, []
    for month in _months():
        for kind, target in (("notices", notices), ("news", news)):
            name = f"ifind_{kind}_{month}.json"
            _, data = reader.ifind(name)
            payload = data if isinstance(data, str) else data.get("data")
            if isinstance(payload, str) and not payload.lstrip().startswith("["):
                empty.append(name)  # iFinD answers "结果为空" in prose for empty windows
                continue
            for row in json.loads(payload) if isinstance(payload, str) else payload or []:
                day = (row.get("日期") or "")[:10]
                title = (row.get("公告标题") or row.get("资讯标题") or "").strip()
                if not title or not WINDOW["start"] <= day <= WINDOW["end"]:
                    continue
                item = {"date": day, "title": title}
                if kind == "news" and str(row.get("URL", "")).startswith("https://"):
                    item["url"] = row["URL"]
                target.setdefault((day, title), item)
    order = lambda items: sorted(items.values(), key=lambda item: item["date"], reverse=True)
    return {"status": "unverified_clue",
            "notices": order(notices), "news": order(news), "empty_result_files": empty,
            "note": "检索线索，未逐条核对原文，不作为正式事件证据（决策 0013 第 7 项、0016）",
            "source": {"provider": "iFinD", "tools": ["search_notice", "search_news"],
                       "raw_files": "ifind_notices_YYYY_MM.json / ifind_news_YYYY_MM.json"}}


def _official_h1(reader: RawReader) -> dict:
    items = reader.local_json("official_extract_h1.json")
    checks = {(row["period_end"], row["item"]): row["comparison"]
              for row in reader.local_json("official_extract_crosscheck.json")}
    for item in items:
        item["crosscheck"] = checks.get((item["period_end"], item["item"]))
    return {"items": items, "source": {"provider": "天齐锂业官方半年报（人工摘录）",
                                       "raw_files": ["official_extract_h1.json", "official_extract_crosscheck.json"],
                                       "method": "逐项摘录 PDF 页码与表名；存货、借款、扣非、投资收益与 iFinD 交叉核对"}}


def build_product_snapshot(raw_dir: Path, *, created_at: str | None = None) -> dict:
    reader = RawReader(raw_dir)
    daily = {code: _daily(reader, code) for code in NAMES}
    calendar = {row["date"] for row in daily[SUBJECT]["rows"]}
    if len(calendar) != 242:
        raise ValueError("trading calendar must contain the 242 audited trading days")
    for code, series in daily.items():
        if {row["date"] for row in series["rows"]} != calendar:
            raise ValueError(f"daily series is not aligned to the trading calendar: {code}")
    payload = {
        "schema_version": SCHEMA_VERSION, "kind": "product", "subject": SUBJECT,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "window": WINDOW, "names": NAMES, "peer_group": list(PEERS),
        "trading_calendar": {"count": len(calendar), "first": min(calendar), "last": max(calendar),
                             "source": "Fuyao 002466.SZ 前复权日线日期"},
        "statements": {code: _statements(reader, code) for code in NAMES},
        "indicators": {code: _indicators(reader, code) for code in NAMES},
        "daily": daily,
        "valuation_cutoff": _valuation_cutoff(reader),
        "valuation_series": _valuation_series(reader, calendar),
        "peer_valuation": _peer_valuation(reader),
        "sector": _sector(reader, calendar),
        "lithium": {
            "carbonate": _series(reader, "lithium_carbonate", calendar, "工业级碳酸锂现货价", "元/吨"),
            "hydroxide": _series(reader, "lithium_hydroxide", calendar, "氢氧化锂现货价", "元/吨"),
            "spodumene": _series(reader, "spodumene", calendar, "锂精矿均价（化工级 Li2O 6%-6.5%，中国）", "元/吨"),
            "futures": _series(reader, "lithium_futures", calendar, "碳酸锂期货活跃合约收盘价（广期所）", "元/吨"),
        },
        "clues": _clues(reader),
        "official_h1": _official_h1(reader),
    }
    payload["raw_manifest"] = dict(sorted(reader.used.items()))
    return payload


def publish_product_snapshot(path: Path, payload: dict) -> dict:
    if path.exists():
        raise FileExistsError("fixed product snapshot already exists")
    snapshot_id = hashlib.sha256(_canonical(payload)).hexdigest()[:20]
    document = {**payload, "snapshot_id": snapshot_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("xb") as handle:
            handle.write(_canonical(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return {"snapshot_id": snapshot_id, "created_at": payload["created_at"]}


def load_product_snapshot(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION or document.get("kind") != "product" or \
            document.get("subject") != SUBJECT:
        raise ValueError("product snapshot schema or subject mismatch")
    payload = {key: value for key, value in document.items() if key != "snapshot_id"}
    if document.get("snapshot_id") != hashlib.sha256(_canonical(payload)).hexdigest()[:20]:
        raise ValueError("product snapshot checksum mismatch")
    if datetime.fromisoformat(document["created_at"]).tzinfo is None:
        raise ValueError("product snapshot timestamp lacks timezone")
    for key in ("statements", "indicators", "daily", "valuation_cutoff", "valuation_series", "peer_valuation",
                "sector", "lithium", "clues"):
        if key not in document:
            raise ValueError(f"product snapshot block missing: {key}")
    return document
