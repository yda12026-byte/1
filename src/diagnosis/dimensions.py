"""Deterministic evidence and conclusions for valuation, financial trend, market and industry.

Numbers are computed here from the fixed product snapshot; every computed item
records its formula and input evidence IDs. Conclusion anchors contain no digits
so the constrained LLM translation can be validated. See decision 0016.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from .catalog import DIMENSIONS, WINDOW
from .models import CannotSay, Conclusion, DiagnosisRun, Evidence, validate_run
from .priority import priority_for_field
from .product_snapshot import NAMES, SUBJECT

CONFIG_VERSION = "dimensions-v1"
DIMENSION_RUNNERS = ("operating_quality", "financial_trend", "valuation", "market", "industry", "risk", "events")
PERIOD, BASE = "2026-06-30", "2025-06-30"
YI = Decimal("100000000")

BASE_CANNOT_SAY = [
    CannotSay("NO_TRADE_ADVICE", "不能给出买卖、仓位或收益建议", "诊断不是投资建议"),
    CannotSay("NO_PRICE_PREDICTION", "不能据此预测股价必然涨跌", "历史数据不支持价格预测"),
    CannotSay("NO_UNSUPPORTED_CAUSALITY", "不能在没有补充证据时解释变化原因", "字段只说明数值与方向"),
    CannotSay("NO_LIVE_DATA", "不能把固定快照称为实时、最新或今天的数据", "考试产品只展示固定快照"),
]
VALUATION_CANNOT_SAY = BASE_CANNOT_SAY + [
    CannotSay("NO_VALUATION_JUDGMENT", "不能据估值分位或同行比较称低估、高估或便宜", "估值位置不等于公允价值判断"),
]


def D(value) -> Decimal:
    return Decimal(str(value))


def q(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


class Run:
    """Collect evidence for one dimension run and build validated conclusions."""

    def __init__(self, snapshot: dict, dimension: str, run_id: str):
        self.snapshot, self.dimension, self.run_id = snapshot, dimension, run_id
        self.fetched_at = snapshot["created_at"]
        self.evidence: dict[str, Evidence] = {}
        self.conclusions: list[Conclusion] = []

    def source(self, eid: str, metric: str, field_id: str, label: str, value, unit: str, *, time: dict,
               scope: dict, source: dict, status: str = "valid", reason: str | None = None) -> Evidence:
        if eid in self.evidence:
            return self.evidence[eid]
        if value is None and status == "valid":
            status, reason = "missing", reason or "快照中该字段为空"
        item = Evidence(id=eid, metric_id=metric, subject=scope.get("subject", SUBJECT), kind="source",
                        value=str(value) if status == "valid" else None, unit=unit,
                        time={**time, "fetched_at": self.fetched_at}, scope=scope, source=source,
                        quality={"status": status, **({"reason": reason} if reason else {})},
                        priority=priority_for_field(field_id), label=label)
        self.evidence[eid] = item
        return item

    def computed(self, eid: str, metric: str, field_id: str, label: str, value, unit: str, *, formula_id: str,
                 formula: str, inputs: list[Evidence], time: dict, scope: dict | None = None,
                 status: str | None = None, reason: str | None = None, summary: dict | None = None) -> Evidence:
        usable = all(item.quality["status"] == "valid" for item in inputs)
        if status is None:
            status = "valid" if usable and value is not None else "missing" if not usable else "not_applicable"
        if status != "valid":
            value = None
            reason = reason or ("输入证据缺失或不可用" if not usable else "计算条件不满足")
        item = Evidence(
            id=eid, metric_id=metric, subject=SUBJECT, kind="computed", value=str(value) if value is not None else None,
            unit=unit, time={**time, "fetched_at": self.fetched_at}, scope=scope or {"basis": "program_calculation"},
            calculation={"formula_id": formula_id, "formula_version": "1", "formula_text": formula,
                         "input_evidence_ids": [item.id for item in inputs],
                         "priority_inputs": [{"evidence_id": item.id, "priority": item.priority.copy()} for item in inputs],
                         "priority_policy": "output_field_profile_no_numeric_weight",
                         **({"summary": summary} if summary else {})},
            quality={"status": status, **({"reason": reason} if reason else {})},
            priority=priority_for_field(field_id), label=label)
        self.evidence[eid] = item
        return item

    def conclude(self, key: str, field_id: str, claim_type: str, assessment: str, anchor: str, text: str,
                 supports: list[Evidence], context: list[Evidence] = (), limitations: list[str] = (),
                 highlights: list[Evidence] = (), cannot_say: list[CannotSay] | None = None,
                 table: dict | None = None) -> None:
        usable = [item for item in supports if item.quality["status"] == "valid"]
        if claim_type != "unknown" and len(usable) != len(supports):
            claim_type, assessment = "unknown", "unknown"
            anchor = f"{anchor.split('，')[0]}的证据不完整"
            text = f"{anchor}，暂不形成结论；请查看各项证据的状态与原因。"
        links = [{"evidence_id": item.id, "role": "supports" if item.quality["status"] == "valid" else "context"}
                 for item in supports] + [{"evidence_id": item.id, "role": "context"} for item in context]
        if any(char.isdigit() for char in anchor):
            raise ValueError("conclusion anchors must not contain digits")
        self.conclusions.append(Conclusion(
            id=f"{key}:{self.run_id}", dimension=self.dimension, claim_code=key, type=claim_type,
            assessment=assessment, evidence_links=links,
            limitations=list(limitations) + ["仅代表固定快照（数据截止 2026-08-31），不代表实时状态"],
            cannot_say=list(cannot_say or BASE_CANNOT_SAY), required_anchor=anchor, fallback_text=text, text=text,
            priority=priority_for_field(field_id), highlights=[item.id for item in highlights], table=table))

    def finish(self, question: str, route: dict) -> DiagnosisRun:
        run = DiagnosisRun(id=self.run_id, subject=SUBJECT, question=question, route=route,
                           config_version=CONFIG_VERSION, created_at=datetime.now(timezone.utc).isoformat(),
                           evidence=list(self.evidence.values()), conclusions=self.conclusions)
        return validate_run(run)


def _pct_change(run: Run, eid: str, metric: str, field_id: str, label: str, current: Evidence, base: Evidence,
                time: dict) -> Evidence:
    value, status, reason = None, None, None
    if current.value is not None and base.value is not None:
        denominator = abs(D(base.value))
        if denominator == 0:
            status, reason = "not_applicable", "基期为零，同比不适用"
        else:
            value = q((D(current.value) - D(base.value)) / denominator * 100)
    return run.computed(eid, metric, field_id, label, value, "%", formula_id="yoy_abs_base",
                        formula="(本期 − 基期) ÷ |基期| × 100；负基期按绝对值（决策 0013 第 2 项）",
                        inputs=[current, base], time=time, status=status, reason=reason)


def _cross_check(computed: Evidence, reference: Evidence, tolerance: Decimal = Decimal("0.1")) -> None:
    """Mark a computed growth rate as conflicting if the provider's own ratio disagrees."""
    if computed.value is None or reference.value is None:
        return
    if abs(D(computed.value) - D(reference.value)) > tolerance:
        computed.quality = {"status": "conflict", "reason": "程序计算值与扶摇同名指标相差超过 0.1 个百分点"}
        computed.value = None


