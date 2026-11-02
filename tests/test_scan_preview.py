"""자동 수집의 미리보기 점수 준비 시험: 점수 낼 후보 고르기(candidates.py top)와 본문 받기(fetch_posting.py).
실제 채용 사이트는 부르지 않는다 — 본문 받기는 이 PC 안의 시험용 웹 서버(가상 공고 페이지)로 시험한다.
"""
import http.server
import json
import sys
import threading
import unittest

from helpers import SCRIPTS, VaultCase

sys.path.insert(0, str(SCRIPTS))
import fetch_posting as F  # noqa: E402

PAGE = """<html><head><meta charset="utf-8"><meta name="description" content="경력 : 신입, 학력 : 대졸, 마감일 : 2026.11.20(금)">
<script>var x = "자격요건 가짜";</script></head><body><nav>메뉴</nav>
<h2>A사 설비 AI 엔지니어</h2><div>담당업무</div><ul><li>설비 센서 데이터 분석</li></ul>
<div>자격요건</div><ul><li>Python 가능자</li></ul><div>우대사항</div><p>LSTM 경험&nbsp;우대 &amp; 시계열</p>
<div>마감일</div><div>2026.11.20(금)</div></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/ok"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


class FetchPostingTest(VaultCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_text_meta_and_deadline(self):
        r = self.run_script("fetch_posting.py", "url:a.example/1", "--url", self.base + "/ok")
        self.assertEqual(r.code, 0, r.text)
        res = json.loads(r.out.strip().splitlines()[-1])
        self.assertTrue(res["body_likely"])
        self.assertEqual(res["deadline_hint"], "2026-11-20")
        txt = self.read(res["files"][0]["txt"])
        self.assertTrue(txt.startswith("요약 칸: 경력 : 신입, 학력 : 대졸"))
        self.assertIn("- Python 가능자", txt)
        self.assertIn("LSTM 경험 우대 & 시계열", txt)
        self.assertNotIn("var x", txt, "스크립트 글자는 걷어 낸다")
        self.assertTrue(self.path(res["files"][0]["html"]).exists(), "원본 html도 남긴다")
        self.assertTrue(str(self.path(res["dir"])).replace("\\", "/").endswith("Areas/취업/_scan-cache/url-a.example-1"))

    def test_not_found_exit_3(self):
        r = self.run_script("fetch_posting.py", "url:a.example/2", "--url", self.base + "/gone")
        self.assertEqual(r.code, 3, r.text)
        self.assertIn("404", r.out)

    def test_unknown_site_needs_url(self):
        r = self.run_script("fetch_posting.py", "wanted:123")
        self.assertEqual(r.code, 2)

    def test_site_targets(self):
        main, reqs = F.targets("jobkorea:42", None)
        self.assertEqual([u for _, u in reqs], ["https://www.jobkorea.co.kr/Recruit/GI_Read/42",
                                                "https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno=42"])
        self.assertIn("rec_idx=7", F.targets("saramin:7", None)[1][1][1])

    def test_deadline_hint_rolling_and_start_date_not_taken(self):
        self.assertEqual(F.deadline_hint(["마감일 : 상시채용"], ""), "상시")
        text = "마감일은 기업의 사정으로 바뀔 수 있습니다\n\n시작일\n\n2026.10.21(수)\n\n마감일\n\n상시채용\n"
        self.assertEqual(F.deadline_hint([], text), "상시")


class TopCandidatesTest(VaultCase):
    def test_top_picks_matching_unscored_by_deadline(self):
        self.write("Areas/취업/공고 후보함.md", "# 공고 후보함\n\n## 후보\n\n"
                   "| 상태 | 회사 | 공고 | 방향 | 지역 | 서류마감(D-n) | 선별 근거 | 점수 | 링크 | 공고 ID | 발견일 |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
                   "| 새로 | 가사 | t | 일치(제조AI) | 서울 | 마감일 미정 |  |  | u | jobkorea:1 | 2026-11-01 |\n"
                   "| 새로 | 나사 | t | 일치 | 서울 | 2026-11-30 (D-28) |  |  | u | jobkorea:2 | 2026-11-02 |\n"
                   "| 새로 | 다사 | t | 일치 | 서울 | 2026-11-10 (D-8) |  |  | u | jobkorea:3 | 2026-11-02 |\n"
                   "| 새로 | 라사 | t | 약함 | 서울 | 2026-11-05 (D-3) |  |  | u | jobkorea:4 | 2026-11-02 |\n"
                   "| 점수 | 마사 | t | 일치 | 서울 | 2026-11-04 (D-2) |  | 70 🟡 | u | jobkorea:5 | 2026-11-02 |\n"
                   "| 새로 | 바사 | t | 일치 | 서울 | 마감일 미정 |  |  | u | jobkorea:6 | 2026-11-02 |\n"
                   "\n## 후보함_지난\n\n| 상태 | 회사 | 공고 | 방향 | 지역 | 서류마감(D-n) | 선별 근거 | 점수 | 링크 | 공고 ID | 발견일 |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
        r = self.run_script("candidates.py", "top", "--k", "3")
        self.assertEqual(r.code, 0, r.text)
        self.assertEqual([x["id"] for x in json.loads(r.out)], ["jobkorea:3", "jobkorea:2", "jobkorea:6"])
        r = self.run_script("candidates.py", "top", "--k", "5")          # 일치가 4건뿐이면 약함으로 채운다
        self.assertEqual([x["id"] for x in json.loads(r.out)], ["jobkorea:3", "jobkorea:2", "jobkorea:6", "jobkorea:1", "jobkorea:4"])
        r = self.run_script("candidates.py", "top")          # K 는 검색 조건.md 값(가짜 볼트 3)
        self.assertEqual(len(json.loads(r.out)), 3)

    def test_set_score_fills_deadline_from_body(self):
        head = "| 상태 | 회사 | 공고 | 방향 | 지역 | 서류마감(D-n) | 선별 근거 | 점수 | 링크 | 공고 ID | 발견일 |", "|---|---|---|---|---|---|---|---|---|---|---|"
        lines = ["# 공고 후보함", "", "## 후보", "", *head,
                 "| 새로 | 가사 | t | 약함 | 서울 | 마감일 미정 | 마감 여부 미확인 · 소스 잡코리아 |  | u | jobkorea:1 | 2026-11-01 |",
                 "", "## 후보함_지난", "", *head, ""]
        self.write("Areas/취업/공고 후보함.md", chr(10).join(lines))
        r = self.run_script("candidates.py", "set-score", "--id", "jobkorea:1", "--score", "74 🟡", "--deadline", "2099-01-31")
        self.assertEqual(r.code, 0, r.text)
        row = next(ln for ln in self.read("Areas/취업/공고 후보함.md").splitlines() if "jobkorea:1" in ln)
        self.assertIn("2099-01-31 (D-", row)
        self.assertIn("마감 본문 확인", row)
        self.assertIn("74 🟡", row)


if __name__ == "__main__":
    unittest.main()
