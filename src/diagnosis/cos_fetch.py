"""Fallback for decision 0020: download the private snapshots from COS at startup.

Used only when DIAGNOSIS_COS_BUCKET is set. Files are written atomically to a
local directory and then read by the existing loaders, which still verify the
content digest. Status reports carry an error code only: no keys, bucket host
or object URL ever reach logs, /healthz or the browser.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

SNAPSHOT_FILES = ("profit_cash_002466.json", "product_snapshot_002466.json")
RETRY_SECONDS = 60


def _default_client(region: str, secret_id: str, secret_key: str):
    from qcloud_cos import CosConfig, CosS3Client  # imported lazily: only needed when the fallback is enabled
    return CosS3Client(CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Scheme="https"))


def _error_code(error: Exception) -> str:
    for attr in ("get_error_code", "get_status_code"):
        getter = getattr(error, attr, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                value = None
            if value:
                return str(value)
    return type(error).__name__


class CosSnapshotFetcher:
    """Download the snapshot files once; retry at most every RETRY_SECONDS after a failure."""

    def __init__(self, env: dict, *, client_factory=_default_client, clock=time.monotonic):
        self.bucket = env.get("DIAGNOSIS_COS_BUCKET", "")
        self.region = env.get("DIAGNOSIS_COS_REGION", "ap-shanghai")
        self.prefix = env.get("DIAGNOSIS_COS_PREFIX", "snapshots/")
        self.target = Path(env.get("DIAGNOSIS_SNAPSHOT_DIR", "/tmp/snapshots"))
        self._secret_id = env.get("DIAGNOSIS_COS_SECRET_ID", "")
        self._secret_key = env.get("DIAGNOSIS_COS_SECRET_KEY", "")
        self._client_factory = client_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._last_attempt: float | None = None
        self.status = {"mode": "cos_download", "state": "pending"}

    @property
    def enabled(self) -> bool:
        return bool(self.bucket)

    def path(self, name: str) -> Path:
        return self.target / name

    def ensure(self) -> dict:
        """Download if not done yet; failed attempts are retried no more than once per RETRY_SECONDS."""
        if self.status["state"] == "ok":
            return self.status
        with self._lock:
            if self.status["state"] == "ok":
                return self.status
            now = self._clock()
            if self._last_attempt is not None and now - self._last_attempt < RETRY_SECONDS:
                return self.status
            self._last_attempt = now
            self.status = self._download()
            return self.status

    def _download(self) -> dict:
        if not (self._secret_id and self._secret_key):
            return {"mode": "cos_download", "state": "failed", "error": "missing_credentials"}
        try:
            client = self._client_factory(self.region, self._secret_id, self._secret_key)
            self.target.mkdir(parents=True, exist_ok=True)
            for name in SNAPSHOT_FILES:
                response = client.get_object(Bucket=self.bucket, Key=f"{self.prefix}{name}")
                data = response["Body"].get_raw_stream().read()
                temp = self.target / f".{name}.{uuid4().hex}.tmp"
                temp.write_bytes(data)
                os.replace(temp, self.path(name))
        except Exception as error:  # report the code only; never the message, which may contain the host
            code = _error_code(error)
            print(f"[snapshot] COS download failed: {code}", file=sys.stderr, flush=True)
            return {"mode": "cos_download", "state": "failed", "error": code}
        print("[snapshot] COS download ok", file=sys.stderr, flush=True)
        return {"mode": "cos_download", "state": "ok"}
