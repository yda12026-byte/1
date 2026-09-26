from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from diagnosis.dimensions import run_dimension  # noqa: E402
from diagnosis.pipeline import diagnose_dimensions  # noqa: E402
from diagnosis.product_snapshot import load_product_snapshot, publish_product_snapshot  # noqa: E402
from diagnosis.routing import route_question  # noqa: E402
from product_fixture import SUBJECT, product_payload  # noqa: E402


def run(dimension: str, payload: dict | None = None):
    result = run_dimension(dimension, payload or product_payload(), "问题", {"intent": dimension})
    return result, {item.id: item for item in result.evidence}, {c.claim_code: c for c in result.conclusions}


class DimensionTests(unittest.TestCase):
    def test_every_dimension_validates_with_digit_free_anchors_and_traceable_inputs(self):
        for dimension in ("financial_trend", "valuation", "market", "industry"):
            result, evidence, conclusions = run(dimension)
            self.assertTrue(conclusions, dimension)
            for conclusion in conclusions.values():
                self.assertFalse(any(ch.isdigit() for ch in conclusion.required_anchor), conclusion.required_anchor)
                self.assertIn(conclusion.required_anchor, conclusion.fallback_text)
                self.assertTrue(set(conclusion.highlights) <= set(evidence))
            for item in result.evidence:
                self.assertEqual(item.time["fetched_at"], product_payload()["created_at"])
                if item.kind == "computed":
                    self.assertTrue(item.calculation["formula_text"])
                    self.assertTrue(set(item.calculation["input_evidence_ids"]) <= set(evidence))

    def test_financial_growth_uses_absolute_base_and_cross_checks_provider_ratio(self):
        _, evidence, conclusions = run("financial_trend")
        self.assertEqual(evidence["operating_income_yoy:2026-06-30"].value, "100.00")
        self.assertEqual(evidence["parent_net_profit_yoy:2026-06-30"].value, "300.00")
        self.assertEqual(conclusions["growth"].assessment, "positive")
        low_base = "归母净利润基期较低，同比倍数被放大，应结合绝对值阅读"
        self.assertNotIn(low_base, conclusions["growth"].limitations)

        payload = product_payload()  # negative base: (40 − (−20)) / |−20| = 300%, agrees with provider
        payload["statements"][SUBJECT][1]["values"]["parent_holder_net_profit"] = -20e8
        _, evidence, _ = run("financial_trend", payload)
        self.assertEqual(evidence["parent_net_profit_yoy:2026-06-30"].value, "300.00")

        payload["indicators"][SUBJECT]["2026-06-30"]["values"]["calculate_parent_holder_net_profit_yoy_growth_ratio"] = 200.0
        _, evidence, conclusions = run("financial_trend", payload)
        yoy = evidence["parent_net_profit_yoy:2026-06-30"]
        self.assertEqual((yoy.quality["status"], yoy.value), ("conflict", None))
        self.assertEqual(conclusions["growth"].type, "unknown")

        payload = product_payload()
        payload["statements"][SUBJECT][1]["values"]["parent_holder_net_profit"] = 2e8
        payload["indicators"][SUBJECT]["2026-06-30"]["values"]["calculate_parent_holder_net_profit_yoy_growth_ratio"] = 1900.0
        _, _, conclusions = run("financial_trend", payload)
        self.assertIn(low_base, conclusions["growth"].limitations)

    def test_zero_base_and_non_positive_profit_are_not_applicable(self):
        payload = product_payload()
        payload["statements"][SUBJECT][1]["values"]["operating_income"] = 0
        payload["statements"][SUBJECT][0]["values"]["net_profit"] = -5e8
        _, evidence, conclusions = run("financial_trend", payload)
        self.assertEqual(evidence["operating_income_yoy:2026-06-30"].quality["status"], "not_applicable")
        self.assertEqual(evidence["cash_to_profit_ratio:2026-06-30"].quality["status"], "not_applicable")
        self.assertEqual((conclusions["growth"].type, conclusions["cash_conversion"].type), ("unknown", "unknown"))

    def test_cash_conversion_and_liabilities_are_labelled_precisely(self):
        _, evidence, conclusions = run("financial_trend")
        self.assertEqual(evidence["cash_to_profit_ratio:2026-06-30"].value, "0.50")
        self.assertEqual(conclusions["cash_conversion"].assessment, "mixed")
        self.assertEqual(evidence["fcf_approx:2026-06-30"].value, "20.0000")
        gap = evidence["cash_minus_liabilities:2026-06-30"]
        self.assertEqual(gap.value, "-50.0000")
        self.assertIn("不是净现金", gap.calculation["formula_text"])
        self.assertEqual(conclusions["balance_sheet"].assessment, "positive")

    def test_valuation_percentile_peer_median_and_negative_multiple(self):
        _, evidence, conclusions = run("valuation")
        self.assertEqual(evidence["pb_percentile:2026-08-31"].value, "100.0")
        self.assertEqual(conclusions["history_position"].required_anchor, "市净率位于自身近一年序列的高区间")
        self.assertEqual(evidence["peer_median_pe_ttm:2026-08-31"].value, "30.00")
        self.assertEqual(conclusions["peer_position"].required_anchor, "市盈率低于同行中位数，市净率低于同行中位数")
        self.assertTrue(all(c.assessment in ("neutral", "unknown") for c in conclusions.values()))
        self.assertIn("NO_VALUATION_JUDGMENT", [rule.code for rule in conclusions["peer_position"].cannot_say])

        payload = product_payload()
        payload["valuation_cutoff"]["values"]["pe_ttm"] = -8
        payload["peer_valuation"]["values"][SUBJECT]["pe_ttm"] = -8
        _, evidence, conclusions = run("valuation", payload)
        self.assertEqual(evidence["pe_ttm:002466.SZ:2026-08-31"].quality["status"], "not_applicable")
        self.assertEqual(conclusions["peer_position"].type, "unknown")
        self.assertEqual(conclusions["mrq_vs_ttm"].type, "unknown")

    def test_market_returns_drawdown_and_sector_conflict(self):
        _, evidence, conclusions = run("market")
        window = [item for key, item in evidence.items() if key.startswith("return:002466.SZ:2025-09-01")][0]
        self.assertEqual(window.value, "20.00")
        self.assertEqual(evidence["max_drawdown:002466.SZ"].value, "-40.00")
        self.assertEqual(evidence["volume_ratio:" + product_payload()["daily"][SUBJECT]["rows"][-1]["date"]].value, "1.44")  # 1500 ÷ ((222×1000 + 20×1500) ÷ 242)
        self.assertEqual(conclusions["relative_sector"].assessment, "positive")  # 20% vs 12.68%

        payload = product_payload()
        payload["sector"]["windows"][8]["weighting"] = "算术平均"
        _, evidence, conclusions = run("market", payload)
        self.assertEqual(evidence["sector_return:window"].quality["status"], "conflict")
        self.assertIn("2026-05", evidence["sector_return:window"].quality["reason"])
        self.assertEqual(conclusions["relative_sector"].type, "unknown")

    def test_industry_prices_and_peer_ranking_do_not_depend_on_dict_order(self):
        payload = product_payload()
        payload["names"] = dict(sorted(payload["names"].items()))  # canonical JSON sorts keys
        _, evidence, conclusions = run("industry", payload)
        self.assertEqual(conclusions["lithium_prices"].assessment, "positive")
        self.assertEqual(conclusions["peer_returns"].required_anchor, "观察区间股价涨跌幅在四家中最低")
        self.assertTrue(conclusions["peer_financials"].required_anchor.startswith("与三家同行相比，销售毛利率最高，加权 ROE高于同行中位数，资产负债率最低"))
        self.assertEqual(evidence["lithium_carbonate_change"].value, "100.00")

    def test_product_snapshot_is_immutable_and_checksummed(self):
        path = ROOT / "data" / "cache" / f"test_product_{uuid4().hex}.json"
        try:
            published = publish_product_snapshot(path, product_payload())
            self.assertEqual(load_product_snapshot(path)["snapshot_id"], published["snapshot_id"])
            with self.assertRaises(FileExistsError):
                publish_product_snapshot(path, product_payload())
            document = json.loads(path.read_text(encoding="utf-8"))
            document["valuation_cutoff"]["values"]["pb_mrq"] = 0.5
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_product_snapshot(path)
        finally:
            path.unlink(missing_ok=True)

    def test_llm_narration_is_validated_per_conclusion_without_values(self):
        payload = {**product_payload(), "snapshot_id": "synthetic"}

        class FakeLLM:
            def __init__(self, mode):
                self.mode, self.sent = mode, []

            def translate_many(self, conclusions, evidence):
                self.sent.append(json.dumps([c.fallback_text for c in conclusions], ensure_ascii=False))
                if self.mode == "fail":
                    raise TimeoutError
                items = [{"id": c.id, "text": c.required_anchor + "。",
                          "evidence_ids": [link["evidence_id"] for link in c.evidence_links if link["role"] == "supports"]}
                         for c in conclusions]
                if self.mode == "bad":
                    items[0]["text"] += "目前估值被低估。"
                    items = items[:-1]
                return items

        route = route_question("估值如何？")
        for mode, first, last in (("ok", "passed", "passed"), ("bad", "fallback", "fallback"), ("fail", "fallback", "fallback")):
            llm = FakeLLM(mode)
            conclusions = diagnose_dimensions("估值如何？", route, lambda: payload, llm)[0].conclusions
            self.assertEqual((conclusions[0].validation, conclusions[-1].validation), (first, last), mode)
            if mode == "bad":
                self.assertIn("prohibited:NO_VALUATION_JUDGMENT", conclusions[0].validation_failures)
                self.assertEqual(conclusions[-1].validation_failures, ["llm_missing_item"])
            if mode == "fail":
                self.assertEqual(conclusions[0].validation_failures, ["llm_unavailable"])

    def test_routing_runs_implemented_dimensions_and_keeps_uncovered_years_planned(self):
        self.assertEqual(route_question("估值如何？")["runnable_dimensions"], ["valuation"])
        overview = route_question("全面诊断一下")
        self.assertEqual(overview["execution_status"], "partial")
        self.assertEqual(set(overview["runnable_dimensions"]), {"financial_trend", "valuation", "market", "industry"})
        self.assertEqual(route_question("2024年净利润同比增长多少？")["execution_status"], "planned")
        revenue = route_question("2026年上半年营收同比增长多少？")
        self.assertEqual((revenue["execution_status"], revenue["runnable_dimensions"]), ("partial", ["financial_trend"]))
        self.assertEqual(route_question("主要风险有哪些？")["execution_status"], "planned")


if __name__ == "__main__":
    unittest.main()
