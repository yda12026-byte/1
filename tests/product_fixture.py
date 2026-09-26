"""Synthetic product snapshot with hand-computable values (not market data)."""

from __future__ import annotations

import copy
from datetime import date, timedelta

SUBJECT = "002466.SZ"
PEERS = ["002460.SZ", "002738.SZ", "002756.SZ"]
NAMES = {SUBJECT: "天齐锂业", "002460.SZ": "赣锋锂业", "002738.SZ": "中矿资源", "002756.SZ": "永兴材料"}
CREATED_AT = "2026-09-01T02:00:00+00:00"


def trading_days(count: int = 242) -> list[str]:
    days, cursor = [], date(2025, 9, 1)
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


DAYS = trading_days()


def _path(points: list[tuple[int, float]]) -> list[float]:
    """Piecewise-linear closes through (index, price) anchors."""
    closes = []
    for (i0, p0), (i1, p1) in zip(points, points[1:]):
        for i in range(i0, i1):
            closes.append(p0 + (p1 - p0) * (i - i0) / (i1 - i0))
    closes.append(points[-1][1])
    return closes


# Subject: 100 → 150 (i=100) → 90 (i=150) → 120 (end): drawdown −40%, window return +20%.
CLOSES = {SUBJECT: _path([(0, 100), (100, 150), (150, 90), (241, 120)]),
          "002460.SZ": _path([(0, 100), (241, 130)]), "002738.SZ": _path([(0, 100), (241, 140)]),
          "002756.SZ": _path([(0, 100), (241, 150)])}


def _daily(code: str) -> dict:
    rows = [{"date": day, "open": c, "high": c, "low": c, "close": round(c, 4), "volume": 1000 + (500 if i >= 222 else 0),
             "turnover": c * 1000} for i, (day, c) in enumerate(zip(DAYS, CLOSES[code]))]
    return {"adjust": "forward", "unit": {}, "rows": rows,
            "source": {"provider": "Fuyao", "endpoint": "/api/a-share/prices/historical", "raw_file": f"synthetic_{code}.json",
                       "query": "synthetic"}}


def _statement(period_end: str, values: dict) -> dict:
    endpoints = {"operating_income": "income", "net_profit": "income", "parent_holder_net_profit": "income",
                 "act_cash_flow_net": "cash", "pay_fixed_assets_etc_cash": "cash", "cash": "balance",
                 "total_debt": "balance", "assets_total": "balance", "holder_equity_total": "balance"}
    return {"period_end": period_end, "basis": "cumulative", "values": values,
            "sources": {field: {"provider": "Fuyao", "endpoint": f"/synthetic/{kind}", "field": field,
                                "raw_file": "synthetic.json"} for field, kind in endpoints.items()}}


CURRENT = {"operating_income": 200e8, "net_profit": 60e8, "parent_holder_net_profit": 40e8, "act_cash_flow_net": 30e8,
           "pay_fixed_assets_etc_cash": 10e8, "cash": 50e8, "total_debt": 100e8, "assets_total": 400e8,
           "holder_equity_total": 300e8}
BASE = {**CURRENT, "operating_income": 100e8, "parent_holder_net_profit": 10e8, "net_profit": 15e8}


def _indicators(values_now: dict, values_base: dict) -> dict:
    def block(period, values):
        return {"period_end": period, "basis": "cumulative", "unit": "%/次", "values": values,
                "source": {"provider": "Fuyao", "endpoint": "/api/a-share/financials/indicators", "raw_file": "synthetic.json"}}
    return {"2026-06-30": block("2026-06-30", values_now), "2025-06-30": block("2025-06-30", values_base)}


def _indicator_values(gross, roe, debt, rev_yoy=100.0, npp_yoy=300.0, turnover=1.5):
    return {"calculate_operating_income_yoy_growth_ratio": rev_yoy, "calculate_parent_holder_net_profit_yoy_growth_ratio": npp_yoy,
            "sale_gross_margin": gross, "index_weighted_avg_roe": roe, "assets_debt_ratio": debt,
            "inventory_turnover_ratio": turnover}


def _months() -> list[tuple[str, str]]:
    windows, cursor = [], date(2025, 9, 1)
    while cursor <= date(2026, 8, 1):
        nxt = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        windows.append((cursor.isoformat(), (nxt - timedelta(days=1)).isoformat()))
        cursor = nxt
    return windows


