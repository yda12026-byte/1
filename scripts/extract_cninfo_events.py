"""Program extraction of key sentences from the downloaded announcement PDFs (decision 0022).

For each important announcement the first sentence matching the category's
ordered keywords is taken verbatim with its page number; earnings forecasts are
also parsed into type and the net-profit range. The result is a local
extraction file (like ``official_extract_h1.json``); it is written once and
never overwritten. Human spot checks are recorded separately in
``cninfo_event_spotcheck.json``.

Requires PyMuPDF (``fitz``), which is only needed on the preparation machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from diagnosis.events import IMPORTANT_CATEGORIES, classify  # noqa: E402

RAW = ROOT / "data" / "raw" / "annual-2025-08-31_2026-08-31"
OUTPUT = "cninfo_event_extract.json"
SHANGHAI = timezone(timedelta(hours=8))
MAX_CHARS = 220
BOILERPLATE = ("保证信息披露的内容真实", "以下简称", "具体内容详见")
# Ordered: the first keyword found anywhere in the document decides the sentence.
KEYWORDS = {
    "forecast": ("业绩预告情况", "预计净利润"),
    "project": ("火情", "首批符合标准", "首袋电池级", "投料试车", "投产", "项目进展情况"),
    "litigation": ("案件所处的诉讼阶段", "判决", "上诉"),
    "guarantee": ("对外担保总额", "担保额度合计"),
    "buyback": ("本次注销的部分回购股份数量", "回购注销股份数量", "回购价格", "总股本将由"),
    "hedging": ("产生的收益合计", "最高合约价值", "保证金和权利金上限"),
    "dividend": ("拟不派发现金红利", "利润分配预案为", "原则上每年进行一次现金分红"),
    "capital": ("配售完成", "择机处置", "已完成", "认缴出资", "签署了", "增资", "出资", "共同投资"),
}


def _pages(path: Path) -> list[str]:
    with fitz.open(path) as document:
        return [re.sub(r"\s+", "", page.get_text()) for page in document]


def _sentences(pages: list[str]):
    for number, text in enumerate(pages, start=1):
        for sentence in re.split(r"(?<=。)", text):
            if sentence.strip():
                yield number, sentence


def extract_sentence(pages: list[str], category: str) -> dict | None:
    for keyword in KEYWORDS[category]:
        for page, sentence in _sentences(pages):
            if keyword in sentence and not any(word in sentence for word in BOILERPLATE[:1]):
                # Drop a leading heading such as "二、项目进展情况" or "特别提示：1、" so the quote starts at the fact.
                text = re.sub(r"^.*?(项目进展情况|事件基本情况|交易进展情况|特别提示：|重要内容提示：)(\d、)?", "", sentence) \
                    if keyword not in ("项目进展情况",) else sentence
                if category != "litigation":  # "2、投资金额：" style list labels; litigation keeps its stage label
                    text = re.sub(r"^\d、[^：]{1,8}：", "", text)
                text = re.sub(r"，?现将[^。]{0,12}如下：.*$", "。", text)  # sentence ran into the next heading
                text = text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "…"
                return {"page": page, "keyword": keyword, "text": text}
    return None


def parse_forecast(pages: list[str]) -> dict:
    text = "".join(pages[:2])
    kind = re.search(r"预计净利润为(正值|负值)且属于(扭亏为盈|同向上升|同向下降|首亏|续亏|增亏|减亏)情形", text)
    period = re.search(r"业绩预告期间：(\d{4})年(\d{1,2})月(\d{1,2})日至(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    start = text.find("归属于上市公司股东的净利润")
    segment = text[start:start + 120]
    values = re.search(r"(盈利|亏损)：([\d,.]+)(?:万元)?～(盈利|亏损)：([\d,.]+)(?:万元)?", segment)
    if not (kind and period and values and start >= 0 and "万元" in text[start - 40:start + 120]):
        raise ValueError("forecast table could not be parsed")
    sign = lambda word: -1 if word == "亏损" else 1
    low, high = sign(values.group(1)) * float(values.group(2).replace(",", "")), \
        sign(values.group(3)) * float(values.group(4).replace(",", ""))
    page = next(i for i, page_text in enumerate(pages, start=1) if "归属于上市公司股东的净利润" in page_text)
    return {"type": kind.group(2), "profit_sign": kind.group(1), "unit": "万元", "metric": "归属于上市公司股东的净利润",
            "period_end": f"{period.group(4)}-{int(period.group(5)):02d}-{int(period.group(6)):02d}",
            "low": min(low, high), "high": max(low, high), "page": page,
            "quote": segment[:values.end()]}


def build() -> dict:
    listing = json.loads((RAW / "cninfo_announcements.json").read_text(encoding="utf-8"))
    items, forecasts, failures = [], [], []
    for row in sorted(listing["announcements"], key=lambda row: row["announcementTime"]):
        category = classify(row["announcementTitle"])
        if category not in IMPORTANT_CATEGORIES:
            continue
        path = RAW / "cninfo_pdf" / f"{row['announcementId']}.pdf"
        pages = _pages(path)
        base = {"id": row["announcementId"], "category": category, "title": row["announcementTitle"],
                "date": datetime.fromtimestamp(row["announcementTime"] / 1000, SHANGHAI).date().isoformat(),
                "url": f"https://static.cninfo.com.cn/{row['adjunctUrl']}", "page_count": len(pages),
                "pdf_sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}
        found = extract_sentence(pages, category)
        if found is None:
            failures.append({**base, "reason": "no keyword sentence"})
            continue
        if category == "forecast":
            forecast = parse_forecast(pages)
            forecasts.append({**base, **forecast})
            # The table sentence is long; quote the type phrase and the net-profit range, both verbatim.
            found = {"page": forecast["page"], "keyword": "业绩预告情况",
                     "text": f"预计净利润为{forecast['profit_sign']}且属于{forecast['type']}情形……{forecast['quote']}"}
        items.append({**base, **found})
    return {"method": "program_extraction", "tool": "PyMuPDF text layer; whitespace removed; first sentence matching ordered category keywords",
            "keywords": KEYWORDS, "max_chars": MAX_CHARS, "extracted_at": datetime.now(timezone.utc).isoformat(),
            "items": items, "forecasts": forecasts, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=RAW / OUTPUT, help="write elsewhere to preview without publishing")
    args = parser.parse_args()
    document = build()
    with args.out.open("x", encoding="utf-8") as handle:  # never overwrite an extraction that may have been checked
        json.dump(document, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"items": len(document["items"]), "forecasts": len(document["forecasts"]),
                      "failures": len(document["failures"])}, ensure_ascii=False))
    return 0 if not document["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
