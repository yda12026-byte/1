"""Acceptance checks against a deployed URL (default: the CloudBase service).

Usage: py scripts/smoke_public.py [BASE_URL]
Prints one line per check and a summary; only statuses and counts, never
financial values. Exit code is 0 only when every check passes.
"""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

DEFAULT = "https://lithium-diagnosis-319862-8-1496111595.sh.run.tcloudbase.com"
OPENER = build_opener(ProxyHandler({}))
DIMENSIONS = ["operating_quality", "financial_trend", "valuation", "market", "industry", "risk"]


def call(base: str, path: str, body: dict | None = None) -> tuple[int, dict | str, float]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = Request(base + path, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"})
    start = time.monotonic()
    try:
        with OPENER.open(request, timeout=90) as response:
            status, raw, kind = response.status, response.read().decode("utf-8"), response.headers.get("Content-Type", "")
    except HTTPError as error:
        status, raw, kind = error.code, error.read().decode("utf-8", "replace"), error.headers.get("Content-Type", "")
    elapsed = time.monotonic() - start
    return status, json.loads(raw) if "json" in kind else raw, elapsed


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT).rstrip("/")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    status, health, _ = call(base, "/healthz")
    check("healthz", status == 200 and isinstance(health, dict) and health.get("status") == "ok", str(health)[:160])
    snapshots = health.get("snapshots", {}) if isinstance(health, dict) else {}
    check("snapshots fixed", snapshots == {"profit_cash": "fixed", "product": "fixed"}, str(snapshots))
    check("llm configured", isinstance(health, dict) and health.get("llm_configured") is True)

    status, page, _ = call(base, "/")
    check("page loads", status == 200 and "研究对话" in str(page))

    status, boot, _ = call(base, "/api/bootstrap")
    statuses = {d["id"]: d["status"] for d in boot.get("dimensions", [])} if isinstance(boot, dict) else {}
    check("bootstrap dimensions", [statuses.get(d) for d in DIMENSIONS] == ["implemented"] * 6 and statuses.get("events") == "clues",
          str(statuses))
    product = boot.get("product_snapshot", {}) if isinstance(boot, dict) else {}
    check("product snapshot time shown", bool(product.get("created_at")) and bool(product.get("id")), product.get("id", ""))

    status, data, took = call(base, "/api/chat", {"question": "全面诊断一下天齐锂业"})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    conclusions = [c for run in runs for c in run["conclusions"]]
    check("overview runs six dimensions", [run["route"]["dimension"] for run in runs] == DIMENSIONS,
          f"{len(conclusions)} conclusions, {took:.1f}s")
    check("overview summary present", isinstance(data, dict) and bool((data.get("summary") or {}).get("text")),
          (data.get("summary") or {}).get("validation", "") if isinstance(data, dict) else "")
    check("overview clues listed", isinstance(data, dict) and bool((data.get("clues") or {}).get("notices")))
    fallbacks = [c["claim_code"] for c in conclusions if c["validation"] != "passed"]
    check("llm narrations validated", not fallbacks, f"fallback: {fallbacks}" if fallbacks else "all passed")
    evidence = {e["id"]: e for run in runs for e in run["evidence"]}
    linked = all(link["evidence_id"] in evidence for c in conclusions for link in c["evidence_links"])
    computed = [e for e in evidence.values() if e["kind"] == "computed"]
    traced = all(set(e["calculation"]["input_evidence_ids"]) <= set(evidence) and e["calculation"].get("formula_text")
                 for e in computed)
    check("evidence drill-down traceable", linked and traced, f"{len(evidence)} evidence, {len(computed)} computed")
    check("fixed snapshot time on evidence", all(e["time"].get("fetched_at") == product.get("created_at")
                                                 for e in evidence.values()))

    status, data, _ = call(base, "/api/chat", {"question": "天齐锂业的利润和经营现金流匹配吗？"})
    context = data.get("context") if isinstance(data, dict) else None
    check("narrow question", status == 200 and data.get("status") == "ok" and bool(data.get("run")))
    status, data, _ = call(base, "/api/chat", {"question": "它们的比值呢", "context": context})
    check("limited follow-up", isinstance(data, dict) and data.get("context") == {"intent": "profit_cash_ratio"})
    status, data, _ = call(base, "/api/chat", {"question": "为什么"})
    check("ambiguous follow-up asks to clarify", isinstance(data, dict) and data.get("status") == "clarification_needed")
    status, data, _ = call(base, "/api/chat", {"question": "天齐锂业明天会涨吗？要不要买入？"})
    check("advice redirected with reason and suggestions", isinstance(data, dict) and data.get("reason") == "out_of_scope"
          and str(data.get("message", "")).startswith("您的提问涉及") and bool(data.get("suggestions")))
    status, data, _ = call(base, "/api/chat", {"question": "天齐锂业近期有哪些公告？"})
    check("events show clues only", isinstance(data, dict) and data.get("status") == "not_implemented" and bool(data.get("clues")))
    status, data, _ = call(base, "/api/chat", {"question": "2024年净利润同比增长多少？"})
    check("uncovered year stays planned", isinstance(data, dict) and data.get("status") == "not_implemented")
    status, _, _ = call(base, "/api/chat", {"question": ""})
    check("invalid request rejected", status == 400)

    status, _, _ = call(base, "/mnt/snapshots/product_snapshot_002466.json")
    check("snapshot file not served", status == 404)
    text = json.dumps([health, boot], ensure_ascii=False)
    check("no secrets or paths exposed", not any(marker in text for marker in ("API_KEY", "Bearer", "/mnt/", "SecretId", "myqcloud")))

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
