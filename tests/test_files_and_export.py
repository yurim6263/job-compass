"""파일을 만드는·검사하는 스크립트 시험: 캘린더(.ics) · 워드(.docx) · 백업 · 입력 범위 훑기 · 글자 추출 · 자소서·카드 검사 · 오늘 현황."""
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile

from helpers import VaultCase

ICS = "Areas/취업/내보내기/지원 마감.ics"
CARD_DOC = "Projects/SecondBrain/wiki/내경험_가상프로젝트A.md"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class CalendarTest(VaultCase):
    def build(self):
        r = self.run_script("calendar_export.py", "build", "--today", "2026-11-01")
        self.assertEqual(r.code, 0, r.text)
        return (self.path(ICS)).read_bytes()

    def setUp(self):
        super().setUp()
        self.add_row("A사", id_="A-1", deadline="2026-11-20")
        self.add_row("B사", job="LLM응용", id_="jobkorea:123", deadline="2026-11-25")
        self.add_row("C사", job="데이터", id_="—", deadline="2026-11-30")          # 공고 ID 가 없는 행(한글 회사·직무로 키를 만든다)

    def events(self, b):
        text = b.decode("utf-8").replace("\r\n ", "")          # 접힌 줄 합치기
        return [blk for blk in text.split("BEGIN:VEVENT")[1:]]

    def test_ics_is_wellformed(self):
        b = self.build()
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"), "줄바꿈은 전부 CRLF 여야 한다")
        for line in b.decode("utf-8").split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, "75옥텟을 넘는 줄은 접어야 한다")
        text = b.decode("utf-8")
        self.assertEqual(text.count("BEGIN:VCALENDAR"), 1)
        self.assertEqual(text.count("BEGIN:VEVENT"), text.count("END:VEVENT"))
        self.assertEqual(len(self.events(b)), 3)
        for ev in self.events(b):
            for need in ("UID:", "DTSTAMP:", "DTSTART", "SUMMARY:"):
                self.assertIn(need, ev)

    def test_uids_are_ascii_unique_and_stable(self):
        first = [re.search(r"UID:(\S+)", e).group(1) for e in self.events(self.build())]
        second = [re.search(r"UID:(\S+)", e).group(1) for e in self.events(self.build())]
        self.assertEqual(first, second)                         # 다시 만들어도 같은 UID(캘린더에 다시 가져와도 중복되지 않게)
        self.assertEqual(len(set(first)), 3)
        self.assertTrue(all(u.isascii() for u in first), first)
        self.assertIn("jobcompass-A-1-deadline@job-compass", first)
        self.assertIn("jobcompass-jobkorea-123-deadline@job-compass", first)

    def test_deadline_has_two_alarms(self):
        ev = self.events(self.build())[0]
        self.assertIn("TRIGGER:-P3D", ev)
        self.assertIn("TRIGGER:-P1D", ev)


class DocxTest(VaultCase):
    def test_table_has_borders_bold_header_and_korean_text(self):
        self.write("in.md", "# 제목\n\n- 목록 항목\n\n| 항목 | 값 |\n|---|---|\n| 글자수 | 100 |\n| 근거 | 카드 A |\n\n끝 문단\n")
        r = self.run_script("docx_export.py", "in.md", "out.docx", "--note", "사본 — 시험")
        self.assertEqual(r.code, 0, r.text)
        with zipfile.ZipFile(self.path("out.docx")) as z:
            self.assertIsNone(z.testzip())
            xml = z.read("word/document.xml").decode("utf-8")
        root = ET.fromstring(xml)                              # 올바른 XML 이어야 Word 가 연다
        self.assertEqual(len(root.findall(f".//{W}tbl")), 1)
        self.assertIsNotNone(root.find(f".//{W}tblBorders"))
        first_row = root.find(f".//{W}tr")
        self.assertIsNotNone(first_row.find(f".//{W}b"), "표의 첫 줄(머리)은 굵게")
        text = "".join(t.text or "" for t in root.iter(f"{W}t"))
        for s in ("사본 — 시험", "제목", "목록 항목", "글자수", "카드 A", "끝 문단"):
            self.assertIn(s, text)

    def test_special_characters_are_escaped(self):
        self.write("in.md", "문단 & < > \" ' 끝\n")
        self.assertEqual(self.run_script("docx_export.py", "in.md", "out.docx").code, 0)
        with zipfile.ZipFile(self.path("out.docx")) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        self.assertIn("& < > \" '", "".join(t.text or "" for t in root.iter(f"{W}t")))


