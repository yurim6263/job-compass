#!/usr/bin/env python3
"""프로젝트 문서(`wiki/내경험_<프로젝트>.md`)의 경험 카드를 규칙대로 검사한다(기획 01 §4-⑦). 문서를 고치지 않는다.

쓰는 법(볼트 루트에서):
  python -I -X utf8 verify_cards.py Projects/SecondBrain/wiki/내경험_가상프로젝트A.md [--json]

카드 형식은 references/card-format.md. 카드마다 판정을 낸다:
  PASS · DONE_WITH_CONCERNS(6단계 중 `[확인 필요]`가 남음) · FAIL(근거 없음·필수 항목 누락·비밀 노출 등)
검사: 근거 링크가 실제 파일을 가리키는가 / 필수 필드 / 값 목록 / 수치 판정(O·△·X)과 `[수치 확인 필요]` /
      수치·키워드가 근거 파일 본문에 있는가 / '내가'와 '팀이/우리가' 섞임 / 모호한 상투 표현('다양한 경험'·'책임감' 등, 경고만) /
      비밀·개인정보 / 받은교재 카드 여부
종료 코드: 0 모두 통과(PASS 또는 DONE_WITH_CONCERNS) / 1 FAIL 있음 / 2 문서 형식 오류
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_common as jc  # noqa: E402

REQUIRED = ["origin", "title", "problem", "role", "action", "change", "evidence", "fact_status", "keywords"]
ORIGINS = {"본인작성", "팀", "교육과제", "받은교재", "미정"}
FACT = {"자료확인", "본인진술", "미확인"}
JOB_TAGS = {"제조AI", "설비데이터", "예지보전", "CBM", "시계열예측", "ML/DL", "LLM응용", "데이터파이프라인", "프론트/웹"}
Q_TYPES = {"지원동기", "직무역량", "문제해결", "협업", "성장", "AI활용", "입사후포부"}
NEED = "[확인 필요]"
NUM_NEED = "[수치 확인 필요]"
LINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
TEAM_WORDS = re.compile(r"(우리가|우리는|팀이|팀원들|팀 전체가)")
# 모호한 상투 표현(문항·면접에서 근거로 못 쓰는 말) — 표현별로 "무엇이 빠졌는지"를 알려 준다
VAGUE = [
    (re.compile(r"다양한\s*(경험|활동|업무)"), "무엇을 했는지 특정되지 않음 — 실제 한 일 하나로 바꿀 것"),
    (re.compile(r"책임감"), "마음가짐만 있고 행동이 안 보임 — 실제로 한 일로 바꿀 것"),
    (re.compile(r"(소통|커뮤니케이션)\s*능력"), "누구와 무엇을 맞췄는지가 빠짐 — 조율한 내용으로 바꿀 것"),
    (re.compile(r"(많은|값진)\s*(것|경험)을?\s*(배웠|얻었)"), "배웠다는 말은 결과가 아님 — 달라진 점으로 바꿀 것"),
    (re.compile(r"(팀|프로젝트)에\s*기여"), "내 몫이 안 보임 — 내가 한 일 한 줄로 바꿀 것"),
    (re.compile(r"열심히|최선을\s*다"), "노력 표현은 근거가 아님 — 한 일과 확인한 결과로 바꿀 것"),
]


def parse(text):
    fm = {}
    m = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    if m:
        fm["_raw"] = m.group(1)
        for key in ("tags", "sources", "updated", "origin"):
            fm[key] = re.search(rf"^{key}:", m.group(1), flags=re.M) is not None
        mo = re.search(r"^origin:\s*(\S+)", m.group(1), flags=re.M)
        fm["origin_value"] = mo.group(1) if mo else ""
    body = text[m.end():] if m else text
    cards = []
    parts = re.split(r"^### (exp-\d{8}-\d{2})[ \t]*(.*)$", body, flags=re.M)
    for i in range(1, len(parts), 3):
        cid, ctitle, block = parts[i], parts[i + 1], parts[i + 2]
        block = re.split(r"^#{1,2} ", block, flags=re.M)[0]      # 다음 큰 제목에서 끝
        fields, cur = {}, None
        for line in block.splitlines():
            mm = re.match(r"^- ([a-z_]+):\s*(.*)$", line)
            if mm:
                cur = mm.group(1)
                fields[cur] = mm.group(2).strip()
            elif cur and line.startswith("  ") and line.strip():
                fields[cur] += "\n" + line.strip()
        cards.append({"id": cid, "heading": ctitle.strip(), "fields": fields, "block": block})
    return fm, cards


def resolve(vault, link):
    for cand in (vault / link, vault / (link + ".md")):
        if cand.exists():
            return cand
    return None


def read_evidence(vault, ev):
    texts, missing = [], []
    for target in LINK.findall(ev):
        p = resolve(vault, target.strip())
        if not p:
            missing.append(target)
            continue
        if p.is_file() and p.suffix.lower() in (".md", ".txt", ".csv"):
            texts.append(p.read_text(encoding="utf-8", errors="replace"))
        elif p.is_dir():
            for f in p.rglob("*.md"):
                texts.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texts), missing


def list_value(v):
    v = v.strip()
    if v.startswith("["):
        v = v.strip("[]")
    return [x.strip() for x in re.split(r"[,，]", v) if x.strip()]


def check_card(card, vault, fm_origin):
    f = card["fields"]
    fails, concerns, notes = [], [], []
    for k in REQUIRED:
        if not f.get(k, "").strip():
            fails.append(f"필수 항목 `{k}` 없음")
    origin = f.get("origin", "")
    if origin and origin not in ORIGINS:
        fails.append(f"origin 값 오류: {origin}")
    if origin == "받은교재":
        fails.append("받은교재는 카드를 만들지 않음")
    if origin == "미정":
        concerns.append("origin 미정 — 사용자에게 물을 것")
    fs = f.get("fact_status", "")
    if fs and fs not in FACT:
        fails.append(f"fact_status 값 오류: {fs}")
    ev = f.get("evidence", "")
    ev_text, missing = read_evidence(vault, ev)
    if ev and not LINK.search(ev):
        fails.append("evidence에 [[링크]]가 없음")
    for m in missing:
        fails.append(f"evidence 링크 대상이 없음: {m}")
    if ev and LINK.search(ev):
        loc = LINK.sub("", ev)
        if len(re.sub(r"[\s\-—|,·]+", "", loc)) < 3:
            concerns.append("evidence에 위치(섹션·커밋·쪽)가 없음")
    for k in ("problem", "role", "action", "change"):
        if NEED in f.get(k, ""):
            concerns.append(f"{k}: {NEED} 남음")
    # 수치
    nums = f.get("numbers", "").strip()
    if nums:
        flag = nums[0]
        if flag not in "O△X":
            fails.append("numbers 앞에 판정(O/△/X)이 없음")
        if flag == "△" and NUM_NEED not in nums:
            fails.append("△ 판정인데 [수치 확인 필요] 표시가 없음")
        if flag == "O" and NUM_NEED in nums:
            fails.append("O 판정인데 [수치 확인 필요]가 들어 있음")
        if flag in "O△" and ev_text:
            for tok in set(re.findall(r"\d+(?:[.,]\d+)?", re.sub(r"\[수치 확인 필요\]", "", nums.split(None, 1)[1] if " " in nums else ""))):
                if tok not in ev_text:
                    fails.append(f"수치 `{tok}`가 근거 파일 본문에 없음(지어낸 수치 의심)")
    elif f.get("change", "") and re.search(r"\d", f["change"]) and ev_text:
        for tok in set(re.findall(r"\d+(?:[.,]\d+)?", f["change"])):
            if tok not in ev_text and len(tok) > 1:
                concerns.append(f"change의 숫자 `{tok}`가 근거 본문에 없음")
    # 낱말
    kws = list_value(f.get("keywords", ""))
    if f.get("keywords", "") and not kws:
        fails.append("keywords가 비어 있음")
    low = ev_text.lower()
    for kw in kws:
        if ev_text and kw.lower() not in low:
            fails.append(f"keyword `{kw}`가 근거 파일 본문에 없음")
    for t in list_value(f.get("job_link_tags", "")):
        if t not in JOB_TAGS:
            fails.append(f"job_link_tags 고정 목록에 없음: {t}")
    for t in list_value(f.get("question_types", "")):
        if t not in Q_TYPES:
            fails.append(f"question_types 고정 목록에 없음: {t}")
    # 4분리
    for k in ("role", "action"):
        if TEAM_WORDS.search(f.get(k, "")):
            concerns.append(f"{k}에 팀 주어('우리가/팀이')가 섞임 — 내 몫만 쓸 것")
    # 모호한 상투 표현: 무엇을 했는지·내 몫·결과가 안 보이는 말은 면접에서 바로 꼬리질문을 받는다(경고만 한다, FAIL 아님)
    for k in ("problem", "role", "action", "change"):
        for pat, why in VAGUE:
            m = pat.search(f.get(k, ""))
            if m:
                concerns.append(f"{k}에 모호한 표현 `{m.group(0)}` — {why}")
    # 비밀·개인정보
    hits = jc.scan_text(card["block"])
    if hits:
        fails.append(f"비밀·개인정보 의심 {len(hits)}줄(줄 {', '.join(str(i) for i, _ in hits[:5])})")
    # 팀 프로젝트의 role
    if origin == "팀" and "role" in f and not f["role"].strip():
        fails.append("팀 프로젝트인데 role 비어 있음")
    verdict = "FAIL" if fails else ("DONE_WITH_CONCERNS" if concerns else "PASS")
    return verdict, fails, concerns, notes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        return 2
    doc = Path(args[0])
    vault = Path.cwd()
    if not doc.exists():
        print(f"문서가 없음: {doc}")
        return 2
    text = doc.read_text(encoding="utf-8")
    fm, cards = parse(text)
    problems = []
    for k in ("tags", "sources", "updated", "origin"):
        if not fm.get(k):
            problems.append(f"frontmatter `{k}` 없음")
    if fm.get("origin_value") == "받은교재":
        print(f"# 카드 검사: {doc}\n\n- 받은교재 문서: 카드가 없어야 정상(카드 {len(cards)}장)")
        return 1 if cards or problems else 0
    if "## 경험 카드" not in text:
        problems.append("`## 경험 카드` 섹션 없음")
    hits = jc.scan_text(text)
    if hits:
        problems.append(f"문서 전체에서 비밀·개인정보 의심 {len(hits)}줄")
    results = []
    for c in cards:
        v, fails, concerns, _ = check_card(c, vault, None)
        results.append({"id": c["id"], "title": c["heading"] or c["fields"].get("title", ""), "verdict": v,
                        "fails": fails, "concerns": concerns})
    if as_json:
        print(json.dumps({"doc": str(doc), "doc_problems": problems, "cards": results}, ensure_ascii=False, indent=1))
    else:
        print(f"# 카드 검사: {doc}\n")
        for p in problems:
            print(f"- [문서] {p}")
        if not cards:
            print("- [문서] 카드가 없음")
        for r in results:
            print(f"\n## {r['id']} {r['title']} → {r['verdict']}")
            for x in r["fails"]:
                print(f"- FAIL: {x}")
            for x in r["concerns"]:
                print(f"- 보완: {x}")
        print(f"\n합계: 카드 {len(results)}장 — " + ", ".join(f"{k} {sum(1 for r in results if r['verdict'] == k)}" for k in ("PASS", "DONE_WITH_CONCERNS", "FAIL")))
    bad = problems or any(r["verdict"] == "FAIL" for r in results)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
