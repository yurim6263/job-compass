"""자소서 카드 추천(card_recommend.py) 시험. 가짜 볼트의 가상 카드 4장(01·02 자료확인, 03 미확인, 04 본인진술)을 쓴다."""
import json
import unittest

from helpers import VaultCase

C01, C02, C03, C04 = (f"exp-20261031-0{i}" for i in (1, 2, 3, 4))

BASE = {
    "company": "A사",
    "job_tags": ["제조AI", "설비데이터", "시계열예측"],
    "questions": [
        {"no": 1, "text": "지원동기", "types": ["지원동기"], "keywords": ["LSTM", "전처리"]},
        {"no": 2, "text": "직무 경험과 역량", "types": ["직무역량"], "keywords": ["Python", "LSTM", "전처리", "F1"]},
    ],
}


class CardRecommendTest(VaultCase):
    def recommend(self, **extra):
        self.write_json("in.json", {**BASE, **extra})
        r = self.run_script("card_recommend.py", "in.json", "--json")
        self.assertEqual(r.code, 0, r.text)
        return json.loads(r.out)

    def test_unconfirmed_card_is_excluded(self):
        res = self.recommend()
        self.assertEqual(res["cards"], 3)
        self.assertEqual(res["excluded"]["미확인"], 1)
        used = {v["first"] for v in res["result"].values()} | {a for v in res["result"].values() for a in v["alts"]}
        self.assertNotIn(C03, used)

    def test_same_input_gives_same_output(self):
        self.assertEqual(self.recommend(), self.recommend())

    def test_one_card_is_main_material_only_once(self):
        res = self.recommend()["result"]
        self.assertEqual(res["1"]["first"], C01)       # 문항 1에는 겹치는 카드가 01 하나뿐
        self.assertNotEqual(res["2"]["first"], C01)    # 01 은 이미 문항 1의 주 소재
        self.assertIn(C01, res["2"]["alts"])           # 대안으로는 보인다

    def test_blocked_better_card_is_reported_in_text(self):
        self.write_json("in.json", BASE)
        r = self.run_script("card_recommend.py", "in.json")
        self.assertIn("주의", r.out)
        self.assertIn(f"{C01}(8.0점)", r.out)
        self.assertIn("1번 문항의 주 소재", r.out)

    def test_pin_is_honored_and_rest_is_redistributed(self):
        res = self.recommend(pins={"2": C01})
        self.assertEqual(res["pin_errors"], [])
        self.assertEqual(res["result"]["2"]["first"], C01)
        self.assertTrue(res["result"]["2"]["pinned"])
        self.assertFalse(res["result"]["1"]["pinned"])
        self.assertNotEqual(res["result"]["1"]["first"], C01)         # 01 은 문항 2 로 고정됐으니 문항 1에서는 빠진다

    def test_pin_text_marks_user_choice(self):
        self.write_json("in.json", {**BASE, "pins": {"1": C01, "2": C02}})
        r = self.run_script("card_recommend.py", "in.json")
        self.assertEqual(r.out.count("사용자 지정"), 2)
        self.assertNotIn("고정 불가", r.out)

    def test_pin_may_override_low_score(self):
        res = self.recommend(pins={"1": C04})                          # 문항 1과 겹침이 없는 카드도 사용자가 고르면 따른다
        self.assertEqual(res["result"]["1"]["first"], C04)

    def test_bad_pins_are_reported_not_applied(self):
        res = self.recommend(pins={"1": C03, "2": "exp-99999999-99", "7": C01})
        self.assertEqual(len(res["pin_errors"]), 3)
        self.assertFalse(any(v["pinned"] for v in res["result"].values()))

    def test_same_card_cannot_be_pinned_twice(self):
        res = self.recommend(pins={"1": C01, "2": C01})
        self.assertEqual(res["result"]["1"]["first"], C01)
        self.assertEqual(len(res["pin_errors"]), 1)
        self.assertIn("2", res["pin_errors"][0])
        self.assertFalse(res["result"]["2"]["pinned"])


if __name__ == "__main__":
    unittest.main()