class BackupTest(VaultCase):
    def test_backup_goes_outside_wiki_and_is_not_duplicated(self):
        doc = "Projects/SecondBrain/wiki/내경험_시험.md"
        self.write(doc, "v1\n")
        r1 = self.run_script("backup_doc.py", doc)
        self.assertIn("사본 만듦", r1.out)
        r2 = self.run_script("backup_doc.py", doc)
        self.assertIn("이미 같은 사본", r2.out)
        self.write(doc, "v2\n")
        self.assertIn("사본 만듦", self.run_script("backup_doc.py", doc).out)
        self.assertEqual(len(list(self.path("Areas/취업/_백업/경험문서").glob("내경험_시험.md.bak-*"))), 2)
        self.assertEqual(list(self.path("Projects/SecondBrain/wiki").glob("*.bak*")), [])   # wiki/ 에는 사본을 두지 않는다

    def test_backup_of_missing_file_fails(self):
        self.assertEqual(self.run_script("backup_doc.py", "없는파일.md").code, 2)


class IntakeScriptsTest(VaultCase):
    def test_scan_json_with_bare_name_goes_to_cache_not_vault_root(self):
        self.write("in/a.txt", "내용\n")
        r = self.run_script("scan_inputs.py", self.path("in"), "--me", "me", "--json", "scan.json")
        self.assertEqual(r.code, 0, r.text)
        self.assertTrue(self.path("Areas/취업/_scan-cache/intake/scan.json").exists())
        self.assertFalse(self.path("scan.json").exists())

    def test_scan_skips_secret_and_excluded(self):
        self.write("in/ok.txt", "내용\n")
        self.write("in/.env", "KEY=value\n")
        self.write("in/node_modules/x.txt", "x\n")
        r = self.run_script("scan_inputs.py", self.path("in"), "--me", "me")
        self.assertIn("들일 파일 1개", r.out)
        self.assertNotIn("KEY=value", r.out)

    def test_extract_text_refuses_to_overwrite(self):
        self.write("in/note.txt", "첫 줄\n")
        self.assertEqual(self.run_script("extract_text.py", "in/note.txt", "--out-dir", "out").code, 0)
        self.assertEqual(self.run_script("extract_text.py", "in/note.txt", "--out-dir", "out").code, 5)

    def test_unreadable_hwp_creates_nothing(self):
        self.path("in").mkdir()
        (self.path("in") / "x.hwp").write_bytes(bytes(range(200)))
        r = self.run_script("extract_text.py", "in/x.hwp", "--out-dir", "out")
        self.assertEqual(r.code, 4, r.text)
        self.assertFalse(self.path("out").exists() and any(self.path("out").iterdir()))


