"""교육 이수 정리(course_tools.py) 시험: 형식 검사 · 점수에서 교육 이수는 최대 '부분' · Notion 경험 정리의 [교육] 줄.
가상 과정·가상 파일만 쓴다."""
import json
import unittest

from helpers import VaultCase

RAW = "Projects/SecondBrain/raw/내경험/가상교육/커리큘럼.md"
LAB = "Projects/SecondBrain/raw/내경험/가상교육/실습1.md"
CARD = "exp-20261031-01"           # 가짜 볼트에 있는 카드(자료확인)


def course_doc(skills, completion="수료", fact="자료확인", evidence=None):
    ev = evidence if evidence is not None else f"  - [[{RAW}|커리큘럼]] — 과정 개요"
    return ("---\ntags: [교육이수]\nsources:\n  - \"[[" + RAW + "|커리큘럼]]\"\nupdated: 2026-11-02\norigin: 교육과정\n---\n\n"
            "# 가상 데이터 과정\n\n### edu-20261102-01 가상 데이터 과정\n- institution: 가상교육원\n- period: 2025-03 ~ 2025-08\n"
            f"- completion: {completion}\n- job_link_tags: [데이터파이프라인, LLM응용]\n- skills:\n" +
            "".join(f"  - {s}\n" for s in skills) + f"- projects: [{CARD}]\n- evidence:\n{ev}\n- fact_status: {fact}\n")


GOOD = [f"데이터 전처리(pandas) | 실습 | [[{LAB}|실습1]] — 2주차", f"AWS EC2 배포 | 수강 | [[{RAW}|커리큘럼]] — 9주차",
        f"FastAPI 백엔드 | 과제 | {CARD}"]


class CourseToolsTest(VaultCase):
    def setUp(self):
        super().setUp()
        self.write(RAW, "# 가상 커리큘럼\n")
        self.write(LAB, "# 가상 실습\n")

    def put(self, text):
        return self.write("Projects/SecondBrain/wiki/교육이수_가상 데이터 과정.md", text)

    def check(self):
        return self.run_script("course_tools.py", "check", "Projects/SecondBrain/wiki/교육이수_가상 데이터 과정.md")

    def test_good_doc_passes_and_lists(self):
        self.put(course_doc(GOOD))
        r = self.check()
        self.assertEqual(r.code, 0, r.text)
        self.assertIn("PASS", r.out)
        r = self.run_script("course_tools.py", "list")
        self.assertIn("과제 1 · 실습 1 · 수강 1", r.out)

    def test_bad_docs_fail(self):
        cases = {
            "수준 밖": [f"파이썬 | 마스터 | [[{RAW}|커리큘럼]]"],
            "과제인데 카드 없음": [f"백엔드 | 과제 | [[{RAW}|커리큘럼]]"],
            "없는 카드": ["백엔드 | 과제 | exp-20991231-99"],
            "근거 없음": ["프론트엔드 | 수강 |"],
            "없는 파일": ["LLM | 실습 | [[Projects/SecondBrain/raw/없음.md|없음]]"],
        }
        for name, skills in cases.items():
            self.put(course_doc(skills))
            r = self.check()
            self.assertEqual(r.code, 1, f"{name}: {r.text}")
        self.put(course_doc(GOOD, completion="졸업"))
        self.assertEqual(self.check().code, 1, "completion 값 목록 밖")

    def test_performance_words_warn(self):
        self.put(course_doc(GOOD + [f"AWS로 서비스 운영했음 | 수강 | [[{RAW}|커리큘럼]]"]))
        r = self.check()
        self.assertEqual(r.code, 0, r.text)
        self.assertIn("DONE_WITH_CONCERNS", r.out)

    def test_score_edu_is_at_most_partial_and_tech_half(self):
        self.put(course_doc(GOOD))
        base = {"job": "제조AI", "region": "서울", "body": True, "P": [],
                "gates": {"경력": "신입가능", "학력": "학사가능", "마감": "남음", "지역": "안"}}
        self.write_json("in.json", {**base, "Q": [{"id": "Q1", "verdict": "증명", "cards": ["edu-20261102-01"], "note": "n"}],
                                    "tech": ["AWS EC2 배포"]})
        r = self.run_script("score_calc.py", "in.json", "--json")
        self.assertEqual(r.code, 0, r.text)
        res = json.loads(r.out)
        # A = 45 × 0.5(증명→부분) = 22.5 · C = 15 × 0.5(교육 이수에만 있는 기술) = 7.5
        self.assertEqual(res["parts"]["A"], 22.5)
        self.assertEqual(res["parts"]["C"], 7.5)

    def test_cover_letter_suggests_course_as_support_only(self):
        self.put(course_doc(GOOD))
        self.write_json("rec.json", {"company": "가상A사", "job_tags": ["LLM응용"], "questions": [
            {"no": 1, "text": "직무 역량", "types": ["직무역량"], "keywords": ["FastAPI 백엔드", "pandas"]},
            {"no": 2, "text": "성장 과정", "types": ["성장"], "keywords": []},
            {"no": 3, "text": "협업", "types": ["협업"], "keywords": ["회의"]}]})
        r = self.run_script("card_recommend.py", "rec.json", "--json")
        self.assertEqual(r.code, 0, r.text)
        res = json.loads(r.out)["result"]
        self.assertEqual(res["1"]["edu"], ["edu-20261102-01"], "기술 낱말이 겹치면 보조 근거")
        self.assertEqual(res["2"]["edu"], ["edu-20261102-01"], "성장 문항은 직무 태그만 맞아도")
        self.assertEqual(res["3"]["edu"], [], "관련 없는 문항엔 제안 안 함")
        for v in res.values():
            self.assertFalse(str(v["first"]).startswith("edu-"), "교육 이수는 카드 자리를 차지하지 않음")
        out = self.run_script("card_recommend.py", "rec.json").out
        self.assertIn("교육 이수(보조 근거): edu-20261102-01 가상 데이터 과정 — ", out)
        self.assertIn("FastAPI 백엔드(과제)", out)
        # 교육 이수는 고정(pins)할 수 없다
        self.write_json("rec2.json", {"job_tags": [], "questions": [{"no": 1, "text": "x", "types": ["성장"], "keywords": []}],
                                      "pins": {"1": "edu-20261102-01"}})
        self.assertTrue(json.loads(self.run_script("card_recommend.py", "rec2.json", "--json").out)["pin_errors"])

    def test_notion_plan_has_course_row(self):
        self.put(course_doc(GOOD))
        r = self.run_script("notion_sync.py", "plan", "--table", "경험정리")
        self.assertEqual(r.code, 0, r.text)
        rows = [i for i in json.loads(r.out)["items"] if i["key"].startswith("edu-")]
        self.assertEqual(len(rows), 1)
        p = rows[0]["props"]
        self.assertEqual(p["카드 제목"], "[교육] 가상 데이터 과정")
        self.assertIn("과제: FastAPI 백엔드", p["한 줄 요약"])
        self.assertIn("수강: AWS EC2 배포", p["한 줄 요약"])
        self.assertEqual(json.loads(r.out)["problems"], [])


if __name__ == "__main__":
    unittest.main()