# --- official half-year extracts ----------------------------------------------

DEBT_ITEMS = ("短期借款", "一年内到期的非流动负债", "长期借款", "应付债券", "租赁负债")


def _official(run: Run, item: str, period_end: str, metric: str, field_id: str, label: str) -> Evidence:
    rows = {(row["period_end"], row["item"]): row for row in run.snapshot.get("official_h1", {}).get("items", [])}
    row = rows.get((period_end, item))
    eid = f"{metric}:{SUBJECT}:{period_end}"
    if row is None:
        return run.source(eid, metric, field_id, f"{label}（{period_end[:7]}）", None, None, time={"period_end": period_end},
                          scope={"subject": SUBJECT}, source={"provider": "官方半年报（人工摘录）", "endpoint": "official_extract_h1.json", "field": item,
                                                              "query_ref": "快照缺少该摘录项"},
                          status="missing", reason="快照缺少该摘录项")
    value, unit, scope = row["value"], row["unit"], {"subject": SUBJECT, "basis": row.get("note", "")}
    status, reason = "valid", None
    if unit == "文本":
        value = (row.get("note") or "").split("原文：")[-1] or None
    elif value is not None and unit == "元":
        value, unit = q(D(value) / YI, "0.0001"), "亿元"
        scope["unit_conversion"] = "元 ÷ 1e8，保留四位小数"
    elif value is not None:
        value = D(value)
    if value is None:
        status, reason = "missing", row.get("note") or "报告未披露"
    elif row.get("crosscheck") and "不一致" in row["crosscheck"]:
        status, reason = "conflict", f"官方报告与 iFinD 不一致：{row['crosscheck']}"
    check = f"；iFinD 交叉核对：{row['crosscheck']}" if row.get("crosscheck") else ""
    return run.source(eid, metric, field_id, f"{label}（{period_end[:7]}）", value, unit, time={"period_end": period_end},
                      scope=scope, source={"provider": "天齐锂业官方半年报（人工摘录）", "endpoint": row["pdf"], "field": item,
                                           "query_ref": f"第 {row['page']} 页 · {row['table_or_section']}{check}"},
                      status=status, reason=reason)


def _net_cash(run: Run, cash: Evidence) -> tuple[Evidence, Evidence]:
    parts = [_official(run, item, PERIOD, f"debt_{i}", "f027", item) for i, item in enumerate(DEBT_ITEMS)]
    total = sum((D(item.value) for item in parts), Decimal(0)) if all(item.value is not None for item in parts) else None
    debt = run.computed("interest_bearing_debt:" + PERIOD, "interest_bearing_debt", "f027", "有息债务合计（期末）",
                        total, "亿元", formula_id="sum_interest_bearing_items",
                        formula="短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券 + 租赁负债（官方半年报合并资产负债表）",
                        inputs=parts, time={"period_end": PERIOD})
    net = run.computed("net_cash:" + PERIOD, "net_cash", "f027", "净现金（货币资金 − 有息债务）",
                       q(D(cash.value) - total, "0.0001") if total is not None and cash.value else None, "亿元",
                       formula_id="cash_minus_interest_bearing_debt", formula="货币资金 − 有息债务合计；为负表示有息债务多于货币资金",
                       inputs=[cash, debt], time={"period_end": PERIOD})
    return net, debt


# --- financial trend -------------------------------------------------------

def _statement(snapshot: dict, code: str, period_end: str) -> dict | None:
    return next((row for row in snapshot["statements"][code] if row["period_end"] == period_end), None)