class CoverLetterCheckTest(VaultCase):
    DOC = "Areas/취업/자소서/t.md"

    def test_char_counts_three_ways_and_limit(self):
        # 문항1 "가나다 라마바 / 사아자": 공백 제외 9 · 공백 포함(줄바꿈 제외) 10 · 줄바꿈까지 11
        self.write(self.DOC, "### 문항 1 지원동기\n가나다 라마바\n사아자\n\n### 문항 2 역량\n> 메모는 세지 않는다\n하나 둘 셋 넷 [수치 확인 필요]\n")
        r = self.run_script("cl_check.py", "chars", self.DOC, "--limits", "1=8,2=100")
        self.assertRegex(r.out, r"\| 1 \| 9 \| 10 \| 11 \| 8\(incl\) \| 125% \| 초과 \|")
        self.assertRegex(r.out, r"\| 2 \| 13 \| 19 \| 19 \|")
        self.assertEqual(r.code, 1, "한도를 넘으면 종료 코드 1")
        r = self.run_script("cl_check.py", "chars", self.DOC, "--limits", "1=100,2=100")
        self.assertEqual(r.code, 0, "한도 안이면(부족해도) 종료 코드 0")
        self.assertIn("부족(90% 미만)", r.out)
        self.assertEqual(self.run_script("cl_check.py", "chars", self.DOC).code, 0)

    def test_placeholders_are_counted(self):
        self.write(self.DOC, "### 문항 1 a\n본문 [수치 확인 필요]\n둘째 [확인 필요] 근거 없음\n")
        r = self.run_script("cl_check.py", "placeholders", self.DOC)
        self.assertIn("`[수치 확인 필요]` 1건", r.out)
        self.assertIn("`[확인 필요]` 1건", r.out)
        self.assertIn("`근거 없음` 1건", r.out)

    def test_numbers_not_in_cards_are_flagged(self):
        self.write(self.DOC, "### 문항 1 a\n정확도 93% 를 냈고 F1 0.89 였다\n")
        r = self.run_script("cl_check.py", "numbers", self.DOC)
        self.assertRegex(r.out, r"\| 0\.89 \| exp-20261031-01 \|")
        self.assertRegex(r.out, r"\| 93% \| \*\*카드에 없음\*\* \|")

    def test_keyword_positions_with_alias(self):
        self.write(self.DOC, "### 문항 1 a\n하나 둘\n\n### 문항 2 b\n셋 넷\n")
        r = self.run_script("cl_check.py", "keywords", self.DOC, "--kw", "하나|넷,없는말")
        self.assertRegex(r.out, r"\| 하나\|넷 \| 1\.1, 2\.1 \| 2 \|")      # 별칭은 어느 쪽이든 센다(문항1 문단1 · 문항2 문단1)
        self.assertRegex(r.out, r"\| 없는말 \| 없음 \| 0 \|")


class CardVerifyTest(VaultCase):
    def test_clean_document_has_no_fail(self):
        r = self.run_script("verify_cards.py", CARD_DOC)
        self.assertEqual(r.code, 0, r.text)
        self.assertIn("FAIL 0", r.out)

    def test_invented_keyword_fails(self):
        bad = self.read(CARD_DOC).replace("- keywords: [LSTM, 전처리, 윈도우, F1, Python]", "- keywords: [LSTM, 양자컴퓨팅]")
        self.write("Projects/SecondBrain/wiki/내경험_불량.md", bad)
        r = self.run_script("verify_cards.py", "Projects/SecondBrain/wiki/내경험_불량.md")
        self.assertEqual(r.code, 1, r.text)
        self.assertIn("양자컴퓨팅", r.out)
        self.assertRegex(r.out, r"FAIL [1-9]")


class VagueExpressionTest(VaultCase):
    def verify_with_role(self, role):
        text = self.read(CARD_DOC)
        new = re.sub(r"(?m)^- role: .*$", "- role: " + role, text, count=1)
        self.assertNotEqual(text, new)
        self.write("Projects/SecondBrain/wiki/내경험_표현.md", new)
        return self.run_script("verify_cards.py", "Projects/SecondBrain/wiki/내경험_표현.md")

    def test_vague_phrases_are_warned_not_failed(self):
        r = self.verify_with_role("다양한 경험을 통해 책임감을 가지고 소통 능력을 발휘해 많은 것을 배웠고 팀에 기여했다. 열심히 했다")
        self.assertEqual(r.code, 0, "경고일 뿐이라 종료 코드는 0")
        self.assertIn("DONE_WITH_CONCERNS", r.out)
        for phrase in ("다양한 경험", "책임감", "소통 능력", "많은 것을 배웠", "팀에 기여", "열심히"):
            self.assertIn(f"`{phrase}`", r.out)

    def test_concrete_role_is_not_warned(self):
        r = self.verify_with_role("센서 로그의 결측값 보간 규칙과 이상치 기준(평균 ±3표준편차)을 정했다")
        self.assertNotIn("모호한 표현", r.out)


