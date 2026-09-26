"""Deterministic classification of official announcements (decision 0022).

Titles from the 巨潮资讯 (cninfo) list are sorted into the nine categories the
user chose; everything else counts as routine disclosure. No LLM is involved.
Supporting documents (legal opinions, feasibility studies, rules and bylaws) are
never events even when they mention a category keyword.
"""

from __future__ import annotations

import re
from datetime import date

CATEGORIES = {
    "periodic": "定期报告",
    "forecast": "业绩预告",
    "project": "项目或扩产",
    "litigation": "诉讼仲裁",
    "guarantee": "担保",
    "buyback": "回购",
    "hedging": "套期保值",
    "dividend": "利润分配",
    "capital": "资本运作",
    "other": "其他公告",
}
IMPORTANT_CATEGORIES = tuple(key for key in CATEGORIES if key not in ("other", "periodic"))  # PDFs to download
EVENT_CATEGORIES = tuple(key for key in CATEGORIES if key != "other")

SUPPORTING = re.compile(r"制度|细则|规则|章程|对照表|法律意见书|核查意见|可行性分析报告|声明与承诺|述职报告|^H股公告")
PERIODIC = re.compile(r"^(\d{4})年(年度报告|半年度报告|[一三]季度报告|第[一三]季度报告)$")
RULES = (
    ("forecast", re.compile(r"业绩预告$")),
    ("litigation", re.compile(r"诉讼|仲裁")),
    ("project", re.compile(r"项目|扩产|工厂")),
    ("guarantee", re.compile(r"担保")),
    ("buyback", re.compile(r"回购")),
    ("hedging", re.compile(r"套期保值")),
    ("dividend", re.compile(r"利润分配|分红|股东回报规划")),
    # Added 2026-09-26 at the user's request: equity/convertible financing, outward investment, stake disposals.
    ("capital", re.compile(r"配售|可转换公司债券|处置.{0,12}股权|对外投资|增资协议|共同投资")),
)


def classify(title: str) -> str:
    title = title.strip()
    if PERIODIC.match(title):
        return "periodic"
    if SUPPORTING.search(title):
        return "other"
    return next((key for key, pattern in RULES if pattern.search(title)), "other")


def periodic_deadline(title: str) -> tuple[str, date] | None:
    """Statutory deadline (证券法/深交所规则): Q1 and annual by 04-30, half-year by 08-31, Q3 by 10-31."""
    match = PERIODIC.match(title.strip())
    if not match:
        return None
    year, kind = int(match.group(1)), match.group(2)
    if kind == "年度报告":
        return "年度报告", date(year + 1, 4, 30)
    if kind == "半年度报告":
        return "半年度报告", date(year, 8, 31)
    if "一" in kind:
        return "一季度报告", date(year, 4, 30)
    return "三季度报告", date(year, 10, 31)
