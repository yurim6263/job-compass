"""계산 스크립트 시험: 공고 점수(score_calc) · 기업 조사 판단(company_calc) · 면접 통과율(interview_tools calc).
기대값은 스크립트를 돌려 베낀 것이 아니라 규칙(스크립트 머리말·기획 문서)으로 **손계산**한 값이다."""
import json
import unittest

from helpers import VaultCase

C01, C02, C04 = "exp-20261031-01", "exp-20261031-02", "exp-20261031-04"   # 01·02 자료확인(×1.0), 04 본인진술(×0.8), 03 미확인


def q(id_, verdict, cards=(), **kw):
    return {"id": id_, "verdict": verdict, "cards": list(cards), "note": "n", **kw}


GATES_OK = {"경력": "신입가능", "학력": "학사가능", "마감": "남음", "지역": "안"}


class ScoreCalcTest(VaultCase):
    def score(self, **inp):
        base = {"job": "제조AI", "region": "서울", "body": True, "Q": [], "P": [], "tech": [], "gates": GATES_OK}
        self.write_json("in.json", {**base, **inp})
        r = self.run_script("score_calc.py", "in.json", "--json")
        return r.code, (json.loads(r.out) if r.out.strip().startswith("{") else None)

    def test_hand_calculated_total(self):
        # A = 45 × (1.0×1.0 + 0.5×0.8 + 0 + 안내는 제외) ÷ 3 = 21.0
        # B = 15 × 1.0 ÷ 1 = 15.0 · C = 15 × (LSTM✓ Python✓ Docker✗) ÷ 3 = 10.0 · D = 15(제조AI) · E = 10(서울)
        code, res = self.score(
            Q=[q("Q1", "증명", [C01]), q("Q2", "부분", [C04]), q("Q3", "갭"), q("Q4", "안내")],
            P=[q("P1", "증명", [C02])], tech=["LSTM", "Python", "Docker"])
        self.assertEqual(code, 0)
        self.assertEqual(res["parts"], {"A": 21.0, "B": 15.0, "C": 10.0, "D": 15.0, "E": 10.0})
        self.assertEqual((res["total"], res["grade"], res["counted"]), (71, "🟡", 5))

    def test_grade_boundaries(self):
        # 증명 1개(자료확인)만: A=45, B·C 없음(분모에서 제외), D=15, E=10 → 70/70 = 100 🟢
        code, res = self.score(Q=[q("Q1", "증명", [C01])])
        self.assertEqual((res["total"], res["grade"]), (100, "🟢"))
        # 전부 갭이면 A=0: 0+15+10 = 25 / 70 = 35.7 → 36 🔴
        code, res = self.score(Q=[q("Q1", "갭")])
        self.assertEqual((res["total"], res["grade"]), (36, "🔴"))

    def test_proof_downgraded_to_partial_when_numbers_required_but_not_confirmed(self):
        # 01 의 numbers 는 △(O 가 아님) → 수치를 요구하는 증명은 부분(0.5)으로: A = 45 × 0.5 = 22.5
        code, res = self.score(Q=[q("Q1", "증명", [C01], needs_numbers=True)])
        self.assertEqual(res["parts"]["A"], 22.5)
        self.assertTrue(res["Q"][0]["calc_notes"])

    def test_no_body_means_no_score(self):
        code, res = self.score(body=False, Q=[q("Q1", "증명", [C01])])
        self.assertNotEqual(res["status"], "산출")

    def test_unknown_card_id_is_input_error(self):
        code, _ = self.score(Q=[q("Q1", "증명", ["exp-00000000-99"])])
        self.assertEqual(code, 2)

    def test_gate_is_attached_not_subtracted(self):
        _, plain = self.score(Q=[q("Q1", "증명", [C01])])
        _, gated = self.score(Q=[q("Q1", "증명", [C01])], gates={**GATES_OK, "경력": "필수"})
        self.assertEqual(plain["total"], gated["total"])
        self.assertTrue(gated["gate_marks"])
        self.assertFalse(plain["gate_marks"])


def kws(verdict, n):
    cards = [C01] if verdict in ("O", "모호") else []
    return [{"kw": f"{verdict}{i}", "verdict": verdict, "cards": cards, "note": "n"} for i in range(n)]


