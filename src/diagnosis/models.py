from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

EvidenceStatus = Literal["valid", "missing", "stale", "conflict", "error", "not_applicable"]
ConclusionType = Literal["fact", "inference", "unknown"]
Assessment = Literal["positive", "negative", "mixed", "unknown"]


@dataclass
class Evidence:
    id: str
    metric_id: str
    subject: str
    kind: Literal["source", "computed"]
    value: str | None
    unit: str | None
    time: dict
    scope: dict
    quality: dict
    source: dict | None = None
    calculation: dict | None = None


@dataclass(frozen=True)
class CannotSay:
    code: str
    statement: str
    reason: str


@dataclass
class Conclusion:
    id: str
    dimension: str
    claim_code: str
    type: ConclusionType
    assessment: Assessment
    evidence_links: list[dict]
    limitations: list[str]
    cannot_say: list[CannotSay]
    required_anchor: str
    fallback_text: str
    text: str
    validation: Literal["fallback", "passed"] = "fallback"
    validation_failures: list[str] = field(default_factory=list)


@dataclass
class DiagnosisRun:
    id: str
    subject: str
    question: str
    route: dict
    config_version: str
    created_at: str
    evidence: list[Evidence]
    conclusions: list[Conclusion]

    def to_dict(self) -> dict:
        return asdict(self)


def validate_run(run: DiagnosisRun) -> DiagnosisRun:
    if not all((run.id, run.subject, run.question.strip(), run.config_version)):
        raise ValueError("run identity or question is missing")
    by_id: dict[str, Evidence] = {}
    for item in run.evidence:
        if not all((item.id, item.metric_id, item.subject, item.time.get("fetched_at"))):
            raise ValueError("evidence identity or fetched_at is missing")
        if item.id in by_id:
            raise ValueError(f"duplicate evidence ID: {item.id}")
        if item.quality.get("status") not in EvidenceStatus.__args__:
            raise ValueError("invalid evidence status")
        if item.quality["status"] == "valid" and item.value is None:
            raise ValueError("valid evidence needs a value")
        if item.quality["status"] != "valid" and item.value is not None:
            raise ValueError("unusable evidence must have a null value")
        if item.kind == "source" and not all((item.source or {}).get(k) for k in ("provider", "endpoint", "field", "query_ref")):
            raise ValueError("source provenance is incomplete")
        if item.kind == "computed" and not (item.calculation or {}).get("input_evidence_ids"):
            raise ValueError("computed evidence lacks inputs")
        by_id[item.id] = item
    for item in run.evidence:
        for input_id in (item.calculation or {}).get("input_evidence_ids", []):
            if input_id not in by_id:
                raise ValueError(f"missing calculation input: {input_id}")
    for conclusion in run.conclusions:
        if conclusion.type not in ConclusionType.__args__ or conclusion.assessment not in Assessment.__args__:
            raise ValueError("invalid conclusion classification")
        if not conclusion.evidence_links or not conclusion.cannot_say or not conclusion.required_anchor:
            raise ValueError("conclusion lacks links, cannot_say, or anchor")
        for link in conclusion.evidence_links:
            if link.get("evidence_id") not in by_id or link.get("role") not in ("supports", "counters", "context"):
                raise ValueError("invalid evidence link")
        if conclusion.type != "unknown" and not any(
            link["role"] == "supports" and by_id[link["evidence_id"]].quality["status"] == "valid"
            for link in conclusion.evidence_links
        ):
            raise ValueError("fact or inference lacks valid supporting evidence")
    return run
