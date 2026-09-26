"""Expand an allowlisted question intent into inspectable field requirements."""

from __future__ import annotations

import re

from .catalog import (CATALOG_VERSION, COVERED_YEARS, DIMENSION_EXECUTABLE, EXECUTABLE_FIELDS, IMPLEMENTED_FIELD_IDS,
                      INTENTS, SUBJECT, WINDOW, load_catalog)
from .priority import load_priority_profile, make_display_plan

KEYWORDS = {
    "operating_quality": ("经营", "主营", "业务", "毛利", "产能", "研发", "营收"),
    "financial_trend": ("财务", "利润", "盈利", "现金流", "收入", "营收", "ROE", "资产负债"),
    "valuation": ("估值", "市盈率", "市净率", "PE", "PB", "贵吗", "便宜吗"),
    "market": ("行情", "股价", "涨跌", "成交", "波动", "回撤", "走势"),
    "industry": ("行业", "同行", "锂价", "碳酸锂", "氢氧化锂", "锂精矿", "竞争"),
    "events": ("公告", "事件", "分红", "并购", "解禁", "质押", "新闻", "业绩预告", "定期报告", "诉讼", "担保", "回购",
               "套期保值", "扩产", "投产", "火情", "利润分配"),
    "risk": ("风险", "偿债", "减值", "债务", "敞口"),
}
OVERVIEW_WORDS = ("诊断", "分析", "怎么样", "整体", "全面", "现状")
# Out-of-scope requests are answered with a reason and suggested questions, never with advice.
OUT_OF_SCOPE = {
    "买卖或持仓建议": ("买入", "卖出", "该买吗", "该卖吗", "值得买", "能买吗", "要不要买", "应该买", "推荐买",
                  "该不该买", "持有吗", "抄底", "仓位", "加仓", "减仓", "清仓"),
    "股价涨跌预测": ("目标价", "会涨吗", "会跌吗", "能涨", "会不会涨", "会不会跌", "涨到多少", "跌到多少",
                "预测股价", "股价预测", "未来股价", "上涨空间", "下跌空间"),
    "收益承诺": ("保证收益", "稳赚", "能赚多少"),
}
ADVICE_WORDS = tuple(word for words in OUT_OF_SCOPE.values() for word in words)
LITHIUM_WORDS = ("锂价", "碳酸锂", "氢氧化锂", "锂精矿")
STOCK_MARKET_WORDS = ("股价", "行情", "成交", "回撤")


def out_of_scope_categories(question: str) -> list[str]:
    return [category for category, words in OUT_OF_SCOPE.items() if any(word in question for word in words)]
PROFIT_WORDS = ("利润", "盈利", "亏损")
CASH_WORDS = ("经营现金流", "经营活动现金流", "经营现金")
RATIO_WORDS = ("比值", "比例", "比率", "倍数", "覆盖利润", "现金含量")
TIME_SERIES_WORDS = ("同比", "环比", "趋势", "变化", "增长", "连续", "去年", "今年", "过去", "近一年",
                     "近几年", "季度", "历史", "未来", "预测", "上个月", "月度")
MAGNITUDE_COMPARISON_WORDS = ("哪个高", "谁更高", "高多少", "差多少", "相差", "差额", "多于", "少于")
EXTRA_NARROW_KEYWORDS = {
    "operating_quality": ("主营", "业务", "毛利", "产能", "研发", "营收"),
    "valuation": KEYWORDS["valuation"],
    "market": KEYWORDS["market"],
    "industry": KEYWORDS["industry"],
    "events": KEYWORDS["events"],
    "risk": KEYWORDS["risk"],
}


def _has_profit(question: str) -> bool:
    return any(word in question for word in PROFIT_WORDS)


def _has_cash(question: str) -> bool:
    return any(word in question for word in CASH_WORDS)


def _narrow_intent_is_supported(intent: str, question: str) -> bool:
    if intent in EXECUTABLE_FIELDS and (any(word in question for word in TIME_SERIES_WORDS) or re.search(r"20\d{2}", question)):
        return False
    if intent in ("profit_cash_alignment", "profit_cash_ratio") and any(word in question for word in MAGNITUDE_COMPARISON_WORDS):
        return False
    if intent == "profit_cash_alignment":
        return _has_profit(question) and _has_cash(question)
    if intent == "profit_cash_ratio":
        return _has_profit(question) and _has_cash(question) and any(word in question for word in RATIO_WORDS)
    if intent == "net_profit_status":
        return any(word in question for word in ("净利润", "净亏损")) and not _has_cash(question)
    if intent == "operating_cash_flow_status":
        return _has_cash(question) and not _has_profit(question)
    return True


