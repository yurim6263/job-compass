#!/usr/bin/env python3
"""요건 판정 표 → 항목 점수 · 합계 · 등급. 모델은 판정(증명·부분·갭·안내)과 인용 카드 id만 쓰고, 계산은 여기서 한다.

쓰는 법(볼트 루트에서):
  python -I -X utf8 score_calc.py <입력.json> [--json]
  (입력을 표준입력으로 줄 때는 파일 이름 자리에 `-`)

입력 JSON 예:
{
  "job": "제조AI",                       # 직무 옵션(D 항목)
  "region": "서울",                      # 지역 낱말. 공고에 없으면 null (E 항목 제외)
  "body": true,                          # 공고 본문을 확보했는가. false 면 점수를 내지 않는다(미산출)
  "Q": [ {"id": "Q1", "verdict": "증명", "cards": ["exp-20261031-01"], "note": "…", "needs_numbers": false}, … ],
  "P": [ {"id": "P1", "verdict": "갭", "cards": [], "note": "…"} ],
  "tech": ["LSTM", "Python", "Docker"],  # 공고 '사용 기술' 낱말(공고 표기 그대로)
  "gates": {"경력": "신입가능|필수|불명", "학력": "학사가능|석사필수|불명", "마감": "남음|지남|불명", "지역": "안|밖|불명"}
}

규칙(기획 02 §3):
  배점 A 자격(Q) 45 · B 우대(P) 15 · C 사용 기술 15 · D 직무 방향 15 · E 지역 10 (합계 100)
  A·B: 증명 1.0 · 부분 0.5 · 갭 0 · 안내는 제외. 점수 = 배점 × Σ(값×근거 배수) ÷ (안내 제외 개수)
  근거 배수: 카드 fact_status 자료확인 ×1.0 · 본인진술 ×0.8 · 미확인 ×0(그 카드는 근거로 쓰지 않음). 인용 카드가 여럿이면 가장 높은 배수
  교육 이수 정리(wiki/교육이수_*.md 의 edu-… id)도 인용할 수 있다: 교육 이수만 인용한 증명은 부분으로 내리고, 사용 기술 낱말이 교육 이수에만 있으면 ×0.5
  C: 공고 기술 낱말 중 (미확인이 아닌) 카드 keywords 에 있는 것 ÷ 전체. 대소문자·띄어쓰기만 정규화. 동의어 추정 없음. 낱말마다 근거 배수 적용
  D: 제조AI·CBM시스템개발자·LLM응용 15 / 데이터 8 / 그 밖 0.  E: 서울·경기·원격 10 / 대구·부산·울산·포항 7 / 그 밖 3 / null 이면 제외
  증명인데 요건이 수치를 요구하고(needs_numbers) 인용 카드 중 numbers 판정 O 가 없으면 → 부분으로 내린다
  산정 불가 항목은 분모에서 뺀다: 합계 = 얻은 점수 ÷ 산정된 항목 배점 합 × 100  ·  표기 `산정 n/5`
  등급: 80 이상 🟢 · 60~79 🟡 · 60 미만 🔴 (표시한 정수 기준)
  게이트는 점수를 지우지 않고 옆에 붙인다: 🚫(경력 필수·석사 이상 필수·마감 지남) · 확인 필요(불명) · ⚠️(지역 밖)
카드는 `Projects/SecondBrain/wiki/내경험_*.md` 에서 읽는다(없는 id 를 인용하면 오류).
종료 코드: 0 성공 / 2 입력 오류
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402
import verify_cards as VC  # noqa: E402
import course_tools as CT  # noqa: E402

WEIGHTS = {"A": 45, "B": 15, "C": 15, "D": 15, "E": 10}
VERDICT = {"증명": 1.0, "부분": 0.5, "갭": 0.0}
MULT = {"자료확인": 1.0, "본인진술": 0.8, "미확인": 0.0}
JOB_D = {"제조AI": 15, "CBM시스템개발자": 15, "LLM응용": 15, "데이터": 8, "기타": 0}
REGION_E = {"서울": 10, "경기": 10, "원격": 10, "대구": 7, "부산": 7, "울산": 7, "포항": 7, "그 밖": 3}


def norm(s):
    return "".join(str(s).lower().split())


def half_up(x):
    return int(math.floor(x + 0.5))


def load_cards(wiki_dir=Path("Projects/SecondBrain/wiki")):
    cards = {}
    for p in sorted(wiki_dir.glob("내경험_*.md")):
        if p.name == "내경험_자료목록.md":
            continue
        _, cs = VC.parse(p.read_text(encoding="utf-8"))
        for c in cs:
            f = c["fields"]
            kws = VC.list_value(f.get("keywords", ""))
            cards[c["id"]] = {"id": c["id"], "fact": f.get("fact_status", ""), "origin": f.get("origin", ""),
                              "numbers": f.get("numbers", "").strip(), "keywords": kws, "doc": p.name}
    # 교육 이수 정리(edu-…): 배운 것 — 인용해도 최대 '부분', 사용 기술은 절반만(references/course-format.md)
    for c in CT.load_courses(wiki_dir):
        kws = [k for sk in c["skills"] for k in CT.skill_keywords(sk["name"])]
        cards[c["id"]] = {"id": c["id"], "fact": c["fact"], "origin": "교육과정", "numbers": "", "keywords": kws,
                          "doc": c["doc"], "edu": True}
    return cards


def item_value(item, cards, errs):
    """요건 하나 → (값 0~1 또는 None(제외), 적용된 판정, 메모들)"""
    v = item.get("verdict")
    notes = []
    if v == "안내":
        return None, "안내", notes
    if v not in VERDICT:
        errs.append(f"{item.get('id')}: verdict 는 증명·부분·갭·안내 중 하나여야 함(받은 값 `{v}`)")
        return 0.0, "갭", notes
    used = []
    for cid in item.get("cards", []):
        if cid not in cards:
            errs.append(f"{item.get('id')}: 카드 `{cid}`가 wiki에 없음")
        else:
            used.append(cards[cid])
    if v in ("증명", "부분") and not used:
        errs.append(f"{item.get('id')}: {v} 판정인데 인용한 카드가 없음 — 근거 없는 판정")
        return 0.0, "갭", notes + ["인용 카드 없음 → 갭 처리"]
    if v == "증명" and used and all(c.get("edu") for c in used):
        v = "부분"
        notes.append("교육 이수만 인용 — 배운 것은 증명이 아니라 부분으로 셈")
    if v == "증명" and item.get("needs_numbers") and not any(c["numbers"].startswith("O") for c in used):
        v = "부분"
        notes.append("요건이 수치를 요구하는데 numbers 판정 O 카드가 없어 증명→부분으로 내림")
    mult = max([MULT.get(c["fact"], 0.0) for c in used], default=0.0)
    if used and mult == 0.0:
        notes.append("인용 카드가 모두 미확인이라 근거로 쓰지 않음")
    elif used and mult < 1.0:
        notes.append("본인진술 카드라 ×0.8")
    return VERDICT[v] * mult, v, notes


def score_list(items, weight, cards, errs):
    rows, total, n = [], 0.0, 0
    for it in items:
        val, v, notes = item_value(it, cards, errs)
        rows.append({"id": it.get("id"), "verdict": v, "cards": it.get("cards", []), "value": val, "note": it.get("note", ""),
                     "calc_notes": notes})
        if val is not None:
            total += val
            n += 1
    if n == 0:
        return rows, None
    return rows, weight * total / n


def score_tech(tech, cards, errs):
    tech = [t for t in tech if str(t).strip()]
    if not tech:
        return [], None
    usable = [c for c in cards.values() if MULT.get(c["fact"], 0.0) > 0]
    rows, got = [], 0.0
    for t in tech:
        best, by = 0.0, []
        for c in usable:
            if norm(t) in [norm(k) for k in c["keywords"]]:
                by.append(c["id"])
                best = max(best, MULT[c["fact"]] * (0.5 if c.get("edu") else 1.0))
        rows.append({"tech": t, "matched": bool(by), "cards": by, "mult": best})
        got += best
    return rows, WEIGHTS["C"] * got / len(tech)


def build(inp):
    errs = []
    cards = load_cards()
    n_use = sum(1 for c in cards.values() if MULT.get(c["fact"], 0) > 0)
    n_unconf = sum(1 for c in cards.values() if c["fact"] == "미확인")
    res = {"errors": errs, "cards_total": len(cards), "cards_usable": n_use, "cards_unconfirmed": n_unconf}
    gates = inp.get("gates", {})
    marks, checks = [], []
    if gates.get("경력") == "필수":
        marks.append("🚫경력 필수")
    elif gates.get("경력", "불명") == "불명":
        checks.append("경력")
    if gates.get("학력") == "석사필수":
        marks.append("🚫석사 이상 필수")
    elif gates.get("학력", "불명") == "불명":
        checks.append("학력")
    if gates.get("마감") == "지남":
        marks.append("🚫마감 지남")
    elif gates.get("마감", "불명") == "불명":
        checks.append("마감")
    if gates.get("지역") == "밖":
        marks.append("⚠️지역 밖")
    elif gates.get("지역", "불명") == "불명":
        checks.append("지역")
    res["gate_marks"] = marks
    res["gate_checks"] = checks

    if not inp.get("body", True):
        res.update(status="미산출", reason="본문 미확보", fit="미산출" + "".join(" " + m for m in marks if m.startswith("🚫")))
        return res
    if n_use == 0:
        res.update(status="미산출", reason=f"경험 카드 {len(cards)}장(근거로 쓸 수 있는 카드 0장) — 먼저 /exp-organize가 필요",
                   fit="미산출" + "".join(" " + m for m in marks if m.startswith("🚫")))
        return res

    parts = {}
    qrows, a = score_list(inp.get("Q", []), WEIGHTS["A"], cards, errs)
    prows, b = score_list(inp.get("P", []), WEIGHTS["B"], cards, errs)
    trows, c = score_tech(inp.get("tech", []), cards, errs)
    job = inp.get("job")
    if job not in JOB_D:
        errs.append(f"job `{job}`가 직무 옵션이 아님")
        d = None
    else:
        d = float(JOB_D[job])
    region = inp.get("region")
    if region is None or region == "미기재":
        e = None
    elif region in REGION_E:
        e = float(REGION_E[region])
    else:
        errs.append(f"region `{region}`가 지역 낱말이 아님")
        e = None
    parts = {"A": a, "B": b, "C": c, "D": d, "E": e}
    done = {k: v for k, v in parts.items() if v is not None}
    earned = sum(done.values())
    base = sum(WEIGHTS[k] for k in done)
    total = half_up(earned / base * 100) if base else None
    grade = None if total is None else ("🟢" if total >= 80 else ("🟡" if total >= 60 else "🔴"))

    # 보강 거리: 잃은 점수가 큰 요건 3개
    gaps = []
    for tag, rows, w in (("Q", qrows, WEIGHTS["A"]), ("P", prows, WEIGHTS["B"])):
        n = sum(1 for r in rows if r["value"] is not None)
        for idx, r in enumerate(rows):
            if r["value"] is None:
                continue
            loss = w / n * (1 - r["value"]) if n else 0
            if loss > 1e-9:
                gaps.append({"id": r["id"], "verdict": r["verdict"], "loss": round(loss, 2), "note": r["note"],
                             "_k": (-round(loss, 6), 0 if tag == "Q" else 1, idx)})
    gaps.sort(key=lambda g: g["_k"])
    for g in gaps:
        g.pop("_k")
    res.update(status="산출", parts={k: (None if v is None else round(v, 2)) for k, v in parts.items()},
               weights=WEIGHTS, earned=round(earned, 2), base=base, total=total, grade=grade, counted=len(done),
               Q=qrows, P=prows, tech=trows, gaps=gaps[:3],
               fit=f"{total} {grade}" + "".join(" " + m for m in marks if m.startswith("🚫")))
    return res


def render(res):
    out = ["## 0. 점수", ""]
    if res["status"] == "미산출":
        out.append(f"**미산출** — {res['reason']}")
        if res["gate_marks"]:
            out.append("게이트: " + " · ".join(res["gate_marks"]))
        if res["gate_checks"]:
            out.append("확인 필요: " + "·".join(res["gate_checks"]))
        return "\n".join(out) + "\n"
    P = res["parts"]

    def pt(k):
        return "제외" if P[k] is None else f"{P[k]:.1f}"

    def cnt(rows):
        c = {"증명": 0, "부분": 0, "갭": 0, "안내": 0}
        for r in rows:
            c[r["verdict"]] += 1
        return f"증명 {c['증명']} · 부분 {c['부분']} · 갭 {c['갭']}" + (f" · 안내 {c['안내']}" if c["안내"] else "")

    def ids(rows):
        return "; ".join(f"{r['id']} {r['verdict']}" + (f"({', '.join(r['cards'])})" if r["cards"] else "") for r in rows)

    out += ["| 항목 | 배점 | 얻은 점수 | 산정 근거 |", "|---|---|---|---|",
            f"| A 자격 요건(Q) | 45 | {pt('A')} | {cnt(res['Q']) if res['Q'] else '해당 없음'} — {ids(res['Q'])} |",
            f"| B 우대 사항(P) | 15 | {pt('B')} | {cnt(res['P']) if res['P'] else '해당 없음'} — {ids(res['P'])} |",
            f"| C 사용 기술 | 15 | {pt('C')} | " + (f"{sum(1 for t in res['tech'] if t['matched'])}/{len(res['tech'])} 낱말이 카드 keywords에 있음 — "
                                           + "; ".join(f"{t['tech']}{'✓' if t['matched'] else '✗'}" for t in res["tech"]) if res["tech"] else "기술 낱말 없음") + " |",
            f"| D 직무 방향 | 15 | {pt('D')} | 공고 직무 기준 |",
            f"| E 지역 | 10 | {pt('E')} | " + ("공고에 근무지 없음" if P["E"] is None else "근무지 기준") + " |", ""]
    out.append(f"합계 **{res['total']}** / 산정 {res['counted']}/5 / {res['grade']} / 게이트: "
               + (" · ".join(res["gate_marks"]) if res["gate_marks"] else "🚫 없음")
               + (f" · 확인 필요 {len(res['gate_checks'])}({'·'.join(res['gate_checks'])})" if res["gate_checks"] else ""))
    out.append(f"카드 {res['cards_total']}장 중 근거로 쓴 것 {res['cards_usable']}장" + (f" · 미확인 {res['cards_unconfirmed']}장 제외" if res["cards_unconfirmed"] else ""))
    if res["gaps"]:
        out.append("")
        out.append("공백(갭) — 가장 큰 보강 거리: " + "; ".join(f"{g['id']}({g['verdict']}, −{g['loss']}점){' — ' + g['note'] if g['note'] else ''}" for g in res["gaps"]))
    notes = [f"{r['id']}: {n}" for r in res["Q"] + res["P"] for n in r["calc_notes"]]
    if notes:
        out.append("")
        out += [f"- 계산 메모 {n}" for n in notes]
    out.append("")
    out.append(f"현황표 `적합도`: `{res['fit']}`")
    return "\n".join(out) + "\n"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        return 2
    raw = sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text(encoding="utf-8")
    try:
        inp = json.loads(raw)
    except ValueError as e:
        print(f"입력 JSON 오류: {e}")
        return 2
    res = build(inp)
    if res["errors"]:
        print("입력 오류 — 점수를 믿지 말고 고쳐서 다시:")
        for e in res["errors"]:
            print("- " + e)
        if "--force" not in sys.argv:
            return 2
    print(json.dumps(res, ensure_ascii=False, indent=1) if as_json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
