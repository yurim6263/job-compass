"""현황표 스크립트(status_table.py) 시험: 행 추가·상태 변경·되돌리기 거부·실수 취소(undo-status)."""
import unittest

from helpers import VaultCase


class StatusTableTest(VaultCase):
    def set_status(self, state, *extra, id_="A-1"):
        return self.run_script("status_table.py", "set-status", "--id", id_, "--state", state, *extra)

    # ---- 추가 ----
    def test_add_row_and_reject_duplicate_id(self):
        self.add_row("A사")
        self.assertEqual(self.row("A사")["진행상태"], "Not started")
        r = self.run_script("status_table.py", "add", "--company", "A사", "--job", "제조AI", "--id", "A-1")
        self.assertEqual(r.code, 3, r.text)           # 같은 공고 ID 는 추가하지 않는다
        self.assertEqual(self.read("Areas/취업/지원 현황.md").count("| A-1 |"), 1)

    def test_add_rejects_value_outside_list(self):
        r = self.run_script("status_table.py", "add", "--company", "A사", "--job", "없는직무", "--id", "A-1")
        self.assertNotEqual(r.code, 0)
        self.assertIsNone(self.row("A사"))

    # ---- 상태 변경 ----
    def test_set_status_updates_state_final_stage_and_memo(self):
        self.add_row("A사")
        r = self.set_status("서류합")
        self.assertEqual(r.code, 0, r.text)
        row = self.row("A사")
        self.assertEqual((row["진행상태"], row["최종 단계"]), ("서류합", "서류합"))
        self.assertIn("서류합", row["메모"])

    def test_invalid_state_rejected(self):
        self.add_row("A사")
        self.assertEqual(self.set_status("없는상태").code, 2)
        self.assertEqual(self.row("A사")["진행상태"], "Not started")

    def test_backwards_move_refused_unless_allowed_and_final_stage_kept(self):
        self.add_row("A사")
        self.set_status("서류합")
        self.assertEqual(self.set_status("지원완료").code, 4)
        self.assertEqual(self.row("A사")["진행상태"], "서류합")
        self.assertEqual(self.set_status("지원완료", "--allow-back").code, 0)
        row = self.row("A사")
        self.assertEqual((row["진행상태"], row["최종 단계"]), ("지원완료", "서류합"))   # 최종 단계는 낮아지지 않는다

    def test_closed_row_is_not_overwritten(self):
        self.add_row("A사")
        self.set_status("불합")
        self.assertEqual(self.set_status("지원완료").code, 4)
        self.assertEqual(self.row("A사")["진행상태"], "불합")

    def test_rows_without_id_are_not_guessed(self):
        self.add_row("C사", job="데이터", id_="—")
        self.add_row("C사", job="LLM응용", id_="—")
        r = self.run_script("status_table.py", "set-status", "--company", "C사", "--state", "지원완료")
        self.assertEqual(r.code, 5, r.text)               # 둘 이상이면 고르지 않는다
        r = self.run_script("status_table.py", "set-status", "--company", "C사", "--job", "데이터", "--state", "지원완료")
        self.assertEqual(r.code, 0, r.text)
        self.assertEqual(self.row("C사", "데이터")["진행상태"], "지원완료")
        self.assertEqual(self.row("C사", "LLM응용")["진행상태"], "Not started")

    # ---- 실수 취소 ----
    def test_undo_without_record_is_refused(self):
        self.add_row("A사")
        self.assertEqual(self.run_script("status_table.py", "undo-status").code, 4)

    def test_undo_preview_changes_nothing_and_apply_restores_four_fields_once(self):
        self.add_row("A사")
        before = self.row("A사")
        self.set_status("서류합")
        after = self.row("A사")
        r = self.run_script("status_table.py", "undo-status")           # 미리보기
        self.assertEqual(r.code, 0, r.text)
        self.assertEqual(self.row("A사"), after)
        r = self.run_script("status_table.py", "undo-status", "--apply")
        self.assertEqual(r.code, 0, r.text)
        self.assertEqual(self.row("A사"), before)                       # 진행상태·상태일·최종 단계·메모 모두 원래대로
        self.assertEqual(self.run_script("status_table.py", "undo-status").code, 4)   # 한 번만

    def test_undo_for_row_without_id(self):
        self.add_row("C사", job="데이터", id_="—")
        before = self.row("C사")
        self.run_script("status_table.py", "set-status", "--company", "C사", "--state", "지원완료")
        self.assertEqual(self.run_script("status_table.py", "undo-status", "--apply").code, 0)
        self.assertEqual(self.row("C사"), before)

    def test_undo_refused_when_row_changed_afterwards(self):
        self.add_row("A사")
        self.set_status("서류합")
        self.run_script("status_table.py", "update-fit", "--id", "A-1", "--memo-add", "추가메모")
        after = self.row("A사")
        self.assertEqual(self.run_script("status_table.py", "undo-status", "--apply").code, 4)
        self.assertEqual(self.row("A사"), after)

    def test_every_write_leaves_a_backup(self):
        self.add_row("A사")
        self.set_status("서류합")
        backups = list(self.path("Areas/취업/_백업").glob("지원 현황.md.bak-*"))
        self.assertGreaterEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
