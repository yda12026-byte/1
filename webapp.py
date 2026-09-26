"""Flask entry point for the fixed-snapshot, limited-question product."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.catalog import DIMENSIONS, EXECUTABLE_FIELDS, SUBJECT, WINDOW  # noqa: E402
from diagnosis.deepseek import DeepSeek  # noqa: E402
from diagnosis.net import load_env  # noqa: E402
from diagnosis.pipeline import diagnose_profit_cash  # noqa: E402
from diagnosis.routing import route_question  # noqa: E402
from diagnosis.snapshot import load_snapshot  # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "data" / "cache" / "profit_cash_002466.json"
_AUTO_LLM = object()
EXAMPLES = [
    "天齐锂业的净利润是正还是负？",
    "天齐锂业的经营活动现金流净额为正吗？",
    "天齐锂业的经营现金流与净利润的比值是多少？",
    "天齐锂业的利润和经营现金流匹配吗？",
]
FOLLOWUPS = {
    "那现金流呢": "operating_cash_flow_status",
    "那经营现金流呢": "operating_cash_flow_status",
    "那净利润呢": "net_profit_status",
    "它们的比值呢": "profit_cash_ratio",
    "那它们的比值呢": "profit_cash_ratio",
    "它们匹配吗": "profit_cash_alignment",
    "那它们匹配吗": "profit_cash_alignment",
}
PAIR_CONTEXT = {"profit_cash_ratio", "profit_cash_alignment"}
AMBIGUOUS = re.compile(r"^(?:那|那么|它|它们|这个|这些|上面|再说说|继续|为什么|原因)(?:呢|怎么样|如何|\??)?$")


def _snapshot_state(path: Path) -> dict:
    try:
        snapshot = load_snapshot(path)["_snapshot"]
    except FileNotFoundError:
        return {"status": "missing", "message": "固定快照文件尚未提供；诊断暂不可用。"}
    except (ValueError, KeyError, TypeError, OSError):
        return {"status": "invalid", "message": "固定快照校验失败；诊断暂不可用。"}
    return {"status": "fixed", "id": snapshot["id"], "created_at": snapshot["created_at"]}


def _resolve_question(question: str, context: object) -> tuple[str | None, str | None]:
    """Return a complete question or a clarification message. Client context is never trusted."""
    compact = re.sub(r"\s+", "", question).rstrip("？?。！!")
    previous = context.get("intent") if isinstance(context, dict) else None
    if previous not in EXECUTABLE_FIELDS:
        previous = None
    if compact in FOLLOWUPS:
        target = FOLLOWUPS[compact]
        if previous is None or ("它们" in compact and previous not in PAIR_CONTEXT):
            return None, "请补全要问的指标，例如点击下方完整问题；本轮无法确定追问指向。"
        return EXAMPLES[["net_profit_status", "operating_cash_flow_status", "profit_cash_ratio",
                         "profit_cash_alignment"].index(target)], None
    if AMBIGUOUS.fullmatch(compact):
        return None, "请说明要看的指标或维度；这个追问无法安全映射到已实现的问题。"
    return question, None


def _planned_payload(route: dict) -> dict:
    fields = [{key: field.get(key) for key in ("id", "label", "dimension", "source_ref",
                                              "candidate_status", "product_state", "priority_tier",
                                              "priority_reason", "kind", "formula_id", "input_fields")}
              for field in route["fields"] if field["id"] in route["display_plan"]["default_field_ids"]]
    return {"status": "not_implemented", "message": "数据或计算待接入，当前不能生成金融结论。",
            "route": {"intent": route["intent"], "dimensions": route["dimensions"],
                      "execution_status": route["execution_status"], "field_ids": route["field_ids"],
                      "display_plan": route["display_plan"], "fields": fields},
            "missing_evidence": fields, "context": None}


def create_app(*, snapshot_path: Path | None = None, llm=_AUTO_LLM) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    env = load_env(ROOT / ".env") if (ROOT / ".env").exists() else dict(os.environ)
    configured_path = env.get("DIAGNOSIS_SNAPSHOT_PATH", "")
    path = Path(configured_path) if configured_path and snapshot_path is None else snapshot_path or DEFAULT_SNAPSHOT
    if not path.is_absolute():
        path = ROOT / path
    if llm is _AUTO_LLM:
        llm = DeepSeek(env["DEEPSEEK_API_KEY"], env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                       env.get("DEEPSEEK_MODEL", "deepseek-flash")) if env.get("DEEPSEEK_API_KEY") else None

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok", "service": "diagnosis-web"})

    @app.get("/api/bootstrap")
    def bootstrap():
        return jsonify({"subject": {"code": SUBJECT, "name": "天齐锂业"}, "window": WINDOW,
                        "examples": EXAMPLES, "dimensions": [{"id": key, "label": value,
                                                                  "status": "limited" if key == "financial_trend" else "planned"}
                                                                 for key, value in DIMENSIONS.items()],
                        "snapshot": _snapshot_state(path),
                        "scope": "仅四类财务问法可运行；其他维度展示字段与证据缺口。"})

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("question"), str):
            return jsonify({"status": "invalid_request", "message": "请提供 JSON 格式的 question 字符串。"}), 400
        question = body["question"].strip()
        if not question or len(question) > 500:
            return jsonify({"status": "invalid_request", "message": "问题长度需在 1 至 500 字之间。"}), 400
        resolved, clarification = _resolve_question(question, body.get("context"))
        if clarification:
            return jsonify({"status": "clarification_needed", "message": clarification, "context": None})
        route = route_question(resolved, llm)
        if route["execution_status"] == "unsupported":
            return jsonify({"status": "unsupported_question", "message": "当前只提供受限财务诊断与证据缺口查询，请改用完整研究问题；不提供买卖或确定性涨跌建议。",
                            "context": None})
        if route["execution_status"] == "planned":
            return jsonify(_planned_payload(route))
        state = _snapshot_state(path)
        if state["status"] != "fixed":
            return jsonify({"status": "snapshot_unavailable", "snapshot": state,
                            "message": state["message"], "context": None}), 503
        try:
            result = diagnose_profit_cash(resolved, lambda: load_snapshot(path), llm, route=route)
        except (FileNotFoundError, ValueError, KeyError, TypeError, OSError):
            return jsonify({"status": "snapshot_unavailable", "snapshot": _snapshot_state(path),
                            "message": "固定快照读取或校验失败；诊断暂不可用。", "context": None}), 503
        if not hasattr(result, "to_dict"):
            return jsonify(_planned_payload(route)) if result["status"] == "not_implemented" else jsonify(
                {"status": "unsupported_question", "message": "当前问题无法安全映射到四类已实现诊断。", "context": None})
        return jsonify({"status": "ok", "run": result.to_dict(), "snapshot": state,
                        "context": {"intent": result.route["intent"]},
                        "resolved_question": resolved if resolved != question else None})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8080")))
