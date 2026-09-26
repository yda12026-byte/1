from __future__ import annotations

import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from diagnosis.cos_fetch import RETRY_SECONDS, CosSnapshotFetcher  # noqa: E402
from diagnosis.product_snapshot import publish_product_snapshot  # noqa: E402
from diagnosis.snapshot import publish_snapshot  # noqa: E402
from product_fixture import product_payload  # noqa: E402
from webapp import create_app  # noqa: E402

CACHE = ROOT / "data" / "cache"
SECRET_ID, SECRET_KEY = "AKIDsyntheticid000", "synthetic-secret-value-000"


class FakeServiceError(Exception):
    def __init__(self, code: str):
        super().__init__(f"{code} at bucket-1250000000.cos.ap-shanghai.myqcloud.com")  # message would leak the host
        self.code = code

    def get_error_code(self):
        return self.code


class FakeClient:
    def __init__(self, objects: dict[str, bytes], fail: list):
        self.objects, self.fail, self.requests = objects, fail, []

    def get_object(self, Bucket, Key):
        self.requests.append((Bucket, Key))
        if self.fail:
            raise self.fail.pop(0)
        return {"Body": type("Body", (), {"get_raw_stream": lambda _self: io.BytesIO(self.objects[Key])})()}


class CosFetchTests(unittest.TestCase):
    def setUp(self):
        self.work = CACHE / f"test_cos_{uuid4().hex}"
        source = self.work / "source"
        source.mkdir(parents=True)
        row = {"value": "100", "period_end": "2025-12-31", "unit": "CNY", "period_basis": "annual",
               "consolidation": "consolidated", "status": "valid"}
        publish_snapshot(source / "profit_cash_002466.json", {"net_profit": row, "operating_cash_flow": row},
                         created_at="2026-09-01T02:00:00+00:00")
        publish_product_snapshot(source / "product_snapshot_002466.json", product_payload())
        self.objects = {f"snapshots/{p.name}": p.read_bytes() for p in source.iterdir()}
        self.clock = [1000.0]

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def fetcher(self, fail=(), secret=True):
        env = {"DIAGNOSIS_COS_BUCKET": "bucket-1250000000", "DIAGNOSIS_SNAPSHOT_DIR": str(self.work / "download"),
               **({"DIAGNOSIS_COS_SECRET_ID": SECRET_ID, "DIAGNOSIS_COS_SECRET_KEY": SECRET_KEY} if secret else {})}
        self.client = FakeClient(self.objects, list(fail))
        return CosSnapshotFetcher(env, client_factory=lambda *args: self.client, clock=lambda: self.clock[0])

    def test_download_serves_both_snapshots_and_full_diagnosis(self):
        client = create_app(llm=None, cos_fetcher=self.fetcher()).test_client()
        health = client.get("/healthz").get_json()
        self.assertEqual(health["snapshots"], {"profit_cash": "fixed", "product": "fixed"})
        self.assertEqual(health["snapshot_source"], {"mode": "cos_download", "state": "ok"})
        self.assertEqual([key for _, key in self.client.requests],
                         ["snapshots/profit_cash_002466.json", "snapshots/product_snapshot_002466.json"])
        self.assertEqual(client.post("/api/chat", json={"question": "天齐锂业估值处于什么位置？"}).get_json()["status"], "ok")
        self.assertEqual(client.post("/api/chat", json={"question": "天齐锂业的净利润是正还是负？"}).get_json()["status"], "ok")

    def test_missing_credentials_or_access_denied_are_reported_without_leaks(self):
        no_keys = create_app(llm=None, cos_fetcher=self.fetcher(secret=False)).test_client()
        health = no_keys.get("/healthz").get_json()
        self.assertEqual(health["snapshot_source"]["error"], "missing_credentials")
        self.assertEqual(health["snapshots"], {"profit_cash": "missing", "product": "missing"})

        denied = create_app(llm=None, cos_fetcher=self.fetcher(fail=[FakeServiceError("AccessDenied")])).test_client()
        text = denied.get("/healthz").get_data(as_text=True)
        self.assertIn('"error":"AccessDenied"', text.replace(" ", ""))
        for secret in (SECRET_ID, SECRET_KEY, "myqcloud", "bucket-1250000000"):
            self.assertNotIn(secret, text)
        status, data = denied.post("/api/chat", json={"question": "天齐锂业估值处于什么位置？"}).status_code, None
        self.assertEqual(status, 503)

    def test_failed_download_retries_at_most_once_per_interval(self):
        fetcher = self.fetcher(fail=[FakeServiceError("RequestTimeout")])
        client = create_app(llm=None, cos_fetcher=fetcher).test_client()
        self.assertEqual(fetcher.status["state"], "failed")
        client.get("/healthz")
        self.assertEqual(len(self.client.requests), 1)  # within the retry window: no new attempt
        self.clock[0] += RETRY_SECONDS + 1
        health = client.get("/healthz").get_json()  # the request hook retries and succeeds
        self.assertEqual(health["snapshots"], {"profit_cash": "fixed", "product": "fixed"})
        self.assertEqual(len(self.client.requests), 3)

    def test_tampered_download_is_rejected_by_existing_checksum(self):
        key = "snapshots/product_snapshot_002466.json"
        document = json.loads(self.objects[key])
        document["valuation_cutoff"]["values"]["pb_mrq"] = 9
        self.objects[key] = json.dumps(document).encode()
        health = create_app(llm=None, cos_fetcher=self.fetcher()).test_client().get("/healthz").get_json()
        self.assertEqual((health["snapshot_source"]["state"], health["snapshots"]["product"]), ("ok", "invalid"))

    def test_file_mode_is_unchanged_without_bucket(self):
        fetcher = CosSnapshotFetcher({})
        self.assertFalse(fetcher.enabled)
        health = create_app(llm=None, snapshot_path=self.work / "absent.json",
                            product_snapshot_path=self.work / "absent_product.json").test_client().get("/healthz").get_json()
        self.assertEqual(health["snapshot_source"], {"mode": "file"})


if __name__ == "__main__":
    unittest.main()
