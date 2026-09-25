from __future__ import annotations

import re

from .models import Conclusion, DiagnosisRun, Evidence

PROHIBITED_PATTERNS = {
    "NO_TRADE_ADVICE": r"买入|卖出|加仓|减仓|清仓|抄底|建仓|持仓建议|建议.{0,5}(?:买|卖|投资)",
    "NO_PRICE_PREDICTION": r"必然上涨|必然下跌|一定上涨|一定下跌|保证收益|稳赚|目标价位|股价将会",
    "NO_FRAUD_INFERENCE": r"财务造假|利润造假|虚增利润|假利润",
    "NO_PROFIT_QUALITY_CERTAINTY": r"(?:盈利|利润)质量.{0,4}(?:确定|证明|完全|没有问题)",
    "NO_UNSUPPORTED_CAUSALITY": r"导致|造成|因为|归因于|源于|主要原因是",
    "NO_LIVE_DATA": r"实时|最新|今天|刚刚|当前行情|截至目前|当下",
}


def validate_narrative(candidate: dict, conclusion: Conclusion, evidence: list[Evidence]) -> list[str]:
    failures: list[str] = []
    text = candidate.get("text") if isinstance(candidate, dict) else None
    cited = candidate.get("evidence_ids") if isinstance(candidate, dict) else None
    if not isinstance(text, str) or not text.strip():
        failures.append("empty_text")
        text = ""
    if not isinstance(cited, list) or any(not isinstance(item, str) for item in cited):
        failures.append("missing_evidence_ids")
        cited = []
    linked = {link["evidence_id"] for link in conclusion.evidence_links}
    if len(cited) != len(set(cited)) or any(item not in linked for item in cited):
        failures.append("invalid_evidence_ids")
    evidence_by_id = {item.id: item for item in evidence}
    required = {
        link["evidence_id"] for link in conclusion.evidence_links
        if link["role"] == "supports" or
        (conclusion.type == "unknown" and evidence_by_id[link["evidence_id"]].kind == "source")
    }
    if not required.issubset(cited):
        failures.append("missing_supporting_citation")
    if re.search(r"[0-9０-９%％]", text):
        failures.append("numbers_in_prose")
    if conclusion.required_anchor not in text:
        failures.append("missing_required_anchor")
    for rule in conclusion.cannot_say:
        pattern = PROHIBITED_PATTERNS.get(rule.code)
        if pattern is None:
            failures.append(f"unknown_prohibition:{rule.code}")
        elif re.search(pattern, text):
            failures.append(f"prohibited:{rule.code}")
    if conclusion.type == "unknown" and re.search(r"正常|安全|没有风险|匹配良好|质量较好", text):
        failures.append("unsupported_positive_claim")
    return failures


def apply_narrative(run: DiagnosisRun, candidate: dict) -> DiagnosisRun:
    conclusion = run.conclusions[0]
    failures = validate_narrative(candidate, conclusion, run.evidence)
    conclusion.text = candidate["text"].strip() if not failures else conclusion.fallback_text
    conclusion.validation = "passed" if not failures else "fallback"
    conclusion.validation_failures = failures
    return run
