"""Official-announcement events dimension (decision 0022), on synthetic data only."""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from diagnosis.dimension_events import events_run, price_chart  # noqa: E402
from diagnosis.events import classify, periodic_deadline  # noqa: E402
from diagnosis.validator import PROHIBITED_PATTERNS  # noqa: E402
from product_fixture import product_payload  # noqa: E402


def run(payload=None):
    return events_run(payload or product_payload(events=True), "近一年有哪些重要公告？", {"intent": "events"}, "r1")


class ClassificationTests(unittest.TestCase):
    def test_titles_map_to_the_eight_categories_and_supporting_documents_are_excluded(self):
        cases = {
            "2026年半年度报告": "periodic", "2026年半年度报告摘要": "other", "H股公告：2025年度报告": "other",
            "2026年第一季度业绩预告": "forecast", "关于泰利森第三期化学级锂精矿扩产项目进展情况的公告": "project",
            "关于泰利森第三期化学级锂精矿工厂发生局部火情的公告": "project",
            "关于全资子公司提起诉讼及参股公司重大合同的进展公告": "litigation",
            "关于公司及控股子公司申请2026年度金融机构授信额度暨提供各类担保的公告": "guarantee",
            "对外担保管理制度（2025年12月修订）": "other", "关于部分限制性股票回购注销完成的公告": "buyback",
            "关于开展外汇套期保值业务的公告": "hedging", "关于开展外汇套期保值业务的可行性分析报告": "other",
            "关于2025年度拟不进行利润分配的公告": "dividend", "未来三年（2026-2028年度）股东回报规划": "dividend",
            "2026年第二次临时股东会的法律意见书": "other", "第七届董事会第三次会议决议公告": "other",
            "关于新H股配售完成及可转换公司债券发行完成的公告": "capital", "关于择机处置公司部分参股公司股权的公告": "capital",
            "关于全资子公司对外投资暨签署《增资协议》的公告": "capital",
            "H股公告：关于根据一般性授权配售新H股及发行可转换公司债券的公告": "other",
        }
        for title, expected in cases.items():
            self.assertEqual(classify(title), expected, title)

    def test_statutory_deadlines(self):
        self.assertEqual(periodic_deadline("2025年年度报告"), ("年度报告", date(2026, 4, 30)))
        self.assertEqual(periodic_deadline("2026年半年度报告"), ("半年度报告", date(2026, 8, 31)))
        self.assertEqual(periodic_deadline("2026年一季度报告"), ("一季度报告", date(2026, 4, 30)))
        self.assertEqual(periodic_deadline("2025年三季度报告"), ("三季度报告", date(2025, 10, 31)))
        self.assertIsNone(periodic_deadline("2026年半年度报告摘要"))


class EventsRunTests(unittest.TestCase):
    def test_conclusions_are_facts_with_traceable_excerpts(self):
        result = run()
        codes = [c.claim_code for c in result.conclusions]
        self.assertEqual(codes, ["event_overview", "periodic_disclosure", "forecast_accuracy", "project_progress",
                                 "legal_guarantee", "capital_return", "capital_operations"])
        by_code = {c.claim_code: c for c in result.conclusions}
        self.assertEqual(by_code["periodic_disclosure"].required_anchor, "观察区间内定期报告均在法定期限内披露")
        self.assertEqual(by_code["project_progress"].required_anchor, "观察区间内披露了项目或扩产进展，另有一起工厂局部火情")
        self.assertIn("不派发现金红利", by_code["capital_return"].required_anchor)
        self.assertEqual(by_code["capital_operations"].required_anchor, "观察区间内有参股股权处置等资本运作事项披露")
        self.assertEqual(by_code["event_overview"].required_anchor, "观察区间内的官方公告已按九类重要事项归类")
        evidence = {e.id: e for e in result.evidence}
        excerpt = evidence["announcement:2"]
        self.assertEqual((excerpt.unit, excerpt.source["page"]), ("文本", 1))
        self.assertTrue(excerpt.source["url"].startswith("https://static.cninfo.com.cn/"))
        self.assertIn("人工抽查一致", excerpt.source["query_ref"])
        self.assertEqual(evidence["deadline_margin:7"].value, "3")
        self.assertEqual(evidence["forecast_position:6"].value, "50.00")  # actual 40 亿 in 30–50 亿
        self.assertEqual(evidence["announcement_count:project"].value, "2")
        for c in result.conclusions:
            self.assertIn("NO_EVENT_PRICE_LINK", [rule.code for rule in c.cannot_say])
            self.assertFalse(any(ch.isdigit() for ch in c.required_anchor))

    def test_late_report_and_missed_forecast_turn_negative(self):
        payload = product_payload(events=True)
        payload["events"]["announcements"][6]["date"] = "2026-09-02"
        payload["events"]["forecasts"][0]["high"] = 350000.0
        by_code = {c.claim_code: c for c in run(payload).conclusions}
        self.assertEqual(by_code["periodic_disclosure"].assessment, "negative")
        self.assertEqual(by_code["forecast_accuracy"].assessment, "negative")

    def test_inconsistent_spot_check_marks_excerpt_as_conflict(self):
        payload = product_payload(events=True)
        payload["events"]["excerpts"][0]["spot_check"] = {"status": "inconsistent"}
        result = run(payload)
        item = next(e for e in result.evidence if e.id == "announcement:2")
        self.assertEqual((item.quality["status"], item.value), ("conflict", None))
        project = next(c for c in result.conclusions if c.claim_code == "project_progress")
        self.assertEqual(project.type, "unknown")

    def test_event_price_link_wording_is_prohibited(self):
        import re
        for text in ("火情公告是利空", "项目进展推动股价上涨"):
            self.assertTrue(re.search(PROHIBITED_PATTERNS["NO_EVENT_PRICE_LINK"], text), text)

    def test_price_chart_lists_only_event_categories(self):
        chart = price_chart(product_payload(events=True))
        self.assertEqual([s["label"] for s in chart["series"]], ["天齐锂业", "赣锋锂业", "中矿资源", "永兴材料"])
        self.assertEqual({len(s["values"]) for s in chart["series"]}, {242})
        self.assertEqual({s["values"][0] for s in chart["series"]}, {100.0})
        self.assertEqual([s["values"][-1] for s in chart["series"]], [120.0, 130.0, 140.0, 150.0])
        # Same routine as the market dimension: peak on day 100 (150), trough on day 150 (90).
        self.assertEqual((chart["drawdown"]["start"], chart["drawdown"]["end"], chart["drawdown"]["pct"]),
                         (chart["dates"][100], chart["dates"][150], -40.0))
        self.assertIn("历史走势不预示未来", chart["note"])
        self.assertEqual({m["category"] for m in chart["markers"]}, {"定期报告", "项目或扩产", "利润分配", "诉讼仲裁", "业绩预告", "资本运作"})
        self.assertIn("不表示因果关系", chart["note"])
        self.assertEqual(price_chart(product_payload())["markers"], [])


if __name__ == "__main__":
    unittest.main()
