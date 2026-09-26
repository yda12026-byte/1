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

    def _complete(self, system: str, user: str, timeout: int = 12) -> dict:
        payload = {"model": self.model, "temperature": 0,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        request = Request(self.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                          method="POST")
        with open_direct(request, timeout=timeout) as response:
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

    def translate_many(self, conclusions: list[Conclusion], evidence: list[Evidence]) -> list[dict]:
        by_id = {item.id: item for item in evidence}
        summary = []
        for conclusion in conclusions:
            required = [link["evidence_id"] for link in conclusion.evidence_links
                        if link["role"] == "supports" or
                        (conclusion.type == "unknown" and by_id[link["evidence_id"]].kind == "source")]
            summary.append({
                "id": conclusion.id, "type": conclusion.type, "assessment": conclusion.assessment,
                "priority_tier": conclusion.priority["tier"], "fallback_text": conclusion.fallback_text,
                "required_anchor": conclusion.required_anchor, "must_cite_evidence_ids": required,
                "cannot_say": [rule.statement for rule in conclusion.cannot_say],
                "evidence": [{"id": link["evidence_id"], "label": by_id[link["evidence_id"]].label,
                              "status": by_id[link["evidence_id"]].quality["status"]}
                             for link in conclusion.evidence_links],
            })
        result = self._complete(
            '你把多条已由程序得出的结论分别改写成简洁、专业的中文解读，不新增事实、因果、数字或投资建议。数据来自一次性固定快照。'
            '每条正文必须逐字包含该条 required_anchor；只陈述结论本身，不写限制、免责声明或“不能/不代表”类句子；'
            '正文不得出现任何数字或百分号，也不得出现这些词（即使用于否定）：实时、最新、今天、当下、低估、高估、便宜、偏贵、导致、造成、因为、买入、卖出。'
            'type 为 unknown 时只说明证据不足或冲突，不作判断。priority_tier 为 driver 的结论可多写一句它对锂周期公司的研究意义，但仍不得引入新事实。'
            '只输出 JSON 对象 {"items":[{"id":"...","text":"...","evidence_ids":["..."]}]}，每条 evidence_ids 必须恰好包含 must_cite_evidence_ids，可再加该条 evidence 中的其他 ID。',
            json.dumps(summary, ensure_ascii=False), timeout=30,
        )
        items = result.get("items")
        if not isinstance(items, list):
            raise ValueError("LLM returned no items")
        return items

    def summarize(self, basis: dict) -> str:
        result = self._complete(
            '你为一只锂业股票的多维诊断写开头的总体解读，二到四句中文，面向研究者。只能重述输入中各维度已由程序得出的结论锚点，'
            '先用一句话给出最重要的判断（优先 priority 为 driver 的结论），再指出不同维度之间值得注意的一致或分歧（例如财务与同行指标领先而股价表现落后），但不得新增事实、原因、数字、预测或投资建议。'
            '以研究员口吻直接陈述，不要提及“程序”“锚点”“输入”等字样；pending 或 not_covered 不存在时不要提及。'
            '必须逐字包含 must_include 中的每一条锚点；pending 中的条目要说明尚待核实；not_covered 中的维度说明尚未纳入。'
            '正文不得出现任何数字或百分号，也不得出现：实时、最新、今天、当下、低估、高估、便宜、偏贵、导致、造成、因为、买入、卖出、建议。'
            '全文字数不得超过 max_chars；维度多时每个维度只用一句，不要逐条罗列。只输出 JSON 对象 {"text":"..."}。',
            json.dumps(basis, ensure_ascii=False), timeout=30,
        )
        text = result.get("text")
        if not isinstance(text, str):
            raise ValueError("LLM returned no summary text")
        return text

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
