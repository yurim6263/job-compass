"""위젯(apps/widget)의 화면 밖 부분 시험: JSON 읽기·요약·열 대상. PySide6 없이 돈다.
그리고 dashboard.py 가 위젯용 칸(schema·files·doc·후보 마감)을 쓰는지.
"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from helpers import REPO, VaultCase

sys.path.insert(0, str(REPO / "apps" / "widget"))
from jc_widget import model, settings  # noqa: E402


class ModelTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.vault = Path(self._tmp.name)

    def put(self, obj):
        p = model.status_path(self.vault)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_missing_and_broken_files_do_not_raise(self):
        self.assertIsNotNone(model.load_status("")[1])
        self.assertIn("/job-flow", model.load_status(self.vault)[1])
        self.put("{ 쓰는 중")
        data, prob = model.load_status(self.vault)
        self.assertIsNone(data)
        self.assertIn("읽지 못했습니다", prob)

    def test_newer_schema_warns_but_shows(self):
        self.put({"schema": 99, "counts": {}})
        data, prob = model.load_status(self.vault)
        self.assertIsNotNone(data)
        self.assertIn("업데이트", prob)

    def test_summary_badge_stale_and_failed_scan(self):
        data = {"generated_at": "2026-11-02T09:22+09:00", "counts": {"urgent": 1, "overdue": 1, "new_candidates_today": 4, "new_candidates": 12},
                "last_scan": {"at": "2026-11-02 09:19", "code": 0}}
        s = model.summarize(data, now=datetime(2026, 11, 2, 10, 0))
        self.assertEqual(s["badge"], 6)
        self.assertEqual(s["notes"], [])
        self.assertEqual(s["last_scan"], "11/02 09:19 성공")
        s = model.summarize({**data, "last_scan": {"at": "2026-11-02 09:19", "code": 1}}, now=datetime(2026, 11, 4, 10, 0))
        kinds = [k for k, _ in s["notes"]]
        self.assertIn("warn", kinds)       # 하루 넘음
        self.assertIn("error", kinds)      # 수집 실패
        self.assertIn("새 소식", model.tooltip(model.summarize({"counts": {}})))

    def test_d_label(self):
        today = date(2026, 11, 2)
        self.assertEqual(model.d_label("2026-11-05", today), "11/05 (D-3)")
        self.assertEqual(model.d_label("2026-11-02", today), "11/02 (D-day)")
        self.assertEqual(model.d_label(None, today), "마감 미정")

    def test_vault_file_stays_inside_vault(self):
        self.assertEqual(model.vault_file(self.vault, "Areas/취업/공고 후보함.md"), (self.vault / "Areas/취업/공고 후보함.md").resolve())
        self.assertIsNone(model.vault_file(self.vault, "../../Windows/system.ini"))
        self.assertIsNone(model.vault_file(self.vault, None))

    def test_links_and_obsidian_uri(self):
        self.assertIsNone(model.safe_web_link("javascript:alert(1)"))
        self.assertEqual(model.safe_web_link("<https://a.example/1>"), "https://a.example/1")
        self.assertTrue(model.obsidian_uri(Path("C:/v/공고 후보함.md")).startswith("obsidian://open?path=C%3A"))

    def test_settings_roundtrip_keeps_defaults(self):
        p = self.vault / "s.json"
        cfg = settings.load(p)
        self.assertTrue(cfg["floating"]["visible"])
        cfg["vault"] = "X"
        cfg["floating"]["x"] = 10
        settings.save(cfg, p)
        again = settings.load(p)
        self.assertEqual((again["vault"], again["floating"]["x"], again["floating"]["visible"]), ("X", 10, True))


class DashboardWidgetFieldsTest(VaultCase):
    def test_json_has_widget_fields(self):
        self.add_row("A사", id_="jobkorea:1")
        self.write("Areas/취업/공고 후보함.md", "# 공고 후보함\n\n## 후보\n\n"
                   "| 상태 | 회사 | 공고 | 방향 | 지역 | 서류마감(D-n) | 선별 근거 | 점수 | 링크 | 공고 ID | 발견일 |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
                   "| 점수 | B사 | 설비 AI | 일치 | 서울 | 2026-11-20 (D-18) |  | 74 🟡 | https://www.jobkorea.co.kr/Recruit/GI_Read/2 | jobkorea:2 | 2026-11-02 |\n")
        r = self.run_script("dashboard.py", "today", "--today", "2026-11-02", "--write")
        self.assertEqual(r.code, 0, r.text)
        j = json.loads(self.read("Areas/취업/_widget/오늘 현황.json"))
        self.assertEqual(j["schema"], 1)
        self.assertEqual(j["files"], {"candidates": "Areas/취업/공고 후보함.md", "today": "Areas/취업/오늘 현황.md"})
        self.assertIn("doc", j["in_progress"][0])
        c = j["new_candidates"][0]
        self.assertEqual((c["company"], c["deadline"], c["score"], c["id"]), ("B사", "2026-11-20", "74 🟡", "jobkorea:2"))
        data, prob = model.load_status(self.vault)
        self.assertIsNone(prob)
        self.assertEqual(model.summarize(data)["new_today"], 1)


if __name__ == "__main__":
    unittest.main()
