import json
import unittest

from scripts import audit_annual_coverage, download_annual_raw


class AnnualDownloadPlanTests(unittest.TestCase):
    def test_months_cover_window_once(self):
        windows = list(download_annual_raw.month_windows())
        self.assertEqual(windows[0][0], download_annual_raw.WINDOW_START)
        self.assertEqual(windows[-1][1], download_annual_raw.WINDOW_END)
        self.assertEqual(len(windows), 13)
        for (_, previous_end), (next_start, _) in zip(windows, windows[1:]):
            self.assertEqual((next_start - previous_end).days, 1)

    def test_every_candidate_has_an_acquisition_plan(self):
        fields = json.loads(audit_annual_coverage.CATALOG.read_text(encoding="utf-8"))["fields"]
        self.assertEqual(len(fields), 72)
        self.assertEqual({field["id"] for field in fields}, set(audit_annual_coverage.FIELD_GROUPS))
        self.assertEqual(set(audit_annual_coverage.requirements()),
                         {group for groups in audit_annual_coverage.FIELD_GROUPS.values() for group in groups})

    def test_business_error_is_not_parsed_as_data(self):
        document = {"response": {"result": {"content": [{"text": '{"code": 1, "data": {"answer": "ok"}}'}]}}}
        self.assertEqual(download_annual_raw.parsed_ifind(document)["code"], 1)
        document["response"]["result"]["isError"] = True
        self.assertEqual(download_annual_raw.parsed_ifind(document), {})


if __name__ == "__main__":
    unittest.main()