def _statement_evidence(run: Run, code: str, period_end: str, field: str, metric: str, field_id: str,
                        label: str) -> Evidence:
    row = _statement(run.snapshot, code, period_end)
    raw = row["values"].get(field) if row else None
    source = row["sources"][field] if row else {"provider": "Fuyao", "endpoint": "", "field": field, "raw_file": ""}
    return run.source(
        f"{metric}:{code}:{period_end}", metric, field_id, f"{label}（{period_end[:7]} 累计）",
        q(D(raw) / YI, "0.0001") if raw is not None else None, "亿元",
        time={"period_end": period_end}, scope={"subject": code, "period_basis": "cumulative", "consolidation": "consolidated",
                                                "unit_conversion": "元 ÷ 1e8，保留四位小数"},
        source={"provider": source["provider"], "endpoint": source["endpoint"], "field": field,
                "query_ref": f"{source['raw_file']};thscode={code};fiscal_period={period_end}"},
        status="valid" if row else "missing", reason=None if row else "快照缺少该报告期")


def _indicator_evidence(run: Run, code: str, period_end: str, index_id: str, metric: str, field_id: str,
                        label: str, unit: str = "%") -> Evidence:
    block = run.snapshot["indicators"][code].get(period_end)
    value = block["values"].get(index_id) if block else None
    return run.source(
        f"{metric}:{code}:{period_end}", metric, field_id, f"{label}（{NAMES[code]}，{period_end[:7]} 累计）",
        D(value) if value is not None else None, unit, time={"period_end": period_end},
        scope={"subject": code, "period_basis": "cumulative"},
        source={"provider": "Fuyao", "endpoint": "/api/a-share/financials/indicators", "field": index_id,
                "query_ref": f"{block['source']['raw_file'] if block else ''};thscode={code}"},
        status="valid" if block else "missing", reason=None if block else "快照缺少该报告期指标")


