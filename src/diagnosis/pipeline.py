from __future__ import annotations

from collections.abc import Callable

from .models import DiagnosisRun
from .profit_cash import build_profit_cash_run
from .validator import apply_narrative


def _fallback_intent(question: str) -> str:
    return "profit_cash_alignment" if any(word in question for word in ("利润", "盈利")) and \
        any(word in question for word in ("现金流", "经营现金")) else "unsupported"


def diagnose_profit_cash(question: str, data_provider: Callable[[], dict], llm=None) -> DiagnosisRun | dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    intent, route_method = _fallback_intent(question), "deterministic_fallback"
    if llm is not None:
        try:
            proposed = llm.classify(question)
            if proposed in ("profit_cash_alignment", "unsupported"):
                intent, route_method = proposed, "llm_allowlisted"
        except Exception:
            pass
    if intent != "profit_cash_alignment":
        return {"status": "unsupported_question", "question": question, "supported_intent": "profit_cash_alignment"}
    inputs = data_provider().copy()
    snapshot = inputs.pop("_snapshot", None)
    run = build_profit_cash_run(question, **inputs)
    run.route["method"] = route_method
    if snapshot is not None:
        run.route["snapshot"] = snapshot
    if llm is not None:
        try:
            apply_narrative(run, llm.translate(run.conclusions[0], run.evidence))
        except Exception:
            run.conclusions[0].validation_failures = ["llm_unavailable"]
    return run
