#!/usr/bin/env python3
"""자소서 정본(md)의 글자수 · 키워드 포함 · placeholder · 수치 대조를 계산한다. 문서를 고치지 않는다. 볼트 루트에서 실행.

문서 형식: 문항마다 `### 문항 N …` 제목 아래에 답을 쓴다. 답으로 세는 줄은 그 제목부터 다음 `#` 제목 전까지 중
`>`(인용·메모) · `|`(표) · `<!--`(주석)로 시작하지 않는 줄이다. `## v1 뼈대` · `## v2 …` · `## 최종` 같은 버전 절이 있으면 `--section 최종` 으로 그 절만 본다.

쓰는 법:
  python -I -X utf8 cl_check.py chars <문서.md> [--section 최종] [--limits "1=800,2=1000"] [--basis incl|excl]
      문항별 글자수 3가지(공백 제외 / 공백 포함·줄바꿈 제외 / 공백·줄바꿈 포함). --limits 를 주면 기준(--basis, 기본 incl)에 맞춰 한도 대비 %와 초과 여부
      ※ 사이트가 공백·줄바꿈을 어떻게 세는지는 양식에서 확인해야 한다(모르면 세 값을 모두 본다)
  python -I -X utf8 cl_check.py keywords <문서.md> --kw "LSTM|시계열,전처리" [--section 최종]
      키워드(쉼표 구분, `|`는 별칭)별로 몇 문항 몇 문단에 있는지. 같은 문단에 키워드가 3개 이상 몰려 있으면 표시. 근거 문장이 있는지는 모델이 판단한다
  python -I -X utf8 cl_check.py placeholders <문서.md> [--section 최종]
      `[수치 확인 필요]` `[추정]` `[확인 필요]` `근거 없음` 개수와 위치(.docx 내보내기 조건)
  python -I -X utf8 cl_check.py numbers <문서.md> [--section 최종]
      초안 속 숫자(%·건·명·개월 등)를 뽑아 wiki 경험 카드 어디에 있는지 표시(없으면 `카드에 없음` → 일관성 검사 대상)
"""
import argparse
import re
import sys
from pathlib import Path

WIKI = Path("Projects/SecondBrain/wiki")
PLACEHOLDERS = ["[수치 확인 필요]", "[추정]", "[확인 필요]", "근거 없음"]


def section_text(text, name):
    if not name:
        return text
    m = re.search(rf"^##\s+{re.escape(name)}.*$", text, flags=re.M)
    if not m:
        sys.exit(f"`## {name}` 절을 찾지 못했다")
    rest = text[m.end():]
    n = re.search(r"^##\s+(?!#)", rest, flags=re.M)
    return rest[: n.start()] if n else rest


def answers(text):
    """{문항 번호: [문단 문자열...]}"""
    res, cur, paras, buf = {}, None, [], []

    def flush():
        nonlocal buf
        if buf and cur is not None:
            paras.append("\n".join(buf).strip())
        buf = []

    for ln in text.splitlines():
        m = re.match(r"^###\s+문항\s*(\d+)", ln)
        if m:
            flush()
            if cur is not None:
                res[cur] = [p for p in paras if p]
            cur, paras = int(m.group(1)), []
            continue
        if re.match(r"^#{1,3}\s", ln):
            flush()
            if cur is not None:
                res[cur] = [p for p in paras if p]
            cur, paras = None, []
            continue
        if cur is None:
            continue
        s = ln.strip()
        if s.startswith((">", "|", "<!--")):
            continue
        if not s:
            flush()
            continue
        buf.append(ln)
    flush()
    if cur is not None:
        res[cur] = [p for p in paras if p]
    return res


def counts(paras):
    body = "\n".join(paras)
    no_ws = len(re.sub(r"\s", "", body))
    incl = len(body.replace("\n", ""))
    incl_nl = len(body)
    return no_ws, incl, incl_nl


