from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .catalog import DIMENSIONS, EXECUTABLE_FIELDS
from .dimensions import run_dimension
from .models import DiagnosisRun
from .profit_cash import build_profit_cash_run
from .routing import route_question
from .validator import PROHIBITED_PATTERNS, apply_narrative


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


def _summary_basis(runs: list[DiagnosisRun], route: dict) -> dict:
    items, must_include, pending = [], [], []
    for run in runs:
        label = run.route.get("dimension_label", run.route.get("dimension"))
        known = [c for c in run.conclusions if c.type != "unknown"]
        if known:
            must_include.append(known[0].required_anchor)
        pending += [c.required_anchor for c in run.conclusions if c.type == "unknown"]
        items.append({"dimension": label, "conclusions": [
            {"anchor": c.required_anchor, "type": c.type, "assessment": c.assessment, "priority": c.priority["tier"]}
            for c in run.conclusions]})
    not_covered = [DIMENSIONS[d] for d in route.get("dimensions", []) if d not in route.get("runnable_dimensions", [])]
    basis = {"items": items, "must_include": must_include}
    return {**basis, **({"pending": pending} if pending else {}), **({"not_covered": not_covered} if not_covered else {})}


def fallback_summary(runs: list[DiagnosisRun], basis: dict) -> str:
    parts = []
    for run in runs:
        anchors = [c.required_anchor for c in run.conclusions if c.type != "unknown"]
        if anchors:
            parts.append(f"{run.route.get('dimension_label')}方面，{'，'.join(anchors)}")
    text = ("综合来看：" + "；".join(parts) + "。") if parts else "现有证据不足以形成总体解读。"
    if basis.get("pending"):
        text += f"尚待核实：{'；'.join(basis['pending'])}。"
    if basis.get("not_covered"):
        text += f"{'、'.join(basis['not_covered'])}维度尚未接入，未纳入本解读。"
    return text


def validate_summary(text: object, basis: dict) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return ["empty_text"]
    failures = []
    if len(text) > 320:
        failures.append("too_long")
    if re.search(r"[0-9０-９%％]", text):
        failures.append("numbers_in_prose")
    failures += [f"prohibited:{code}" for code, pattern in PROHIBITED_PATTERNS.items() if re.search(pattern, text)]
    failures += ["missing_anchor" for anchor in basis["must_include"] if anchor not in text][:1]
    return failures


def summarize(runs: list[DiagnosisRun], route: dict, llm=None) -> dict:
    """Overall reading placed before the cards: LLM prose checked against program anchors, else fallback."""
    basis = _summary_basis(runs, route)
    fallback = fallback_summary(runs, basis)
    if llm is None:
        return {"text": fallback, "validation": "fallback", "validation_failures": []}
    try:
        candidate = llm.summarize(basis)
    except Exception:
        return {"text": fallback, "validation": "fallback", "validation_failures": ["llm_unavailable"]}
    failures = validate_summary(candidate, basis)
    return {"text": candidate.strip() if not failures else fallback,
            "validation": "passed" if not failures else "fallback", "validation_failures": failures}


def diagnose_dimensions(question: str, route: dict, snapshot_provider: Callable[[], dict],
                        llm=None) -> tuple[list[DiagnosisRun], dict | None]:
    dimensions = route.get("runnable_dimensions") or []
    if not dimensions:
        return [], None
    snapshot = snapshot_provider()
    base_route = {"intent": route["intent"], "dimensions": route["dimensions"], "method": route["method"],
                  "catalog_version": route["config_version"], "execution_status": route["execution_status"],
                  "snapshot": {"id": snapshot["snapshot_id"], "created_at": snapshot["created_at"], "status": "fixed"}}
    runs = [run_dimension(dimension, snapshot, question, base_route) for dimension in dimensions]
    if llm is None:
        return runs, summarize(runs, route)
    # Conclusions are fixed before any LLM call, so the summary runs alongside the narrations.
    with ThreadPoolExecutor(max_workers=len(runs) + 1) as pool:
        summary_future = pool.submit(summarize, runs, route, llm)
        runs = list(pool.map(lambda run: _narrate(run, llm), runs))
        summary = summary_future.result()
    return runs, summary
