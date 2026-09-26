from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .catalog import EXECUTABLE_FIELDS
from .dimensions import run_dimension
from .models import DiagnosisRun
from .profit_cash import build_profit_cash_run
from .routing import route_question
from .validator import apply_narrative


def diagnose_profit_cash(question: str, data_provider: Callable[[], dict], llm=None,
                         *, route: dict | None = None) -> DiagnosisRun | dict:
    route = route if route is not None else route_question(question, llm)
    if route["execution_status"] == "unsupported" or route["intent"] not in EXECUTABLE_FIELDS:
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


def _narrate(run: DiagnosisRun, llm) -> DiagnosisRun:
    """One constrained LLM call per dimension; each conclusion is validated separately."""
    try:
        items = llm.translate_many(run.conclusions, run.evidence)
    except Exception:
        items = None
    by_id = {item.get("id"): item for item in items or [] if isinstance(item, dict)}
    for index, conclusion in enumerate(run.conclusions):
        candidate = by_id.get(conclusion.id)
        if candidate is None:
            conclusion.validation_failures = ["llm_unavailable" if items is None else "llm_missing_item"]
            continue
        apply_narrative(run, candidate, index)
    return run


def diagnose_dimensions(question: str, route: dict, snapshot_provider: Callable[[], dict], llm=None) -> list[DiagnosisRun]:
    dimensions = route.get("runnable_dimensions") or []
    if not dimensions:
        return []
    snapshot = snapshot_provider()
    base_route = {"intent": route["intent"], "dimensions": route["dimensions"], "method": route["method"],
                  "catalog_version": route["config_version"], "execution_status": route["execution_status"],
                  "snapshot": {"id": snapshot["snapshot_id"], "created_at": snapshot["created_at"], "status": "fixed"}}
    runs = [run_dimension(dimension, snapshot, question, base_route) for dimension in dimensions]
    if llm is not None:
        with ThreadPoolExecutor(max_workers=len(runs)) as pool:
            runs = list(pool.map(lambda run: _narrate(run, llm), runs))
    return runs
