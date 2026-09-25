from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from .models import CannotSay, Conclusion, DiagnosisRun, Evidence, validate_run

SUBJECT = "002466.SZ"
CONFIG_VERSION = "profit-cash-v1"

CANNOT_SAY = [
    CannotSay("NO_TRADE_ADVICE", "不能给出买卖、仓位或收益建议", "诊断不是投资建议"),
    CannotSay("NO_PRICE_PREDICTION", "不能据此预测股价必然涨跌", "财报字段不支持价格预测"),
    CannotSay("NO_FRAUD_INFERENCE", "不能仅凭背离断言财务造假", "背离只是进一步研究的信号"),
    CannotSay("NO_PROFIT_QUALITY_CERTAINTY", "不能仅凭两个字段断定整体盈利质量", "还需核对营运资本、非经常性损益等"),
    CannotSay("NO_UNSUPPORTED_CAUSALITY", "不能在没有补充证据时解释背离的具体原因", "两个字段只表明方向"),
    CannotSay("NO_LIVE_DATA", "不能把固定快照称为实时、最新或今天的数据", "考试产品只展示固定快照"),
]

CLAIMS = {
    "profit_positive_cash_negative": ("inference", "mixed", "净利润为正而经营活动现金流净额为负",
        "同一报告期内，净利润为正而经营活动现金流净额为负，两项指标方向背离。需要继续核查应收、存货和其他现金流项目。"),
    "profit_negative_cash_positive": ("inference", "mixed", "净利润为负而经营活动现金流净额为正",
        "同一报告期内，净利润为负而经营活动现金流净额为正，两项指标方向背离。原因仍需结合财报附注核查。"),
    "both_positive": ("fact", "positive", "净利润和经营活动现金流净额均为正",
        "同一报告期内，净利润和经营活动现金流净额均为正。这只说明两项数值的方向，尚不足以判断整体盈利质量。"),
    "both_negative": ("fact", "negative", "净利润和经营活动现金流净额均为负",
        "同一报告期内，净利润和经营活动现金流净额均为负。需要结合具体经营与投资活动继续研究。"),
    "insufficient_evidence": ("unknown", "unknown", "证据不足",
        "此快照的证据不足以比较净利润与经营活动现金流；请查看缺失原因或口径差异。"),
}


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _source(metric: str, field: str, row: dict | None, fetched_at: str) -> Evidence:
    row = row or {}
    supplied_status = row.get("status", "missing")
    number = _decimal(row.get("value")) if supplied_status == "valid" else None
    status = "missing" if supplied_status == "valid" and number is None else supplied_status
    period_end = row.get("period_end")
    endpoint = row.get("endpoint") or (
        "/api/a-share/financials/income-statements" if metric == "net_profit"
        else "/api/a-share/financials/cash-flow-statements"
    )
    return Evidence(
        id=f"{metric}:{period_end or 'unknown'}", metric_id=metric, subject=SUBJECT, kind="source",
        value=str(number) if status == "valid" else None, unit=row.get("unit"),
        time={"period_end": period_end, "fetched_at": fetched_at},
        scope={"period_basis": row.get("period_basis", "unverified"),
               "consolidation": row.get("consolidation", "consolidated")},
        source={"provider": "Fuyao", "endpoint": endpoint, "field": field,
                "query_ref": row.get("query_ref", f"{SUBJECT};period=annual;limit=4")},
        quality={"status": status,
                 **({"reason": row.get("reason") or ("字段值缺失或不是有限数字" if status != supplied_status
                    else "源字段为空或不可用")} if status != "valid" else {})},
    )


def build_profit_cash_run(question: str, net_profit: dict | None, operating_cash_flow: dict | None,
                          *, fetched_at: str | None = None, created_at: str | None = None,
                          run_id: str | None = None) -> DiagnosisRun:
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    run_id = run_id or str(uuid4())
    profit = _source("net_profit", "net_profit", net_profit, fetched_at)
    cash = _source("operating_cash_flow", "act_cash_flow_net", operating_cash_flow, fetched_at)
    profit_number, cash_number = _decimal(profit.value), _decimal(cash.value)
    aligned = bool(profit.time["period_end"]) and profit.time["period_end"] == cash.time["period_end"] \
        and profit.scope == cash.scope and profit.scope["period_basis"] in ("annual", "cumulative", "single_quarter") \
        and profit.unit is not None and profit.unit == cash.unit
    usable = aligned and profit_number is not None and cash_number is not None
    ratio_value = (cash_number / profit_number).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) \
        if usable and profit_number > 0 else None
    ratio = Evidence(
        id=f"cash_to_profit_ratio:{profit.time['period_end'] or 'unknown'}", metric_id="cash_to_profit_ratio",
        subject=SUBJECT, kind="computed", value=str(ratio_value) if ratio_value is not None else None,
        unit="ratio", time={"period_end": profit.time["period_end"] if aligned else None, "fetched_at": fetched_at},
        scope=profit.scope.copy(),
        calculation={"formula_id": "operating_cash_flow_div_net_profit", "formula_version": "1",
                     "input_evidence_ids": [cash.id, profit.id]},
        quality={"status": "valid" if ratio_value is not None else "not_applicable" if usable else "missing",
                 **({"reason": "输入缺失、无效或报告期及口径未对齐"} if not usable else
                    {"reason": "净利润不大于零，普通比值不适用"} if ratio_value is None else {})},
    )
    claim_code = "insufficient_evidence"
    if usable:
        if profit_number > 0 and cash_number < 0:
            claim_code = "profit_positive_cash_negative"
        elif profit_number < 0 and cash_number > 0:
            claim_code = "profit_negative_cash_positive"
        elif profit_number > 0 and cash_number > 0:
            claim_code = "both_positive"
        elif profit_number < 0 and cash_number < 0:
            claim_code = "both_negative"
    claim_type, assessment, anchor, fallback = CLAIMS[claim_code]
    conclusion = Conclusion(
        id=f"profit_cash:{run_id}", dimension="financial_trend", claim_code=claim_code,
        type=claim_type, assessment=assessment,
        evidence_links=[{"evidence_id": item.id, "role": "supports" if item.kind == "source" and item.quality["status"] == "valid" else "context"}
                        for item in (profit, cash, ratio)],
        limitations=["仅比较同一期、同一累计/单季及合并口径的两个指标", "仅代表固定快照，不代表实时状态", "背离不能直接说明原因或财务造假"]
                    + (["当前输入缺失、无效或口径未对齐"] if not usable else []),
        cannot_say=CANNOT_SAY.copy(), required_anchor=anchor, fallback_text=fallback, text=fallback,
    )
    run = DiagnosisRun(
        id=run_id, subject=SUBJECT, question=question,
        route={"intent": "profit_cash_alignment", "dimensions": ["financial_trend", "risk"]},
        config_version=CONFIG_VERSION, created_at=created_at or datetime.now(timezone.utc).isoformat(),
        evidence=[profit, cash, ratio], conclusions=[conclusion],
    )
    return validate_run(run)
