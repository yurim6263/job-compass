#!/usr/bin/env python3
"""자소서 문항 × 경험 카드 추천. 같은 입력이면 같은 추천이 나온다(고정 가중치, 기획 04 §3-3). 모델은 유형·낱말 판정만 한다.

쓰는 법(볼트 루트에서):
  python -I -X utf8 card_recommend.py <입력.json> [--json]      (표준입력은 `-`)

입력 JSON:
{
 "company": "A사",                         # `> 해석(입사 후 적용, A사 …)` 가 있는 카드에 +2
 "job_tags": ["제조AI"],                   # 공고 직무에 해당하는 job_link_tags 값(고정 목록)
 "questions": [
   {"no": 1, "text": "지원동기를 쓰시오", "types": ["지원동기"], "keywords": ["LSTM", "예지보전"]},   # types = question_types 고정 목록의 값
   ...
 ]
}
후보 자격: evidence 있음 · fact_status 가 자료확인/본인진술(미확인은 빼고 "미확인 N장 제외") · origin 이 받은교재가 아님 · AI활용 문항은 ai_usage 가 채워진 카드만.
점수: 카드 question_types 에 문항 유형 +3 · 문항·공고 키워드와 카드 keywords 겹침 낱말 수×1(최대 +4) · 이 회사 apply_plans +2 · job_link_tags 일치 +1 · numbers 판정 O +1  →  × 근거 배수(자료확인 1.0 / 본인진술 0.8)
동점: numbers=O 우선 → 카드 날짜(id 의 YYYYMMDD)가 최근 → id 오름차순.
교육 이수(wiki/교육이수_*.md, 2026-11-02): 카드 자리(주 소재)를 차지하지 않고 문항마다 **보조 근거**로만 최대 2개 제안한다.
      점수 = 문항 키워드와 겹친 기술(과제·실습 +2, 수강 +1) · 공고 직무 태그 일치 +1 · 성장·지원동기·직무역량 문항이면 +1(이때는 태그 일치만으로도 후보)
      × 근거 배수(자료확인 1.0 / 본인진술 0.8). 미확인은 빼고, 카드처럼 고정(pins)할 수 없다. 자소서에는 "배운 것"까지만(성과·수치는 카드에서만).
배분: 후보가 적은 문항부터 1순위를 정한다. 한 카드는 한 문서에서 주 소재로 한 번만(다른 문항은 "보조 언급"까지), 같은 프로젝트(문서)는 문항 2개까지.
      남는 카드가 없으면 `카드 부족` + 가까운 카드를 "다른 면으로 재사용" 후보로 제안.
      어떤 문항의 1순위보다 점수가 높은 카드가 다른 문항의 주 소재라서 못 들어갔으면 그 사실을 `주의`로 적는다.
카드 고정: 입력에 "pins": {"2": "exp-20261031-01"} 처럼 문항 번호 → 카드 id 를 주면 그 문항은 그 카드로 먼저 고정하고
      (점수가 낮거나 겹침이 없어도 사용자가 정한 것이므로 따른다) 나머지 문항만 다시 배분한다. 후보가 아닌 카드(미확인·받은교재·근거 없음·없는 id),
      같은 카드를 두 문항에 고정한 경우는 고정하지 않고 `고정 불가` 이유를 적는다. 한 카드를 한 문항의 주 소재로, 다른 문항의 보조로 쓰는 것은
      배분과 무관하게 글쓰기 단계에서 하는 일이다(보조 언급은 고정하지 않는다).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_cards as VC  # noqa: E402
import course_tools as CT  # noqa: E402

WIKI = Path("Projects/SecondBrain/wiki")
MULT = {"자료확인": 1.0, "본인진술": 0.8}


def norm(s):
    return "".join(str(s).lower().split())


def load_cards(company):
    cards, excluded = [], {"미확인": 0, "받은교재": 0, "근거없음": 0}
    for p in sorted(WIKI.glob("내경험_*.md")):
        if p.name == "내경험_자료목록.md":
            continue
        _, cs = VC.parse(p.read_text(encoding="utf-8"))
        for c in cs:
            f = c["fields"]
            fs, org = f.get("fact_status", ""), f.get("origin", "")
            if not f.get("evidence", "").strip():
                excluded["근거없음"] += 1
                continue
            if org == "받은교재":
                excluded["받은교재"] += 1
                continue
            if fs not in MULT:
                excluded["미확인"] += 1
                continue
            m = re.match(r"exp-(\d{8})-", c["id"])
            cards.append({"id": c["id"], "title": f.get("title", c["heading"]), "doc": p.stem, "fact": fs, "origin": org,
                          "types": VC.list_value(f.get("question_types", "")), "kw": VC.list_value(f.get("keywords", "")),
                          "tags": VC.list_value(f.get("job_link_tags", "")), "num_o": f.get("numbers", "").strip().startswith("O"),
                          "ai": bool(f.get("ai_usage", "").strip() and "없음" not in f.get("ai_usage", "")),
                          "plan": bool(re.search(r"입사 후 적용,\s*" + re.escape(company or "∅"), c["block"])) if company else False,
                          "date": m.group(1) if m else "00000000"})
    return cards, excluded


EDU_TYPES = {"성장", "지원동기", "직무역량"}


def load_edu():
    out = []
    for c in CT.load_courses(WIKI):
        if c["fact"] not in MULT:
            continue
        out.append({**c, "kw": [(k, s["level"], s["name"]) for s in c["skills"] for k in CT.skill_keywords(s["name"])]})
    return out


def edu_matches(q, job_tags, courses, top=2):
    qk = {norm(k) for k in q.get("keywords", [])}
    typed = bool(set(q.get("types", [])) & EDU_TYPES)
    res = []
    for c in courses:
        hits = {}
        for k, level, name in c["kw"]:
            if norm(k) in qk:
                hits[name] = level
        tag = bool(set(c["tags"]) & set(job_tags))
        sc = sum(2 if lv in ("과제", "실습") else 1 for lv in hits.values()) + (1 if tag else 0) + (1 if typed else 0)
        if hits or (typed and tag):
            res.append({"course": c, "score": round(sc * MULT[c["fact"]], 2), "hits": hits, "tag": tag})
    res.sort(key=lambda r: (-r["score"], r["course"]["id"]))
    return res[:top]


def score(card, q, job_tags):
    parts = []
    s = 0.0
    qt = set(q.get("types", []))
    if qt & set(card["types"]):
        s += 3
        parts.append("유형 +3")
    qk = {norm(k): k for k in q.get("keywords", [])}
    hit = [qk[norm(k)] for k in card["kw"] if norm(k) in qk]
    if hit:
        n = min(len(hit), 4)
        s += n
        parts.append(f"낱말 {'·'.join(hit[:4])} +{n}")
    if card["plan"]:
        s += 2
        parts.append("입사 후 적용 +2")
    if set(card["tags"]) & set(job_tags):
        s += 1
        parts.append("직무 +1")
    if card["num_o"]:
        s += 1
        parts.append("수치 O +1")
    mult = MULT[card["fact"]]
    return round(s * mult, 2), parts, mult


def relevant(parts):
    return any(x.startswith(("유형", "낱말", "입사 후 적용")) for x in parts)


def tie_key(c, sc):
    return (-sc, 0 if c["num_o"] else 1, -int(c["date"]), c["id"])


def recommend(inp):
    cards, excluded = load_cards(inp.get("company", ""))
    courses = load_edu()
    qs = inp.get("questions", [])
    job_tags = inp.get("job_tags", [])
    cand = {}
    for q in qs:
        lst = []
        for c in cards:
            if "AI활용" in q.get("types", []) and not c["ai"]:
                continue
            sc, parts, mult = score(c, q, job_tags)
            lst.append({"card": c, "score": sc, "parts": parts, "mult": mult})
        lst.sort(key=lambda r: tie_key(r["card"], r["score"]))
        cand[q["no"]] = lst
    order = sorted(qs, key=lambda q: (sum(1 for r in cand[q["no"]] if relevant(r["parts"])), q["no"]))
    used, per_doc, result = set(), {}, {}

    def take(q, only_relevant):
        for r in cand[q["no"]]:
            c = r["card"]
            if r["score"] <= 0 or c["id"] in used or per_doc.get(c["doc"], 0) >= 2:
                continue
            if only_relevant and not relevant(r["parts"]):
                continue
            used.add(c["id"])
            per_doc[c["doc"]] = per_doc.get(c["doc"], 0) + 1
            return r
        return None

    picks, pinned, pin_errors = {}, set(), []
    eligible = {c["id"]: c for c in cards}
    for key, cid in sorted((inp.get("pins") or {}).items(), key=lambda kv: str(kv[0])):
        qno = next((q["no"] for q in qs if str(q["no"]) == str(key)), None)
        if qno is None:
            pin_errors.append(f"문항 {key}: 그런 문항이 없어 고정하지 않았다")
        elif cid not in eligible:
            pin_errors.append(f"문항 {key}: {cid}는 추천 후보가 아니라(없는 id·미확인·받은교재·근거 없음) 고정하지 않았다")
        elif cid in used:
            pin_errors.append(f"문항 {key}: {cid}는 이미 다른 문항에 고정돼 있어 고정하지 않았다(한 카드는 주 소재로 한 번만)")
        else:
            r = next(r for r in cand[qno] if r["card"]["id"] == cid)
            used.add(cid)
            per_doc[r["card"]["doc"]] = per_doc.get(r["card"]["doc"], 0) + 1
            picks[qno] = r
            pinned.add(qno)
    for q in order:                       # 1차: 유형·낱말·입사 후 적용이 실제로 겹치는 카드만
        if q["no"] not in picks:
            picks[q["no"]] = take(q, True)
    for q in order:                       # 2차: 남은 문항은 약한 후보(직무·수치 가산만)라도
        if picks[q["no"]] is None:
            picks[q["no"]] = take(q, False)
    owner = {r["card"]["id"]: no for no, r in picks.items() if r}
    for q in qs:
        edu = edu_matches(q, job_tags, courses)
        pick = picks[q["no"]]
        alts = [r for r in cand[q["no"]] if r is not pick and r["score"] > 0 and relevant(r["parts"])][:2]
        if pick:
            notes = []
            if q["no"] not in pinned:
                for r in cand[q["no"]]:   # 이 문항 1순위보다 점수가 높은데 다른 문항의 주 소재라 못 들어온 카드
                    if r["score"] <= pick["score"]:
                        break
                    if relevant(r["parts"]) and owner.get(r["card"]["id"], q["no"]) != q["no"]:
                        notes.append((r, owner[r["card"]["id"]]))
            result[q["no"]] = {"first": pick, "alts": alts, "lack": False, "weak": q["no"] not in pinned and not relevant(pick["parts"]),
                               "pinned": q["no"] in pinned, "blocked": notes, "edu": edu}
        else:
            reuse = next((r for r in cand[q["no"]] if r["score"] > 0 and relevant(r["parts"])), None)
            result[q["no"]] = {"first": None, "alts": [x for x in alts if x is not reuse], "lack": True, "reuse": reuse, "edu": edu}
    return {"cards": len(cards), "courses": len(courses), "excluded": excluded, "result": result, "questions": qs, "pin_errors": pin_errors}


def fmt(r):
    c = r["card"]
    return f"{c['id']} ({c['doc'].replace('내경험_', '')}, {c['origin']}, {c['fact']}) {r['score']}점 = " + (", ".join(r["parts"]) or "겹침 없음") + (f" ×{r['mult']}" if r["mult"] != 1.0 else "")


def fmt_edu(e):
    c = e["course"]
    hits = "·".join(f"{n}({lv})" for n, lv in e["hits"].items()) or "직무 태그 일치"
    return f"{c['id']} {c['title']} — {hits} · {e['score']}점"


def render(res):
    out = ["## 카드 추천", "", f"후보 카드 {res['cards']}장" + (f" · 교육 이수 {res['courses']}개" if res.get("courses") else "")
           + (f" · 미확인 {res['excluded']['미확인']}장 제외" if res["excluded"]["미확인"] else "")
           + (f" · 받은교재 {res['excluded']['받은교재']}장 제외" if res["excluded"]["받은교재"] else ""), ""]
    for q in res["questions"]:
        r = res["result"][q["no"]]
        out.append(f"### 문항 {q['no']} — {q.get('text', '')[:40]} (유형: {'·'.join(q.get('types', []))})")
        if r["lack"]:
            out.append("- **카드 부족** — 쓸 수 있는 카드가 남지 않았다.")
            if r.get("reuse"):
                out.append(f"  - 다른 면으로 재사용 후보: {fmt(r['reuse'])} (이미 다른 문항의 주 소재 — 보조 언급까지만 / 다른 면을 써야 함)")
        else:
            out.append(f"- 1순위: {fmt(r['first'])}" + (" — **사용자 지정**" if r.get("pinned") else "")
                       + (" — **약한 추천**(유형·낱말 일치 없음, 직무·수치 가산만)" if r.get("weak") else ""))
        for a in r["alts"]:
            out.append(f"- 대안: {fmt(a)}")
        for e in r.get("edu", []):
            out.append(f"- 교육 이수(보조 근거): {fmt_edu(e)} — \"교육 과정에서 ○○을 실습/수강했다\"까지만, 성과·수치는 카드에서만")
        if r["lack"] and r.get("edu"):
            out.append("  - 카드가 없으면 위 교육 이수로 '배운 것과 앞으로 할 것'을 쓸 수 있다(경험한 것처럼 쓰지 않는다)")
        for b, owner_no in r.get("blocked", []):
            out.append(f"- **주의**: {b['card']['id']}({b['score']}점)는 {owner_no}번 문항의 주 소재라 이 문항엔 못 들어갔다. "
                       f"이 문항에 쓰려면 `pins`로 고정하면 된다(그러면 {owner_no}번 문항은 남은 카드로 다시 배분된다)")
        out.append("")
    for e in res.get("pin_errors", []):
        out.append(f"- **고정 불가**: {e}")
    out.append("사용자가 카드를 바꾸면 입력의 `pins`(문항 번호 → 카드 id)에 넣고 이 스크립트를 다시 돌린다. 고른 문항은 그대로 두고 나머지만 다시 배분한다.")
    return "\n".join(out) + "\n"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    raw = sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text(encoding="utf-8")
    res = recommend(json.loads(raw))
    if "--json" in sys.argv:
        slim = {str(k): {"first": (v["first"]["card"]["id"] if v["first"] else None), "lack": v["lack"], "pinned": v.get("pinned", False),
                         "alts": [a["card"]["id"] for a in v["alts"]], "edu": [e["course"]["id"] for e in v.get("edu", [])]}
                for k, v in res["result"].items()}
        print(json.dumps({"cards": res["cards"], "excluded": res["excluded"], "result": slim, "pin_errors": res["pin_errors"]}, ensure_ascii=False, indent=1))
    else:
        print(render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