def financial_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "financial_trend", run_id)
    t = {"period_end": PERIOD, "base_period_end": BASE}
    rev, rev_b = (_statement_evidence(run, SUBJECT, p, "operating_income", "operating_income", "f016", "营业收入") for p in (PERIOD, BASE))
    npp, npp_b = (_statement_evidence(run, SUBJECT, p, "parent_holder_net_profit", "parent_net_profit", "f018", "归母净利润") for p in (PERIOD, BASE))
    rev_yoy = _pct_change(run, "operating_income_yoy:" + PERIOD, "operating_income_yoy", "f016", "营业收入同比（累计）", rev, rev_b, t)
    npp_yoy = _pct_change(run, "parent_net_profit_yoy:" + PERIOD, "parent_net_profit_yoy", "f018", "归母净利润同比（累计）", npp, npp_b, t)
    _cross_check(rev_yoy, _indicator_evidence(run, SUBJECT, PERIOD, "calculate_operating_income_yoy_growth_ratio",
                                              "fuyao_operating_income_yoy", "f016", "扶摇营业收入同比"))
    _cross_check(npp_yoy, _indicator_evidence(run, SUBJECT, PERIOD, "calculate_parent_holder_net_profit_yoy_growth_ratio",
                                              "fuyao_parent_net_profit_yoy", "f018", "扶摇归母净利润同比"))
    growth_limits = ["比较 2026 年半年报与 2025 年半年报的累计值（决策 0013 第 1 项）"]
    if npp.value and npp_b.value and abs(D(npp_b.value)) < abs(D(npp.value)) / 10:
        growth_limits.append("归母净利润基期较低，同比倍数被放大，应结合绝对值阅读")
    signs = [D(item.value) > 0 for item in (rev_yoy, npp_yoy) if item.value is not None]
    if len(signs) == 2 and all(signs):
        spec = ("fact", "positive", "营业收入与归母净利润同比均增长", "按半年报累计口径，营业收入与归母净利润同比均增长；增速与基期见证据。")
    elif len(signs) == 2 and not any(signs):
        spec = ("fact", "negative", "营业收入与归母净利润同比均下降", "按半年报累计口径，营业收入与归母净利润同比均下降。")
    else:
        spec = ("fact", "mixed", "营业收入与归母净利润同比方向不一致", "按半年报累计口径，营业收入与归母净利润的同比方向不一致。")
    ded, ded_b = (_official(run, "归属于上市公司股东的扣除非经常性损益的净利润", p, "deducted_net_profit", "f019", "扣非归母净利润")
                  for p in (PERIOD, BASE))
    ded_yoy = _pct_change(run, "deducted_net_profit_yoy:" + PERIOD, "deducted_net_profit_yoy", "f019", "扣非归母净利润同比（累计）",
                          ded, ded_b, t)
    run.conclude("growth", "f018", *spec, supports=[rev_yoy, npp_yoy], context=[rev, rev_b, npp, npp_b, ded, ded_b, ded_yoy],
                 limitations=growth_limits, highlights=[rev_yoy, npp_yoy, npp])

    np_ = _statement_evidence(run, SUBJECT, PERIOD, "net_profit", "net_profit", "f021", "净利润")
    ocf = _statement_evidence(run, SUBJECT, PERIOD, "act_cash_flow_net", "operating_cash_flow", "f022", "经营活动现金流净额")
    capex = _statement_evidence(run, SUBJECT, PERIOD, "pay_fixed_assets_etc_cash", "fixed_asset_cash", "f025", "购建长期资产支付现金")
    ratio_value = q(D(ocf.value) / D(np_.value)) if ocf.value and np_.value and D(np_.value) > 0 else None
    ratio = run.computed("cash_to_profit_ratio:" + PERIOD, "cash_to_profit_ratio_h1", "f024", "经营现金流 / 净利润（累计）",
                         ratio_value, "倍", formula_id="operating_cash_flow_div_net_profit",
                         formula="经营活动现金流净额 ÷ 净利润；净利润须大于零", inputs=[ocf, np_], time={"period_end": PERIOD},
                         reason="净利润不大于零，比值不适用")
    fcf = run.computed("fcf_approx:" + PERIOD, "fcf_approx", "f026", "自由现金流近似值（累计）",
                       q(D(ocf.value) - D(capex.value), "0.0001") if ocf.value and capex.value else None, "亿元",
                       formula_id="operating_cash_flow_minus_fixed_asset_cash",
                       formula="经营活动现金流净额 − 购建固定资产、无形资产和其他长期资产支付的现金", inputs=[ocf, capex],
                       time={"period_end": PERIOD})
    if ratio.value is None:
        spec = ("unknown", "unknown", "经营现金流对净利润的覆盖无法计算", "经营现金流对净利润的覆盖无法计算；请查看输入状态。")
    elif D(ratio.value) >= 1:
        spec = ("fact", "positive", "经营现金流覆盖了同期净利润", "按半年报累计口径，经营活动现金流净额不低于同期净利润。")
    elif D(ratio.value) >= 0:
        spec = ("fact", "mixed", "经营现金流低于同期净利润", "按半年报累计口径，经营现金流低于同期净利润（经营活动现金流净额为正），利润的现金实现程度需要继续核查。")
    else:
        spec = ("fact", "negative", "经营现金流为负而净利润为正", "按半年报累计口径，经营现金流为负而净利润为正。")
    run.conclude("cash_conversion", "f024", *spec, supports=[ratio], context=[ocf, np_, capex, fcf],
                 limitations=["半年累计口径，受季节性营运资本影响", "不能据此判断盈利质量的整体高低或解释差异原因"],
                 highlights=[ratio, ocf, fcf])

    debt, debt_b = (_indicator_evidence(run, SUBJECT, p, "assets_debt_ratio", "assets_debt_ratio", "f028", "资产负债率") for p in (PERIOD, BASE))
    turn, turn_b = (_indicator_evidence(run, SUBJECT, p, "inventory_turnover_ratio", "inventory_turnover", "f030", "存货周转率", "次") for p in (PERIOD, BASE))
    cash = _statement_evidence(run, SUBJECT, PERIOD, "cash", "cash", "f027", "货币资金")
    net_cash, ib_debt = _net_cash(run, cash)
    inv, inv_b = (_official(run, "存货", p, "inventory", "f030", "存货") for p in (PERIOD, BASE))
    inv_change = _pct_change(run, "inventory_change:" + PERIOD, "inventory_change", "f030", "存货较上年同期末变化", inv, inv_b, t)
    if debt.value is not None and debt_b.value is not None:
        change = D(debt.value) - D(debt_b.value)
        spec = (("fact", "positive", "资产负债率较上年同期下降", "资产负债率较上年同期下降；净现金、存货与周转见证据。") if change < 0 else
                ("fact", "negative", "资产负债率较上年同期上升", "资产负债率较上年同期上升；净现金、存货与周转见证据。") if change > 0 else
                ("fact", "neutral", "资产负债率与上年同期持平", "资产负债率与上年同期持平。"))
    else:
        spec = ("unknown", "unknown", "资产负债率变化证据不足", "资产负债率变化证据不足。")
    run.conclude("balance_sheet", "f028", *spec, supports=[debt, debt_b],
                 context=[net_cash, ib_debt, cash, inv, inv_b, inv_change, turn, turn_b],
                 limitations=["存货周转率为半年累计口径，只与上年同期比较",
                              "有息债务按五项借款类科目合计，一年内到期的非流动负债可能含少量非借款项目"],
                 highlights=[debt, net_cash, inv_change, turn])
    return run.finish(question, route)


# --- valuation ---------------------------------------------------------------

def _percentile(values: list[Decimal], current: Decimal) -> Decimal:
    return q(D(sum(1 for value in values if value <= current)) / D(len(values)) * 100, "0.1")


def _band(percentile: Decimal) -> str:
    return "低区间" if percentile <= Decimal("33.3") else "高区间" if percentile >= Decimal("66.7") else "中间区间"