class CandidatesTest(VaultCase):
    def items(self, query, n, source="잡코리아"):
        return [{"company": f"{query}사{i}", "title": f"{query} 엔지니어 {i}", "url": f"https://example.com/{query}/{i}", "id": f"{query}:{i}",
                 "deadline": "", "region": "서울", "source": source, "query": query} for i in range(n)]

    def set_limit(self, n):
        cond = self.read("Areas/취업/검색 조건.md")
        self.assertIn("| 후보 최대 N건 | 20 |", cond)
        self.write("Areas/취업/검색 조건.md", cond.replace("| 후보 최대 N건 | 20 |", f"| 후보 최대 N건 | {n} |"))

    def ingest(self, items):
        self.write_json("Areas/취업/_scan-cache/c.json", items)
        r = self.run_script("candidates.py", "ingest", "Areas/취업/_scan-cache/c.json")
        self.assertEqual(r.code, 0, r.text)
        return r

    def test_limit_is_shared_between_queries_not_used_up_by_the_first(self):
        self.set_limit(4)
        self.ingest(self.items("예지보전", 5) + self.items("스마트팩토리", 5))       # 첫 검색어만으로 상한을 채울 수 있는 입력
        board = self.read("Areas/취업/공고 후보함.md")
        self.assertEqual(board.count("| 예지보전사"), 2)
        self.assertEqual(board.count("| 스마트팩토리사"), 2)
        self.assertIn("상한 초과", self.read("Areas/취업/_scan-log.md") + "상한 초과")   # 로그에는 '더 있음'이 남는다(아래에서 별도 확인)
        self.assertIn("더 있음(상한 초과)", self.read("Areas/취업/_scan-log.md"))

    def test_without_query_field_original_order_is_kept(self):
        self.set_limit(3)
        items = self.items("가", 4)
        for it in items:
            del it["query"]
        self.ingest(items)
        board = self.read("Areas/취업/공고 후보함.md")
        self.assertEqual([board.count(f"| 가사{i} ") for i in range(4)], [1, 1, 1, 0])

    def test_interleave_is_stable(self):
        self.set_limit(20)
        self.ingest(self.items("a", 2) + self.items("b", 2))
        rows = [ln for ln in self.read("Areas/취업/공고 후보함.md").splitlines() if "엔지니어" in ln]
        self.assertEqual(len(rows), 4)

    def test_dashboard_counts_each_candidate_once(self):
        self.ingest(self.items("a", 3))
        r = self.run_script("dashboard.py", "today", "--today", "2026-11-01")
        self.assertIn("후보 3건", r.out)                 # `후보함_지난` 표의 머리 줄을 후보로 세지 않는다


class DashboardTest(VaultCase):
    def test_empty_table_is_a_normal_entry(self):
        r = self.run_script("dashboard.py", "today", "--today", "2026-11-01")
        self.assertEqual(r.code, 0, r.text)
        self.assertIn("정상 진입", r.out)

    def test_near_deadline_row_is_shown_and_write_makes_copies(self):
        self.add_row("A사", id_="A-1", deadline="2026-11-03")
        r = self.run_script("dashboard.py", "today", "--today", "2026-11-01", "--write")
        self.assertEqual(r.code, 0, r.text)
        self.assertIn("A사", r.out)
        self.assertIn("A사", self.read("Areas/취업/오늘 현황.md"))
        self.assertTrue(self.path("Areas/취업/_widget/오늘 현황.json").exists())


if __name__ == "__main__":
    unittest.main()
