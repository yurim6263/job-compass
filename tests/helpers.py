"""스크립트 자동 시험의 공통 부품. 표준 라이브러리(unittest)만 쓴다.

돌리는 법(저장소 루트에서):
    python -I -X utf8 -m unittest discover -s tests -v

시험마다 가짜 볼트(`fixtures/test-vault`)를 **임시 폴더에 새로 복사**해서 그 안에서 `skills/_공용/scripts/` 의 스크립트를 돌린다.
저장소의 파일은 바뀌지 않는다. 실제 볼트·개인 자료는 쓰지 않는다. 모델(Claude)은 부르지 않는다 — 스크립트의 결정적인 부분만 시험한다.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skills" / "_공용" / "scripts"
FAKE_VAULT = REPO / "fixtures" / "test-vault"
TABLE = Path("Areas/취업/지원 현황.md")


class Result:
    def __init__(self, cp):
        self.code = cp.returncode
        self.out = cp.stdout
        self.err = cp.stderr

    @property
    def text(self):
        return self.out + self.err


class VaultCase(unittest.TestCase):
    """각 시험 메서드마다 새 가짜 볼트 사본(`self.vault`)을 만든다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="jc-test-")
        self.addCleanup(self._tmp.cleanup)
        self.vault = Path(self._tmp.name) / "vault"
        shutil.copytree(FAKE_VAULT, self.vault, ignore=shutil.ignore_patterns(".claude", "_backup*"))

    # ---- 실행 ----
    def run_script(self, name, *args, stdin=None):
        """볼트 루트를 현재 폴더로 해서 `python -I -X utf8 <스크립트> args` 를 돌린다."""
        cp = subprocess.run([sys.executable, "-I", "-X", "utf8", str(SCRIPTS / name), *map(str, args)],
                            cwd=self.vault, input=stdin, capture_output=True, text=True, encoding="utf-8")
        return Result(cp)

    # ---- 파일 ----
    def path(self, rel):
        return self.vault / rel

    def read(self, rel):
        return self.path(rel).read_text(encoding="utf-8")

    def write(self, rel, text):
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        return p

    def write_json(self, rel, obj):
        return self.write(rel, json.dumps(obj, ensure_ascii=False))

    # ---- 현황표 ----
    def add_row(self, company, job="제조AI", id_="A-1", deadline="2026-12-31", **kw):
        args = ["add", "--company", company, "--job", job, "--id", id_, "--deadline", deadline, "--type", "신입", "--region", "서울"]
        for k, v in kw.items():
            args += [f"--{k}", v]
        r = self.run_script("status_table.py", *args)
        self.assertEqual(r.code, 0, r.text)
        return r

    def row(self, company, job=None):
        """현황표에서 회사(+직무) 행을 {열이름: 값} 으로."""
        lines = self.read(TABLE).splitlines()
        head = next(i for i, ln in enumerate(lines) if ln.startswith("| 기업명"))
        cols = [c.strip() for c in lines[head].strip("|").split("|")]
        for ln in lines[head + 2:]:
            if not ln.startswith("|"):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            d = dict(zip(cols, cells))
            if d.get("기업명") == company and (job is None or d.get("직무") == job):
                return d
        return None
