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
        for dimension in ("operating_quality", "financial_trend", "valuation", "market", "industry", "risk"):
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
        self.assertEqual(evidence["interest_bearing_debt:2026-06-30"].value, "70.0000")  # 10 + 5 + 50 + 0 + 5
        self.assertEqual(evidence["net_cash:2026-06-30"].value, "-20.0000")  # cash 50 − debt 70
        self.assertEqual(evidence["inventory_change:2026-06-30"].value, "20.00")
        self.assertEqual(evidence["deducted_net_profit_yoy:2026-06-30"].value, "322.22")
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

    def test_peer_comparisons_carry_tables_of_evidence(self):
        from diagnosis.models import validate_run
        result, evidence, conclusions = run("industry")
        table = conclusions["peer_financials"].table
        self.assertEqual(table["columns"], ["天齐锂业", "赣锋锂业", "中矿资源", "永兴材料"])
        self.assertEqual([row["label"] for row in table["rows"]], ["销售毛利率", "加权 ROE", "资产负债率", "营业收入同比"])
        self.assertEqual([evidence[cell].value for cell in table["rows"][0]["cells"]], ["60", "50", "40", "30"])
        self.assertEqual(len(conclusions["peer_returns"].table["rows"][0]["cells"]), 4)
        _, evidence_v, conclusions_v = run("valuation")
        peer = conclusions_v["peer_position"].table
        self.assertEqual(peer["columns"][-1], "同行中位数")
        self.assertEqual(evidence_v[peer["rows"][0]["cells"][-1]].value, "30.00")
        conclusions["peer_returns"].table["rows"][0]["cells"][1] = "missing-id"
        with self.assertRaisesRegex(ValueError, "comparison table"):
            validate_run(result)

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
            conclusions = diagnose_dimensions("估值如何？", route, lambda: payload, llm)[0][0].conclusions
            self.assertEqual((conclusions[0].validation, conclusions[-1].validation), (first, last), mode)
            if mode == "bad":
                self.assertIn("prohibited:NO_VALUATION_JUDGMENT", conclusions[0].validation_failures)
                self.assertEqual(conclusions[-1].validation_failures, ["llm_missing_item"])
            if mode == "fail":
                self.assertEqual(conclusions[0].validation_failures, ["llm_unavailable"])

    def test_operating_quality_from_official_extracts(self):
        _, evidence, conclusions = run("operating_quality")
        self.assertEqual(evidence["segment_share_1:2026-06-30"].value, "60.00")
        self.assertEqual(conclusions["segment_structure"].required_anchor, "锂化合物及衍生品收入占比较高，锂矿毛利率较高")
        self.assertEqual(conclusions["segment_margin"].assessment, "positive")
        self.assertEqual(evidence["investment_income_share:2026-06-30"].value, "30.00")
        self.assertEqual(conclusions["investment_income"].required_anchor, "投资收益占同期归母净利润的比重较大")
        self.assertEqual(evidence["concentrate_output_yoy:2026-06-30"].value, "25.00")
        self.assertEqual(evidence["undisclosed_0:002466.SZ:2026-06-30"].quality["status"], "missing")
        self.assertIn("第 1 页", evidence["segment_revenue_0:002466.SZ:2026-06-30"].source["query_ref"])

        payload = product_payload()
        row = next(r for r in payload["official_h1"]["items"] if r["item"] == "存货" and r["period_end"] == "2026-06-30")
        row["crosscheck"] = "不一致（差 5%）"
        _, evidence, _ = run("financial_trend", payload)
        self.assertEqual(evidence["inventory:002466.SZ:2026-06-30"].quality["status"], "conflict")
        self.assertEqual(evidence["inventory_change:2026-06-30"].quality["status"], "missing")

    def test_risk_dimension(self):
        _, evidence, conclusions = run("risk")
        self.assertEqual(conclusions["liquidity"].required_anchor, "流动比率较上年同期上升")
        self.assertEqual(evidence["cash_cover_debt:2026-06-30"].value, "0.71")
        self.assertEqual(conclusions["debt_cover"].assessment, "negative")
        self.assertEqual(evidence["inventory_reserve_change:2026-06-30"].value, "-75.00")
        self.assertEqual(evidence["capex_to_ocf:2026-06-30"].value, "0.50")
        self.assertEqual(evidence["project_1:002466.SZ:2026-06-30"].value, "建设中")

        payload = product_payload()
        payload["official_h1"]["items"] = [r for r in payload["official_h1"]["items"] if r["item"] != "长期借款"]
        _, evidence, conclusions = run("risk", payload)
        self.assertEqual(evidence["interest_bearing_debt:2026-06-30"].quality["status"], "missing")
        self.assertEqual(conclusions["debt_cover"].type, "unknown")

    def test_routing_runs_implemented_dimensions_and_keeps_uncovered_years_planned(self):
        self.assertEqual(route_question("估值如何？")["runnable_dimensions"], ["valuation"])
        overview = route_question("全面诊断一下")
        self.assertEqual(overview["execution_status"], "implemented")
        self.assertEqual(set(overview["runnable_dimensions"]),
                         {"operating_quality", "financial_trend", "valuation", "market", "industry", "risk", "events"})
        self.assertEqual(route_question("2024年净利润同比增长多少？")["execution_status"], "planned")
        revenue = route_question("2026年上半年营收同比增长多少？")
        self.assertEqual((revenue["execution_status"], revenue["runnable_dimensions"]),
                         ("implemented", ["operating_quality", "financial_trend"]))
        self.assertEqual(route_question("主要风险有哪些？")["execution_status"], "implemented")
        self.assertEqual(route_question("近期有哪些公告？")["execution_status"], "implemented")  # needs the events block at run time

    def test_overall_summary_is_validated_and_falls_back_to_program_anchors(self):
        payload = {**product_payload(), "snapshot_id": "synthetic"}
        route = route_question("全面诊断一下")
        runs, summary = diagnose_dimensions("全面诊断一下", route, lambda: payload)
        self.assertEqual(summary["validation"], "fallback")
        for run in runs:
            known = [c for c in run.conclusions if c.type != "unknown"]
            self.assertIn(known[0].required_anchor, summary["text"])
        self.assertIn("重要事件", summary["text"])  # uncovered dimensions are named, not silently dropped
        from diagnosis.pipeline import _summary_basis, summary_limit
        basis = _summary_basis(runs, route)
        self.assertEqual(summary_limit(basis), 200 + 40 * 6)
        self.assertLessEqual(len(summary["text"]), summary_limit(basis))
        self.assertFalse(any(ch.isdigit() for ch in summary["text"]))

        class SummaryLLM:
            def __init__(self, text):
                self.text = text

            def translate_many(self, conclusions, evidence):
                raise TimeoutError

            def summarize(self, basis):
                return self.text(basis)

        anchors = lambda basis: "；".join(basis["must_include"]) + "。"
        cases = {"passed": (anchors, []),
                 "digits": (lambda b: anchors(b) + "市盈率约二十倍，分位为 30。", ["numbers_in_prose"]),
                 "advice": (lambda b: anchors(b) + "估值被低估，可以买入。", ["prohibited:NO_TRADE_ADVICE", "prohibited:NO_VALUATION_JUDGMENT"]),
                 "anchor": (lambda b: "整体表现不错。", ["missing_anchor"])}
        for name, (text, failures) in cases.items():
            _, summary = diagnose_dimensions("全面诊断一下", route, lambda: payload, SummaryLLM(text))
            self.assertEqual(summary["validation"], "passed" if not failures else "fallback", name)
            self.assertEqual(summary["validation_failures"], failures, name)
            if failures:
                self.assertTrue(summary["text"].startswith("综合来看："), name)


class PendingRiskTests(unittest.TestCase):
    def test_unverified_risk_questions_are_explicit_unknowns_with_missing_evidence(self):
        from product_fixture import product_payload as payload_for
        run = run_dimension("risk", {**payload_for(), "snapshot_id": "synthetic"}, "主要风险", {"intent": "risk"})
        pending = {c.claim_code: c for c in run.conclusions if c.type == "unknown"}
        self.assertEqual(set(pending), {"lithium_sensitivity", "overseas_exposure"})
        evidence = {e.id: e for e in run.evidence}
        for conclusion in pending.values():
            self.assertEqual(conclusion.assessment, "unknown")
            item = evidence[conclusion.evidence_links[0]["evidence_id"]]
            self.assertEqual((item.quality["status"], item.value), ("missing", None))
            self.assertTrue(item.quality["reason"])

if __name__ == "__main__":
    unittest.main()