def valuation_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "valuation", run_id)
    cut = snapshot["valuation_cutoff"]
    src = cut["source"]
    t = {"date": cut["date"]}
    specs = {"pe_ttm": ("f034", "市盈率 PE(TTM)", "归母净利润 TTM，基准日为报表公告日期"),
             "pe_mrq": ("f035", "市盈率 PE(MRQ)", "最新一期归母净利润 × 年化系数（半年报 ×2）"),
             "pb_mrq": ("f036", "市净率 PB(MRQ)", "最新一期归母净资产"),
             "ps_ttm": ("f037", "市销率 PS(TTM)", "营业收入 TTM"),
             "pcf_ttm": ("f038", "市现率 PCF(TTM)", "经营活动现金流净额 TTM")}
    items = {}
    for key, (field_id, label, denominator) in specs.items():
        value = D(cut["values"][key])
        items[key] = run.source(
            f"{key}:{SUBJECT}:{cut['date']}", key, field_id, label, value if value > 0 else None, "倍", time=t,
            scope={"subject": SUBJECT, "numerator": "总股本（A+H）× A 股收盘价", "denominator": denominator},
            source={"provider": src["provider"], "endpoint": src["tool"], "field": label,
                    "query_ref": f"{src['raw_file']};{src['query']}"},
            status="valid" if value > 0 else "not_applicable",
            reason=None if value > 0 else "分母为负或为零，估值倍数不适用（决策 0014）")
    series = snapshot["valuation_series"]
    hist = {}
    for key, label, field_id in (("pb", "市净率", "f036"), ("pe_ttm", "市盈率 TTM", "f034")):
        values = [D(point[key]) for _, point in series["points"]]
        series_item = run.source(
            f"valuation_series:{key}", f"{key}_series", "f039", f"{label}逐交易日序列（{len(values)} 个交易日）",
            len(values), "个交易日", time={"start": series["points"][0][0], "end": series["points"][-1][0]},
            scope={"subject": SUBJECT, "filter": f"按扶摇交易日历过滤，剔除非交易日行 {series['dropped_non_trading_rows']} 条"},
            source={"provider": "iFinD", "endpoint": "get_stock_performance", "field": label,
                    "query_ref": "ifind_valuation_YYYY_MM.json（13 个月度请求）"})
        current = D(series["points"][-1][1][key])
        pct = _percentile(values, current) if current > 0 else None
        hist[key] = run.computed(
            f"{key}_percentile:{cut['date']}", f"{key}_percentile", "f039", f"{label}近一年分位", pct, "%",
            formula_id="empirical_percentile_rank", formula="序列中不高于截止日数值的交易日占比 × 100（只在 iFinD 自身序列内计算）",
            inputs=[series_item, items["pb_mrq" if key == "pb" else "pe_ttm"]], time=t,
            summary={"min": str(min(values)), "max": str(max(values)), "median": str(q(D(statistics.median(values)))),
                     "n": len(values)}, reason="截止日倍数不适用，分位不计算")
    pb_pct = hist["pb"]
    if pb_pct.value is not None:
        band = _band(D(pb_pct.value))
        spec = ("fact", "neutral", f"市净率位于自身近一年序列的{band}", f"截止数据日，市净率位于自身近一年序列的{band}（按交易日计）；具体分位、区间高低点见证据。")
    else:
        spec = ("unknown", "unknown", "市净率历史位置无法计算", "市净率历史位置无法计算。")
    run.conclude("history_position", "f039", *spec, supports=[pb_pct], context=[hist["pe_ttm"], items["pe_ttm"], items["pb_mrq"]],
                 limitations=["市盈率 TTM 在半年报公告后切换分母，序列前后不完全可比，故以市净率为主", "分位只说明相对自身历史的位置"],
                 highlights=[items["pb_mrq"], pb_pct, items["pe_ttm"], hist["pe_ttm"]], cannot_say=VALUATION_CANNOT_SAY)

    peer = snapshot["peer_valuation"]
    medians = {}
    for key, label, field_id in (("pe_ttm", "市盈率 TTM", "f040"), ("pb", "市净率", "f040")):
        inputs = []
        for code in snapshot["peer_group"]:
            value = D(peer["values"][code][key])
            inputs.append(run.source(
                f"peer_{key}:{code}:{peer['date']}", f"peer_{key}", "f054", f"{NAMES[code]} {label}",
                value if value > 0 else None, "倍", time={"date": peer["date"]}, scope={"subject": code},
                source={"provider": "iFinD", "endpoint": "get_stock_performance", "field": label,
                        "query_ref": f"{peer['source']['raw_file']}；{peer['note']}"},
                status="valid" if value > 0 else "not_applicable", reason=None if value > 0 else "倍数为负或为零"))
        values = [D(item.value) for item in inputs if item.value is not None]
        medians[key] = run.computed(
            f"peer_median_{key}:{peer['date']}", f"peer_median_{key}", field_id, f"同行{label}中位数",
            q(D(statistics.median(values))) if len(values) == 3 else None, "倍", formula_id="median_of_formal_peers",
            formula="赣锋锂业、中矿资源、永兴材料三家同日数值的中位数（决策 0013 第 5 项）", inputs=inputs, time={"date": peer["date"]})
    own_pe = D(peer["values"][SUBJECT]["pe_ttm"])
    own_pb = D(peer["values"][SUBJECT]["pb"])
    if medians["pe_ttm"].value and medians["pb"].value and own_pe > 0:
        rel = lambda own, med: "低于" if own < D(med) else "高于" if own > D(med) else "等于"
        pe_rel, pb_rel = rel(own_pe, medians["pe_ttm"].value), rel(own_pb, medians["pb"].value)
        anchor = f"市盈率{pe_rel}同行中位数，市净率{pb_rel}同行中位数"
        spec = ("fact", "neutral", anchor, f"同日比较，天齐锂业{anchor}。")
    else:
        spec = ("unknown", "unknown", "同行估值比较证据不足", "同行估值比较证据不足。")
    peer_table = {"columns": [NAMES[code] for code in (SUBJECT, *snapshot["peer_group"])] + ["同行中位数"],
                  "rows": [{"label": label, "cells": [own.id] + [f"peer_{key}:{code}:{peer['date']}" for code in snapshot["peer_group"]]
                            + [medians[key].id]}
                           for label, key, own in (("市盈率 PE(TTM)", "pe_ttm", items["pe_ttm"]), ("市净率 PB", "pb", items["pb_mrq"]))]}
    run.conclude("peer_position", "f040", *spec, supports=[medians["pe_ttm"], medians["pb"], items["pe_ttm"], items["pb_mrq"]],
                 table=peer_table,
                 limitations=["同行组为资源＋锂盐冶炼一体化三家，业务结构仍有差异", "四家估值同源（iFinD），不与其他来源混算"],
                 highlights=[items["pe_ttm"], medians["pe_ttm"], items["pb_mrq"], medians["pb"]], cannot_say=VALUATION_CANNOT_SAY)

    if items["pe_mrq"].value and items["pe_ttm"].value:
        lower = D(items["pe_mrq"].value) < D(items["pe_ttm"].value)
        anchor = "按最近一期年化的市盈率低于滚动市盈率" if lower else "按最近一期年化的市盈率不低于滚动市盈率"
        spec = ("inference", "neutral", anchor,
                f"{anchor}，说明最近一期利润的年化水平{'高于' if lower else '不高于'}过去四个季度合计；年化假设不代表全年实际。")
    else:
        spec = ("unknown", "unknown", "年化市盈率与滚动市盈率无法比较", "年化市盈率与滚动市盈率无法比较。")
    run.conclude("mrq_vs_ttm", "f035", *spec, supports=[items["pe_mrq"], items["pe_ttm"]], context=[items["ps_ttm"], items["pcf_ttm"]],
                 limitations=["半年报年化系数为二，季节性会影响年化结果"], highlights=[items["pe_mrq"], items["ps_ttm"], items["pcf_ttm"]],
                 cannot_say=VALUATION_CANNOT_SAY)
    return run.finish(question, route)


