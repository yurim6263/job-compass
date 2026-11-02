#!/usr/bin/env python3
"""교육 이수 정리(`wiki/교육이수_*.md`) 읽기·검사. 볼트 루트에서 실행한다. 형식: references/course-format.md

쓰는 법:
  python -I -X utf8 course_tools.py check <wiki/교육이수_…md> [...]   # 형식·근거 검사 (PASS / FAIL, 종료 코드 0/1)
  python -I -X utf8 course_tools.py list [--json]                     # 교육 이수 목록(과정·기간·수준별 기술 수)

검사하는 것: 필수 필드 · 수준(수강·실습·과제) · 기술마다 근거 · 근거 링크가 볼트에 있는지 · '과제' 수준은 교육과제 카드 id(있는 카드)를 근거로
· job_link_tags 고정 목록 · fact_status 값. 파일을 고치지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

WIKI = Path("Projects/SecondBrain/wiki")
LEVELS = ["수강", "실습", "과제"]
FACTS = ["자료확인", "본인진술", "미확인"]
COMPLETION = ["수료", "수강중", "중도", "[확인 필요]"]
TAGS = ["제조AI", "설비데이터", "예지보전", "CBM", "시계열예측", "ML/DL", "LLM응용", "데이터파이프라인", "프론트/웹"]
LINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
CARD_ID = re.compile(r"\bexp-\d{8}-\d{2}\b")


def parse(text):
    """→ [{id, title, fields:{…}, skills:[{name, level, evidence}]}]"""
    m = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    body = text[m.end():] if m else text
    out = []
    parts = re.split(r"^### (edu-\d{8}-\d{2})[ \t]*(.*)$", body, flags=re.M)
    for i in range(1, len(parts), 3):
        cid, title, block = parts[i], parts[i + 1].strip(), parts[i + 2]
        block = re.split(r"^#{1,2} ", block, flags=re.M)[0]
        fields, cur = {}, None
        for line in block.splitlines():
            mm = re.match(r"^- ([a-z_]+):\s*(.*)$", line)
            if mm:
                cur = mm.group(1)
                fields[cur] = mm.group(2).strip()
            elif cur and line.startswith("  ") and line.strip():
                fields[cur] += "\n" + line.strip()
        skills = []
        for ln in fields.get("skills", "").splitlines():
            ln = ln.strip().lstrip("-").strip()
            if not ln:
                continue
            cells = [c.strip() for c in ln.split("|")]
            skills.append({"name": cells[0], "level": cells[1] if len(cells) > 1 else "",
                           "evidence": "|".join(cells[2:]).strip() if len(cells) > 2 else ""})
        out.append({"id": cid, "title": title, "fields": fields, "skills": skills})
    return out


def list_value(v):
    v = (v or "").strip().strip("[]")
    return [x.strip() for x in v.split(",") if x.strip()]


def card_ids(wiki=WIKI):
    ids = set()
    for p in wiki.glob("내경험_*.md"):
        ids |= set(re.findall(r"^### (exp-\d{8}-\d{2})", p.read_text(encoding="utf-8"), flags=re.M))
    return ids


def load_courses(wiki=WIKI):
    res = []
    for p in sorted(wiki.glob("교육이수_*.md")):
        for c in parse(p.read_text(encoding="utf-8")):
            f = c["fields"]
            res.append({"id": c["id"], "title": c["title"], "doc": p.name, "institution": f.get("institution", ""),
                        "period": f.get("period", ""), "completion": f.get("completion", ""),
                        "tags": list_value(f.get("job_link_tags", "")), "fact": f.get("fact_status", ""),
                        "projects": CARD_ID.findall(f.get("projects", "")), "skills": c["skills"]})
    return res


def skill_keywords(name):
    """'데이터 전처리(pandas)' → ['데이터 전처리(pandas)', '데이터 전처리', 'pandas']"""
    out = [name]
    m = re.match(r"^(.*?)\((.*)\)\s*$", name)
    if m:
        out += [m.group(1).strip()] + [x.strip() for x in re.split(r"[,/·]", m.group(2)) if x.strip()]
    return [x for x in out if x]


def check_file(path, vault=Path(".")):
    text = Path(path).read_text(encoding="utf-8")
    fails, warns = [], []
    m = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    if not m or "교육이수" not in m.group(1):
        fails.append("frontmatter 에 tags: [교육이수] 가 없음")
    entries = parse(text)
    if not entries:
        fails.append("`### edu-YYYYMMDD-NN 과정 이름` 항목이 없음")
    known_cards = card_ids(vault / WIKI) if (vault / WIKI).exists() else set()
    for e in entries:
        f, pre = e["fields"], e["id"]
        for k in ("institution", "period", "completion", "skills", "evidence", "fact_status"):
            if not f.get(k, "").strip():
                fails.append(f"{pre}: `{k}` 비어 있음")
        if f.get("completion") and f["completion"] not in COMPLETION:
            fails.append(f"{pre}: completion `{f['completion']}`는 {COMPLETION} 중 하나")
        if f.get("fact_status") and f["fact_status"] not in FACTS:
            fails.append(f"{pre}: fact_status `{f['fact_status']}`는 {FACTS} 중 하나")
        if f.get("completion") == "수료" and f.get("fact_status") == "자료확인" and not LINK.search(f.get("evidence", "")):
            fails.append(f"{pre}: 수료를 자료확인으로 쓰려면 evidence 에 근거 링크가 있어야 함")
        for t in list_value(f.get("job_link_tags", "")):
            if t not in TAGS:
                fails.append(f"{pre}: job_link_tags `{t}`는 고정 목록 밖")
        for lk in LINK.findall(f.get("evidence", "")):
            if not ((vault / lk).exists() or (vault / (lk + ".md")).exists()):
                fails.append(f"{pre}: evidence 링크가 볼트에 없음 — {lk}")
        if not e["skills"]:
            fails.append(f"{pre}: skills 에 기술이 하나도 없음")
        for s in e["skills"]:
            lab = f"{pre}: 기술 `{s['name']}`"
            if s["level"] not in LEVELS:
                fails.append(f"{lab} 수준 `{s['level']}`는 수강·실습·과제 중 하나")
                continue
            if s["level"] == "과제":
                ids = CARD_ID.findall(s["evidence"])
                if not ids:
                    fails.append(f"{lab} 과제 수준은 근거 칸에 교육과제 카드 id(exp-…)가 있어야 함")
                for cid in ids:
                    if known_cards and cid not in known_cards:
                        fails.append(f"{lab} 카드 `{cid}`가 wiki 에 없음")
            else:
                links = LINK.findall(s["evidence"])
                if not links and f.get("fact_status") != "본인진술":
                    fails.append(f"{lab} 근거 링크가 없음(근거 없는 기술은 쓰지 않는다)")
                for lk in links:
                    if not ((vault / lk).exists() or (vault / (lk + ".md")).exists()):
                        fails.append(f"{lab} 근거 링크가 볼트에 없음 — {lk}")
        if re.search(r"(운영했|구축했|개발했|담당했|성과|개선|향상|\d+\s*%)", f.get("skills", "")):
            warns.append(f"{pre}: skills 에 실무·성과처럼 읽히는 말이 있음 — 배운 것은 배운 것으로만(성과는 교육과제 카드에)")
    return fails, warns


def cmd_check(a):
    bad = 0
    for path in a.files:
        fails, warns = check_file(path)
        verdict = "FAIL" if fails else ("DONE_WITH_CONCERNS" if warns else "PASS")
        print(f"## {path} — {verdict}")
        for x in fails:
            print(f"- FAIL {x}")
        for x in warns:
            print(f"- 주의 {x}")
        bad += bool(fails)
    return 1 if bad else 0


def cmd_list(a):
    cs = load_courses()
    if a.json:
        print(json.dumps(cs, ensure_ascii=False, indent=1))
        return 0
    if not cs:
        print("(교육 이수 정리 없음)")
    for c in cs:
        cnt = {lv: sum(1 for s in c["skills"] if s["level"] == lv) for lv in LEVELS}
        print(f"- {c['id']} {c['title']} · {c['institution']} · {c['period']} · {c['completion']} · "
              f"과제 {cnt['과제']} · 실습 {cnt['실습']} · 수강 {cnt['수강']} · {c['fact']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("files", nargs="+")
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return {"check": cmd_check, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
