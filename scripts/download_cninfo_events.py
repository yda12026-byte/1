"""One-time download of the official announcement list and selected announcement PDFs (decision 0022).

Phase 1 saves the complete 巨潮资讯 (cninfo) announcement list for 002466 in the
observation window. Phase 2 classifies titles with the deterministic rules in
``diagnosis.events`` and downloads the PDFs of the important categories. Files
are written once under the Git-ignored annual raw directory and never
overwritten; rerunning resumes missing PDFs only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from diagnosis.events import IMPORTANT_CATEGORIES, classify  # noqa: E402
from diagnosis.net import open_direct  # noqa: E402

OUTPUT = ROOT / "data" / "raw" / "annual-2025-08-31_2026-08-31"
LIST_FILE = "cninfo_announcements.json"
PDF_DIR = "cninfo_pdf"
BASE = "https://www.cninfo.com.cn"
STATIC = "https://static.cninfo.com.cn/"
HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
QUERY = {"stock_code": "002466", "column": "szse", "plate": "sz", "tabName": "fulltext",
         "seDate": "2025-08-31~2026-08-31", "pageSize": 30}


def _post(path: str, form: dict) -> dict:
    request = Request(f"{BASE}{path}", data=urlencode(form).encode(), headers=HEADERS)
    with open_direct(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError("cninfo HTTP status is not 200")
        return json.load(response)


def download_list() -> dict:
    path = OUTPUT / LIST_FILE
    if path.exists():
        return {"status": "saved_existing", "file": path.name, "count": len(json.loads(path.read_text(encoding="utf-8"))["announcements"])}
    matches = [row for row in _post("/new/information/topSearch/query", {"keyWord": QUERY["stock_code"], "maxNum": 5})
               if row.get("code") == QUERY["stock_code"]]
    if len(matches) != 1:
        raise ValueError("cninfo orgId lookup is ambiguous")
    org_id = matches[0]["orgId"]
    rows, page, total = [], 1, None
    while True:
        body = _post("/new/hisAnnouncement/query", {
            "stock": f"{QUERY['stock_code']},{org_id}", "tabName": QUERY["tabName"], "pageSize": QUERY["pageSize"],
            "pageNum": page, "column": QUERY["column"], "category": "", "plate": QUERY["plate"],
            "seDate": QUERY["seDate"], "searchkey": "", "secid": "", "sortName": "", "sortType": "", "isHLtitle": "true"})
        total = body.get("totalAnnouncement")
        rows += body.get("announcements") or []
        if not body.get("hasMore"):
            break
        page += 1
        time.sleep(0.5)
    if total != len(rows) or len({row["announcementId"] for row in rows}) != len(rows):
        raise ValueError("cninfo list is incomplete or has duplicate announcement IDs")
    keep = ("announcementId", "announcementTitle", "announcementTime", "adjunctUrl", "adjunctSize", "adjunctType", "secCode", "secName")
    document = {"source": "cninfo", "endpoint": "/new/hisAnnouncement/query", "http_status": 200,
                "params": {**QUERY, "orgId": org_id}, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "total": total, "announcements": [{key: row.get(key) for key in keep} for row in rows]}
    with path.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    return {"status": "downloaded", "file": path.name, "count": len(rows)}


def download_pdfs() -> list[dict]:
    document = json.loads((OUTPUT / LIST_FILE).read_text(encoding="utf-8"))
    folder = OUTPUT / PDF_DIR
    folder.mkdir(exist_ok=True)
    results = []
    for row in document["announcements"]:
        category = classify(row["announcementTitle"])
        if category not in IMPORTANT_CATEGORIES or row.get("adjunctType") != "PDF":
            continue
        path = folder / f"{row['announcementId']}.pdf"
        if path.exists():
            payload, status = path.read_bytes(), "saved_existing"
        else:
            with open_direct(Request(STATIC + row["adjunctUrl"], headers={"User-Agent": HEADERS["User-Agent"]}), timeout=70) as response:
                payload = response.read(25_000_001)
            if not payload.startswith(b"%PDF-") or len(payload) > 25_000_000:
                raise ValueError(f"announcement is not a bounded PDF: {row['announcementId']}")
            with path.open("xb") as handle:
                handle.write(payload)
            status = "downloaded"
            time.sleep(0.4)
        results.append({"id": row["announcementId"], "category": category, "status": status,
                        "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()[:16]})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps(download_list(), ensure_ascii=False))
    if args.list_only:
        return 0
    results = download_pdfs()
    counts: dict[str, int] = {}
    for item in results:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    (OUTPUT / "audit_cninfo.json").write_text(json.dumps({
        "state": "raw_download_only_unvalidated", "checked_at": datetime.now(timezone.utc).isoformat(),
        "pdfs": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pdfs": len(results), "by_category": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
