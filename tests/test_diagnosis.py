from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diagnosis.pipeline import diagnose_profit_cash
from diagnosis.deepseek import DeepSeek
from diagnosis.models import validate_run
from diagnosis.profit_cash import build_profit_cash_run
from diagnosis.providers import _date_from_ms
from diagnosis.snapshot import load_snapshot, publish_snapshot
from diagnosis.validator import apply_narrative, validate_narrative


def row(value, period="2025-12-31", *, status="valid", basis="annual"):
    return {"value": value, "period_end": period, "unit": "CNY", "period_basis": basis,
            "consolidation": "consolidated", "status": status}


class DiagnosisTests(unittest.TestCase):
    def build(self, profit=row("100"), cash=row("-20")):
        return build_profit_cash_run("利润和经营现金流匹配吗？", profit, cash,
                                     fetched_at="2026-09-26T00:00:00+00:00", run_id="synthetic-test")

    def test_opposite_signs_are_mixed_and_ratio_is_traceable(self):
        run = self.build()
        conclusion = run.conclusions[0]
        self.assertEqual((conclusion.claim_code, conclusion.type, conclusion.assessment),
                         ("profit_positive_cash_negative", "inference", "mixed"))
        ratio = run.evidence[2]
        self.assertEqual(ratio.value, "-0.20")
        self.assertEqual(ratio.calculation["input_evidence_ids"], [run.evidence[1].id, run.evidence[0].id])
        self.assertTrue(conclusion.cannot_say)

    def test_priority_is_recorded_for_source_computation_and_conclusion(self):
        run = self.build()
        self.assertEqual([item.priority["field_id"] for item in run.evidence],
                         ["f021", "f022", "f024"])
        self.assertEqual([item.priority["tier"] for item in run.evidence], ["driver"] * 3)
        self.assertEqual(run.conclusions[0].priority["field_id"], "f066")
        ratio = run.evidence[2]
        self.assertEqual(ratio.calculation["priority_inputs"],
                         [{"evidence_id": item.id, "priority": item.priority}
                          for item in (run.evidence[1], run.evidence[0])])
        self.assertEqual(ratio.calculation["priority_policy"], "output_field_profile_no_numeric_weight")
        self.assertEqual(ratio.value, "-0.20")
        self.assertEqual(run.to_dict()["evidence"][2]["priority"]["profile_version"], "002466-priority-v1")

    def test_priority_tampering_or_broken_lineage_is_rejected(self):
        run = self.build()
        original = run.evidence[0].priority
        run.evidence[0].priority = {**original, "tier": "low"}
        with self.assertRaisesRegex(ValueError, "priority"):
            validate_run(run)
        run.evidence[0].priority = original
        run.evidence[0].priority = run.evidence[1].priority.copy()
        with self.assertRaisesRegex(ValueError, "does not match its metric"):
            validate_run(run)
        run.evidence[0].priority = original
        run.evidence[2].calculation["priority_inputs"] = []
        with self.assertRaisesRegex(ValueError, "priority lineage"):
            validate_run(run)

    def test_llm_receives_priority_without_financial_values(self):
        class RecordingDeepSeek(DeepSeek):
            def _complete(self, system, user):
                self.recorded_system = system
                self.recorded_user = json.loads(user)
                return {"text": "", "evidence_ids": []}

        llm = RecordingDeepSeek("test-key")
        run = self.build()
        llm.translate(run.conclusions[0], run.evidence)
        self.assertEqual(llm.recorded_user["priority"], run.conclusions[0].priority)
        self.assertEqual(llm.recorded_user["evidence"][0]["priority"], run.evidence[0].priority)
        self.assertNotIn("value", llm.recorded_user["evidence"][0])
        self.assertIn("优先级不能把缺失", llm.recorded_system)

    def test_mismatched_period_or_basis_stays_unknown(self):
        for cash in (row("20", "2024-12-31"), row("20", basis="single_quarter")):
            with self.subTest(cash=cash):
                run = self.build(cash=cash)
                self.assertEqual(run.conclusions[0].type, "unknown")
                self.assertIsNone(run.evidence[2].value)

    def test_missing_and_zero_denominator(self):
        missing = self.build(cash=row(None, status="missing"))
        self.assertEqual(missing.conclusions[0].assessment, "unknown")
        self.assertIsNone(missing.evidence[1].value)
        self.assertEqual(missing.evidence[1].priority["tier"], "driver")
        zero = self.build(profit=row("0"), cash=row("20"))
        self.assertEqual(zero.evidence[2].quality["status"], "not_applicable")
        self.assertIn("净利润不大于零", zero.evidence[2].quality["reason"])

    def test_explicit_cannot_say_rules_reject_prohibited_translation(self):
        run = self.build()
        ids = [item.id for item in run.evidence[:2]]
        candidate = {"text": "净利润为正而经营活动现金流净额为负，证明财务造假，建议卖出。", "evidence_ids": ids}
        failures = validate_narrative(candidate, run.conclusions[0], run.evidence)
        self.assertIn("prohibited:NO_FRAUD_INFERENCE", failures)
        self.assertIn("prohibited:NO_TRADE_ADVICE", failures)
        live = {"text": "净利润为正而经营活动现金流净额为负，这是最新的实时数据。", "evidence_ids": ids}
        self.assertIn("prohibited:NO_LIVE_DATA", validate_narrative(live, run.conclusions[0], run.evidence))
        apply_narrative(run, candidate)
        self.assertEqual(run.conclusions[0].validation, "fallback")
        self.assertEqual(run.conclusions[0].text, run.conclusions[0].fallback_text)

    def test_valid_translation_needs_anchor_and_source_ids(self):
        run = self.build()
        ids = [item.id for item in run.evidence[:2]]
        valid = {"text": "净利润为正而经营活动现金流净额为负，值得进一步核对现金流项目。", "evidence_ids": ids}
        self.assertEqual(validate_narrative(valid, run.conclusions[0], run.evidence), [])
        apply_narrative(run, valid)
        self.assertEqual(run.conclusions[0].validation, "passed")
        invalid = {"text": "净利润为正而经营活动现金流净额为负，现金流是利润的20%。", "evidence_ids": ids[:1]}
        self.assertIn("numbers_in_prose", validate_narrative(invalid, run.conclusions[0], run.evidence))
        self.assertIn("missing_supporting_citation", validate_narrative(invalid, run.conclusions[0], run.evidence))

    def test_pipeline_does_not_fetch_for_unsupported_question(self):
        result = diagnose_profit_cash("明天会涨吗？", lambda: self.fail("provider should not run"))
        self.assertEqual(result["status"], "unsupported_question")

    def test_provider_error_remains_visible(self):
        run = self.build(profit=row(None, status="error"))
        self.assertEqual(run.evidence[0].quality["status"], "error")
        self.assertEqual(run.conclusions[0].type, "unknown")

    def test_provider_period_end_uses_shanghai_date(self):
        self.assertEqual(_date_from_ms(1767110400000), "2025-12-31")

    def test_fixed_snapshot_roundtrip_without_expiry(self):
        path = Path(__file__).resolve().parents[1] / "data" / "cache" / f"test_snapshot_{uuid4().hex}.json"
        try:
            downloaded_at = "2026-09-26T00:00:00+00:00"
            published = publish_snapshot(path, {"net_profit": row("100"), "operating_cash_flow": row("-20")},
                                         created_at=downloaded_at)
            fixed = load_snapshot(path)
            self.assertEqual(fixed["_snapshot"]["id"], published["snapshot_id"])
            self.assertEqual(fixed["_snapshot"]["status"], "fixed")
            self.assertEqual(fixed["fetched_at"], downloaded_at)
            run = diagnose_profit_cash("利润和经营现金流匹配吗？", lambda: fixed)
            self.assertEqual(run.route["snapshot"]["id"], published["snapshot_id"])
            self.assertEqual(run.evidence[0].time["fetched_at"], downloaded_at)
            self.assertEqual(fixed["net_profit"]["value"], "100")
        finally:
            path.unlink(missing_ok=True)

    def test_fixed_snapshot_cannot_be_overwritten(self):
        path = Path(__file__).resolve().parents[1] / "data" / "cache" / f"test_snapshot_{uuid4().hex}.json"
        try:
            publish_snapshot(path, {"net_profit": row("100"), "operating_cash_flow": row("20")})
            previous = path.read_bytes()
            with self.assertRaises(FileExistsError):
                publish_snapshot(path, {"net_profit": row(None, status="error"), "operating_cash_flow": row("20")})
            self.assertEqual(path.read_bytes(), previous)
        finally:
            path.unlink(missing_ok=True)

    def test_single_metric_questions_use_only_their_own_evidence(self):
        profit = build_profit_cash_run("净利润为正吗？", row("100"), row(None, status="error"),
                                      intent="net_profit_status", run_id="profit-only")
        self.assertEqual(profit.route["intent"], "net_profit_status")
        self.assertEqual([item.metric_id for item in profit.evidence], ["net_profit"])
        self.assertEqual((profit.conclusions[0].type, profit.conclusions[0].assessment), ("fact", "positive"))
        self.assertEqual(profit.conclusions[0].evidence_links[0]["evidence_id"], profit.evidence[0].id)
        cash = build_profit_cash_run("经营现金流为负吗？", row(None, status="error"), row("-20"),
                                    intent="operating_cash_flow_status", run_id="cash-only")
        self.assertEqual([item.metric_id for item in cash.evidence], ["operating_cash_flow"])
        self.assertEqual((cash.conclusions[0].type, cash.conclusions[0].assessment), ("fact", "negative"))

    def test_single_metric_missing_or_outside_cutoff_is_unknown(self):
        missing = build_profit_cash_run("净利润为正吗？", row(None, status="missing"), row("20"),
                                        intent="net_profit_status")
        self.assertEqual(missing.conclusions[0].type, "unknown")
        late = build_profit_cash_run("净利润为正吗？", row("100", period="2026-09-30"), row("20"),
                                     intent="net_profit_status")
        self.assertEqual(late.conclusions[0].type, "unknown")
        self.assertEqual(late.evidence[0].quality["status"], "not_applicable")
        self.assertIn("仅回答单项指标", late.conclusions[0].limitations[0])

    def test_ratio_question_has_computed_evidence_and_denominator_guard(self):
        run = build_profit_cash_run("经营现金流与净利润的比值是多少？", row("100"), row("80"),
                                    intent="profit_cash_ratio", run_id="ratio-question")
        self.assertEqual(run.evidence[2].value, "0.80")
        self.assertEqual(run.conclusions[0].claim_code, "cash_to_profit_ratio_available")
        self.assertEqual(run.conclusions[0].type, "fact")
        self.assertEqual({link["evidence_id"] for link in run.conclusions[0].evidence_links},
                         {item.id for item in run.evidence})
        invalid = build_profit_cash_run("经营现金流与净利润的比值是多少？", row("-100"), row("80"),
                                        intent="profit_cash_ratio")
        self.assertEqual(invalid.evidence[2].quality["status"], "not_applicable")
        self.assertEqual(invalid.conclusions[0].type, "unknown")


if __name__ == "__main__":
    unittest.main()