# --- market ------------------------------------------------------------------

def _close(run: Run, code: str, row: dict, field_id: str = "f044") -> Evidence:
    daily = run.snapshot["daily"][code]
    return run.source(f"close:{code}:{row['date']}", "close_forward", field_id, f"{NAMES[code]}前复权收盘价（{row['date']}）",
                      D(row["close"]), "元", time={"date": row["date"]}, scope={"subject": code, "adjust": "forward"},
                      source={"provider": "Fuyao", "endpoint": daily["source"]["endpoint"], "field": "close_price",
                              "query_ref": f"{daily['source']['raw_file']};{daily['source']['query']}"})


def _return(run: Run, code: str, start: dict, end: dict, label: str, field_id: str = "f044") -> Evidence:
    first, last = _close(run, code, start, field_id), _close(run, code, end, field_id)
    return run.computed(f"return:{code}:{start['date']}:{end['date']}", "price_return", field_id, label,
                        q((D(last.value) / D(first.value) - 1) * 100), "%", formula_id="adjusted_close_return",
                        formula="期末前复权收盘价 ÷ 期初前复权收盘价 − 1", inputs=[last, first],
                        time={"start": start["date"], "end": end["date"]}, scope={"subject": code, "adjust": "forward"})


def max_drawdown(closes: list[Decimal]) -> tuple[Decimal, tuple[int, int]]:
    """Largest fall from a running peak: (drawdown ratio ≤ 0, (peak index, trough index)). Shared with the chart."""
    peak, peak_i, worst, worst_pair = closes[0], 0, Decimal(0), (0, 0)
    for i, close in enumerate(closes):
        if close > peak:
            peak, peak_i = close, i
        drawdown = close / peak - 1
        if drawdown < worst:
            worst, worst_pair = drawdown, (peak_i, i)
    return worst, worst_pair


