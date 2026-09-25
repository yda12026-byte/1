from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlparse
from urllib.request import Request

from .models import Conclusion, Evidence
from .net import open_direct


class DeepSeek:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-flash"):
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.netloc != "api.deepseek.com":
            raise ValueError("DEEPSEEK_BASE_URL must be the official HTTPS host")
        self.api_key = api_key
        self.url = "https://api.deepseek.com/chat/completions"
        self.model = model

    def _complete(self, system: str, user: str) -> dict:
        payload = {"model": self.model, "temperature": 0,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        request = Request(self.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                          method="POST")
        with open_direct(request, timeout=20) as response:
            body = json.load(response)
        content = body["choices"][0]["message"]["content"].strip()
        if content.startswith("```json"):
            content = content[7:].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned a non-object")
        return parsed

    def classify(self, question: str) -> str:
        result = self._complete(
            '你是受限意图分类器。只输出 JSON 对象 {"intent":"profit_cash_alignment"|"unsupported"}。'
            '只有问题涉及净利润或盈利与经营现金流之间的关系时选 profit_cash_alignment；其他问题选 unsupported。不要回答问题。',
            question,
        )
        intent = result.get("intent")
        if intent not in ("profit_cash_alignment", "unsupported"):
            raise ValueError("LLM returned an unknown intent")
        return intent

    def translate(self, conclusion: Conclusion, evidence: list[Evidence]) -> dict:
        summary = {
            "claim_code": conclusion.claim_code, "type": conclusion.type, "assessment": conclusion.assessment,
            "fallback_text": conclusion.fallback_text, "required_anchor": conclusion.required_anchor,
            "limitations": conclusion.limitations,
            "cannot_say": [{"code": rule.code, "statement": rule.statement, "reason": rule.reason}
                           for rule in conclusion.cannot_say],
            "evidence": [
                {"id": item.id, "metric_id": item.metric_id, "status": item.quality["status"],
                 "sign": None if item.quality["status"] != "valid" or item.kind == "computed" else
                 "positive" if Decimal(item.value) > 0 else "negative" if Decimal(item.value) < 0 else "zero",
                 "period_end": item.time.get("period_end"), "period_basis": item.scope.get("period_basis")}
                for item in evidence
            ],
        }
        return self._complete(
            '你只把已有结论翻译成简洁中文，不新增事实、因果、数字或投资建议。数据来自一次性固定快照，不是实时数据。严格遵守 cannot_say。'
            '只输出 JSON 对象 {"text":"...","evidence_ids":["..."]}。正文必须逐字包含 required_anchor，'
            '不要出现数字或百分号；evidence_ids 包含所用的所有来源证据 ID。',
            json.dumps(summary, ensure_ascii=False),
        )
