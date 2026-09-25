"""Prepare one immutable normalized snapshot for the exam product."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1
SUBJECT = "002466.SZ"
REQUIRED_METRICS = ("net_profit", "operating_cash_flow")


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def publish_snapshot(path: Path, inputs: dict, *, created_at: str | None = None) -> dict:
    """Publish a fixed snapshot once; never replace an existing snapshot."""
    if path.exists():
        raise FileExistsError("fixed snapshot already exists")
    rows = {metric: inputs.get(metric) for metric in REQUIRED_METRICS}
    if any(not isinstance(row, dict) or row.get("status") == "error" for row in rows.values()):
        raise ValueError("download has missing or failed source groups")
    if any(row.get("status") not in ("valid", "missing", "stale", "conflict", "not_applicable") for row in rows.values()):
        raise ValueError("download has an invalid source status")
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    payload = {"schema_version": SCHEMA_VERSION, "subject": SUBJECT, "created_at": created_at, "rows": rows}
    snapshot_id = hashlib.sha256(_canonical(payload)).hexdigest()[:20]
    document = {**payload, "snapshot_id": snapshot_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("xb") as temporary:
            temporary.write(_canonical(document))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return {"snapshot_id": snapshot_id, "created_at": created_at, "metric_count": len(rows)}


def load_snapshot(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION or document.get("subject") != SUBJECT:
        raise ValueError("snapshot schema or subject mismatch")
    payload = {key: value for key, value in document.items() if key != "snapshot_id"}
    if document.get("snapshot_id") != hashlib.sha256(_canonical(payload)).hexdigest()[:20]:
        raise ValueError("snapshot checksum mismatch")
    created_at = datetime.fromisoformat(document["created_at"])
    if created_at.tzinfo is None:
        raise ValueError("snapshot timestamp lacks timezone")
    rows = document.get("rows")
    if not isinstance(rows, dict) or any(not isinstance(rows.get(metric), dict) for metric in REQUIRED_METRICS):
        raise ValueError("snapshot metric groups are missing")
    selected = {}
    for metric in REQUIRED_METRICS:
        row = rows[metric].copy()
        selected[metric] = row
    return {**selected, "fetched_at": document["created_at"],
            "_snapshot": {"id": document["snapshot_id"], "created_at": document["created_at"],
                          "status": "fixed"}}
