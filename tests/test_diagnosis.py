from __future__ import annotations

import sys
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diagnosis.pipeline import diagnose_profit_cash
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


if __name__ == "__main__":
    unittest.main()