def market_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "market", run_id)
    rows = snapshot["daily"][SUBJECT]["rows"]
    last = rows[-1]
    r_all = _return(run, SUBJECT, rows[0], last, "观察区间涨跌幅（前复权）")
    r60 = _return(run, SUBJECT, rows[-61], last, "近 60 个交易日涨跌幅")
    r20 = _return(run, SUBJECT, rows[-21], last, "近 20 个交易日涨跌幅")
    series = run.source(f"daily_series:{SUBJECT}", "daily_series", "f042", f"前复权日线序列（{len(rows)} 个交易日）",
                        len(rows), "个交易日", time={"start": rows[0]["date"], "end": last["date"]},
                        scope={"subject": SUBJECT, "adjust": "forward"},
                        source={"provider": "Fuyao", "endpoint": "/api/a-share/prices/historical", "field": "open/high/low/close/volume",
                                "query_ref": snapshot["daily"][SUBJECT]["source"]["raw_file"]})
    recent_volume = D(statistics.mean(row["volume"] for row in rows[-20:]))
    volume_ratio = run.computed(f"volume_ratio:{last['date']}", "volume_ratio", "f046", "近 20 日均量 / 区间日均量",
                                q(recent_volume / D(statistics.mean(row["volume"] for row in rows))), "倍",
                                formula_id="volume_vs_window_average", formula="最近 20 个交易日平均成交量 ÷ 观察区间全部交易日平均成交量",
                                inputs=[series], time={"date": last["date"]})
    direction = D(r_all.value)
    spec = ("fact", "positive" if direction > 0 else "negative" if direction < 0 else "neutral",
            "观察区间内前复权股价上涨" if direction > 0 else "观察区间内前复权股价下跌" if direction < 0 else "观察区间内前复权股价持平",
            ("观察区间内前复权股价上涨" if direction > 0 else "观察区间内前复权股价下跌" if direction < 0 else "观察区间内前复权股价持平")
            + "；近二十和近六十个交易日的涨跌幅及量能变化见证据。")
    run.conclude("price_trend", "f044", *spec, supports=[r_all], context=[r60, r20, volume_ratio],
                 limitations=["区间起点为窗口内首个交易日收盘，不含该日涨跌", "历史涨跌不预示未来"],
                 highlights=[r_all, r60, r20, volume_ratio])

    closes = [D(row["close"]) for row in rows]
    worst, worst_pair = max_drawdown(closes)
    high, low = _close(run, SUBJECT, rows[worst_pair[0]], "f045"), _close(run, SUBJECT, rows[worst_pair[1]], "f045")
    mdd = run.computed(f"max_drawdown:{SUBJECT}", "max_drawdown", "f045", "区间最大回撤（前复权）", q(worst * 100), "%",
                       formula_id="max_drawdown_forward_close", formula="逐日计算收盘价相对此前最高收盘价的跌幅，取最小值；输入为回撤起点高点与终点低点",
                       inputs=[low, high], time={"start": rows[0]["date"], "end": last["date"]})
    returns = [float(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    vol = run.computed(f"volatility:{SUBJECT}", "annualized_volatility", "f045", "年化波动率（日收益，前复权）",
                       q(D(statistics.stdev(returns)) * D(len(rows)).sqrt() * 100), "%", formula_id="annualized_daily_volatility",
                       formula="日简单收益率样本标准差 × √交易日数（本窗口二百四十二日）；自算而非采用 iFinD 周频、不复权口径（决策 0016）",
                       inputs=[series], time={"start": rows[0]["date"], "end": last["date"]})
    run.conclude("drawdown_volatility", "f045", "fact", "neutral", "区间最大回撤与年化波动率已按前复权日线计算",
                 "区间最大回撤与年化波动率已按前复权日线计算，高点、低点日期及公式见证据。", supports=[mdd, vol],
                 limitations=["波动与回撤描述历史路径，不是风险预测"], highlights=[mdd, vol])

    sector = snapshot["sector"]
    windows = [w for w in sector["windows"] if w["start"] >= rows[0]["date"]]
    inconsistent = [w["start"][:7] for w in windows if w["weighting"] != "总市值加权平均"]
    window_items = [run.source(f"sector_window:{w['start']}", "sector_window_return", "f049",
                               f"申万有色 {w['start'][:7]} 区间涨跌幅（{w['weighting']}）", D(w["return_pct"]), "%",
                               time={"start": w["start"], "end": w["end"]}, scope={"weighting": w["weighting"]},
                               source={"provider": "iFinD", "endpoint": "sector_data", "field": "成份区间涨跌幅",
                                       "query_ref": f"ifind_sector_{w['start'][:4]}_{w['start'][5:7]}.json"})
                    for w in windows]
    compound = Decimal(1)
    for item in window_items:
        compound *= 1 + D(item.value) / 100
    sector_ret = run.computed(
        "sector_return:window", "sector_return", "f049", "申万有色观察区间涨跌幅（月度复合）", q((compound - 1) * 100), "%",
        formula_id="compound_monthly_window_returns", formula="∏(1 + 月度区间涨跌幅) − 1，要求各月同为总市值加权",
        inputs=window_items, time={"start": windows[0]["start"], "end": windows[-1]["end"]},
        status="conflict" if inconsistent else None,
        reason=f"{'、'.join(inconsistent)} 月度窗口为算术平均加权，与其他月份总市值加权不一致，不能复合" if inconsistent else None)
    relative = run.computed(
        "relative_to_sector:window", "relative_return", "f047", "相对申万有色超额涨跌幅",
        q(D(r_all.value) - D(sector_ret.value)) if sector_ret.value is not None else None, "个百分点",
        formula_id="stock_minus_sector_return", formula="个股观察区间涨跌幅 − 行业月度复合涨跌幅", inputs=[r_all, sector_ret],
        time={"start": rows[0]["date"], "end": last["date"]})
    if relative.value is not None:
        better = D(relative.value) > 0
        spec = ("inference", "positive" if better else "negative",
                "观察区间内股价表现强于申万有色板块" if better else "观察区间内股价表现弱于申万有色板块",
                "观察区间内股价表现" + ("强于" if better else "弱于") + "申万有色板块。")
    else:
        spec = ("unknown", "unknown", "相对行业表现暂不能计算",
                "相对行业表现暂不能计算：行业月度涨跌幅的加权口径不一致，已标为冲突；各月原值可在证据中查看。")
    run.conclude("relative_sector", "f047", *spec, supports=[relative], context=[sector_ret, r_all],
                 limitations=["行业起点与个股起点可能相差一个交易日", "申万有色含多种金属，不是锂行业专属指数"],
                 highlights=[r_all, sector_ret])
    return run.finish(question, route)


# --- industry ----------------------------------------------------------------

PRICE_FIELDS = {"carbonate": "f050", "hydroxide": "f051", "spodumene": "f051", "futures": "f052"}


def _position_word(own: Decimal, others: list[Decimal]) -> str:
    if own > max(others):
        return "最高"
    if own < min(others):
        return "最低"
    median = D(statistics.median(others))
    return "高于同行中位数" if own > median else "低于同行中位数" if own < median else "等于同行中位数"


def industry_run(snapshot: dict, question: str, route: dict, run_id: str) -> DiagnosisRun:
    run = Run(snapshot, "industry", run_id)
    changes = []
    for key, series in snapshot["lithium"].items():
        field_id = PRICE_FIELDS[key]
        points = series["points"]
        ends = []
        for day, value in (points[0], points[-1]):
            ends.append(run.source(f"lithium_{key}:{day}", f"lithium_{key}", field_id, f"{series['label']}（{day}）",
                                   D(value), series["unit"], time={"date": day},
                                   scope={"filter": f"按交易日历过滤，剔除 {series['dropped_non_trading_rows']} 条非交易日行"},
                                   source={"provider": "iFinD", "endpoint": "EDB", "field": series["label"],
                                           "query_ref": f"ifind_{'lithium_' if key in ('carbonate', 'hydroxide', 'futures') else ''}{key}_YYYY_MM.json；{series['source']['query']}"}))
        values = [D(value) for _, value in points]
        changes.append(run.computed(
            f"lithium_{key}_change", f"lithium_{key}_change", field_id, f"{series['label']}观察区间变化",
            q((D(ends[1].value) / D(ends[0].value) - 1) * 100), "%", formula_id="series_endpoint_change",
            formula="期末值 ÷ 期初值 − 1（首末交易日）", inputs=[ends[1], ends[0]],
            time={"start": points[0][0], "end": points[-1][0]},
            summary={"min": str(min(values)), "max": str(max(values)), "n": len(values), "unit": series["unit"]}))
    ups = [D(item.value) > 0 for item in changes]
    if all(ups):
        spec = ("inference", "positive", "观察区间内锂盐、锂精矿现货与期货价格均上涨",
                "观察区间内锂盐、锂精矿现货与期货价格均上涨，行业价格环境较期初改善。")
    elif not any(ups):
        spec = ("inference", "negative", "观察区间内锂盐、锂精矿现货与期货价格均下跌",
                "观察区间内锂盐、锂精矿现货与期货价格均下跌，行业价格环境较期初走弱。")
    else:
        spec = ("inference", "mixed", "观察区间内各类锂价方向不一致", "观察区间内各类锂价方向不一致。")
    run.conclude("lithium_prices", "f050", *spec, supports=changes,
                 limitations=["锂价是行业环境证据，不等于公司实现售价，也不是交易信号（决策 0013 第 4 项）",
                              "公司利润对锂价的敏感性尚未核准"], highlights=changes)

    metrics = (("sale_gross_margin", "销售毛利率", "%"), ("index_weighted_avg_roe", "加权 ROE", "%"),
               ("assets_debt_ratio", "资产负债率", "%"), ("calculate_operating_income_yoy_growth_ratio", "营业收入同比", "%"))
    words, highlights, supports, rows = [], [], [], []
    order = [SUBJECT, *snapshot["peer_group"]]
    for index_id, label, unit in metrics:
        items = {code: _indicator_evidence(run, code, PERIOD, index_id, f"peer_{index_id}", "f053", label, unit)
                 for code in snapshot["names"]}
        if all(item.value is not None for item in items.values()):
            own = D(items[SUBJECT].value)
            others = [D(items[code].value) for code in snapshot["peer_group"]]
            words.append(f"{label}{_position_word(own, others)}")
        supports.extend(items.values())
        highlights.append(items[SUBJECT])
        rows.append({"label": label, "cells": [items[code].id for code in order]})
    if len(words) == len(metrics):
        anchor = "，".join(words[:3])
        spec = ("fact", "neutral", f"与三家同行相比，{anchor}",
                f"与三家同行相比，{anchor}，{'，'.join(words[3:])}（半年报累计口径）。")
    else:
        spec = ("unknown", "unknown", "同行财务比较证据不足", "同行财务比较证据不足。")
    run.conclude("peer_financials", "f053", *spec, supports=supports,
                 table={"columns": [NAMES[code] for code in order], "rows": rows},
                 limitations=["四家指标均取扶摇同一接口、同一报告期，口径一致；ROE 为半年累计未年化",
                              "业务结构与资源自给率不同，排序不代表经营优劣"], highlights=highlights)

    rets = []
    for code in [SUBJECT, *snapshot["peer_group"]]:  # explicit order: canonical JSON sorts the names dict
        rows = snapshot["daily"][code]["rows"]
        rets.append(_return(run, code, rows[0], rows[-1], f"{NAMES[code]}观察区间涨跌幅（前复权）", "f054"))
    own = D(rets[0].value)
    word = _position_word(own, [D(item.value) for item in rets[1:]])
    returns_table = {"columns": [NAMES[code] for code in (SUBJECT, *snapshot["peer_group"])],
                     "rows": [{"label": "观察区间涨跌幅（前复权）", "cells": [item.id for item in rets]}]}
    run.conclude("peer_returns", "f054", "fact", "neutral", f"观察区间股价涨跌幅在四家中{word}",
                 f"天齐锂业观察区间股价涨跌幅在四家中{word}（前复权，同区间）。", supports=rets,
                 limitations=["同区间、同复权口径比较；历史表现不预示未来"], highlights=rets, table=returns_table)
    return run.finish(question, route)


RUNNERS = {"financial_trend": financial_run, "valuation": valuation_run, "market": market_run, "industry": industry_run}


def _runners() -> dict:
    from .dimension_events import events_run  # late imports: these modules build on this one
    from .dimensions_extra import operating_quality_run, risk_run
    return {**RUNNERS, "operating_quality": operating_quality_run, "risk": risk_run, "events": events_run}


def run_dimension(dimension: str, snapshot: dict, question: str, route: dict) -> DiagnosisRun:
    runners = _runners()
    if dimension not in runners:
        raise ValueError(f"dimension is not implemented: {dimension}")
    return runners[dimension](snapshot, question, {**route, "dimension": dimension,
                                                   "dimension_label": DIMENSIONS[dimension],
                                                   "window": WINDOW.copy()}, str(uuid4()))
