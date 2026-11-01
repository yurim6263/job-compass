#!/usr/bin/env python3
"""기업 조사의 키워드 반영 가능률과 지원 판단(5기준 → 3단계)을 고정 규칙으로 계산한다. 모델은 판정만 쓴다.

쓰는 법:
  python -I -X utf8 company_calc.py <입력.json>     (표준입력은 `-`)   [--json]

입력 JSON:
{
 "keywords": [{"kw":"예지보전","verdict":"O|모호|X|제외","cards":["exp-…"],"note":"한 줄 근거"}, …],
 "job_fit":  "🟢|🟡|🔴|미산출"        # /job-posting 점수의 등급을 그대로(여기서 다시 계산하지 않음)
 "growth":   "O|△|X|보류",  "stability": "O|△|X|보류",  "region": "O|△|X|보류",
 "gate_blocked": false,                # 공고 게이트 🚫(경력 필수·석사 이상 필수·마감 지남)가 있는가
 "body_missing": false                 # 공고 본문 미확보로 직무 적합이 보류인가
}
규칙(기획 03 §3-3, §3-5):
  키워드 반영 가능률 = (O + 0.5×모호) ÷ (O + 모호 + X) × 100, `제외`(경험으로 답할 수 없는 회사 일반어)는 분모에서 뺀다. `산정 n/m`을 같이 쓴다.
  직무 적합: 점수 등급 🟢 → O · 🟡 → △ · 🔴 → X · 미산출 → 보류(X가 아님)
  기술 적합: 반영 가능률 70% 이상 O · 40~69% △ · 40% 미만 X (공고 5건 후 보정). 산정 키워드가 0이면 보류
  보상은 평가하지 않는다(미수집). 보류 칸은 세지 않는다.
  3단계: 게이트 🚫 → 신중 검토 / X가 2개 이상 → 신중 검토 / O 3개 이상이고 X 없음 → 지원 권장 / 그 밖 → 조건부 지원.
         공고 본문 미확보로 직무 적합이 보류면 최대 조건부 지원.
"""
import json
import sys
from pathlib import Path

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    raw = sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text(encoding="utf-8")
    d = json.loads(raw)
    kws = d.get("keywords", [])
    errs = []
    cnt = {"O": 0, "모호": 0, "X": 0, "제외": 0}
    for k in kws:
        v = k.get("verdict")
        if v not in cnt:
            errs.append(f"키워드 `{k.get('kw')}`의 verdict `{v}`가 O·모호·X·제외가 아님")
            continue
        if v in ("O", "모호") and not k.get("cards"):
            errs.append(f"키워드 `{k.get('kw')}`: {v} 판정인데 카드 id가 없음")
        cnt[v] += 1
    if errs:
        print("입력 오류:\n- " + "\n- ".join(errs))
        return 2
    m = cnt["O"] + cnt["모호"] + cnt["X"]
    rate = None if m == 0 else (cnt["O"] + 0.5 * cnt["모호"]) / m * 100
    job = {"🟢": "O", "🟡": "△", "🔴": "X"}.get(d.get("job_fit", "미산출"), "보류")
    tech = "보류" if rate is None else ("O" if rate >= 70 else ("△" if rate >= 40 else "X"))
    crit = {"직무 적합": job, "기술 적합": tech, "성장 가능성": d.get("growth", "보류"), "안정성": d.get("stability", "보류"), "지역·근무 환경": d.get("region", "보류")}
    for k, v in crit.items():
        if v not in ("O", "△", "X", "보류"):
            print(f"기준 `{k}` 값 `{v}`가 O·△·X·보류가 아님")
            return 2
    o = sum(1 for v in crit.values() if v == "O")
    x = sum(1 for v in crit.values() if v == "X")
    if d.get("gate_blocked"):
        dec, why = "신중 검토", "공고 게이트 🚫"
    elif x >= 2:
        dec, why = "신중 검토", f"X {x}개"
    elif o >= 3 and x == 0:
        dec, why = "지원 권장", f"O {o}개, X 없음"
    else:
        dec, why = "조건부 지원", f"O {o}개 · X {x}개"
    if d.get("body_missing") and job == "보류" and dec == "지원 권장":
        dec, why = "조건부 지원", "공고 본문 미확보로 직무 적합 보류 — 최대 조건부"
    res = {"counts": cnt, "rate": None if rate is None else round(rate, 1), "counted": f"{m}/{len(kws)}", "criteria": crit, "decision": dec, "why": why}
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print("## 키워드 반영 가능률\n")
    print(f"O {cnt['O']} · 모호 {cnt['모호']} · X {cnt['X']} → " + ("산정할 키워드 없음" if rate is None else f"**{rate:.0f}%**") + f" (산정 {res['counted']}, 제외 {cnt['제외']})\n")
    print("## 지원 판단\n\n| 기준 | 판정 |\n|---|---|")
    for k, v in crit.items():
        print(f"| {k} | {v} |")
    print("| 보상 | 미수집 |")
    print(f"\n**{dec}** — {why}. (최종 결정은 사용자가 한다)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