def cmd_chars(a):
    ans = answers(section_text(Path(a.file).read_text(encoding="utf-8"), a.section))
    limits = {}
    for part in (a.limits or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            limits[int(k)] = int(v)
    print("| 문항 | 공백 제외 | 공백 포함(줄바꿈 제외) | 공백·줄바꿈 포함 | 한도 | 채움 | 판정 |\n|---|---|---|---|---|---|---|")
    bad = 0
    for no in sorted(ans):
        ex, inc, nl = counts(ans[no])
        lim = limits.get(no)
        used = {"incl": inc, "excl": ex}.get(a.basis, inc)
        if lim:
            pct = used / lim * 100
            verdict = "초과" if used > lim else ("부족(90% 미만)" if pct < 90 else "통과")
            bad += used > lim
            print(f"| {no} | {ex} | {inc} | {nl} | {lim}({a.basis}) | {pct:.0f}% | {verdict} |")
        else:
            print(f"| {no} | {ex} | {inc} | {nl} | — | — | 한도 미입력 |")
    if not ans:
        print("(`### 문항 N` 제목을 찾지 못함)")
    return 1 if bad else 0


def cmd_keywords(a):
    ans = answers(section_text(Path(a.file).read_text(encoding="utf-8"), a.section))
    print("| 키워드 | 반영 위치(문항.문단) | 개수 |\n|---|---|---|")
    packed = []
    for kw in [k.strip() for k in a.kw.split(",") if k.strip()]:
        alts = [x.strip().lower() for x in kw.split("|") if x.strip()]
        locs = []
        for no in sorted(ans):
            for i, p in enumerate(ans[no], 1):
                if any(x in p.lower() for x in alts):
                    locs.append(f"{no}.{i}")
        print(f"| {kw} | {', '.join(locs) or '없음'} | {len(locs)} |")
    for no in sorted(ans):
        for i, p in enumerate(ans[no], 1):
            hit = [k for k in a.kw.split(",") if k.strip() and any(x.strip().lower() in p.lower() for x in k.split("|") if x.strip())]
            if len(hit) >= 3:
                packed.append(f"{no}.{i}({len(hit)}개)")
    if packed:
        print("\n⚠️ 한 문단에 키워드가 3개 이상 몰림: " + ", ".join(packed) + " — 문단당 1~2개로 나눌 것")
    print("\n※ 키워드가 같은 문단의 카드 사실(행동·수치)과 함께 있을 때만 '반영'이다. 근거 없이 키워드만 있으면 미반영으로 재분류(모델이 판단).")
    return 0


def cmd_placeholders(a):
    ans_text = section_text(Path(a.file).read_text(encoding="utf-8"), a.section)
    total = 0
    for ph in PLACEHOLDERS:
        locs = [i for i, ln in enumerate(ans_text.splitlines(), 1) if ph in ln]
        total += len(locs)
        print(f"- `{ph}` {len(locs)}건" + (f" (줄 {', '.join(map(str, locs[:10]))})" if locs else ""))
    print(f"합계 {total}건 — " + ("내보내기 조건 통과(placeholder 0)" if total == 0 else "내보내기 전에 해결하거나 사용자가 `내 진술`로 확인해야 함"))
    return 0 if total == 0 else 1


def cmd_numbers(a):
    text = section_text(Path(a.file).read_text(encoding="utf-8"), a.section)
    ans = answers(text)
    cards = {}
    for p in sorted(WIKI.glob("내경험_*.md")):
        if p.name == "내경험_자료목록.md":
            continue
        for blk in re.split(r"^### (?=exp-)", p.read_text(encoding="utf-8"), flags=re.M)[1:]:
            cards[blk.split()[0]] = blk
    pat = re.compile(r"(?<![A-Za-z가-힣\d.])\d+(?:[.,]\d+)?\s*(?:%|퍼센트|건|명|개월|개|배|회|시간|일|주|초|ms|점)?")
    print("| 문항.문단 | 초안의 숫자 | 카드 속 위치 |\n|---|---|---|")
    for no in sorted(ans):
        for i, p in enumerate(ans[no], 1):
            for tok in sorted({m.group().strip() for m in pat.finditer(p) if re.search(r"\d", m.group())}):
                digits = re.match(r"\d+(?:[.,]\d+)?", tok).group()
                where = [cid for cid, blk in cards.items() if digits in blk]
                print(f"| {no}.{i} | {tok} | {', '.join(where) if where else '**카드에 없음**'} |")
    print("\n※ `카드에 없음`인 숫자는 근거 없음 — 지원 이력서의 같은 항목과도 대조(일관성 검사, 모델)한다.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("chars", "keywords", "placeholders", "numbers"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--section")
        if name == "chars":
            p.add_argument("--limits"); p.add_argument("--basis", default="incl", choices=["incl", "excl"])
        if name == "keywords":
            p.add_argument("--kw", required=True)
    a = ap.parse_args()
    return {"chars": cmd_chars, "keywords": cmd_keywords, "placeholders": cmd_placeholders, "numbers": cmd_numbers}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
