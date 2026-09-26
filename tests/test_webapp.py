from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from diagnosis.product_snapshot import publish_product_snapshot  # noqa: E402
from diagnosis.snapshot import publish_snapshot  # noqa: E402
from product_fixture import product_payload  # noqa: E402
from webapp import EXAMPLES, create_app  # noqa: E402

CACHE = ROOT / "data" / "cache"
CREATED_AT = "2026-09-01T02:00:00+00:00"


def row(value, period="2025-12-31", *, status="valid"):
    return {"value": value, "period_end": period, "unit": "CNY", "period_basis": "annual",
            "consolidation": "consolidated", "status": status}


class FakeLLM:
    def __init__(self, *, fail_translate=False):
        self.classified: list[str] = []
        self.fail_translate = fail_translate

    def classify(self, question):
        self.classified.append(question)
        return "valuation"

    def translate(self, conclusion, evidence):
        if self.fail_translate:
            raise TimeoutError("synthetic LLM timeout")
        return {"text": conclusion.fallback_text, "evidence_ids": [link["evidence_id"] for link in conclusion.evidence_links]}


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.paths: list[Path] = []

    def tearDown(self):
        for path in self.paths:
            path.unlink(missing_ok=True)

    def snapshot(self, profit=row("100"), cash=row("80")) -> Path:
        path = CACHE / f"test_web_{uuid4().hex}.json"
        self.paths.append(path)
        publish_snapshot(path, {"net_profit": profit, "operating_cash_flow": cash}, created_at=CREATED_AT)
        return path

    def product(self, payload: dict | None = None) -> Path:
        path = CACHE / f"test_web_product_{uuid4().hex}.json"
        self.paths.append(path)
        publish_product_snapshot(path, payload or product_payload())
        return path

    def client(self, path: Path | None = None, llm=None, product: Path | None = None):
        # Always pass an explicit product path so tests never read the real data/cache snapshot.
        return create_app(snapshot_path=path or self.snapshot(), llm=llm,
                          product_snapshot_path=product or CACHE / f"absent_product_{uuid4().hex}.json").test_client()

    def ask(self, client, question, context=None):
        response = client.post("/api/chat", json={"question": question, "context": context})
        return response.status_code, response.get_json()

    def test_health_and_bootstrap_show_fixed_snapshot_time(self):
        client = self.client()
        self.assertEqual(client.get("/healthz").get_json()["status"], "ok")
        data = client.get("/api/bootstrap").get_json()
        self.assertEqual(data["snapshot"]["status"], "fixed")
        self.assertEqual(data["snapshot"]["created_at"], CREATED_AT)
        self.assertEqual(data["examples"], EXAMPLES)
        self.assertEqual({d["id"]: d["status"] for d in data["dimensions"]}["financial_trend"], "limited")
        self.assertEqual(data["product_snapshot"]["status"], "missing")
        self.assertEqual(data["dimension_examples"], [])
        self.assertEqual(client.get("/").status_code, 200)
        ready = self.client(product=self.product()).get("/api/bootstrap").get_json()
        statuses = {d["id"]: d["status"] for d in ready["dimensions"]}
        self.assertEqual([statuses[k] for k in ("valuation", "financial_trend", "market", "industry", "events", "risk")],
                         ["implemented"] * 4 + ["clues", "planned"])
        self.assertEqual(ready["product_snapshot"]["trading_days"], 242)

    def test_four_examples_return_traceable_runs(self):
        client = self.client()
        for question, intent in zip(EXAMPLES, ["net_profit_status", "operating_cash_flow_status",
                                               "profit_cash_ratio", "profit_cash_alignment"]):
            status, data = self.ask(client, question)
            self.assertEqual((status, data["status"]), (200, "ok"), question)
            self.assertEqual(data["context"], {"intent": intent})
            self.assertEqual(data["snapshot"]["created_at"], CREATED_AT)
            run = data["run"]
            evidence_ids = {item["id"] for item in run["evidence"]}
            conclusion = run["conclusions"][0]
            self.assertTrue(conclusion["evidence_links"])
            self.assertTrue({link["evidence_id"] for link in conclusion["evidence_links"]} <= evidence_ids)
            for item in run["evidence"]:
                self.assertEqual(item["time"]["fetched_at"], CREATED_AT)
                self.assertTrue(item["priority"]["tier"])
                if item["kind"] == "computed":
                    self.assertTrue(set(item["calculation"]["input_evidence_ids"]) <= evidence_ids)

    def test_limited_followups_use_only_allowed_context(self):
        client = self.client()
        _, first = self.ask(client, EXAMPLES[0])
        _, follow = self.ask(client, "那现金流呢？", first["context"])
        self.assertEqual(follow["status"], "ok")
        self.assertEqual(follow["resolved_question"], EXAMPLES[1])
        # "它们" needs a previous two-metric question.
        _, pair = self.ask(client, "它们的比值呢", follow["context"])
        self.assertEqual(pair["status"], "clarification_needed")
        _, alignment = self.ask(client, EXAMPLES[3])
        _, ratio = self.ask(client, "它们的比值呢", alignment["context"])
        self.assertEqual(ratio["context"], {"intent": "profit_cash_ratio"})

    def test_followup_without_or_with_forged_context_asks_for_clarification(self):
        client = self.client()
        for context in (None, {"intent": "buy_now"}, "profit_cash_ratio", {"intent": "valuation"}):
            _, data = self.ask(client, "那现金流呢", context)
            self.assertEqual(data["status"], "clarification_needed", context)
            self.assertIsNone(data["context"])
        for question in ("为什么", "继续", "它们"):
            _, data = self.ask(client, question, {"intent": "profit_cash_alignment"})
            self.assertEqual(data["status"], "clarification_needed", question)

    def test_planned_dimensions_show_gaps_without_reading_snapshot(self):
        client = self.client(CACHE / f"absent_{uuid4().hex}.json")
        for question in ("天齐锂业主要风险有哪些？", "经营质量如何？", "2024年净利润同比增长多少？"):
            status, data = self.ask(client, question)
            self.assertEqual((status, data["status"]), (200, "not_implemented"), question)
            self.assertNotIn("run", data)
            self.assertTrue(data["missing_evidence"])
            self.assertIsNone(data["context"])

    def test_trade_advice_and_prediction_are_refused(self):
        client = self.client()
        for question in ("天齐锂业明天会涨吗？", "现在要不要买入天齐锂业？"):
            _, data = self.ask(client, question)
            self.assertEqual(data["status"], "unsupported_question", question)
            self.assertNotIn("run", data)

    def test_missing_or_tampered_snapshot_is_unavailable(self):
        absent = self.client(CACHE / f"absent_{uuid4().hex}.json")
        self.assertEqual(absent.get("/api/bootstrap").get_json()["snapshot"]["status"], "missing")
        status, data = self.ask(absent, EXAMPLES[0])
        self.assertEqual((status, data["status"]), (503, "snapshot_unavailable"))

        path = self.snapshot()
        document = json.loads(path.read_text(encoding="utf-8"))
        document["rows"]["net_profit"]["value"] = "999"
        path.write_text(json.dumps(document), encoding="utf-8")
        tampered = self.client(path)
        self.assertEqual(tampered.get("/api/bootstrap").get_json()["snapshot"]["status"], "invalid")
        status, data = self.ask(tampered, EXAMPLES[3])
        self.assertEqual((status, data["status"]), (503, "snapshot_unavailable"))
        self.assertNotIn(str(path), json.dumps(data, ensure_ascii=False))

    def test_conflict_and_missing_evidence_stay_unknown(self):
        client = self.client(self.snapshot(profit=row(None, status="conflict"), cash=row(None, status="missing")))
        _, data = self.ask(client, EXAMPLES[3])
        conclusion = data["run"]["conclusions"][0]
        self.assertEqual((conclusion["type"], conclusion["assessment"]), ("unknown", "unknown"))
        states = {item["metric_id"]: (item["quality"]["status"], item["value"]) for item in data["run"]["evidence"]}
        self.assertEqual(states["net_profit"], ("conflict", None))
        self.assertEqual(states["operating_cash_flow"], ("missing", None))

    def test_non_positive_denominator_is_not_applicable(self):
        for profit in ("0", "-50"):
            client = self.client(self.snapshot(profit=row(profit)))
            _, data = self.ask(client, EXAMPLES[2])
            ratio = [item for item in data["run"]["evidence"] if item["kind"] == "computed"][0]
            self.assertEqual((ratio["quality"]["status"], ratio["value"]), ("not_applicable", None), profit)
            self.assertEqual(data["run"]["conclusions"][0]["type"], "unknown")

    def test_invalid_requests_are_rejected(self):
        client = self.client()
        self.assertEqual(client.post("/api/chat", data="text").status_code, 400)
        self.assertEqual(client.post("/api/chat", json=["list"]).status_code, 400)
        self.assertEqual(client.post("/api/chat", json={"question": 3}).status_code, 400)
        self.assertEqual(client.post("/api/chat", json={"question": "  "}).status_code, 400)
        self.assertEqual(client.post("/api/chat", json={"question": "问" * 501}).status_code, 400)
        self.assertEqual(client.post("/api/chat", json={"question": "问" * 20000}).status_code, 413)

    def test_llm_skips_executable_classification_and_failure_falls_back(self):
        llm = FakeLLM()
        client = self.client(llm=llm)
        _, data = self.ask(client, EXAMPLES[3])
        self.assertEqual(llm.classified, [])
        self.assertEqual(data["run"]["route"]["method"], "deterministic_fallback")
        self.assertEqual(data["run"]["conclusions"][0]["validation"], "passed")
        self.ask(client, "天齐锂业估值高吗？")
        self.assertEqual(llm.classified, ["天齐锂业估值高吗？"])

        failing = self.client(llm=FakeLLM(fail_translate=True))
        status, data = self.ask(failing, EXAMPLES[0])
        conclusion = data["run"]["conclusions"][0]
        self.assertEqual((status, conclusion["validation"]), (200, "fallback"))
        self.assertEqual(conclusion["validation_failures"], ["llm_unavailable"])

    def test_responses_expose_no_secrets_paths_or_storage_links(self):
        path = self.snapshot()
        client = self.client(path)
        bodies = [client.get("/api/bootstrap").get_data(as_text=True)]
        for question in EXAMPLES + ["天齐锂业估值高吗？"]:
            bodies.append(client.post("/api/chat", json={"question": question}).get_data(as_text=True))
        text = "\n".join(bodies)
        for marker in ("API_KEY", "Bearer", "AUTH_TOKEN", str(path), str(CACHE), "DIAGNOSIS_SNAPSHOT_PATH",
                       "tcloudbaseapp", "myqcloud", "tcb.qcloud"):
            self.assertNotIn(marker, text)

    def test_dimension_questions_return_runs_gaps_and_clues(self):
        client = self.client(product=self.product())
        status, data = self.ask(client, "天齐锂业估值处于什么位置？")
        self.assertEqual((status, data["status"]), (200, "ok"))
        self.assertEqual([run["route"]["dimension"] for run in data["runs"]], ["valuation"])
        self.assertEqual((data["gaps"], data["clues"]), ([], None))
        self.assertEqual(data["snapshot"]["created_at"], product_payload()["created_at"])
        _, overview = self.ask(client, "天齐锂业全面诊断一下")
        self.assertEqual([run["route"]["dimension"] for run in overview["runs"]],
                         ["financial_trend", "valuation", "market", "industry"])
        self.assertTrue(overview["gaps"])
        self.assertTrue({gap["dimension"] for gap in overview["gaps"]} <= {"operating_quality", "events", "risk"})
        self.assertEqual(overview["clues"]["status"], "unverified_clue")
        _, events = self.ask(client, "天齐锂业近期有哪些公告？")
        self.assertEqual(events["status"], "not_implemented")
        self.assertEqual(events["clues"]["total"], {"notices": 2, "news": 2})

    def test_dimension_question_without_product_snapshot_is_unavailable_but_narrow_questions_work(self):
        client = self.client()
        status, data = self.ask(client, "天齐锂业估值处于什么位置？")
        self.assertEqual((status, data["status"], data["snapshot"]["status"]), (503, "snapshot_unavailable", "missing"))
        self.assertEqual(self.ask(client, EXAMPLES[0])[1]["status"], "ok")
        path = self.product()
        text = path.read_text(encoding="utf-8").replace('"pb_mrq":2', '"pb_mrq":9')
        path.write_text(text, encoding="utf-8")
        status, data = self.ask(self.client(product=path), "天齐锂业估值处于什么位置？")
        self.assertEqual((status, data["snapshot"]["status"]), (503, "invalid"))


if __name__ == "__main__":
    unittest.main()
