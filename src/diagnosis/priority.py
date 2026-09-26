"""Company-specific editorial display priority, separate from evidence quality."""

from __future__ import annotations

import json
from pathlib import Path

from .catalog import DIMENSIONS, EXECUTABLE_FIELDS, SUBJECT, load_catalog

PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "priority_profile_002466.json"
PROFILE_VERSION = "002466-priority-v2"
TIERS = ("driver", "support", "context", "low")


def priority_for_field(field_id: str) -> dict:
    """Capture the company profile assignment in an evidence or conclusion."""
    profile = load_priority_profile()
    if field_id not in profile["fields"]:
        raise ValueError(f"unknown priority field: {field_id}")
    tier, reason = profile["fields"][field_id]
    return {"field_id": field_id, "tier": tier, "reason": reason,
            "profile_version": PROFILE_VERSION}


def load_priority_profile() -> dict:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if profile.get("version") != PROFILE_VERSION or profile.get("subject") != SUBJECT:
        raise ValueError("priority profile version or subject mismatch")
    catalog = {field["id"]: field for field in load_catalog()}
    assignments = profile.get("fields")
    if not isinstance(assignments, dict) or set(assignments) != set(catalog):
        raise ValueError("priority profile must assign every catalog field exactly once")
    tiers = profile.get("tier_order")
    if tiers != ["driver", "support", "context", "low"]:
        raise ValueError("priority tier order is invalid")
    for field_id, assignment in assignments.items():
        if not isinstance(assignment, list) or len(assignment) != 2 or assignment[0] not in tiers or \
                not isinstance(assignment[1], str) or not assignment[1].strip():
            raise ValueError(f"priority assignment invalid: {field_id}")
    if set(profile.get("dimension_order", [])) != set(DIMENSIONS):
        raise ValueError("priority dimension order is incomplete")
    quotas = profile.get("overview_quotas", {})
    limits = profile.get("display_limits", {})
    if set(quotas) != set(DIMENSIONS) or any(not isinstance(value, int) or value < 1 for value in quotas.values()) or \
            sum(quotas.values()) != limits.get("overview") or \
            any(not isinstance(value, int) or value < len(DIMENSIONS) for key, value in limits.items() if key != "single_dimension") or \
            not isinstance(limits.get("single_dimension"), int) or limits["single_dimension"] < 1:
        raise ValueError("priority display limits are invalid")
    spotlight = profile.get("spotlight_order", {})
    if set(spotlight) != set(DIMENSIONS):
        raise ValueError("priority spotlight dimensions are incomplete")
    for dimension, ids in spotlight.items():
        if len(ids) != len(set(ids)) or any(field_id not in catalog or catalog[field_id]["dimension"] != dimension
                                         for field_id in ids):
            raise ValueError(f"invalid spotlight order: {dimension}")
    focus = profile.get("focus_terms", {})
    if any(field_id not in catalog or not isinstance(terms, list) or not terms for field_id, terms in focus.items()):
        raise ValueError("invalid question focus terms")
    return profile


def _rank(field: dict, profile: dict, focused: set[str]) -> tuple[int, int, int, str]:
    tier = profile["fields"][field["id"]][0]
    spotlight = profile["spotlight_order"][field["dimension"]]
    return (0 if field["id"] in focused else 1,
            profile["tier_order"].index(tier),
            spotlight.index(field["id"]) if field["id"] in spotlight else len(spotlight),
            field["id"])


def make_display_plan(intent: str, dimensions: tuple[str, ...], fields: list[dict], question: str) -> dict:
    profile = load_priority_profile()
    available = {field["id"] for field in fields}
    focused = {field_id for field_id, terms in profile["focus_terms"].items()
               if field_id in available and any(term.casefold() in question.casefold() for term in terms)}
    if intent in EXECUTABLE_FIELDS:
        picked = [field_id for field_id in EXECUTABLE_FIELDS[intent] if field_id in available]
        budget, rule = len(picked), "executable_route_requires_all_inputs"
    elif intent == "unsupported":
        picked, budget, rule = [], 0, "unsupported_question"
    elif intent == "overview":
        budget, rule = profile["display_limits"]["overview"], "company_profile_dimension_quotas"
        picked = []
        for dimension in profile["dimension_order"]:
            candidates = sorted((field for field in fields if field["dimension"] == dimension),
                                key=lambda field: _rank(field, profile, focused))
            picked.extend(field["id"] for field in candidates[:profile["overview_quotas"][dimension]])
    elif len(dimensions) == 1:
        budget, rule = profile["display_limits"]["single_dimension"], "company_profile_priority"
        picked = [field["id"] for field in sorted(fields, key=lambda field: _rank(field, profile, focused))[:budget]]
    else:
        budget, rule = profile["display_limits"]["multi_dimension"], "balanced_company_profile_priority"
        ordered_dimensions = [dimension for dimension in profile["dimension_order"] if dimension in dimensions]
        queues = {dimension: sorted((field for field in fields if field["dimension"] == dimension),
                                    key=lambda field: _rank(field, profile, focused))
                  for dimension in ordered_dimensions}
        picked = []
        while len(picked) < budget and any(queues.values()):
            for dimension in ordered_dimensions:
                if queues[dimension] and len(picked) < budget:
                    picked.append(queues[dimension].pop(0)["id"])
    chosen = set(picked)
    return {
        "profile_version": PROFILE_VERSION,
        "business_profile": profile["business_profile"],
        "budget": budget,
        "selection_rule": rule,
        "focus_field_ids": [field_id for field_id in picked if field_id in focused],
        "default_field_ids": picked,
        "drilldown_field_ids": [field["id"] for field in fields if field["id"] not in chosen],
        "note": "展示优先级不是投资评分；候选可用性与运行时证据质量须分别校验。",
    }