class CompanyCalcTest(VaultCase):
    def calc(self, **inp):
        base = {"keywords": [], "job_fit": "🟡", "growth": "O", "stability": "O", "region": "O", "gate_blocked": False, "body_missing": False}
        self.write_json("in.json", {**base, **inp})
        r = self.run_script("company_calc.py", "in.json", "--json")
        return r.code, (json.loads(r.out) if r.out.strip().startswith("{") else None)

    def test_rate_and_criteria(self):
        # (3 + 0.5×2) ÷ (3+2+1) = 66.7%, 제외 1개는 분모에서 뺌 → 기술 적합 △, 직무 🟡 → △
        code, res = self.calc(keywords=kws("O", 3) + kws("모호", 2) + kws("X", 1) + kws("제외", 1), stability="보류")
        self.assertEqual((res["rate"], res["counted"]), (66.7, "6/7"))
        self.assertEqual((res["criteria"]["기술 적합"], res["criteria"]["직무 적합"]), ("△", "△"))
        self.assertEqual(res["decision"], "조건부 지원")

    def test_recommend_when_three_o_and_no_x(self):
        _, res = self.calc(keywords=kws("O", 4), job_fit="🟢")     # 기술 O(100%) · 직무 O · 성장 O · 안정 O · 지역 O
        self.assertEqual(res["decision"], "지원 권장")

    def test_gate_block_forces_careful_review(self):
        _, res = self.calc(keywords=kws("O", 4), job_fit="🟢", gate_blocked=True)
        self.assertEqual(res["decision"], "신중 검토")

    def test_two_x_forces_careful_review(self):
        _, res = self.calc(keywords=kws("O", 4), job_fit="🔴", growth="X")
        self.assertEqual(res["decision"], "신중 검토")

    def test_unscored_job_fit_is_pending_not_x(self):
        _, res = self.calc(keywords=kws("O", 4), job_fit="미산출")
        self.assertEqual(res["criteria"]["직무 적합"], "보류")

    def test_keyword_without_card_is_input_error(self):
        code, _ = self.calc(keywords=[{"kw": "a", "verdict": "O", "cards": [], "note": "n"}])
        self.assertEqual(code, 2)


def checks(over=None):
    c = {str(i): True for i in range(1, 10)}
    c["10"] = None                                   # 해당 없음은 분모에서 뺀다
    c.update({str(k): v for k, v in (over or {}).items()})
    return c


def answer(q_, topic, ch, unanswered=False):
    return {"q": q_, "topic": topic, "unanswered": unanswered, "checks": ch, "quotes": {k: "인용" for k, v in ch.items() if v}}


class InterviewCalcTest(VaultCase):
    def calc(self, answers):
        self.write_json("s.json", {"mode": "인성", "intensity": "보통", "company": "A사", "job": "j", "answers": answers})
        r = self.run_script("interview_tools.py", "calc", "s.json", "--json")
        return r.code, (json.loads(r.out) if r.out.strip().startswith("{") else None), r

    def test_rate_counts_only_applicable_items(self):
        # 질문1: 1~9 중 5·9번 아니오 → 7/9 · 질문2: 무응답 → 0/0(분모에 안 넣음) · 합계 7/9 = 77.8% → 78
        code, res, _ = self.calc([answer("Q1", "지원동기", checks({5: False, 9: False})),
                                  answer("Q2", "역량", {}, unanswered=True)])
        self.assertEqual(code, 0)
        self.assertEqual((res["yes"], res["n"], res["rate"]), (7, 9, 78))
        self.assertEqual([(a["yes"], a["n"]) for a in res["per_answer"]], [(7, 9), (0, 0)])

    def test_fact_mismatch_is_reported(self):
        _, res, _ = self.calc([answer("Q1", "지원동기", checks({7: False}))])
        self.assertTrue(res["fact_mismatch"])

    def test_yes_without_quote_is_input_error(self):
        ans = answer("Q1", "지원동기", checks())
        ans["quotes"] = {}
        code, _, r = self.calc([ans])
        self.assertEqual(code, 2, r.text)


if __name__ == "__main__":
    unittest.main()
