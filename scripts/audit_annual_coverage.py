"""Check private annual raw-file coverage for every catalog field, without values."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "annual-2025-08-31_2026-08-31"
CATALOG = ROOT / "config" / "diagnosis_fields.json"

FIELD_GROUPS: dict[str, set[str]] = {}


def assign(group: str, ids: str) -> None:
    for field_id in ids.split():
        FIELD_GROUPS.setdefault(field_id, set()).add(group)


assign("company", "f001 f002 f003 f004")
assign("income", "f005 f006 f008 f009 f011 f016 f017 f018 f021 f024 f033 f066")
assign("indicators", "f007 f010 f016 f017 f018 f023 f028 f029 f030 f031 f032 f063 f064")
assign("ifind_financial", "f012 f013 f019 f020 f030 f069")
assign("official_reports", "f004 f013 f014 f015 f056 f057 f058 f069 f070 f071 f072")
assign("cash_flow", "f022 f024 f025 f026 f066 f072")
assign("balance", "f027 f031 f065")
assign("valuation_cutoff", "f034 f035 f036 f037 f038 f040 f054")
assign("valuation_series", "f039")
assign("daily", "f041 f042 f043 f044 f045 f046 f047 f054 f067")
assign("corporate_actions", "f059")
assign("anomaly_historical", "f048")
assign("sector_series", "f047 f049")
assign("carbonate_series", "f050 f070")
assign("hydroxide_series", "f051")
assign("spodumene_series", "f051 f070")
assign("futures_series", "f052")
assign("peer_financial", "f053")
assign("peer_daily", "f054")
assign("peer_valuation", "f040 f054")
assign("notices", "f055 f056 f057 f058 f060 f061 f069 f071 f072")
assign("shareholders", "f060 f068")
assign("events", "f060 f061 f068")
assign("news", "f062")
assign("risk", "f045 f067")
assign("cash_flow", "f065")


def requirements() -> dict[str, list[str]]:
    months = ["2025_09", "2025_10", "2025_11", "2025_12",
              "2026_01", "2026_02", "2026_03", "2026_04", "2026_05",
              "2026_06", "2026_07", "2026_08"]
    def series(stem: str) -> list[str]:
        return [f"ifind_{stem}_{month}.json" for month in months]
    return {
        "company": ["ifind_company_info.json"],
        "income": ["fuyao_stock_income_quarters.json"],
        "indicators": ["fuyao_stock_indicators_2025-2.json", "fuyao_stock_indicators_2025-3.json",
                       "fuyao_stock_indicators_2025-4.json", "fuyao_stock_indicators_2026-1.json",
                       "fuyao_stock_indicators_2026-2.json"],
        "ifind_financial": ["ifind_financial_2025_h1.json", "ifind_financial_2025_fy.json",
                            "ifind_financial_2026_h1.json", "ifind_business_2026_h1.json"],
        "official_reports": [f"official_stock_{period}.pdf" for period in
                             ("2025_h1", "2025_q3", "2025_fy", "2026_q1", "2026_h1")],
        "cash_flow": ["fuyao_stock_cash_flow_quarters.json"],
        "balance": ["fuyao_stock_balance_quarters.json"],
        "valuation_cutoff": ["ifind_stock_valuation_cutoff.json", "ifind_peer_valuation_cutoff.json"],
        "valuation_series": series("valuation"),
        "daily": ["fuyao_stock_daily.json"],
        "corporate_actions": ["fuyao_stock_corporate_actions.json"],
        "anomaly_historical": [],
        "sector_series": series("sector"),
        "carbonate_series": series("lithium_carbonate"),
        "hydroxide_series": series("lithium_hydroxide"),
        "spodumene_series": series("spodumene"),
        "futures_series": series("lithium_futures"),
        "peer_financial": ["ifind_peer_financial_2026_h1.json", "fuyao_peer_income_quarters.json",
                           "fuyao_peer_indicators_2026-2.json",
                           "ifind_peer002738_financial_2026_h1.json", "fuyao_peer002738_income_quarters.json",
                           "fuyao_peer002738_indicators_2026-2.json",
                           "ifind_peer002756_financial_2026_h1.json", "fuyao_peer002756_income_quarters.json",
                           "fuyao_peer002756_indicators_2026-2.json"],
        "peer_daily": ["fuyao_peer_daily.json", "fuyao_peer002738_daily.json", "fuyao_peer002756_daily.json"],
        "peer_valuation": ["ifind_peer_valuation_cutoff_group.json"],
        "notices": ["ifind_notices_2025_08.json", "ifind_project_notices_2025_08.json"] +
                   series("notices") + series("project_notices"),
        "shareholders": ["ifind_shareholders_cutoff.json"],
        "events": ["ifind_events_cutoff.json"],
        "news": ["ifind_news_2025_08.json"] + series("news"),
        "risk": ["ifind_risk_cutoff.json"],
    }


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["fields"]
    ids = {field["id"] for field in catalog}
    if len(catalog) != 72 or ids != set(FIELD_GROUPS):
        raise ValueError("Field coverage map differs from the 72-field catalog")
    required = requirements()
    rows = []
    for field in catalog:
        groups = sorted(FIELD_GROUPS[field["id"]])
        missing = sorted({filename for group in groups for filename in required[group]
                          if not (RAW / filename).exists()})
        state = "raw_files_present_review_required" if not missing else "raw_files_incomplete"
        if "anomaly_historical" in groups:
            state = "historical_interface_unavailable"
        elif "corporate_actions" in groups and not missing:
            envelope = json.loads((RAW / "fuyao_stock_corporate_actions.json").read_text(encoding="utf-8"))
            if envelope.get("body", {}).get("code") == 3002:
                state = "source_no_matching_events"
        rows.append({"id": field["id"], "label": field["label"], "groups": groups,
                     "state": state, "missing_files": missing})
    summary = {state: sum(row["state"] == state for row in rows)
               for state in sorted({row["state"] for row in rows})}
    output = {"window": ["2025-08-31", "2026-08-31"], "source": "local private raw files",
              "warning": "File presence does not validate values, dates, units, rights, or completeness of semantic search.",
              "summary": summary, "fields": rows}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "field_coverage.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary,
                      "incomplete_ids": [row["id"] for row in rows if row["state"] != "raw_files_present_review_required"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
