#!/usr/bin/env python3
"""`wiki/내경험_자료목록.md` 를 관리한다. intake가 만들고 organize가 읽는다.

쓰는 법(볼트 루트에서):
  python -I -X utf8 source_list.py init   [--me a,b]
  python -I -X utf8 source_list.py has    --orig <원 경로> [--sha <12자>]      # 있으면 0, 없으면 1
  python -I -X utf8 source_list.py add    --orig <원 경로> --kind <형태> --size <크기> --raw <raw 경로(볼트 기준)>
                                          --sha <12자> [--origin 후보] [--key 후보] [--sensitive 메모] [--status 상태]
  python -I -X utf8 source_list.py skip   --orig <원 경로> --reason <이유>
  python -I -X utf8 source_list.py ask    --text <organize에서 물을 것>
  python -I -X utf8 source_list.py me     --names a,b                           # 내 작성자 이름 기록(사용자가 알려 준 것만)

문서는 표 3개(들인 자료 / 건너뜀·미수집 / 물을 것)와 '내 작성자 이름' 한 줄로 이루어진다.
frontmatter 의 sources 에는 들인 raw 파일을 [[링크]]로 단다(볼트 규칙 3). 같은 줄은 두 번 넣지 않는다.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_common as jc  # noqa: E402

DOC = Path("Projects/SecondBrain/wiki/내경험_자료목록.md")
H_ME = "## 내 작성자 이름"
H_IN = "## 들인 자료"
H_SKIP = "## 건너뜀·미수집"
H_ASK = "## organize에서 물을 것"
TBL_IN = ("| 원 경로 | 형태 | 크기 | 들인 곳 | sha256(12) | origin 후보 | project_key 후보 | 민감 | 수집일 | 상태 |\n"
          "|---|---|---|---|---|---|---|---|---|---|")
TBL_SKIP = "| 원 경로 | 이유 | 수집일 |\n|---|---|---|"

TEMPLATE = f"""---
tags: [내경험, 자료목록]
sources: []
updated: {{today}}
---

# 내경험 자료목록

> `/exp-intake`가 만들고 `/exp-organize`가 읽는다. 들인 자료를 한 줄씩 적는다. origin·project_key는 **후보**일 뿐이고 확정은 `/exp-organize`에서 사용자와 한다.

{H_ME}

(아직 사용자에게 확인하지 않음)

{H_IN}

{TBL_IN}

{H_SKIP}

{TBL_SKIP}

{H_ASK}

"""


def load():
    if not DOC.exists():
        sys.exit("자료목록이 없다. 먼저 init 을 실행한다.")
    return DOC.read_text(encoding="utf-8")


def save(text):
    text = re.sub(r"^updated: .*$", f"updated: {jc.today()}", text, count=1, flags=re.M)
    DOC.write_text(text, encoding="utf-8", newline="\n")


def section_end(text, header):
    """header 섹션 끝(다음 '## ' 직전 또는 문서 끝)의 위치."""
    i = text.index(header)
    m = re.search(r"^## ", text[i + len(header):], flags=re.M)
    return i + len(header) + (m.start() if m else len(text) - i - len(header))


def append_line(text, header, line):
    end = section_end(text, header)
    chunk = text[:end].rstrip("\n") + "\n" + line + "\n\n"
    return chunk + text[end:].lstrip("\n")


def add_source(text, raw):
    link = f'  - "[[{raw}|{Path(raw).name}]]"'
    if link in text:
        return text
    if "sources: []" in text:
        return text.replace("sources: []", f"sources:\n{link}", 1)
    return re.sub(r"(sources:\n(?:  - .*\n)*)", lambda m: m.group(1) + link + "\n", text, count=1)


def row_exists(text, orig, sha=None):
    for line in text.splitlines():
        if line.startswith("|") and (jc.md_cell(orig) in line):
            return line
        if sha and line.startswith("|") and f"| {sha} |" in line:
            return line
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "has", "add", "skip", "ask", "me"])
    ap.add_argument("--orig")
    ap.add_argument("--sha")
    ap.add_argument("--kind", default="")
    ap.add_argument("--size", default="")
    ap.add_argument("--raw", default="")
    ap.add_argument("--origin", default="미정")
    ap.add_argument("--key", default="")
    ap.add_argument("--sensitive", default="-")
    ap.add_argument("--status", default="들임")
    ap.add_argument("--reason", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--names", default="")
    ap.add_argument("--me", default="")
    o = ap.parse_args()

    if o.cmd == "init":
        if DOC.exists():
            print("이미 있음 — 그대로 둔다")
            return 0
        DOC.parent.mkdir(parents=True, exist_ok=True)
        text = TEMPLATE.replace("{today}", jc.today())
        if o.me:
            text = text.replace("(아직 사용자에게 확인하지 않음)", f"{o.me} (사용자가 알려 준 이름)")
        DOC.write_text(text, encoding="utf-8", newline="\n")
        print(f"만듦: {DOC}")
        return 0

    text = load()
    if o.cmd == "has":
        line = row_exists(text, o.orig, o.sha)
        if line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            print(f"이미 들임(수집일 {cells[-2] if len(cells) > 2 else '?'}): {cells[0]}")
            return 0
        print("없음")
        return 1
    if o.cmd == "add":
        if row_exists(text, o.orig):
            print("이미 있는 줄 — 추가하지 않음")
            return 0
        row = "| " + " | ".join(jc.md_cell(x) for x in [o.orig, o.kind, o.size, f"[[{o.raw}]]" if o.raw else "-", o.sha or "-",
                                                         o.origin, o.key or "-", o.sensitive, jc.today(), o.status]) + " |"
        text = append_line(text, H_IN, row)
        if o.raw:
            text = add_source(text, o.raw)
        save(text)
        print("추가함")
        return 0
    if o.cmd == "skip":
        if row_exists(text.split(H_SKIP)[-1], o.orig):
            print("이미 있는 줄 — 추가하지 않음")
            return 0
        text = append_line(text, H_SKIP, f"| {jc.md_cell(o.orig)} | {jc.md_cell(o.reason)} | {jc.today()} |")
        save(text)
        print("추가함")
        return 0
    if o.cmd == "ask":
        line = f"- {o.text}"
        if line not in text:
            text = append_line(text, H_ASK, line)
            save(text)
        print("추가함")
        return 0
    if o.cmd == "me":
        text = re.sub(rf"({re.escape(H_ME)}\n\n).*?\n", lambda m: m.group(1) + f"{o.names} (사용자가 알려 준 이름)\n", text, count=1, flags=re.S)
        save(text)
        print("기록함")
        return 0


if __name__ == "__main__":
    sys.exit(main())
