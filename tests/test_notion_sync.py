"""Notion 반영 계산(notion_sync.py) 시험. Notion은 부르지 않는다 — 무엇을 올릴지·바뀌었는지·선택지 검사·매핑·밀린 반영만 본다."""
import json
import unittest

from helpers import VaultCase

DS = "collection://00000000-0000-0000-0000-000000000000"
PAGE = "https://www.notion.so/00000000000000000000000000000001"


class NotionSyncTest(VaultCase):
    def ns(self, *args):
        return self.run_script("notion_sync.py", *args)

    def js(self, r):
        self.assertEqual(r.code, 0, r.text)
        return json.loads(r.out)

    def test_status_defaults_off_and_nothing_linked(self):
        s = self.js(self.ns("status"))
        self.assertEqual(s["notion"], "off")
        self.assertEqual(s["linked"], {})
        self.assertEqual(s["pending"], 0)
        self.assertIn("지원현황", s["missing_tables"])

    def test_schema_matches_status_values(self):
        sc = self.js(self.ns("schema", "--table", "지원현황"))["지원현황"]["props"]
        self.assertIn("지원취소", sc["진행상태"]["options"])
        self.assertNotIn("메모", sc, "현황표 메모는 Notion에 올리지 않는다")

    def test_plan_status_rows_split_fit_and_skip_memo(self):
        self.add_row("A사", id_="jobkorea:123", fit="74 🟡", memo="연락처 메모")
        p = self.js(self.ns("plan", "--table", "지원현황", "--today", "2026-11-02"))
        self.assertEqual(p["counts"], {"create": 1, "update": 0, "same": 0})
        it = p["items"][0]
        self.assertEqual(it["key"], "jobkorea:123")
        self.assertEqual(it["props"]["적합도"], 74)
        self.assertEqual(it["props"]["적합도 등급"], "🟡")
        self.assertEqual(it["props"]["공고 링크"], "https://www.jobkorea.co.kr/Recruit/GI_Read/123")
        self.assertEqual(it["props"]["date:서류마감:start"], "2026-12-31")
        self.assertNotIn("메모", json.dumps(it["props"], ensure_ascii=False))
        self.assertEqual(p["problems"], [])

    def test_record_then_same_then_update(self):
        self.add_row("A사", id_="jobkorea:123")
        it = self.js(self.ns("plan", "--table", "지원현황"))["items"][0]
        self.assertEqual(self.ns("record", "--table", "지원현황", "--key", it["key"], "--page", PAGE, "--hash", it["hash"]).code, 0)
        again = self.js(self.ns("plan", "--table", "지원현황", "--today", "2026-12-01"))["items"][0]
        self.assertEqual(again["action"], "same", "날짜(볼트 반영일)만 바뀌면 같음")
        self.assertEqual(again["page"], PAGE)
        self.run_script("status_table.py", "set-status", "--id", "jobkorea:123", "--state", "자소서 작성중")
        self.assertEqual(self.js(self.ns("plan", "--table", "지원현황"))["items"][0]["action"], "update")
        self.assertEqual(self.ns("lookup", "--table", "지원현황", "--key", "jobkorea:123").out.strip(), PAGE)

    def test_record_rejects_non_notion_url(self):
        r = self.ns("record", "--table", "지원현황", "--key", "x", "--page", "https://example.com/p", "--hash", "h")
        self.assertNotEqual(r.code, 0)

    def test_check_rejects_option_outside_list_and_resolves_relation(self):
        self.add_row("A사", id_="jobkorea:123")
        it = self.js(self.ns("plan", "--table", "지원현황"))["items"][0]
        self.ns("record", "--table", "지원현황", "--key", "jobkorea:123", "--page", PAGE, "--hash", it["hash"])
        self.write_json("v.json", {"회사": "A사", "지원 판단": "강력 추천", "키워드 반영 가능률": 72, "지원 현황": "jobkorea:123"})
        r = self.ns("check", "--table", "회사조사", "--key", "A사", "--props", "v.json")
        self.assertEqual(r.code, 4)
        bad = json.loads(r.out)["problems"]
        self.assertTrue(any("선택지 밖" in b for b in bad))
        self.assertTrue(any("0~1" in b for b in bad))
        self.write_json("v.json", {"회사": "A사", "지원 판단": "조건부 지원", "키워드 반영 가능률": 0.72, "지원 현황": "jobkorea:123"})
        ok = self.js(self.ns("check", "--table", "회사조사", "--key", "A사", "--props", "v.json"))
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["props"]["지원 현황"], [PAGE])
        self.assertEqual(ok["action"], "create")

    def test_check_relation_missing_is_note_not_error(self):
        self.write_json("v.json", {"제목": "A사_설비AI", "상태": "작성중", "지원 현황": "jobkorea:999"})
        ok = self.js(self.ns("check", "--table", "자소서", "--key", "A사_설비AI", "--props", "v.json"))
        self.assertTrue(ok["ok"])
        self.assertNotIn("지원 현황", ok["props"])
        self.assertTrue(ok["notes"])

    def test_plan_cards_summary_only(self):
        p = self.js(self.ns("plan", "--table", "경험정리"))
        self.assertGreater(len(p["items"]), 0)
        for it in p["items"]:
            self.assertTrue(it["key"].startswith("exp-"))
            self.assertEqual(set(it["props"]) - {"카드 제목", "카드 ID", "프로젝트", "기간", "직무 태그", "한 줄 요약", "근거 상태",
                                                 "date:볼트 반영일:start", "date:볼트 반영일:is_datetime"}, set())
        self.assertEqual(p["problems"], [])

    def test_plan_candidates_min_score(self):
        self.write("Areas/취업/공고 후보함.md", "# 공고 후보함\n\n## 후보\n\n"
                   "| 상태 | 회사 | 공고 | 방향 | 지역 | 서류마감(D-n) | 선별 근거 | 점수 | 링크 | 공고 ID | 발견일 |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
                   "| 점수 | A사 | 설비 AI 신입 | 일치 | 서울 | 2026-11-20 (D-18) | 키워드 | 78 🟡 | https://www.jobkorea.co.kr/Recruit/GI_Read/1 | jobkorea:1 | 2026-11-02 |\n"
                   "| 새로 | B사 | 데이터 신입 | 약함 | 경기 | 마감일 미정 |  |  | https://www.jobkorea.co.kr/Recruit/GI_Read/2 | jobkorea:2 | 2026-11-02 |\n")
        p = self.js(self.ns("plan", "--table", "수집공고", "--min-score", "70"))
        self.assertEqual([i["key"] for i in p["items"]], ["jobkorea:1"])
        self.assertEqual(p["items"][0]["props"]["date:마감:start"], "2026-11-20")
        self.assertEqual(p["items"][0]["props"]["출처"], "잡코리아")
        self.assertEqual(len(self.js(self.ns("plan", "--table", "수집공고"))["items"]), 2)

    def test_link_and_pending_cycle(self):
        self.assertEqual(self.ns("link", "--table", "지원현황", "--ds", DS, "--hub", PAGE).code, 0)
        self.assertNotEqual(self.ns("link", "--table", "지원현황", "--ds", "https://x").code, 0)
        s = self.js(self.ns("status"))
        self.assertEqual(s["linked"], {"지원현황": DS})
        self.assertEqual(s["hub"], PAGE)
        self.ns("pending", "add", "--table", "지원현황", "--key", "jobkorea:1", "--why", "연결 안 됨")
        self.ns("pending", "add", "--table", "지원현황", "--key", "jobkorea:1", "--why", "연결 안 됨")
        self.assertEqual(self.js(self.ns("status"))["pending"], 1, "같은 건은 한 번만")
        self.ns("record", "--table", "지원현황", "--key", "jobkorea:1", "--page", PAGE, "--hash", "h")
        self.assertEqual(self.js(self.ns("status"))["pending"], 0, "올리면 밀린 반영에서 빠진다")

    def test_diff_shows_differences_without_choosing(self):
        self.add_row("A사", id_="jobkorea:123")
        self.write_json("n.json", [{"기업명": "A사", "직무": "제조AI", "진행상태": "서류합", "서류마감": "2026-12-31", "공고 ID": "jobkorea:123"},
                                   {"기업명": "C사", "직무": "데이터", "진행상태": "Not started"}])
        before = self.read("Areas/취업/지원 현황.md")
        d = self.js(self.ns("diff", "--notion", "n.json"))
        self.assertEqual([(x["칸"], x["볼트"], x["노션"]) for x in d["diffs"]], [("진행상태", "Not started", "서류합")])
        self.assertEqual(d["only_in_notion"][0]["기업명"], "C사")
        self.assertEqual(self.read("Areas/취업/지원 현황.md"), before, "diff 는 현황표를 고치지 않는다")


class WidgetJsonTest(VaultCase):
    def test_widget_json_has_notion_and_scan_fields(self):
        self.write("Areas/취업/_scan-log.md", "# 로그\n- 2026-11-02 08:00 · 무인 실행 종료(소요 90초, 코드 0)\n")
        self.write("Areas/취업/_notion-대기.md", "# 대기\n\n| 날짜 | 표 | 키 | 이유 |\n|---|---|---|---|\n| 2026-11-02 | 지원현황 | a | 연결 안 됨 |\n")
        r = self.run_script("dashboard.py", "today", "--today", "2026-11-02", "--write")
        self.assertEqual(r.code, 0, r.text)
        j = json.loads(self.read("Areas/취업/_widget/오늘 현황.json"))
        self.assertEqual(j["notion"], "off")
        self.assertEqual(j["counts"]["notion_pending"], 1)
        self.assertEqual(j["last_scan"], {"at": "2026-11-02 08:00", "code": 0})
        self.assertIn("new_candidates_today", j["counts"])


if __name__ == "__main__":
    unittest.main()
