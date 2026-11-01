#!/usr/bin/env python3
"""모의면접 계산·기록 도구. 볼트 루트에서 실행한다. 모델은 체크리스트 예/아니오와 인용만 쓰고 숫자는 여기서 센다.

쓰는 법:
  python -I -X utf8 interview_tools.py calc <세션.json> [--map Areas/취업/자소서/<회사>_<직무>_방어맵.md] [--json]
  python -I -X utf8 interview_tools.py next-path --company A사 --job "설비 AI 엔지니어 신입" --mode 인성 --intensity 보통
        오늘 날짜의 세션 파일 경로를 정한다(같은 날 같은 모드면 `_2`…, 덮어쓰지 않음)
  python -I -X utf8 interview_tools.py log-summary --company A사 --job "…" --mode 인성 --intensity 보통 --rate "62% (산정 38/61)" --weak "근거,사실 일치" [--aborted]
        `Areas/취업/면접/기록 요약.md` 에 한 줄 추가(없으면 만든다)
  python -I -X utf8 interview_tools.py defense-list <방어맵.md>
  python -I -X utf8 interview_tools.py defense-set <방어맵.md> --id dm-001 --state ready|weak|unprepared [--hint "사용자가 확인한 1분 골자"]
        방어 상태 갱신(+선택적으로 골자 기록). 수정 전 `Areas/취업/_백업/` 사본.
  python -I -X utf8 interview_tools.py bank-add --text "받은 질문" --company A사 --kind 인성 [--note "기억 기준"]
        `Areas/취업/면접/실전 질문 은행.md`에 한 줄 추가(후기기록)

세션 JSON:
{"mode":"인성","intensity":"보통","company":"A사","job":"…",
 "answers":[{"q":"Q1","topic":"지원동기","defense_id":"dm-001"(선택),"unanswered":false,
             "checks":{"1":true,"2":false,…,"10":null},          # 1~10 예/아니오, 해당 없으면 null
             "quotes":{"2":"답변에서 인용 한 줄", …}}]}
체크리스트(기획 05 §3-4): 1 질문에 답함 · 2 결론 먼저 · 3 구체 사례 · 4 내 역할 구분 · 5 근거(수치·전후·검증) · 6 판단 이유 · 7 사실이 서류와 일치 · 8 분량 · 9 실행형 어조 · 10 입사 후 적용 근거(해당 시)
방어 상태 판정(§3-7): 1~7번 중 예 5개 이상 + 7번 예 → ready · 일부 부족 → weak · 답을 못 함(unanswered) → unprepared
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

AREA = Path("Areas/취업")
ITEMS = {"1": "질문에 답함", "2": "결론 먼저", "3": "구체 사례", "4": "내 역할 구분", "5": "근거(수치·전후·검증)", "6": "판단 이유",
         "7": "사실이 서류와 일치", "8": "분량", "9": "실행형 어조", "10": "입사 후 적용 근거"}
STATES = ["ready", "weak", "unprepared"]


def read_map(path):
    text = Path(path).read_text(encoding="utf-8")
    rows, cols = [], None
    for ln in text.splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        c = J.split_row(ln)
        if cols is None:
            if "id" in c and "방어 상태" in c:
                cols = c
            continue
        if re.match(r"^[\s:-]+$", "".join(c)):
            continue
        rows.append({k: (c[i] if i < len(c) else "") for i, k in enumerate(cols)})
    return text, cols, rows


def cmd_calc(a):
    s = json.loads(Path(a.file).read_text(encoding="utf-8"))
    ans = s.get("answers", [])
    errs, per, fail_count = [], [], {k: 0 for k in ITEMS}
    tot_yes = tot_n = 0
    fact_bad = []
    defense_res = {}
    for x in ans:
        ch = x.get("checks", {})
        yes = n = 0
        for k in ITEMS:
            v = ch.get(k)
            if v is None:
                continue
            if not isinstance(v, bool):
                errs.append(f"{x.get('q')}: 항목 {k} 값은 true/false/null")
                continue
            n += 1
            yes += v
            if not v:
                fail_count[k] += 1
                if k == "7" and not x.get("unanswered"):
                    fact_bad.append(x.get("q"))
            elif k not in x.get("quotes", {}) and not x.get("unanswered"):
                errs.append(f"{x.get('q')}: 항목 {k}가 예인데 인용(quotes)이 없음")
        per.append({"q": x.get("q"), "topic": x.get("topic", ""), "yes": yes, "n": n})
        tot_yes += yes
        tot_n += n
        did = x.get("defense_id")
        if did:
            core = [ch.get(str(i)) for i in range(1, 8)]
            core_yes = sum(1 for v in core if v is True)
            if x.get("unanswered"):
                st = "unprepared"
            elif core_yes >= 5 and ch.get("7") is True:
                st = "ready"
            else:
                st = "weak"
            defense_res[did] = st
    if errs:
        print("입력 오류:\n- " + "\n- ".join(errs))
        return 2
    rate = None if tot_n == 0 else round(tot_yes / tot_n * 100)
    weak3 = [f"{ITEMS[k]}({v}회)" for k, v in sorted(fail_count.items(), key=lambda kv: (-kv[1], int(kv[0]))) if v > 0][:3]
    util = None
    if a.map:
        _, _, rows = read_map(a.map)
        total = len(rows)
        used = len({x.get("defense_id") for x in ans if x.get("defense_id") and not x.get("unanswered")})
        util = (used, total)
    res = {"mode": s.get("mode"), "intensity": s.get("intensity"), "per_answer": per, "rate": rate, "yes": tot_yes, "n": tot_n,
           "fact_mismatch": fact_bad, "weak3": weak3, "defense": defense_res, "map_use": util}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print(f"## 통과율 — {s.get('mode')} · {s.get('intensity')}\n")
    print("| 질문 | 주제 | 예/해당 항목 |\n|---|---|---|")
    for p in per:
        print(f"| {p['q']} | {p['topic']} | {p['yes']}/{p['n']} |")
    print(f"\n**세션 통과율 {rate if rate is not None else '—'}%** (예 {tot_yes} ÷ 해당 항목 {tot_n}, 산정 {tot_n}) — 같은 모드·같은 강도끼리만 추이를 비교한다.")
    print(f"\n**사실 일치(7번)**: " + (f"⚠️ 서류와 다르게 말한 답변 {', '.join(fact_bad)} — 자소서·카드와 어느 쪽이 맞는지 확인할 것" if fact_bad else "불일치 없음"))
    print("\n반복 약점 상위: " + (", ".join(weak3) if weak3 else "없음"))
    if defense_res:
        print("\n방어 상태 판정(갱신 후보): " + ", ".join(f"{k}→{v}" for k, v in defense_res.items()))
    if util:
        print(f"\n방어 맵 활용률: {util[0]}/{util[1]}" + (f" = {util[0] / util[1] * 100:.0f}%" if util[1] else ""))
    return 0


def cmd_next_path(a):
    d = AREA / "면접" / f"{a.company}_{a.job}"
    base = f"{J.today_kst().isoformat()}_{a.mode}_{a.intensity}"
    p = d / f"{base}.md"
    n = 1
    while p.exists():
        n += 1
        p = d / f"{base}_{n}.md"
    print(str(p))
    return 0


def cmd_log_summary(a):
    f = AREA / "면접" / "기록 요약.md"
    head = "# 면접 기록 요약\n\n> `/mock-interview`가 세션마다 한 줄씩 쌓는다. 같은 모드·같은 강도끼리만 추이를 비교한다.\n\n| 날짜 | 회사 | 직무 | 모드 | 강도 | 통과율 | 핵심 약점 | 비고 |\n|---|---|---|---|---|---|---|---|\n"
    line = "| " + " | ".join(J.cell(x) for x in (J.today_kst().isoformat(), a.company, a.job, a.mode, a.intensity, a.rate or "—", a.weak or "—", "중단" if a.aborted else "")) + " |"
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        J.backup_file(f)
        text = f.read_text(encoding="utf-8").rstrip("\n") + "\n" + line + "\n"
    else:
        text = head + line + "\n"
    f.write_text(text, encoding="utf-8", newline="\n")
    print("기록 요약에 추가함")
    return 0


def cmd_defense_list(a):
    _, cols, rows = read_map(a.file)
    if cols is None:
        print("방어 맵 표를 찾지 못함")
        return 1
    order = {"unprepared": 0, "weak": 1, "ready": 2}
    for r in sorted(rows, key=lambda r: order.get(r.get("방어 상태", ""), 3)):
        print(f"{r['id']} [{r['방어 상태']}] {r.get('문장', '')[:60]} ({r.get('위치', '')})")
    print(f"합계 {len(rows)}개 — 출제 우선순위: unprepared → weak → ready")
    return 0


def cmd_defense_set(a):
    if a.state not in STATES:
        J.die(f"상태는 {STATES}", 2)
    p = Path(a.file)
    text, cols, rows = read_map(p)
    if cols is None or not any(r["id"] == a.id for r in rows):
        print("그 id를 찾지 못함")
        return 1
    J.backup_file(p)
    out = []
    in_row = False
    for ln in text.splitlines():
        if ln.lstrip().startswith("|"):
            c = J.split_row(ln)
            if c and c[0] == a.id and len(c) == len(cols):
                c[cols.index("방어 상태")] = a.state
                if a.hint is not None and "1분 답변 골자" in cols:
                    c[cols.index("1분 답변 골자")] = a.hint
                ln = "| " + " | ".join(J.cell(x) if not x.endswith("\\|") else x for x in c) + " |"
        out.append(ln)
    p.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"{a.id} → {a.state}" + (" (골자 기록)" if a.hint else ""))
    return 0


def cmd_bank_add(a):
    f = AREA / "면접" / "실전 질문 은행.md"
    head = "# 실전 질문 은행\n\n> `/mock-interview 후기기록`으로 모은 실제 면접 질문. 기억 기준이라 문구가 정확하지 않을 수 있다. 제3자 이름은 적지 않는다.\n\n| 날짜 | 회사 | 종류 | 질문 | 비고 |\n|---|---|---|---|---|\n"
    line = "| " + " | ".join(J.cell(x) for x in (J.today_kst().isoformat(), a.company, a.kind or "", a.text, a.note or "기억 기준")) + " |"
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        J.backup_file(f)
        text = f.read_text(encoding="utf-8").rstrip("\n") + "\n" + line + "\n"
    else:
        text = head + line + "\n"
    f.write_text(text, encoding="utf-8", newline="\n")
    print("질문 은행에 추가함")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("calc"); p.add_argument("file"); p.add_argument("--map"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("next-path")
    for k in ("company", "job", "mode", "intensity"):
        p.add_argument("--" + k, required=True)
    p = sub.add_parser("log-summary")
    for k in ("company", "job", "mode", "intensity"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--rate"); p.add_argument("--weak"); p.add_argument("--aborted", action="store_true")
    p = sub.add_parser("defense-list"); p.add_argument("file")
    p = sub.add_parser("defense-set"); p.add_argument("file"); p.add_argument("--id", required=True); p.add_argument("--state", required=True); p.add_argument("--hint")
    p = sub.add_parser("bank-add"); p.add_argument("--text", required=True); p.add_argument("--company", required=True); p.add_argument("--kind"); p.add_argument("--note")
    a = ap.parse_args()
    return {"calc": cmd_calc, "next-path": cmd_next_path, "log-summary": cmd_log_summary, "defense-list": cmd_defense_list,
            "defense-set": cmd_defense_set, "bank-add": cmd_bank_add}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
