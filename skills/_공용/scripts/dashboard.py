#!/usr/bin/env python3
"""오늘 현황 · 단계 체크리스트 · 다음 행동 제안 · 통계. 볼트 루트에서 실행한다. 읽기 전용(--write 를 주면 사본 2개만 쓴다).

쓰는 법:
  python -I -X utf8 dashboard.py today [--today YYYY-MM-DD] [--write]   # 오늘 현황. --write 면 Areas/취업/오늘 현황.md 와 _widget/오늘 현황.json 갱신
  python -I -X utf8 dashboard.py steps --id jobkorea:123                 # 한 건의 단계 체크리스트와 다음 행동 (공고 ID가 `—`인 행은 --company [--job])
  python -I -X utf8 dashboard.py stats [--today YYYY-MM-DD]              # 통계(분모와 표본 크기를 함께)

규칙(기획 07): 순서 고정 = 먼저 볼 것 → 마감 임박(D-7) → 7일 넘게 변화 없음 → 새 후보 → 진행 중 → 다음 행동.
  단계 체크리스트는 파일을 실제로 찾아서 정한다(링크가 끊겼으면 ✗가 아니라 `링크 끊김`).
  이 스크립트는 현황표·후보함·wiki·output 을 고치지 않는다.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

WIKI = Path("Projects/SecondBrain/wiki")
OUTPUT = Path("Projects/SecondBrain/output")
AREA = Path("Areas/취업")
CAND = AREA / "공고 후보함.md"
OUT_MD = AREA / "오늘 현황.md"
OUT_JSON = AREA / "_widget" / "오늘 현황.json"
STALE_DAYS = 7
SOON_DAYS = 7
OPEN = [s for s in J.STATES if s not in J.CLOSED]


def read_setting(path, key):
    p = Path(path)
    if not p.exists():
        return None
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.lstrip().startswith("|"):
            c = J.split_row(ln)
            if len(c) >= 2 and key in c[0]:
                return c[1]
    return None


def link_target(cell):
    m = re.match(r"^\[\[(.+?)\]\]$", cell.strip())
    if not m:
        return None
    inner = m.group(1).replace("\\|", "|")
    return inner.split("|")[0]


def score_of(fit):
    m = re.match(r"^(\d{1,3}) ", fit.strip())
    return int(m.group(1)) if m else None


def gate_marks(fit):
    return "🚫" in fit


def company_job(row):
    """파일 이름에 쓰는 (회사, 직무). 직무는 공고 wiki 파일명에서 따온다(`채용공고_<회사> <직무>`)."""
    comp = row["기업명"]
    t = link_target(row["공고"]) or ""
    job = ""
    if t.startswith("채용공고_" + comp + " "):
        job = t[len("채용공고_" + comp + " "):]
    return comp, job


def checklist(row, today):
    comp, job = company_job(row)
    res = {}
    t = link_target(row["공고"])
    if not t:
        res["공고"] = "✗"
    else:
        res["공고"] = "✓" if (WIKI / (t + ".md")).exists() else "링크 끊김"
    out_hit = False
    if t and OUTPUT.exists():
        for f in OUTPUT.glob("*지원 준비*.md"):
            try:
                if f"[[{t}" in f.read_text(encoding="utf-8"):
                    out_hit = True
                    break
            except OSError:
                pass
    res["점수"] = "✓" if (out_hit and row["적합도"].strip()) else ("✗" if not out_hit else "점수없음")
    cr = WIKI / f"기업조사_{comp}.md"
    if cr.exists():
        m = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", cr.read_text(encoding="utf-8"), flags=re.M)
        old = bool(m and (today - J.parse_date(m.group(1))).days > 30)
        res["조사"] = "✓(오래됨)" if old else "✓"
    else:
        res["조사"] = "✗"
    cl = AREA / "자소서" / f"{comp}_{job}.md" if job else None
    if cl and cl.exists():
        res["자소서"] = "✓(최종)" if "## 최종" in cl.read_text(encoding="utf-8") else "작성중"
    else:
        res["자소서"] = "✗"
    dm = AREA / "자소서" / f"{comp}_{job}_방어맵.md" if job else None
    res["방어맵"] = "✓" if (dm and dm.exists()) else "✗"
    iv = AREA / "면접" / f"{comp}_{job}" if job else None
    n = sum(1 for _ in iv.rglob("*") if _.is_file()) if (iv and iv.exists()) else 0
    res["면접"] = f"{n}회" if n else "✗"
    return res


def fmt_steps(c):
    return " ".join(f"{k}{v}" for k, v in c.items())


def d_label(d, today):
    n = (d - today).days
    return f"D-{n}" if n > 0 else ("D-day" if n == 0 else f"D+{-n}")


def read_candidates(today):
    if not CAND.exists():
        return []
    cols, rows = None, []
    for ln in CAND.read_text(encoding="utf-8").splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        c = J.split_row(ln)
        if "상태" in c and "회사" in c:      # 표 머리(후보 표와 `후보함_지난` 표가 각각 있다) — 데이터 행으로 세지 않는다
            cols = c
            continue
        if cols is None:
            continue
        if re.match(r"^[\s:-]+$", "".join(c)):
            continue
        rows.append({k: (c[i] if i < len(c) else "") for i, k in enumerate(cols)})
    return rows


def suggest(row, steps, today):
    st, fit = row["진행상태"], row["적합도"]
    sc = score_of(fit)
    if st == "Not started":
        if gate_marks(fit):
            return "지원 불가 사유를 확인하고 `지원취소`로 정리할까요?", "게이트 🚫"
        if fit.startswith("미산출") or not fit.strip():
            return "`/job-posting`으로 본문·점수를 보강", "적합도 미산출"
        if sc is not None and sc < 60:
            return "정말 지원할지 확인(점수 낮음)", f"적합도 {fit}"
        if steps["조사"] == "✗":
            return "`/company-research 빠른`", f"적합도 {fit}, 기업 조사 없음"
        return "`/cover-letter 항목정리`", "기업 조사 ✓"
    if st == "일정 + 자소서 항목 정리":
        return "`/cover-letter 신규`", "항목 정리 끝"
    if st in ("인적사항 입력완료", "자소서 작성중"):
        if steps["자소서"] in ("작성중", "✓(최종)"):
            return "`/cover-letter 첨삭`(키워드 반영률·일관성 점검)", f"{st}"
        return "`/cover-letter 신규`", f"{st}, 자소서 파일 없음"
    if st == "자소서 작성 완료":
        return "제출 전 점검(글자수·placeholder·.docx). 제출은 사용자가 합니다", st
    if st == "지원완료":
        return "결과 대기. 전형에 AI 역량검사가 있으면 `/mock-interview AI 역량검사`", st
    if st == "서류합":
        return "`/mock-interview 인성` 또는 `기술`", st
    if st in ("역량검사", "인적성"):
        return "`/mock-interview AI 역량검사`", st
    if st in ("1차면접", "2차면접", "최종면접"):
        return f"`/mock-interview` {st} 연습, 면접 뒤 `후기기록`", st
    if st in ("불합", "지원취소"):
        return "`/mock-interview 후기기록`(받은 질문이 있으면)", st
    if st == "최종합":
        return "나머지 진행 중인 건을 `지원취소`로 정리할지 확인", st
    return "", ""


def read_expire_record(today):
    """오늘 `status_table.py expire --apply`가 지원취소로 바꾼 회사 이름들(브리핑용). 기록이 없거나 오늘 것이 아니면 빈 목록."""
    try:
        rec = json.loads(J.EXPIRE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if rec.get("date") != today.isoformat():
        return []
    return [it.get("기업명", "") for it in rec.get("items", [])]


def build(today):
    t = J.Table()
    warnings, rows = [], []
    if t.head_idx is None:
        return {"today": today, "empty": True, "rows": [], "warnings": ["현황표가 없음"]}
    probs = t.problems()
    if probs:
        warnings += ["현황표 형식 문제(고치지 않음): " + "; ".join(probs)]
        return {"today": today, "empty": False, "rows": [], "warnings": warnings}
    rows = t.as_dicts()
    ids = [r["공고 ID"] for r in rows if r["공고 ID"] not in ("", "—")]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    for i in dups:
        warnings.append(f"같은 공고 ID `{i}`가 두 행 이상 — 합치지 않고 둘 다 보여 줌")
    first, urgent, overdue, wait_result, stale, bad_date, inprog = [], [], [], [], [], [], []
    for r in rows:
        st = r["진행상태"]
        if st in J.CLOSED:
            continue
        dl = None
        if r["서류마감"]:
            try:
                dl = J.parse_date(r["서류마감"])
            except ValueError:
                bad_date.append(r["기업명"])
        steps = checklist(r, today)
        item = {"row": r, "deadline": dl, "steps": steps}
        inprog.append(item)
        if dl:
            if st in J.PRE_APPLY:
                if dl < today:
                    overdue.append(item)
                elif (dl - today).days <= SOON_DAYS:
                    urgent.append(item)
            elif st == "지원완료" and dl < today:
                wait_result.append(item)
        try:
            days = (today - J.parse_date(r["상태일"])).days
        except ValueError:
            days = None
        if days is not None and days >= STALE_DAYS and st in J.STAGE_ORDER[:6]:
            stale.append((item, days))
    log = AREA / "_scan-log.md"
    scan_warn = []
    if log.exists():
        scan_warn = [ln.strip("-• ").strip() for ln in log.read_text(encoding="utf-8").splitlines() if "연속 실패" in ln][-3:]
    cands = [c for c in read_candidates(today) if c.get("상태", "") in ("새로", "본문확보", "점수")]
    cands.sort(key=lambda c: -(score_of(c.get("점수", "")) or -1))
    urgent.sort(key=lambda i: i["deadline"])
    overdue.sort(key=lambda i: i["deadline"])
    # 마감 지남 브리핑(2026-11-17 사용자 결정): 이 함수는 현황표를 고치지 않는다. 정리는 `status_table.py expire`(/job-flow가 호출)가 한다.
    expired_auto = [i for i in overdue if i["row"]["진행상태"] in J.EXPIRE_AUTO]
    expired_ask = [i for i in overdue if i["row"]["진행상태"] in J.EXPIRE_ASK]
    expired_done = read_expire_record(today)

    # 다음 행동: 게이트 🚫(Not started) 뒤로, 마감 임박순, 점수 높은 순
    def prio(i):
        r = i["row"]
        dl = i["deadline"] or (today + timedelta(days=3650))
        return (1 if gate_marks(r["적합도"]) and r["진행상태"] == "Not started" else 0, dl, -(score_of(r["적합도"]) or -1))
    actions = []
    for i in sorted(inprog, key=prio):
        s, why = suggest(i["row"], i["steps"], today)
        if s:
            actions.append({"company": i["row"]["기업명"], "id": i["row"]["공고 ID"], "do": s, "why": why})
    closed = sum(1 for r in rows if r["진행상태"] in J.CLOSED)
    inprog.sort(key=lambda i: (i["deadline"] is None, i["deadline"] or today, i["row"]["기업명"]))
    return {"today": today, "empty": not rows, "rows": rows, "overdue": overdue, "wait_result": wait_result, "urgent": urgent,
            "expired_auto": expired_auto, "expired_ask": expired_ask, "expired_done": expired_done,
            "stale": stale, "cands": cands, "cand_total": len(cands), "inprog": inprog, "closed": closed, "actions": actions[:3],
            "warnings": warnings, "scan_warn": scan_warn, "bad_date": bad_date, "dups": dups}


def render_today(b, now):
    today = b["today"]
    notion = read_setting(AREA / "설정.md", "notion") or "off"
    pub = read_setting(AREA / "검색 조건.md", "공공기관") or "끔"
    L = [f"오늘 현황 · 기준일 {today.isoformat()} ({J.weekday_ko(today)}, KST) · Notion {'꺼짐' if notion.strip() == 'off' else '켜짐'} · 공공기관 {pub.strip()}",
         "━" * 32]
    if b.get("empty") and not b["rows"]:
        cards = len(list(WIKI.glob("내경험_*.md"))) if WIKI.exists() else 0
        L += ["현황표가 비어 있거나 없습니다 — 정상 진입입니다.", f"- 지금 있는 것: 경험 문서 {cards}개 · 현황표 0행 · 후보 {sum(1 for c in read_candidates(today) if c.get('상태', '') in ('새로', '본문확보', '점수'))}건",
              "- 순서 제안: ① `/exp-intake`로 경험 넣기 → ② `/exp-organize`로 카드 만들기 → ③ 공고 링크로 `/job-posting`"]
        for w in b["warnings"]:
            L.append(f"- ⚠️ {w}")
        return "\n".join(L) + "\n"
    for w in b["warnings"]:
        L.append(f"⚠️ {w}")
    exp_auto, exp_ask, exp_done = b.get("expired_auto", []), b.get("expired_ask", []), b.get("expired_done", [])
    n_exp = len(exp_auto) + len(exp_ask) + len(exp_done)
    if n_exp:
        L.append(f"⏰ 마감 지남 — 지원 준비 중이던 공고 {n_exp}개")
        if exp_done:
            L.append("  - 오늘 자동 정리(지원취소 · 메모 \"마감 지남(미지원)\"): " + ", ".join(exp_done))
        if exp_auto:
            L.append("  - 정리 대기(다음에 `/job-flow`를 열 때 자동 정리): "
                     + ", ".join(f"{i['row']['기업명']}({i['deadline'].strftime('%m-%d')})" for i in exp_auto))
        if exp_ask:
            L.append("  - 제출 여부 확인 필요(제출했으면 `지원완료`, 안 했으면 `지원취소`라고 말씀해 주세요): "
                     + ", ".join(f"{i['row']['기업명']}({i['deadline'].strftime('%m-%d')}, {i['row']['진행상태']})" for i in exp_ask))
    L.append("⚠️ 먼저 볼 것")
    first = []
    for i in b["wait_result"]:
        first.append(f"  - 마감 경과 — 결과 확인 필요: {i['row']['기업명']} ({d_label(i['deadline'], today)}) [{i['row']['진행상태']}]")
    for w in b["scan_warn"]:
        first.append(f"  - 스캔 소스 경고: {w}")
    if b["bad_date"]:
        first.append("  - 서류마감 형식 확인 필요: " + ", ".join(b["bad_date"]))
    if notion.strip() == "on" and notion_pending():
        first.append(f"  - Notion 밀린 반영 {notion_pending()}건 — \"Notion 밀린 반영 올려줘\"로 확인 후 올리기")
    L += first or ["  - 없음"]
    L.append(f"📅 마감 임박 (D-{SOON_DAYS} 이내)")
    L += [f"  - {i['deadline'].strftime('%m-%d')} ({d_label(i['deadline'], today)}) {i['row']['기업명']} · {i['row']['직무']} · 적합도 {i['row']['적합도'] or '—'} [{i['row']['진행상태']}]"
          for i in b["urgent"]] or ["  - 없음"]
    L.append("🔔 7일 넘게 변화 없음")
    L += [f"  - {i['row']['기업명']} · {i['row']['진행상태']} · {d}일째" for i, d in b["stale"]] or ["  - 없음"]
    L.append("🆕 새 후보 (후보함 · 점수 높은 순 3)")
    if b["cands"]:
        for c in b["cands"][:3]:
            L.append(f"  - {c.get('회사', '')} · {c.get('방향', '')} · 미리보기 점수 {c.get('점수', '—') or '—'} · 마감 {c.get('서류마감(D-n)', c.get('서류마감', '—'))}")
        if b["cand_total"] > 3:
            L.append(f"  - 그 밖에 {b['cand_total'] - 3}건")
    else:
        L.append("  - 없음")
    L.append("▶ 진행 중 (마감순)")
    for i in b["inprog"]:
        r = i["row"]
        dl = f"{i['deadline'].strftime('%m-%d')} ({d_label(i['deadline'], today)})" if i["deadline"] else "마감 미정"
        L.append(f"  - {dl} {r['기업명']} · {r['직무']} · [{r['진행상태']}] · 적합도 {r['적합도'] or '—'}  — {fmt_steps(i['steps'])}")
    if not b["inprog"]:
        L.append("  - 없음")
    if b["closed"]:
        L.append(f"종결 {b['closed']}건(최종합·불합·지원취소)")
    L.append("다음 행동 제안 (1~3개)")
    for n, a in enumerate(b["actions"], 1):
        L.append(f"  {n}. {a['company']} — {a['do']}  ({a['why']})")
    if not b["actions"]:
        L.append("  - 없음")
    return "\n".join(L) + "\n"


def last_scan():
    """`_scan-log.md` 에서 마지막 무인 실행 종료 줄의 시각(YYYY-MM-DD HH:MM)과 코드. 없으면 None"""
    log = AREA / "_scan-log.md"
    if not log.exists():
        return None
    hit = None
    for ln in log.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^-\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · 무인 실행 종료.*코드 (\d+)", ln.strip())
        if m:
            hit = {"at": m.group(1), "code": int(m.group(2))}
    return hit


def filtered_today(today):
    """오늘 수집 기록(_수집기록.md)으로 걸러 낸 공고 수 — 후보함에 올리지 않은 것"""
    p = AREA / "_수집기록.md"
    if not p.exists():
        return 0
    return sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
               if ln.startswith("| " + today.isoformat() + " |"))


def notion_pending():
    p = AREA / "_notion-대기.md"
    if not p.exists():
        return 0
    rows = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.lstrip().startswith("|")]
    return max(0, len(rows) - 2)      # 머리줄·구분줄 제외


JSON_SCHEMA = 1     # 위젯(apps/widget)이 읽는 판. 칸을 지우거나 뜻을 바꾸면 올린다(더하기만 하면 그대로)


def doc_of(row):
    """그 행의 공고 wiki 문서 경로(볼트 루트 기준, `/` 구분). 파일이 없으면 None"""
    t = link_target(row["공고"])
    p = WIKI / (t + ".md") if t else None
    return p.as_posix() if p and p.exists() else None


def to_json(b, now):
    def item(i):
        r = i["row"]
        return {"company": r["기업명"], "job": r["직무"], "id": r["공고 ID"], "state": r["진행상태"], "fit": r["적합도"],
                "deadline": i["deadline"].isoformat() if i["deadline"] else None, "steps": i["steps"], "doc": doc_of(r)}

    def cand(c):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", c.get("서류마감(D-n)", "").strip())
        return {"company": c.get("회사", ""), "title": c.get("공고", ""), "id": c.get("공고 ID", ""), "direction": c.get("방향", ""),
                "score": c.get("점수", ""), "link": c.get("링크", ""), "deadline": m.group(1) if m else None}
    return {"schema": JSON_SCHEMA, "generated_at": now.isoformat(timespec="minutes"), "today": b["today"].isoformat(), "timezone": "KST",
            "files": {"candidates": CAND.as_posix(), "today": OUT_MD.as_posix(), "ledger": (AREA / "_수집기록.md").as_posix()},
            "counts": {"in_progress": len(b.get("inprog", [])), "closed": b.get("closed", 0), "urgent": len(b.get("urgent", [])),
                       "overdue": len(b.get("overdue", [])), "wait_result": len(b.get("wait_result", [])),
                       "expired_pending": len(b.get("expired_auto", [])), "expired_ask": len(b.get("expired_ask", [])),
                       "expired_cleaned_today": len(b.get("expired_done", [])),
                       "new_candidates": b.get("cand_total", 0),
                       "new_candidates_today": sum(1 for c in read_candidates(b["today"])
                                                   if c.get("발견일", "").strip() == b["today"].isoformat()),
                       "notion_pending": notion_pending(), "filtered_today": filtered_today(b["today"])},
            "notion": (read_setting(AREA / "설정.md", "notion") or "off").strip(),
            "last_scan": last_scan(),
            "urgent": [item(i) for i in b.get("urgent", [])], "overdue": [item(i) for i in b.get("overdue", [])],
            "wait_result": [item(i) for i in b.get("wait_result", [])],
            "expired": {"pending": [item(i) for i in b.get("expired_auto", [])], "ask": [item(i) for i in b.get("expired_ask", [])],
                        "cleaned_today": b.get("expired_done", [])},
            "stale": [{**item(i), "days": d} for i, d in b.get("stale", [])],
            "new_candidates": [cand(c) for c in b.get("cands", [])[:3]],
            "in_progress": [item(i) for i in b.get("inprog", [])], "next_actions": b.get("actions", []),
            "warnings": b.get("warnings", []) + b.get("scan_warn", [])}


def cmd_today(a):
    today = J.parse_date(a.today) if a.today else J.today_kst()
    b = build(today)
    now = datetime.now(J.KST)
    text = render_today(b, now)
    print(text)
    if a.write:
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(f"> 사본 — 정본은 `지원 현황.md`, 생성 {now.strftime('%Y-%m-%d %H:%M')} (KST). 고치지 마세요(다음에 덮어씁니다).\n\n```\n{text}```\n",
                          encoding="utf-8", newline="\n")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(to_json(b, now), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(f"(사본 갱신: {OUT_MD} · {OUT_JSON})")
    return 0


def cmd_steps(a):
    today = J.today_kst()
    t = J.Table()
    rows = t.as_dicts() if t.head_idx is not None else []
    if a.id and a.id.strip() not in ("", "—"):
        hit = [d for d in rows if d["공고 ID"].strip() == a.id.strip()]
    else:
        hit = [d for d in rows if d["기업명"] == a.company and (not a.job or d["직무"] == a.job)]
    if not hit:
        print("그런 행이 없다")
        return 1
    if len(hit) > 1:
        print("해당하는 행이 둘 이상이다 — 직무(--job)로 하나를 고른다:")
        for d in hit:
            print("  " + d["기업명"] + " | " + d["직무"] + " | " + d["진행상태"])
        return 5
    r = hit[0]
    steps = checklist(r, today)
    s, why = suggest(r, steps, today)
    print(f"{r['기업명']} · {r['직무']} · [{r['진행상태']}] · 적합도 {r['적합도'] or '—'}")
    print("단계: " + fmt_steps(steps))
    print(f"다음 행동: {s} ({why})")
    return 0


def cmd_stats(a):
    today = J.parse_date(a.today) if a.today else J.today_kst()
    t = J.Table()
    if t.head_idx is None or t.problems():
        print("현황표가 없거나 형식 문제 — 통계를 내지 않는다")
        return 1
    rows = t.as_dicts()
    print(f"# 통계 · 기준일 {today.isoformat()} (KST) · 전체 {len(rows)}행\n")
    dist = {}
    for r in rows:
        dist[r["진행상태"]] = dist.get(r["진행상태"], 0) + 1
    print("## 진행상태 분포\n" + "\n".join(f"- {k}: {v}" for k, v in sorted(dist.items(), key=lambda kv: J.STATES.index(kv[0]) if kv[0] in J.STATES else 99)))
    rank = {s: i for i, s in enumerate(J.STAGE_ORDER)}

    def fin(r):
        f = r["최종 단계"] or r["진행상태"]
        return rank.get(f, -1)
    n_apply = sum(1 for r in rows if fin(r) >= rank["지원완료"] and r["진행상태"] != "지원취소")
    print(f"\n## 퍼널(최종 단계 기준, 지원취소 제외) — 지원 {n_apply}건")
    for s in J.STAGE_ORDER[5:]:
        n = sum(1 for r in rows if fin(r) >= rank[s] and r["진행상태"] != "지원취소")
        print(f"- {s} 이상: {n}")
    passed = sum(1 for r in rows if fin(r) >= rank["서류합"] and r["진행상태"] != "지원취소")
    failed_doc = sum(1 for r in rows if r["최종 단계"] == "지원완료" and r["진행상태"] == "불합")
    den = passed + failed_doc
    tag = "표본 적음 — 참고용" if den < 5 else "표본 5건 이상"
    print(f"\n서류 통과율: {passed}/{den}" + (f" = {passed / den * 100:.0f}%" if den else " (결과가 확정된 서류 지원 없음)") + f"  [{tag}]")
    fin_final = sum(1 for r in rows if r["진행상태"] == "최종합")
    iv_den = sum(1 for r in rows if fin(r) >= rank["1차면접"] and r["진행상태"] in ("최종합", "불합"))
    tag = "표본 적음 — 참고용" if iv_den < 5 else "표본 5건 이상"
    print(f"면접 통과율: {fin_final}/{iv_den}" + (f" = {fin_final / iv_den * 100:.0f}%" if iv_den else " (결과가 확정된 면접 지원 없음)") + f"  [{tag}]")
    print("평균 진행 기간: 지원완료일을 따로 기록하지 않아(상태일은 현재 상태의 날짜) 계산하지 않는다.")
    decided = [r for r in rows if r["진행상태"] in ("최종합", "불합") and score_of(r["적합도"]) is not None]
    hi = [r for r in decided if score_of(r["적합도"]) >= 80]
    lo = [r for r in decided if score_of(r["적합도"]) < 60]
    if len(hi) >= 3 and len(lo) >= 3:
        print(f"적합도 상위(80+) 합격 {sum(1 for r in hi if r['진행상태'] == '최종합')}/{len(hi)} · 하위(60 미만) {sum(1 for r in lo if r['진행상태'] == '최종합')}/{len(lo)}")
    else:
        print(f"적합도 상·하위 비교: 각 그룹에 확정 건이 3건 이상이어야 표시(지금 상위 {len(hi)} · 하위 {len(lo)})")
    print("\n※ 표본이 적을 때는 숫자만 보고 조언을 꾸며 내지 않는다.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("today"); p.add_argument("--today"); p.add_argument("--write", action="store_true")
    p = sub.add_parser("steps"); p.add_argument("--id"); p.add_argument("--company"); p.add_argument("--job")
    p = sub.add_parser("stats"); p.add_argument("--today")
    a = ap.parse_args()
    return {"today": cmd_today, "steps": cmd_steps, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