def _official_items() -> list[dict]:
    """Synthetic half-year extracts; amounts in 元 like the real extraction file."""
    base = {"pdf": "synthetic.pdf", "page": 1, "table_or_section": "synthetic", "note": "半年累计"}
    rows = []

    def add(period, item, value, unit="元", crosscheck=None, note=None):
        rows.append({**base, "item": item, "period_end": period, "value": value, "unit": unit,
                     "crosscheck": crosscheck, **({"note": note} if note else {})})

    for period, current in (("2026-06-30", True), ("2025-06-30", False)):
        k = 1.0 if current else 0.5
        add(period, "锂矿·营业收入", 80e8 * k)
        add(period, "锂矿·毛利率", 70.0 if current else 60.0, "%")
        add(period, "锂化合物及衍生品·营业收入", 120e8 * k)
        add(period, "锂化合物及衍生品·毛利率", 50.0 if current else 30.0, "%")
        add(period, "投资收益", 12e8 * k)
        add(period, "其中：对联营企业和合营企业的投资收益", 11e8 * k)
        add(period, "归属于母公司股东的净利润", 40e8 if current else 10e8)
        add(period, "归属于上市公司股东的扣除非经常性损益的净利润", 38e8 if current else 9e8, crosscheck="一致")
        add(period, "存货", 30e8 if current else 25e8, crosscheck="一致")
        for item, value in (("短期借款", 10e8), ("一年内到期的非流动负债", 5e8), ("长期借款", 50e8),
                            ("应付债券", 0.0), ("租赁负债", 5e8)):
            add(period, item, value)
        add(period, "资产减值损失", -1e8)
        add(period, "信用减值损失", -0.1e8)
        add(period, "存货跌价准备期末余额", 1e8 if current else 4e8)
        add(period, "购建固定资产、无形资产和其他长期资产支付的现金", 15e8)
        add(period, "锂精矿产量", 70.0 if current else 56.0, "万吨")
        for item in ("锂精矿销量", "锂化合物及衍生品·销量", "锂化合物及衍生品·产量"):
            add(period, item, None, "吨", note="报告未披露该期数值")
        for name, text in (("格林布什化学级锂精矿工厂三期", "已完工"), ("雅江锂辉石矿采选一期工程", "建设中"),
                           ("苏州年产3万吨氢氧化锂项目", "已完工")):
            add(period, f"在建项目·{name}·工程进度", None, "文本", note=f"工程进度原文：{text}")
    return rows


def product_payload() -> dict:
    payload = _base_payload()
    payload["official_h1"] = {"items": _official_items(), "source": {}}
    for blocks in payload["indicators"].values():
        for period, block in blocks.items():
            block["values"].update({"current_ratio": 2.5 if period == "2026-06-30" else 2.0,
                                    "quick_ratio": 2.0, "cash_ratio": 120.0})
    return payload


def _base_payload() -> dict:
    series = lambda start, end: [(day, start + (end - start) * i / 241) for i, day in enumerate(DAYS)]
    edb = lambda label, start, end: {"label": label, "unit": "元/吨", "points": series(start, end),
                                     "dropped_non_trading_rows": 0, "source": {"query": "synthetic"}}
    return copy.deepcopy({
        "schema_version": 2, "kind": "product", "subject": SUBJECT, "created_at": CREATED_AT,
        "window": {"start": "2025-08-31", "end": "2026-08-31"}, "names": NAMES, "peer_group": PEERS,
        "trading_calendar": {"count": 242, "first": DAYS[0], "last": DAYS[-1], "source": "synthetic"},
        "statements": {code: [_statement("2026-06-30", CURRENT), _statement("2025-06-30", BASE)] for code in NAMES},
        "indicators": {
            SUBJECT: _indicators(_indicator_values(60, 10, 30), _indicator_values(55, 5, 35, turnover=1.2)),
            "002460.SZ": _indicators(_indicator_values(50, 12, 40), _indicator_values(50, 12, 40)),
            "002738.SZ": _indicators(_indicator_values(40, 8, 50), _indicator_values(40, 8, 50)),
            "002756.SZ": _indicators(_indicator_values(30, 6, 60), _indicator_values(30, 6, 60)),
        },
        "daily": {code: _daily(code) for code in NAMES},
        "valuation_cutoff": {"date": "2026-08-31", "values": {"pe_ttm": 20, "pe_mrq": 10, "pb_mrq": 2, "ps_ttm": 5, "pcf_ttm": 25},
                             "source": {"provider": "iFinD", "tool": "get_stock_performance", "raw_file": "synthetic.json",
                                        "query": "synthetic"}},
        "valuation_series": {"points": [(day, {"pe_ttm": 10 + 10 * i / 241, "pb": 1 + i / 241}) for i, day in enumerate(DAYS)],
                             "dropped_non_trading_rows": 0, "source": {}},
        "peer_valuation": {"date": "2026-08-31", "note": "synthetic", "source": {"raw_file": "synthetic.json"},
                           "values": {SUBJECT: {"pe_ttm": 20, "pb": 2}, "002460.SZ": {"pe_ttm": 10, "pb": 1},
                                      "002738.SZ": {"pe_ttm": 30, "pb": 3}, "002756.SZ": {"pe_ttm": 40, "pb": 4}}},
        "sector": {"name": "申万有色金属", "code": "synthetic", "constituents": [],
                   "windows": [{"start": s, "end": e, "return_pct": 1.0, "weighting": "总市值加权平均"} for s, e in _months()],
                   "source": {}},
        "lithium": {"carbonate": edb("碳酸锂", 100, 200), "hydroxide": edb("氢氧化锂", 100, 150),
                    "spodumene": edb("锂精矿", 100, 300), "futures": edb("期货", 100, 120)},
        "clues": {"status": "unverified_clue", "note": "检索线索，未逐条核对原文",
                  "notices": [{"date": "2026-08-27", "title": "半年度报告"}, {"date": "2026-04-29", "title": "一季度报告"}],
                  "news": [{"date": "2026-08-31", "title": "业绩点评", "url": "https://example.com/a"},
                           {"date": "2026-08-01", "title": "行业动态"}],
                  "empty_result_files": [], "source": {}},
        "raw_manifest": {"synthetic.json": "0" * 16},
    })
