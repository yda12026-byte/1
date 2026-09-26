"""Build the reviewable route manifest from the authoritative candidate table.

Run only when the candidate table changes, then review the generated diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from diagnosis.catalog import CATALOG_VERSION, DIMENSIONS, IMPLEMENTED_FIELD_IDS, IMPLEMENTED_LABELS, SUBJECT  # noqa: E402

SOURCE_GROUPS = (
    ("扶摇", "fuyao"), ("iFinD", "ifind"), ("深交所", "official_filing"), ("官方", "official_filing"),
    ("巨潮", "official_filing"), ("公告", "official_filing"), ("定期报告", "official_filing"),
    ("同行", "peer_group"), ("日 K", "price_series"),
)

# These are candidate computation recipes, not verified production formulas.
# A computed field is only usable after its inputs, period, units and formula
# have been checked and added to the product calculation layer.
CALCULATIONS = {
    "营业利润率": ("operating_profit_div_operating_income", ["operating_profit", "operating_income"]),
    "研发费用及费用率": ("rd_expense_div_operating_income", ["research_and_development_expenses", "operating_income"]),
    "经营现金流 / 净利润": ("operating_cash_flow_div_net_profit", ["act_cash_flow_net", "net_profit"]),
    "自由现金流近似值": ("operating_cash_flow_minus_fixed_asset_cash", ["act_cash_flow_net", "pay_fixed_assets_etc_cash"]),
    "货币资金 / 总债务 / 净现金": ("cash_minus_interest_bearing_debt", ["cash", "official_h1_interest_bearing_debt_items"]),
    "20/60 交易日区间涨跌幅": ("adjusted_close_return_20_60", ["forward_adjusted_daily_close"]),
    "量能变化": ("volume_vs_n_day_average", ["daily_volume"]),
    "现金覆盖总债务": ("cash_div_interest_bearing_debt", ["cash", "official_h1_interest_bearing_debt_items"]),
    "利润与经营现金流背离": ("profit_cash_sign_alignment", ["net_profit", "act_cash_flow_net"]),
}


def main() -> None:
    rows = []
    source = ROOT / "docs" / "field-candidates-002466-v2.md"
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| □ |"):
            continue
        parts = [part.strip() for part in line.strip("| ").split("|")]
        if len(parts) != 6:
            raise ValueError(f"candidate row has unexpected columns: {line}")
        _, dimension_name, label, source_ref, status, review_note = parts
        dimension = next((key for key, name in DIMENSIONS.items() if name == dimension_name), None)
        if dimension is None:
            raise ValueError(f"unknown dimension: {dimension_name}")
        field_id = f"f{len(rows) + 1:03d}"
        if field_id in IMPLEMENTED_LABELS and label != IMPLEMENTED_LABELS[field_id]:
            raise ValueError(f"implemented field ID moved: {field_id}")
        calculation = CALCULATIONS.get(label)
        groups = [key for marker, key in SOURCE_GROUPS if marker in source_ref]
        if calculation and not groups:
            groups = ["fuyao"]
        if not groups:
            groups = ["source_to_verify"]
        row = {
            "id": field_id, "label": label, "dimension": dimension,
            "source_ref": source_ref, "source_groups": sorted(set(groups)),
            "candidate_status": status, "review_note": review_note,
            "kind": "computed" if calculation else "composite" if " / " in label or "及" in label or "和" in label else "source",
            "product_state": "implemented" if field_id in IMPLEMENTED_FIELD_IDS else "pending",
        }
        if calculation:
            row["formula_id"], row["input_fields"] = calculation
        rows.append(row)
    if len(rows) != 72 or set(CALCULATIONS) - {row["label"] for row in rows}:
        raise ValueError("candidate count or calculation mapping changed")
    target = ROOT / "config" / "diagnosis_fields.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps({"version": CATALOG_VERSION, "subject": SUBJECT, "fields": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} candidate routes to {target}")


if __name__ == "__main__":
    main()
