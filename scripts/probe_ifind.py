"""Probe iFinD MCP service discovery without printing the authorization token."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.net import load_env, open_direct  # noqa: E402

SERVICES = {
    "unified": "hexin-ifind-ds-mcp",
    "enterprise": "kuaicha-enterprise-mcp",
    "law": "hexin-law-mcp",
    "stock": "hexin-ifind-ds-stock-mcp",
    "fund": "hexin-ifind-ds-fund-mcp",
    "index": "hexin-ifind-ds-index-mcp",
    "edb": "hexin-ifind-ds-edb-mcp",
    "news": "hexin-ifind-ds-news-mcp",
    "bond": "hexin-ifind-ds-bond-mcp",
    "global_stock": "hexin-ifind-ds-global-stock-mcp",
}


def parse_mcp_response(raw: str) -> dict | None:
    if not raw.strip():
        return None
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        events = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
        result = json.loads(events[-1]) if events else None
    return result if isinstance(result, dict) else None


def post(url: str, token: str, payload: dict, session_id: str | None = None) -> tuple[int, str | None, dict | None]:
    headers = {"Authorization": token, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with open_direct(request, timeout=15) as response:
        raw = response.read().decode("utf-8")
        return response.status, response.headers.get("mcp-session-id"), parse_mcp_response(raw)


def probe(name: str, base: str, token: str) -> dict:
    url = f"{base}/{SERVICES[name]}"
    try:
        status, session, _ = post(url, token, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "stock-diagnosis-probe", "version": "0.1.0"}},
        })
        if status != 200 or not session:
            return {"server": name, "status": "initialize_failed", "http_status": status}
        post(url, token, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        status, _, response = post(url, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session)
        tools = (response or {}).get("result", {}).get("tools")
        return {
            "server": name, "status": "ok" if status == 200 and isinstance(tools, list) else "tools_list_failed",
            "http_status": status, "tool_count": len(tools) if isinstance(tools, list) else None,
            "tool_names": [item.get("name") for item in tools] if isinstance(tools, list) else [],
        }
    except Exception as error:
        return {"server": name, "status": "request_failed", "error_type": type(error).__name__}


def main() -> int:
    env = load_env(ROOT / ".env")
    token, configured = env.get("IFIND_MCP_AUTH_TOKEN"), env.get("IFIND_MCP_URL")
    if not token or not configured:
        print("IFIND_MCP_AUTH_TOKEN or IFIND_MCP_URL is missing", file=sys.stderr)
        return 2
    parsed = urlparse(configured)
    if parsed.scheme != "https" or parsed.hostname != "api-mcp.51ifind.com" or parsed.port != 8643 \
            or not parsed.path.startswith("/ds-mcp-servers/"):
        print("IFIND_MCP_URL must be the official iFinD MCP endpoint", file=sys.stderr)
        return 2
    selected = sys.argv[1:] or list(SERVICES)
    if any(name not in SERVICES for name in selected):
        print("Unknown iFinD service type", file=sys.stderr)
        return 2
    prefix = parsed.path.rsplit("/", 1)[0]
    base = f"{parsed.scheme}://{parsed.netloc}{prefix}"
    results = [probe(name, base, token) for name in selected]
    print(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "results": results}, ensure_ascii=False, indent=2))
    return 1 if any(item["status"] != "ok" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
