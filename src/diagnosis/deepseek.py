from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlparse
from urllib.request import Request

from .models import Conclusion, Evidence
from .net import open_direct
from .catalog import INTENTS


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
        with open_direct(request, timeout=12) as response:
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
            '你是受限意图分类器。只输出 JSON 对象，例如 {"intent":"financial_trend"}。'
            'intent 只能是 overview、profit_cash_alignment、net_profit_status、operating_cash_flow_status、profit_cash_ratio、operating_quality、financial_trend、valuation、market、industry、events、risk、unsupported。'
            '仅问净利润正负选 net_profit_status，仅问经营活动现金流净额正负选 operating_cash_flow_status；同时问利润与经营现金流的比值选 profit_cash_ratio，问两者关系选 profit_cash_alignment。'
            '更宽泛的财务、估值或行业问题选对应维度；整体诊断选 overview；无法归类或要求直接买卖、收益承诺时选 unsupported。不要回答问题。',
            question,
        )
        intent = result.get("intent")
        if intent not in INTENTS and intent != "unsupported":
            raise ValueError("LLM returned an unknown intent")
        return intent

    def translate(self, conclusion: Conclusion, evidence: list[Evidence]) -> dict:
        summary = {
            "claim_code": conclusion.claim_code, "type": conclusion.type, "assessment": conclusion.assessment,
            "priority": conclusion.priority,
            "fallback_text": conclusion.fallback_text, "required_anchor": conclusion.required_anchor,
            "limitations": conclusion.limitations,
            "cannot_say": [{"code": rule.code, "statement": rule.statement, "reason": rule.reason}
                           for rule in conclusion.cannot_say],
            "evidence": [
                {"id": item.id, "metric_id": item.metric_id, "status": item.quality["status"],
                 "priority": item.priority,
                 "sign": None if item.quality["status"] != "valid" or item.kind == "computed" else
                 "positive" if Decimal(item.value) > 0 else "negative" if Decimal(item.value) < 0 else "zero",
                 "period_end": item.time.get("period_end"), "period_basis": item.scope.get("period_basis")}
                for item in evidence
            ],
        }
        return self._complete(
            '你只把已有结论翻译成简洁中文，不新增事实、因果、数字或投资建议。数据来自一次性固定快照，不是实时数据。严格遵守 cannot_say。'
            'priority 的 driver/support/context/low 表示研究重要性，优先突出有效的高优先级证据；低优先级证据仅在直接提问或必要背景时简述。'
            '优先级不能把缺失、冲突或错误证据变成事实，也不能改变公式或程序结论。高优先级证据缺失时保留未知状态。'
            '正文只陈述结论本身，不写限制、免责声明或“不能/不代表”类句子，也不复述 cannot_say 与 limitations；页面会单独展示它们。'
            '正文不得出现这些词，即使用于否定：实时、最新、今天、当下、造假、导致、造成、因为、买入、卖出。'
            '只输出 JSON 对象 {"text":"...","evidence_ids":["..."]}。正文必须逐字包含 required_anchor，'
            '不要出现数字或百分号；evidence_ids 包含所用的所有来源证据 ID。',
            json.dumps(summary, ensure_ascii=False),
        )
