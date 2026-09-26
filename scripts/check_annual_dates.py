"""Audit dates in annual daily-source rows without exposing financial values."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.download_annual_raw import parsed_ifind, transport  # noqa: E402

RAW = ROOT / "data" / "raw" / "annual-2025-08-31_2026-08-31"
SERIES = ("valuation", "sector", "lithium_carbonate", "lithium_hydroxide", "spodumene", "lithium_futures")


def row_dates(path: Path, stem: str) -> list[date]:
    data = parsed_ifind(json.loads(path.read_text(encoding="utf-8"))).get("data")
    if not isinstance(data, dict):
        return []
    if stem in ("valuation", "sector"):
        lines = data.get("answer", "").splitlines()
        texts = [line for line in lines if line.lstrip().startswith("|")]
    else:
        texts = []
        for dataset in data.get("datas", []):
            table = dataset.get("data", {})
            if isinstance(table, dict):
                texts.extend(str(row[0]) for row in table.get("data", []) if isinstance(row, list) and row)
    dates = []
    for text in texts:
        for iso in transport._ifind_dates(text):
            dates.append(date.fromisoformat(iso))
    return dates


def main() -> None:
    totals = defaultdict(lambda: {"files": 0, "rows": 0, "outside_requested_month": 0,
                                 "weekend_rows": 0, "empty_files": 0})
    exceptions = []
    for path in RAW.glob("ifind_*.json"):
        match = re.fullmatch(r"ifind_(.+)_(20\d{2})_(\d{2})\.json", path.name)
        if not match or match.group(1) not in SERIES:
            continue
        stem, year, month = match.groups()
        year, month = int(year), int(month)
        rows = row_dates(path, stem)
        stats = totals[stem]
        stats["files"] += 1
        stats["rows"] += len(rows)
        stats["weekend_rows"] += sum(day.weekday() >= 5 for day in rows)
        outside = sum((day.year, day.month) != (year, month) for day in rows)
        stats["outside_requested_month"] += outside
        if not rows:
            stats["empty_files"] += 1
        if outside or not rows:
            exceptions.append({"file": path.name, "row_dates": len(rows), "outside_requested_month": outside})
    output = {"warning": "Dates parsed from source rows only; not a field/units validation.",
              "groups": dict(totals), "exceptions": sorted(exceptions, key=lambda item: item["file"])}
    (RAW / "date_audit.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
