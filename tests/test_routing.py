from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.catalog import DIMENSIONS, EXECUTABLE_FIELDS, SPECIAL_FIELD_IDS, load_catalog
from diagnosis.pipeline import diagnose_profit_cash
from diagnosis.priority import load_priority_profile
from diagnosis.routing import route_question


class RouterTests(unittest.TestCase):
    def test_all_candidate_rows_have_stable_route_and_source(self):
        catalog = load_catalog()
        source_rows = [line for line in (ROOT / "docs" / "field-candidates-002466-v2.md").read_text(encoding="utf-8").splitlines()
                       if line.startswith("| □ |")]
        self.assertEqual(len(source_rows), len(catalog))
        for item, line in zip(catalog, source_rows):
            parts = [part.strip() for part in line.strip("| ").split("|")]
            self.assertEqual(item["label"], parts[2])
            self.assertEqual(item["source_ref"], parts[3])
            self.assertEqual(item["candidate_status"], parts[4])
            self.assertEqual(DIMENSIONS[item["dimension"]], parts[1])
            self.assertTrue(item["source_groups"])
            self.assertNotIn("主力资金", item["label"])
        self.assertEqual(Counter(item["candidate_status"] for item in catalog),
                         {"已取值": 43, "可计算": 9, "部分可用": 19, "待核": 1})

    def test_special_route_only_uses_implemented_fields(self):
        route = route_question("利润和经营现金流匹配吗？")
        self.assertEqual(route["intent"], "profit_cash_alignment")
        self.assertEqual(set(route["field_ids"]), set(SPECIAL_FIELD_IDS))
        self.assertEqual(route["pending_field_ids"], [])
        self.assertEqual(route["execution_status"], "implemented")
        self.assertEqual(route["window"]["cutoff"], "2026-08-31")

    def test_dimension_and_multi_dimension_expand_with_runnable_subset(self):
        valuation = route_question("估值如何？")
        self.assertEqual(valuation["dimensions"], ["valuation"])
        self.assertEqual(valuation["execution_status"], "implemented")
        self.assertEqual(len(valuation["field_ids"]), 7)
        self.assertEqual(len(valuation["implemented_field_ids"]), 7)
        multi = route_question("估值和行业位置如何？")
        self.assertEqual(multi["intent"], "multi_dimension")
        self.assertEqual(set(multi["dimensions"]), {"valuation", "industry"})
        self.assertEqual(multi["execution_status"], "implemented")
        self.assertEqual(len(multi["field_ids"]), 15)
        self.assertIn("f003", multi["pending_field_ids"])  # peer list is a decision, not a runtime field
        overview = route_question("全面诊断一下")
        self.assertEqual((len(overview["field_ids"]), overview["execution_status"]), (72, "partial"))

    def test_planned_or_advice_question_does_not_read_snapshot(self):
        provider = lambda: self.fail("data provider should not run")
        planned = diagnose_profit_cash("估值如何？", provider)
        self.assertEqual(planned["status"], "not_implemented")
        self.assertEqual(planned["route"]["field_ids"], route_question("估值如何？")["field_ids"])
        advice = diagnose_profit_cash("明天会涨吗？", provider)
        self.assertEqual(advice["status"], "unsupported_question")

    def test_unallowlisted_llm_intent_falls_back(self):
        class BadClassifier:
            def classify(self, question):
                return "buy_now"

        route = route_question("估值如何？", BadClassifier())
        self.assertEqual(route["intent"], "valuation")
        self.assertEqual(route["method"], "deterministic_fallback")

    def test_llm_cannot_send_unrelated_question_to_implemented_route(self):
        class WrongClassifier:
            def classify(self, question):
                return "profit_cash_alignment"

        route = route_question("估值如何？", WrongClassifier())
        self.assertEqual(route["intent"], "valuation")
        self.assertEqual(route["runnable_dimensions"], ["valuation"])
        result = diagnose_profit_cash("估值如何？", lambda: self.fail("provider should not run"), WrongClassifier())
        self.assertEqual(result["status"], "not_implemented")

    def test_new_narrow_questions_are_executable(self):
        cases = {
            "净利润是正还是负？": ("net_profit_status", ["f021"]),
            "经营活动现金流净额为正吗？": ("operating_cash_flow_status", ["f022"]),
            "经营现金流与净利润的比值是多少？": ("profit_cash_ratio", ["f021", "f022", "f024"]),
        }
        for question, (intent, field_ids) in cases.items():
            with self.subTest(question=question):
                route = route_question(question)
                self.assertEqual(route["intent"], intent)
                self.assertEqual(route["field_ids"], field_ids)
                self.assertEqual(route["execution_status"], "implemented")

    def test_narrow_route_does_not_answer_trends_specific_years_or_advice(self):
        # Trend questions go to the financial dimension run, never to a single-period narrow intent.
        for question in ("净利润同比增长了吗？", "经营现金流过去一年趋势如何？", "净利润和经营现金流相差多少？"):
            with self.subTest(question=question):
                route = route_question(question)
                self.assertNotIn(route["intent"], EXECUTABLE_FIELDS)
                self.assertEqual(route["runnable_dimensions"], ["financial_trend"])
        self.assertEqual(route_question("经营现金流在2024年为正吗？")["execution_status"], "planned")
        self.assertEqual(route_question("净利润为正，值得买吗？")["execution_status"], "unsupported")

    def test_llm_cannot_misroute_new_executable_intents(self):
        class WrongClassifier:
            def classify(self, question):
                return "profit_cash_ratio"

        self.assertEqual(route_question("净利润为正吗？", WrongClassifier())["intent"], "net_profit_status")

    def test_narrow_keywords_do_not_hide_other_requested_dimensions(self):
        for question in ("净利润和估值如何？", "利润和经营现金流与行业位置如何？"):
            with self.subTest(question=question):
                route = route_question(question)
                self.assertEqual(route["intent"], "multi_dimension")
                self.assertIn(route["execution_status"], ("implemented", "partial"))
                self.assertIn("financial_trend", route["runnable_dimensions"])
                self.assertGreater(len(route["dimensions"]), 1)

    def test_company_profile_covers_all_fields_and_prioritizes_price_cycle(self):
        profile = load_priority_profile()
        self.assertEqual(len(profile["fields"]), 72)
        self.assertEqual(profile["fields"]["f011"][0], "low")
        overview = route_question("全面诊断一下")
        display = overview["display_plan"]["default_field_ids"]
        self.assertEqual(len(display), 12)
        self.assertEqual(display[:2], ["f050", "f051"])
        self.assertIn("f014", display)
        self.assertNotIn("f011", display)
        self.assertEqual(len(overview["field_ids"]), 72)
        self.assertEqual(len(overview["display_plan"]["drilldown_field_ids"]), 60)

    def test_deprioritized_field_returns_when_explicitly_asked(self):
        generic = route_question("经营质量如何？")
        self.assertNotIn("f011", generic["display_plan"]["default_field_ids"])
        focused = route_question("研发费用如何？")
        self.assertEqual(focused["display_plan"]["default_field_ids"][0], "f011")
        self.assertEqual(focused["display_plan"]["focus_field_ids"], ["f011"])
        self.assertEqual(next(field for field in focused["fields"] if field["id"] == "f011")["priority_tier"], "low")

    def test_question_specific_route_keeps_required_fields(self):
        ratio = route_question("经营现金流与净利润的比值是多少？")
        self.assertEqual(ratio["display_plan"]["default_field_ids"], ["f021", "f022", "f024"])
        self.assertEqual(ratio["display_plan"]["drilldown_field_ids"], [])
        valuation = route_question("估值如何？")
        self.assertEqual(valuation["display_plan"]["default_field_ids"][:2], ["f036", "f039"])

    def test_important_unverified_field_stays_visible_as_a_gap(self):
        risk = route_question("主要风险有哪些？")
        self.assertEqual(risk["execution_status"], "planned")
        self.assertIn("f070", risk["display_plan"]["default_field_ids"])
        sensitivity = next(field for field in risk["fields"] if field["id"] == "f070")
        self.assertEqual(sensitivity["candidate_status"], "待核")
        self.assertEqual(sensitivity["product_state"], "pending")
        self.assertTrue(sensitivity["default_display"])


if __name__ == "__main__":
    unittest.main()
