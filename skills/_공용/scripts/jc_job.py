"""취업 스킬 공용 상수와 현황표 읽기·쓰기 부품. 값 목록의 기준은 references/status-values.md.

status_table.py · calendar_export.py · score_calc.py 가 `import jc_job` 으로 쓴다. 표준 라이브러리만 쓴다.
"""
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

COLUMNS = ["기업명", "직무", "진행상태", "유형", "서류마감", "공고", "공고 ID", "채널", "상태일", "메모", "적합도", "지역", "최종 단계"]
OLD_COLUMNS = COLUMNS[:10]

STAGE_ORDER = ["Not started", "일정 + 자소서 항목 정리", "인적사항 입력완료", "자소서 작성중", "자소서 작성 완료",
               "지원완료", "서류합", "역량검사", "인적성", "1차면접", "2차면접", "최종면접", "최종합"]
TERMINAL = ["불합", "지원취소"]
STATES = STAGE_ORDER + TERMINAL
PRE_APPLY = STAGE_ORDER[:5]                  # 서류마감이 아직 의미 있는 상태
CLOSED = ["최종합", "불합", "지원취소"]
JOBS = ["제조AI", "CBM시스템개발자", "LLM응용", "데이터", "기타"]
TYPES = ["신입", "인턴", "채용연계"]
REGIONS = ["서울", "경기", "대구", "부산", "울산", "포항", "그 밖", "원격", "미기재"]

FILE_TABLE = Path("Areas/취업/지원 현황.md")
BACKUP_DIR = Path("Areas/취업/_백업")

HEADER = """# 지원 현황

> `/job-posting`이 공고를 넣을 때 한 줄씩 추가한다. 상태·메모·최종 단계는 `/job-flow`만 고친다. 같은 공고는 공고 ID로 판단한다(재공고는 ID가 달라 새 행).
> 진행상태 — 할 일: Not started · 일정 + 자소서 항목 정리 / 진행: 인적사항 입력완료 · 자소서 작성중 · 자소서 작성 완료 · 지원완료 / 완료: 서류합 · 역량검사 · 인적성 · 1차면접 · 2차면접 · 최종면접 · 최종합 · 불합 · 지원취소
> 직무 — 제조AI · CBM시스템개발자 · LLM응용 · 데이터 · 기타 중 낱말 하나. 유형 — 신입 · 인턴 · 채용연계 중 하나, 안 맞으면 비움.
> 적합도 — 공고 점수와 등급(예: `82 🟢`), 점수가 없으면 `미산출`. 지역 — 근무지 낱말. 최종 단계 — 지금까지 도달한 가장 높은 단계.

"""


def today_kst():
    return datetime.now(KST).date()


def parse_date(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def weekday_ko(d):
    return WEEKDAY_KO[d.weekday()]


def split_row(line):
    """| a | b \\| c | → ['a', 'b | c'] (이스케이프된 | 는 칸 안의 글자)"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur.append("\\|")
            i += 2
        elif s[i] == "|":
            cells.append("".join(cur).strip())
            cur = []
            i += 1
        else:
            cur.append(s[i])
            i += 1
    cells.append("".join(cur).strip())
    return cells


def cell(v):
    return re.sub(r"(?<!\\)\|", r"\\|", str(v).replace("\n", " ")).strip()    # 이미 \| 인 것은 다시 이스케이프하지 않는다


class Table:
    """`지원 현황.md` 한 파일. 표 밖의 글은 그대로 보존한다."""

    def __init__(self, path=FILE_TABLE):
        self.path = Path(path)
        self.lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        self.head_idx = None
        self.cols = None
        for i, ln in enumerate(self.lines):
            if ln.lstrip().startswith("|") and "기업명" in ln and "진행상태" in ln:
                self.head_idx = i
                self.cols = split_row(ln)
                break
        self.rows = []
        self.first = self.last = None
        if self.head_idx is not None:
            j = self.head_idx + 2          # 구분선 다음
            self.first = j
            while j < len(self.lines) and self.lines[j].lstrip().startswith("|"):
                cells = split_row(self.lines[j])
                self.rows.append(cells)
                j += 1
            self.last = j                  # 표 다음 줄

    def problems(self):
        out = []
        if self.head_idx is None:
            return ["현황표 머리줄(기업명 … 진행상태)을 찾지 못함"]
        if self.cols != COLUMNS:
            if self.cols == OLD_COLUMNS:
                out.append("10열 옛 형식 — `migrate`로 13열로 바꿔야 함")
            else:
                out.append(f"열이 기대와 다름: {self.cols}")
            return out
        sep = self.lines[self.head_idx + 1] if self.head_idx + 1 < len(self.lines) else ""
        if not re.match(r"^\s*\|[\s:|-]+\|\s*$", sep):
            out.append("머리줄 다음이 구분선(|---|)이 아님")
        for n, r in enumerate(self.rows, 1):
            if len(r) != len(COLUMNS):
                out.append(f"{n}번째 행의 칸 수가 {len(r)}개(기대 {len(COLUMNS)})")
        return out

    def as_dicts(self):
        res = []
        for r in self.rows:
            d = {c: (r[i] if i < len(r) else "") for i, c in enumerate(self.cols or COLUMNS)}
            res.append(d)
        return res

    def render_row(self, d):
        return "| " + " | ".join(cell(d.get(c, "")) for c in COLUMNS) + " |"

    def save(self, rows_as_dicts, backup=True, head_lines=None):
        """표 부분만 다시 쓰고 나머지는 보존. 쓰기 전 .bak 사본. head_lines 를 주면 표 앞의 머리말을 그걸로 바꾼다."""
        if self.path.exists() and backup:
            backup_file(self.path)
        if self.head_idx is None:
            lines = (head_lines if head_lines is not None else HEADER.splitlines())
            lines = lines + ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
            lines += [self.render_row(d) for d in rows_as_dicts]
        else:
            lines = list(head_lines if head_lines is not None else self.lines[: self.head_idx])
            lines.append("| " + " | ".join(COLUMNS) + " |")
            lines.append("|" + "---|" * len(COLUMNS))
            lines += [self.render_row(d) for d in rows_as_dicts]
            lines += self.lines[self.last:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def backup_file(path, subdir=None):
    """덮어쓰는 정본 파일은 수정 전 사본을 Areas/취업/_백업/(subdir 를 주면 그 아래) 에 남긴다(자동 삭제 없음).
    가장 최근 사본과 내용이 같으면 새로 만들지 않고 그 사본을 돌려준다(같은 파일을 연달아 보강해도 사본이 쌓이지 않게)."""
    path = Path(path)
    folder = BACKUP_DIR / subdir if subdir else BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    olds = sorted(folder.glob(f"{path.name}.bak-*"), key=lambda p: p.stat().st_mtime)
    if olds and olds[-1].read_bytes() == path.read_bytes():
        return olds[-1]
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    dst = folder / f"{path.name}.bak-{stamp}"
    n = 1
    while dst.exists():
        n += 1
        dst = folder / f"{path.name}.bak-{stamp}-{n}"
    shutil.copy2(path, dst)
    return dst


def fit_ok(s):
    """적합도 칸 형식: 비움 · `미산출` · `74 🟡` (뒤에 🚫/⚠️ 메모 가능)"""
    s = s.strip()
    return s == "" or s.startswith("미산출") or re.match(r"^\d{1,3} [🟢🟡🔴]", s) is not None


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)