def _fallback(question: str) -> tuple[str, tuple[str, ...]]:
    if any(word in question for word in ADVICE_WORDS):
        return "unsupported", ()
    if _has_profit(question) or _has_cash(question):
        extras = tuple(dimension for dimension, words in EXTRA_NARROW_KEYWORDS.items()
                       if any(word in question for word in words) and
                       (dimension != "risk" or not (_has_profit(question) and _has_cash(question))))
        if extras:
            return "multi_dimension", tuple(dict.fromkeys(("financial_trend", *extras)))
    if _narrow_intent_is_supported("profit_cash_ratio", question):
        return "profit_cash_ratio", INTENTS["profit_cash_ratio"]
    if _narrow_intent_is_supported("profit_cash_alignment", question):
        return "profit_cash_alignment", INTENTS["profit_cash_alignment"]
    if _narrow_intent_is_supported("net_profit_status", question):
        return "net_profit_status", INTENTS["net_profit_status"]
    if _narrow_intent_is_supported("operating_cash_flow_status", question):
        return "operating_cash_flow_status", INTENTS["operating_cash_flow_status"]
    # "经营现金流" is a financial item; its "经营" must not also select operating quality.
    scan = re.sub(r"经营(?:活动)?现金", "现金", question)
    dimensions = tuple(dimension for dimension, words in KEYWORDS.items() if any(word in scan for word in words))
    # "锂价走势/涨跌" is about lithium prices (industry), not the stock, unless the stock is named explicitly.
    if "market" in dimensions and any(word in question for word in LITHIUM_WORDS) and \
            not any(word in question for word in STOCK_MARKET_WORDS):
        dimensions = tuple(dimension for dimension in dimensions if dimension != "market")
    if len(dimensions) > 1:
        return "multi_dimension", dimensions
    if dimensions:
        return dimensions[0], dimensions
    if any(word in question for word in OVERVIEW_WORDS):
        return "overview", INTENTS["overview"]
    return "unsupported", ()


def _execution_status(intent: str, dimensions: tuple[str, ...], question: str) -> str:
    if intent == "unsupported":
        return "unsupported"
    if intent in EXECUTABLE_FIELDS:
        return "implemented"
    # A named year outside the snapshot's report periods must not be answered with other periods.
    if any(year not in COVERED_YEARS for year in re.findall(r"(20\d{2})\s*年", question)):
        return "planned"
    runnable = [dimension for dimension in dimensions if dimension in DIMENSION_EXECUTABLE]
    if not runnable:
        return "planned"
    return "implemented" if len(runnable) == len(dimensions) else "partial"


def route_question(question: str, llm=None) -> dict:
    """Plan a route without reading data or making a financial conclusion."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    question = question.strip()
    intent, dimensions = _fallback(question)
    method = "deterministic_fallback"
    # A multi-dimensional question retains all matching dimensions. An LLM
    # may choose only from the fixed single-intent list for other questions.
    # An executable rule match is final: the LLM could only confirm it.
    if llm is not None and intent != "multi_dimension" and intent not in EXECUTABLE_FIELDS and \
            not any(word in question for word in ADVICE_WORDS):
        try:
            proposed = llm.classify(question)
            allowed = proposed in INTENTS or proposed == "unsupported"
            compatible = (proposed == intent or intent in ("unsupported", "overview")) and \
                _narrow_intent_is_supported(proposed, question)
            if allowed and compatible:
                intent = proposed
                dimensions = INTENTS.get(proposed, ())
                method = "llm_allowlisted"
        except Exception:
            pass
    catalog = load_catalog()
    selected = [field for field in catalog if field["id"] in EXECUTABLE_FIELDS[intent]] if intent in EXECUTABLE_FIELDS else [
        field for field in catalog if field["dimension"] in dimensions
    ]
    selected_ids = {field["id"] for field in selected}
    if intent in EXECUTABLE_FIELDS and selected_ids != set(EXECUTABLE_FIELDS[intent]):
        raise ValueError(f"executable route is incomplete: {intent}")
    profile = load_priority_profile()
    display_plan = make_display_plan(intent, dimensions, selected, question)
    display_ids = set(display_plan["default_field_ids"])
    fields_with_priority = [
        {**field, "priority_tier": profile["fields"][field["id"]][0],
         "priority_reason": profile["fields"][field["id"]][1],
         "default_display": field["id"] in display_ids}
        for field in selected
    ]
    return {
        "subject": SUBJECT,
        "question": question,
        "intent": intent,
        "dimensions": list(dimensions),
        "method": method,
        "config_version": CATALOG_VERSION,
        "window": WINDOW.copy(),
        "execution_status": _execution_status(intent, dimensions, question),
        "runnable_dimensions": [] if intent in EXECUTABLE_FIELDS else
                               [dimension for dimension in dimensions if dimension in DIMENSION_EXECUTABLE]
                               if _execution_status(intent, dimensions, question) != "planned" else [],
        "fields": fields_with_priority,
        "field_ids": [field["id"] for field in selected],
        "display_plan": display_plan,
        "out_of_scope": out_of_scope_categories(question),
        "implemented_field_ids": [field["id"] for field in selected if field["id"] in IMPLEMENTED_FIELD_IDS],
        "pending_field_ids": [field["id"] for field in selected if field["id"] not in IMPLEMENTED_FIELD_IDS],
    }
