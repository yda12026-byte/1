"""Flask entry point for the fixed-snapshot, limited-question product."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from diagnosis.catalog import DIMENSION_EXECUTABLE, DIMENSIONS, EXECUTABLE_FIELDS, SUBJECT, WINDOW  # noqa: E402
from diagnosis.deepseek import DeepSeek  # noqa: E402
from diagnosis.net import load_env  # noqa: E402
from diagnosis.pipeline import diagnose_dimensions, diagnose_profit_cash  # noqa: E402
from diagnosis.product_snapshot import load_product_snapshot  # noqa: E402
from diagnosis.routing import route_question  # noqa: E402
from diagnosis.snapshot import load_snapshot  # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "data" / "cache" / "profit_cash_002466.json"
PRODUCT_SNAPSHOT_NAME = "product_snapshot_002466.json"
_AUTO_LLM = object()
EXAMPLES = [
    "天齐锂业的净利润是正还是负？",
    "天齐锂业的经营活动现金流净额为正吗？",
    "天齐锂业的经营现金流与净利润的比值是多少？",
    "天齐锂业的利润和经营现金流匹配吗？",
]
DIMENSION_EXAMPLES = [
    "全面诊断一下天齐锂业",
    "天齐锂业的估值处于什么位置？",
    "天齐锂业近一年的财务趋势如何？",
    "天齐锂业各项业务的毛利率如何？",
    "天齐锂业与同行相比如何？",
    "天齐锂业近一年的股价表现和波动如何？",
    "近一年锂价走势如何？",
    "天齐锂业有哪些主要风险？",
    "天齐锂业近期有哪些公告？",
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
GAP_KEYS = ("id", "label", "dimension", "source_ref", "candidate_status", "product_state", "priority_tier",
            "priority_reason", "kind", "formula_id", "input_fields")


def _snapshot_state(path: Path) -> dict:
    try:
        snapshot = load_snapshot(path)["_snapshot"]
    except FileNotFoundError:
        return {"status": "missing", "message": "固定快照文件尚未提供；诊断暂不可用。"}
    except (ValueError, KeyError, TypeError, OSError):
        return {"status": "invalid", "message": "固定快照校验失败；诊断暂不可用。"}
    return {"status": "fixed", "id": snapshot["id"], "created_at": snapshot["created_at"]}


def _product_state(path: Path) -> tuple[dict, dict | None]:
    try:
        document = load_product_snapshot(path)
    except FileNotFoundError:
        return {"status": "missing", "message": "完整产品快照尚未提供；估值、财务趋势、行情与行业维度暂不可用。"}, None
    except (ValueError, KeyError, TypeError, OSError):
        return {"status": "invalid", "message": "完整产品快照校验失败；相关维度暂不可用。"}, None
    return {"status": "fixed", "id": document["snapshot_id"], "created_at": document["created_at"],
            "trading_days": document["trading_calendar"]["count"]}, document


def _clues(document: dict | None, limit: int = 12) -> dict | None:
    if document is None:
        return None
    clues = document["clues"]
    return {"status": clues["status"], "note": clues["note"], "notices": clues["notices"][:limit],
            "news": clues["news"][:limit], "total": {"notices": len(clues["notices"]), "news": len(clues["news"])}}


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


def _gap_fields(route: dict, skip_dimensions: tuple[str, ...] = ()) -> list[dict]:
    return [{key: field.get(key) for key in GAP_KEYS}
            for field in route["fields"] if field["id"] in route["display_plan"]["default_field_ids"]
            and field["dimension"] not in skip_dimensions]


SCOPE_TEXT = "本模型只基于截至 2026-08-31 的固定数据，对天齐锂业的经营质量、财务趋势、估值、行情特征、行业位置和风险六个维度做有证据的诊断，并列出公告与新闻检索线索"
SUGGESTIONS = {
    "买卖或持仓建议": ["全面诊断一下天齐锂业", "天齐锂业的估值处于什么位置？", "天齐锂业有哪些主要风险？"],
    "股价涨跌预测": ["全面诊断一下天齐锂业", "天齐锂业近一年的股价表现和波动如何？", "天齐锂业与同行相比如何？"],
    "收益承诺": ["全面诊断一下天齐锂业", "天齐锂业有哪些主要风险？", "天齐锂业的估值处于什么位置？"],
    None: ["全面诊断一下天齐锂业", "天齐锂业近一年的财务趋势如何？", "天齐锂业各项业务的毛利率如何？"],
}


def _out_of_scope_payload(categories: list[str]) -> dict:
    """Explain why a question is not answered and offer in-scope questions instead of a bare refusal."""
    if categories:
        message = f"您的提问涉及{'、'.join(categories)}，超出本模型能力范围。{SCOPE_TEXT}，不提供投资建议、涨跌预测或收益承诺。您可以试试下面的问题："
    else:
        message = f"暂时无法识别您的问题。{SCOPE_TEXT}。您可以试试下面的问题："
    suggestions = list(dict.fromkeys(q for key in (categories or [None]) for q in SUGGESTIONS[key]))[:4]
    return {"status": "unsupported_question", "reason": "out_of_scope" if categories else "unrecognized",
            "categories": categories, "message": message, "suggestions": suggestions, "context": None}


def _planned_payload(route: dict) -> dict:
    fields = _gap_fields(route)
    return {"status": "not_implemented", "message": "数据或计算待接入，当前不能生成金融结论。",
            "route": {"intent": route["intent"], "dimensions": route["dimensions"],
                      "execution_status": route["execution_status"], "field_ids": route["field_ids"],
                      "display_plan": route["display_plan"], "fields": fields},
            "missing_evidence": fields, "context": None}


def create_app(*, snapshot_path: Path | None = None, product_snapshot_path: Path | None = None,
               llm=_AUTO_LLM) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    env = load_env(ROOT / ".env") if (ROOT / ".env").exists() else dict(os.environ)
    configured_path = env.get("DIAGNOSIS_SNAPSHOT_PATH", "")
    path = Path(configured_path) if configured_path and snapshot_path is None else snapshot_path or DEFAULT_SNAPSHOT
    if not path.is_absolute():
        path = ROOT / path
    configured_product = env.get("DIAGNOSIS_PRODUCT_SNAPSHOT_PATH", "")
    product_path = product_snapshot_path or (Path(configured_product) if configured_product
                                             else path.with_name(PRODUCT_SNAPSHOT_NAME))
    if not product_path.is_absolute():
        product_path = ROOT / product_path
    if llm is _AUTO_LLM:
        llm = DeepSeek(env["DEEPSEEK_API_KEY"], env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                       env.get("DEEPSEEK_MODEL", "deepseek-flash")) if env.get("DEEPSEEK_API_KEY") else None

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        # Stays 200 when snapshots are missing so the platform does not restart-loop; status is reported, paths are not.
        product, _ = _product_state(product_path)
        return jsonify({"status": "ok", "service": "diagnosis-web",
                        "snapshots": {"profit_cash": _snapshot_state(path)["status"], "product": product["status"]},
                        "llm_configured": llm is not None})

    @app.get("/api/bootstrap")
    def bootstrap():
        product, _ = _product_state(product_path)
        ready = product["status"] == "fixed"

        def status(key: str) -> str:
            if key in DIMENSION_EXECUTABLE:
                return "implemented" if ready else "limited" if key == "financial_trend" else "planned"
            return "clues" if key == "events" and ready else "planned"

        return jsonify({"subject": {"code": SUBJECT, "name": "天齐锂业"}, "window": WINDOW,
                        "examples": EXAMPLES, "dimension_examples": DIMENSION_EXAMPLES if ready else [],
                        "dimensions": [{"id": key, "label": value, "status": status(key)} for key, value in DIMENSIONS.items()],
                        "snapshot": _snapshot_state(path), "product_snapshot": product,
                        "scope": "经营质量、财务趋势、估值、行情特征、行业位置、风险六维可诊断；重要事件仅列待核检索线索。"})

    def dimension_payload(resolved: str, question: str, route: dict):
        state, document = _product_state(product_path)
        if document is None:
            return jsonify({"status": "snapshot_unavailable", "snapshot": state, "message": state["message"],
                            "context": None}), 503
        try:
            runs, summary = diagnose_dimensions(resolved, route, lambda: document, llm)
        except (ValueError, KeyError, TypeError, IndexError, ArithmeticError):
            return jsonify({"status": "snapshot_unavailable", "snapshot": state,
                            "message": "完整产品快照的计算校验失败；诊断暂不可用。", "context": None}), 503
        return jsonify({"status": "ok", "summary": summary, "runs": [run.to_dict() for run in runs], "snapshot": state,
                        "gaps": _gap_fields(route, DIMENSION_EXECUTABLE) if route["execution_status"] == "partial" else [],
                        "clues": _clues(document) if "events" in route["dimensions"] else None,
                        "route": {"intent": route["intent"], "dimensions": route["dimensions"],
                                  "execution_status": route["execution_status"]},
                        "context": None, "resolved_question": resolved if resolved != question else None})

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
            return jsonify(_out_of_scope_payload(route.get("out_of_scope", [])))
        if route["execution_status"] in ("implemented", "partial") and route["intent"] not in EXECUTABLE_FIELDS:
            return dimension_payload(resolved, question, route)
        if route["execution_status"] == "planned":
            payload = _planned_payload(route)
            if "events" in route["dimensions"]:
                payload["clues"] = _clues(_product_state(product_path)[1])
            return jsonify(payload)
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
                _out_of_scope_payload([]))
        return jsonify({"status": "ok", "run": result.to_dict(), "snapshot": state,
                        "context": {"intent": result.route["intent"]},
                        "resolved_question": resolved if resolved != question else None})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8080")))
