"""Fixed question routes and the 72-field candidate catalog.

The catalog is a plan, not evidence. Only an actual Evidence object from a
published snapshot can support a Conclusion.
"""

from __future__ import annotations

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "diagnosis_fields.json"
CATALOG_VERSION = "002466-route-v2"
SUBJECT = "002466.SZ"
WINDOW = {"start": "2025-08-31", "end": "2026-08-31", "cutoff": "2026-08-31"}

DIMENSIONS = {
    "operating_quality": "经营质量",
    "financial_trend": "财务趋势",
    "valuation": "估值",
    "market": "行情特征",
    "industry": "行业位置",
    "events": "重要事件",
    "risk": "风险",
}

DIMENSION_INTENTS = {dimension: (dimension,) for dimension in DIMENSIONS}
INTENTS = {
    "overview": tuple(DIMENSIONS),
    "profit_cash_alignment": ("financial_trend", "risk"),
    "net_profit_status": ("financial_trend",),
    "operating_cash_flow_status": ("financial_trend",),
    "profit_cash_ratio": ("financial_trend",),
    **DIMENSION_INTENTS,
}

SPECIAL_FIELD_IDS = ("f021", "f022", "f024", "f066")
EXECUTABLE_FIELDS = {
    "profit_cash_alignment": SPECIAL_FIELD_IDS,
    "net_profit_status": ("f021",),
    "operating_cash_flow_status": ("f022",),
    "profit_cash_ratio": ("f021", "f022", "f024"),
}
# Dimensions answered from the fixed product snapshot (decision 0016).
# Events need the official announcement block (decision 0022); older snapshots fall back to clues at run time.
DIMENSION_EXECUTABLE = ("operating_quality", "financial_trend", "valuation", "market", "industry", "risk", "events")
DIMENSION_FIELD_IDS = ("f004", "f012", "f013", "f014", "f016", "f018", "f019", "f025", "f026", "f027", "f028", "f030",
                       "f034", "f035", "f036", "f037", "f038", "f039", "f040", "f042", "f044", "f045", "f046", "f047",
                       "f049", "f050", "f051", "f052", "f053", "f054", "f055", "f056", "f057", "f058", "f059", "f063", "f065", "f069",
                       "f072")
COVERED_YEARS = ("2025", "2026")
IMPLEMENTED_FIELD_IDS = frozenset(SPECIAL_FIELD_IDS + DIMENSION_FIELD_IDS)
IMPLEMENTED_LABELS = {
    "f021": "净利润", "f022": "经营活动现金流净额",
    "f024": "经营现金流 / 净利润", "f066": "利润与经营现金流背离",
}


def load_catalog() -> tuple[dict, ...]:
    document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if document.get("version") != CATALOG_VERSION or document.get("subject") != SUBJECT:
        raise ValueError("field catalog version or subject mismatch")
    fields = document.get("fields")
    if not isinstance(fields, list) or len(fields) != 72:
        raise ValueError("field catalog must contain all 72 candidates")
    ids = [field["id"] for field in fields]
    if len(set(ids)) != len(ids) or ids != [f"f{n:03d}" for n in range(1, 73)]:
        raise ValueError("field catalog IDs must be unique and stable")
    valid_statuses = {"已取值", "可计算", "部分可用", "待核", "当前未取得"}
    for field in fields:
        if field["id"] in IMPLEMENTED_LABELS and field["label"] != IMPLEMENTED_LABELS[field["id"]]:
            raise ValueError(f"implemented field ID moved: {field['id']}")
        if field["dimension"] not in DIMENSIONS or field["candidate_status"] not in valid_statuses:
            raise ValueError(f"invalid catalog mapping: {field['id']}")
        if not field["label"] or not field["source_ref"]:
            raise ValueError(f"field lacks label or source: {field['id']}")
        if field["kind"] not in ("source", "computed", "composite"):
            raise ValueError(f"invalid field kind: {field['id']}")
        if field["kind"] == "computed" and not field.get("formula_id"):
            raise ValueError(f"computed field lacks formula: {field['id']}")
        if field["product_state"] != ("implemented" if field["id"] in IMPLEMENTED_FIELD_IDS else "pending"):
            raise ValueError(f"invalid product state: {field['id']}")
    return tuple(fields)


def catalog_by_id() -> dict[str, dict]:
    return {field["id"]: field for field in load_catalog()}
