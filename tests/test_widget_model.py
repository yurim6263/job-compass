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

    def test_mood_priority(self):
        self.assertEqual(model.mood({"notes": [("error", "x")], "urgent": 1, "new_today": 3}), "fail")
        self.assertEqual(model.mood({"notes": [("warn", "x")], "urgent": 0, "overdue": 1, "new_today": 3}), "urgent")
        self.assertEqual(model.mood({"notes": [], "urgent": 0, "overdue": 0, "new_today": 2}), "new")
        self.assertEqual(model.mood({"notes": [], "urgent": 0, "overdue": 0, "new_today": 0}), "sleep")

    def test_tab_view_lines(self):
        base = {"notes": [], "urgent": 0, "overdue": 0, "new_today": 0, "in_progress": 3, "last_scan": "11/02 08:00 성공"}
        self.assertEqual(model.tab_view(base), ("none", None, "새 소식 없음", "진행 중 3 · 수집 11/02 08:00 성공"))
        self.assertEqual(model.tab_view({**base, "new_today": 5})[:3], ("new", "5", "새 후보 5"))
        self.assertEqual(model.tab_view({**base, "urgent": 1, "overdue": 1, "new_today": 5})[:3], ("urgent", "2", "마감 임박 2 · 새 후보 5"))
        self.assertEqual(model.tab_view({**base, "notes": [("error", "x")]})[:3], ("fail", "!", "수집 실패"))
        self.assertEqual(model.tab_view({}, has_data=False)[0], "fail")

    def test_panel_view(self):
        data = {"overdue": [{"company": "가사", "state": "Not started"}],
                "urgent": [{"company": "나사", "deadline": "2026-11-05", "state": "자소서 작성중"},
                           {"company": "다사", "deadline": "2026-11-04", "state": "Not started"}],
                "new_candidates": [{"company": "A사", "title": "설비 AI", "score": "62 🟡 🚫경력 필수", "deadline": None,
                                    "link": "https://a.example/1"},
                                   {"company": "B사", "title": "데이터", "score": "", "deadline": "2026-11-20", "link": "javascript:x"}],
                "in_progress": [{"company": "나사", "state": "자소서 작성중", "deadline": "2026-11-05", "doc": "w/a.md",
                                 "steps": {"공고": "✓", "점수": "✓", "조사": "✗", "자소서": "작성중", "방어맵": "✗", "면접": "2회"}}],
                "next_actions": [{"company": "나사", "do": "`/cover-letter 첨삭`"}], "files": {"candidates": "c.md", "today": "t.md"}}
        s = {"urgent": 2, "overdue": 1, "new_today": 2, "new_total": 7, "in_progress": 1, "notion": "on", "notion_pending": 1,
             "last_scan": "11/02 08:00 성공", "notes": [], "generated": "11/02 09:44"}
        v = model.panel_view(data, s, today=date(2026, 11, 2))
        self.assertEqual(v["stats"][0][:2], ("마감 임박", 3))
        self.assertTrue(v["stats"][0][3])
        self.assertEqual([t for t, _ in v["alerts"]], ["red", "amber"])
        self.assertIn("다사 서류마감 D-2", v["alerts"][1][1], "가장 가까운 마감 하나")
        self.assertEqual((v["cands"][0]["score"], v["cands"][0]["gate"]), (62, "🚫경력 필수"))
        self.assertIsNone(v["cands"][1]["score"])
        self.assertIsNone(v["cands"][1]["link"], "http(s) 아닌 링크는 버림")
        self.assertEqual(v["more"], 5)
        self.assertEqual(v["prog"][0]["steps"], [True, True, False, True, False, True])
        self.assertEqual(v["prog"][0]["tone"], "amber")
        self.assertEqual(v["actions"], ["나사 — /cover-letter 첨삭"])
        self.assertEqual(v["foot"], "수집 11/02 08:00 성공 · 노션 켜짐 · 밀린 반영 1")

    def test_notify_only_increases_once(self):
        def s(new=0, urgent=0, overdue=0, fail=False):
            return {"new_today": new, "urgent": urgent, "overdue": overdue, "notes": [("error", "x")] if fail else []}
        d1 = {"generated_at": "2026-11-02T08:01", "today": "2026-11-02",
              "new_candidates": [{"company": "A사", "score": "74 🟡"}, {"company": "B사", "score": ""}]}
        msg, st = model.notify_decision({}, d1, s(new=5))
        self.assertIsNone(msg, "처음 실행은 기준만 저장")
        self.assertEqual(st["new_today"], 5)
        self.assertEqual(model.notify_decision(st, d1, s(new=5)), (None, st), "같은 현황으로는 한 번만")
        d2 = {**d1, "generated_at": "2026-11-02T12:00"}
        msg, st2 = model.notify_decision(st, d2, s(new=8, urgent=1))
        self.assertEqual(msg, "마감 임박 1건 · 새 후보 3건(최고 74점) — 채용 현황을 확인하세요")
        self.assertNotIn("A사", msg)
        msg, st3 = model.notify_decision(st2, {**d2, "generated_at": "2026-11-02T13:00"}, s(new=8, urgent=0))
        self.assertIsNone(msg, "줄어든 것은 알리지 않음")
        d4 = {**d1, "generated_at": "2026-11-03T08:00", "today": "2026-11-03"}
        msg, _ = model.notify_decision(st3, d4, s(new=2))
        self.assertTrue(msg.startswith("새 후보 2건"), "날짜가 바뀌면 오늘 새 후보는 0부터 비교")
        msg, st5 = model.notify_decision(st3, d4, s(fail=True))
        self.assertIn("자동 수집 실패", msg)
        msg, _ = model.notify_decision(st5, {**d4, "generated_at": "2026-11-03T09:00"}, s(fail=True))
        self.assertIsNone(msg, "실패가 이어지면 다시 알리지 않음")

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

    def test_floating_position_kept_inside_screens(self):
        screens = [(0, 0, 1920, 1040), (1920, 0, 1280, 984)]          # 주 화면 + 오른쪽 보조 모니터
        self.assertEqual(model.clamp_position((100, 200), (56, 56), screens), (100, 200))
        self.assertEqual(model.clamp_position((2000, 100), (56, 56), screens), (2000, 100), "보조 모니터 위도 그대로")
        default = (1920 - 56, int(1040 * 0.6) - 28)                      # 기본: 주 화면 오른쪽 끝에 붙음
        self.assertEqual(model.clamp_position((3300, 100), (56, 56), screens), default, "모니터를 뺐으면 기본 자리로")
        self.assertEqual(model.clamp_position((1900, 100), (56, 56), screens[:1]), default, "화면 경계에 걸치면 되돌림")
        self.assertEqual(model.clamp_position(None, (56, 56), screens), default)
        self.assertEqual(model.clamp_position((None, None), (56, 56), screens), default)

    def test_dock_to_nearest_side(self):
        scr = (0, 0, 1920, 1040)
        self.assertEqual(model.dock_to_side((1500, 400), (48, 48), scr), (1872, 400), "오른쪽 절반 → 오른쪽 끝")
        self.assertEqual(model.dock_to_side((300, 400), (48, 48), scr), (0, 400), "왼쪽 절반 → 왼쪽 끝")
        self.assertEqual(model.dock_to_side((1500, 1100), (48, 48), scr), (1872, 992), "화면 아래로 끌어도 안으로")
        self.assertEqual(model.dock_to_side((2900, 400), (48, 48), (1920, 0, 1280, 984)), (3152, 400), "보조 모니터 오른쪽 절반")
        self.assertEqual(model.dock_to_side((2300, 400), (48, 48), (1920, 0, 1280, 984)), (1920, 400), "보조 모니터 왼쪽 절반")

    def test_panel_above_tab_at_edge(self):
        scr = (0, 0, 1536, 816)
        self.assertEqual(model.panel_position((340, 590), scr, (700, 52), "right"), (1196, 108), "오른쪽 끝, 탭 바로 위")
        self.assertEqual(model.panel_position((340, 590), scr, (700, 52), "left"), (0, 108), "왼쪽 끝")
        self.assertEqual(model.panel_position((340, 590), scr, (100, 52), "right"), (1196, 154), "위가 모자라면 탭 아래")
        self.assertEqual(model.panel_position((340, 590), scr, (300, 52), "right"), (1196, 226), "위·아래 다 모자라면 화면 안으로")
        self.assertEqual(model.panel_position((340, 590), scr, None, "right"), (1196, 226))

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
