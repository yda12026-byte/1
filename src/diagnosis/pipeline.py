from __future__ import annotations

from collections.abc import Callable

from .models import DiagnosisRun
from .profit_cash import build_profit_cash_run
from .routing import route_question
from .validator import apply_narrative


def diagnose_profit_cash(question: str, data_provider: Callable[[], dict], llm=None,
                         *, route: dict | None = None) -> DiagnosisRun | dict:
    route = route if route is not None else route_question(question, llm)
    if route["execution_status"] != "implemented":
        return {"status": "unsupported_question" if route["execution_status"] == "unsupported" else "not_implemented",
                "question": question, "supported_intents": ["profit_cash_alignment", "net_profit_status",
                                                            "operating_cash_flow_status", "profit_cash_ratio"], "route": route}
    inputs = data_provider().copy()
    snapshot = inputs.pop("_snapshot", None)
    run = build_profit_cash_run(question, **inputs, intent=route["intent"])
    run.route.update({"method": route["method"], "catalog_version": route["config_version"],
                      "field_ids": route["field_ids"], "display_plan": route["display_plan"],
                      "execution_status": "implemented"})
    if snapshot is not None:
        run.route["snapshot"] = snapshot
    if llm is not None:
        try:
            apply_narrative(run, llm.translate(run.conclusions[0], run.evidence))
        except Exception:
            run.conclusions[0].validation_failures = ["llm_unavailable"]
    return run
