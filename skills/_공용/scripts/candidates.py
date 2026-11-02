#!/usr/bin/env python3
"""공고 후보함 `Areas/취업/공고 후보함.md` 관리와 1차 선별. 볼트 루트에서 실행한다.

쓰는 법:
  python -I -X utf8 candidates.py conditions                 # 검색 조건.md 를 읽어 검색어 목록·제외 조건·N·K 를 JSON으로
  python -I -X utf8 candidates.py ingest <후보.json> [--dry] [--today YYYY-MM-DD]   # 1차 선별 + 중복 제거 + 후보함 기록
  python -I -X utf8 candidates.py expire [--today YYYY-MM-DD]                      # 마감 지난 후보 정리
  python -I -X utf8 candidates.py set-state --id <공고 ID> --state 지원예정|건너뜀|본문확보|점수|새로|마감
  python -I -X utf8 candidates.py set-score --id <공고 ID> --score "78 🟡" [--state 점수] [--deadline YYYY-MM-DD]
  python -I -X utf8 candidates.py list [--json] [--state 새로]
  python -I -X utf8 candidates.py top [--k K]                 # 미리보기 점수를 낼 후보 K건(점수 없음 · 일치 먼저, 모자라면 약함 · 마감 임박순)

후보 JSON(모델이 검색 결과를 정규화한 것): [{"company","title","url","id","deadline"(YYYY-MM-DD 또는 ""),"region","source","query"}]
  `query`(그 후보를 찾은 검색어)를 적으면 상한(N)에 걸릴 때 소스·검색어별로 번갈아 담는다(첫 검색어가 상한을 다 쓰지 않게).
1차 선별은 점수가 아니다(기획 02 §6-④): 마감 지남 · 제목의 필수 경력("n년 이상"·"경력채용"·"경력직"·"[경력]", 제목에 신입이 함께 있으면 남김) · 제목의 석사 이상 필수 ·
  제외 키워드/회사 · 이미 있는 공고 ID(현황표·raw·후보함)를 거른다. 방향은 제목이 연결 직무 키워드와 맞는지로 `일치/약함`만 표시한다.
쓰는 곳: 후보함, `_scan-log.md` 두 파일뿐. raw·wiki·현황표·Notes 는 건드리지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

AREA = Path("Areas/취업")
CAND = AREA / "공고 후보함.md"
COND = AREA / "검색 조건.md"
LOG = AREA / "_scan-log.md"
RAW_POSTINGS = Path("Projects/SecondBrain/raw/채용공고")
COLS = ["상태", "회사", "공고", "방향", "지역", "서류마감(D-n)", "선별 근거", "점수", "링크", "공고 ID", "발견일"]
STATES = ["새로", "본문확보", "점수", "지원예정", "건너뜀", "마감"]
H_MAIN, H_PAST = "## 후보", "## 후보함_지난"

HEAD = """# 공고 후보함

> `/job-scan`이 채우고 `/job-flow`가 `지원예정`·`건너뜀`만 바꾼다. 아직 고르지 않은 공고의 목록이며 현황표와 분리돼 있다.
> 상태: `새로` → `본문확보` → `점수` → `지원예정`(사용자가 말했을 때) / `건너뜀`(사용자가 뺀 것) / `마감`(정리). 마감이 지난 후보는 일주일 뒤 `후보함_지난`으로 접는다(삭제 없음).

"""
TBL = "| " + " | ".join(COLS) + " |\n|" + "---|" * len(COLS) + "\n"

EXP_REQ = re.compile(r"(\d+)\s*년\s*(이상|↑|차\s*이상|~)|경력\s*(필수|\d+\s*년)|\b(\d+)\+\s*years"
                     r"|경력\s*(채용|직|사원|자\s*(채용|모집))|[\[\(【<]\s*경력\s*[\]\)】>]", re.I)   # 제목의 "경력채용·경력직·[경력]"
EXP_OK = re.compile(r"(신입|경력\s*무관|무관|인턴|신입\s*가능|경력자?\s*우대|\d+\s*년\s*(이하|미만))")
MASTER_REQ = re.compile(r"(석사|박사|석[·ㆍ]박사)\s*(이상\s*)?(필수|만\s*지원)|(석사|박사)\s*이상\s*(?!우대)(?!또는)")
MASTER_OK = re.compile(r"(우대|또는|가능)")


def table_rows(text, header_key):
    """## 섹션 아래의 표를 [dict] 로"""
    if header_key not in text:
        return [], None
    start = text.index(header_key)
    nxt = re.search(r"^## ", text[start + len(header_key):], flags=re.M)
    end = start + len(header_key) + (nxt.start() if nxt else len(text))
    seg = text[start:end]
    cols, rows = None, []
    for ln in seg.splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        c = J.split_row(ln)
        if cols is None:
            cols = c
            continue
        if re.match(r"^[\s:-]+$", "".join(c)):
            continue
        rows.append({k: (c[i] if i < len(c) else "") for i, k in enumerate(cols)})
    return rows, (start, end)


def load():
    if not CAND.exists():
        return [], []
    text = CAND.read_text(encoding="utf-8")
    main, _ = table_rows(text, H_MAIN + "\n")
    past, _ = table_rows(text, H_PAST)
    return main, past


def render_row(d):
    return "| " + " | ".join(J.cell(d.get(c, "")) for c in COLS) + " |"


def save(main, past):
    if CAND.exists():
        J.backup_file(CAND)
    AREA.mkdir(parents=True, exist_ok=True)
    text = HEAD + H_MAIN + "\n\n" + TBL + "\n".join(render_row(d) for d in main) + ("\n" if main else "") + "\n" \
        + H_PAST + "\n\n" + TBL + "\n".join(render_row(d) for d in past) + ("\n" if past else "")
    CAND.write_text(text, encoding="utf-8", newline="\n")


def read_conditions():
    out = {"queries": [], "exclude_keywords": [], "exclude_companies": [], "N": 20, "K": 3, "public": "끔", "regions": "", "types": ""}
    if not COND.exists():
        return out
    text = COND.read_text(encoding="utf-8")
    section = ""
    for ln in text.splitlines():
        if ln.startswith("## "):
            section = ln[3:].strip()
            continue
        if not ln.lstrip().startswith("|"):
            continue
        c = J.split_row(ln)
        if re.match(r"^[\s:-]+$", "".join(c)) or len(c) < 2:
            continue
        if section.startswith("키워드"):
            if c[0] in ("키워드",):
                continue
            for q in re.split(r"\s*/\s*", c[0]):
                if q.strip():
                    out["queries"].append({"query": q.strip(), "direction": c[1] if len(c) > 1 else ""})
        elif section.startswith("조건"):
            k, v = c[0], c[1]
            if "제외" in k:
                parts = [x.strip() for x in re.split(r"[,/]", v) if x.strip() and "없음" not in x]
                out["exclude_keywords"] += parts
                out["exclude_companies"] += parts
            elif "후보 최대" in k:
                m = re.search(r"\d+", v)
                out["N"] = int(m.group()) if m else 20
            elif "분석 최대" in k:
                m = re.search(r"\d+", v)
                out["K"] = int(m.group()) if m else 3
            elif "공공기관" in k:
                out["public"] = v.strip()
            elif k == "지역":
                out["regions"] = v
            elif k == "유형":
                out["types"] = v
    return out


def known_ids():
    ids = set()
    t = J.Table()
    if t.head_idx is not None and not t.problems():
        ids |= {d["공고 ID"].strip() for d in t.as_dicts() if d["공고 ID"] not in ("", "—")}
    main, past = load()
    ids |= {d["공고 ID"].strip() for d in main + past if d["공고 ID"]}
    raw_text = ""
    if RAW_POSTINGS.exists():
        for f in RAW_POSTINGS.glob("*.md"):
            try:
                raw_text += f.read_text(encoding="utf-8")[:3000] + "\n"
            except OSError:
                pass
    return ids, raw_text


def id_in_raw(cid, raw_text):
    if not cid:
        return False
    num = cid.split(":", 1)[-1]
    site = cid.split(":", 1)[0]
    pat = {"jobkorea": r"(GI_Read/|Gno=|jobkorea:)", "saramin": r"(rec_idx=|saramin:)", "wanted": r"(/wd/|wanted:)"}.get(site, r"(" + re.escape(site) + r":)")
    return re.search(r"(출처|공고 ID):.*" + pat + re.escape(num) + r"(\D|$)", raw_text) is not None


def d_label(d, today):
    n = (d - today).days
    return f"D-{n}" if n > 0 else ("D-day" if n == 0 else f"D+{-n}")


def direction_of(title, queries):
    low = title.lower()
    for q in queries:
        words = [w for w in re.split(r"\s+", q["query"].lower()) if w]
        if words and all(w in low for w in words) or q["query"].lower() in low:
            return f"일치({q['direction']})" if q["direction"] else "일치"
    # 낱말 일부만 겹치면 약함 판정 대신 '약함'
    return "약함"


def cmd_conditions(a):
    print(json.dumps(read_conditions(), ensure_ascii=False, indent=1))
    return 0


def log_line(msg):
    AREA.mkdir(parents=True, exist_ok=True)
    now = J.datetime.now(J.KST).strftime("%Y-%m-%d %H:%M")
    if not LOG.exists():
        LOG.write_text("# 스캔 로그\n\n> `/job-scan` 실행 기록(실행 시각 KST). 마감까지 남은 일수는 실행 시각 기준이다.\n\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"- {now} · {msg}\n")


def interleave(items):
    """상한(N)이 첫 검색어 결과로 다 차 버리지 않게, 후보를 (소스, 검색어)별로 번갈아 한 건씩 놓는다. 같은 입력이면 같은 순서.
    후보에 `query` 가 없으면(또는 한 묶음뿐이면) 받은 순서를 그대로 쓴다."""
    groups, order = {}, []
    for it in items:
        key = (it.get("source", ""), it.get("query", ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(it)
    if len(order) < 2:
        return items
    out = []
    for i in range(max(len(g) for g in groups.values())):
        for key in order:
            if i < len(groups[key]):
                out.append(groups[key][i])
    return out


def cmd_ingest(a):
    today = J.parse_date(a.today) if a.today else J.today_kst()
    items = interleave(json.loads(Path(a.file).read_text(encoding="utf-8")))
    cond = read_conditions()
    ids, raw_text = known_ids()
    main, past = load()
    seen = set(ids)
    added, stats = [], {"중복": 0, "마감 지남": 0, "경력 제외": 0, "학력 제외": 0, "제외 조건": 0, "상한 초과": 0}
    same_firm = []
    for it in items:
        cid = (it.get("id") or "").strip()
        title, comp = it.get("title", ""), it.get("company", "")
        if (cid and (cid in seen or id_in_raw(cid, raw_text))):
            stats["중복"] += 1
            continue
        dl = None
        if it.get("deadline"):
            try:
                dl = J.parse_date(it["deadline"])
            except ValueError:
                dl = None
        if dl and dl < today:
            stats["마감 지남"] += 1
            continue
        if EXP_REQ.search(title) and not EXP_OK.search(title):
            stats["경력 제외"] += 1
            continue
        if MASTER_REQ.search(title) and not MASTER_OK.search(title):
            stats["학력 제외"] += 1
            continue
        if any(k and (k in title or k in comp) for k in cond["exclude_keywords"]) or comp in cond["exclude_companies"]:
            stats["제외 조건"] += 1
            continue
        if len(added) >= cond["N"]:
            stats["상한 초과"] += 1
            continue
        why = []
        if dl is None:
            why.append("마감 여부 미확인")
        if it.get("source"):
            why.append(f"소스 {it['source']}")
        d = {"상태": "새로", "회사": comp, "공고": title, "방향": direction_of(title, cond["queries"]), "지역": it.get("region", "") or "미기재",
             "서류마감(D-n)": (f"{dl.isoformat()} ({d_label(dl, today)})" if dl else "마감일 미정"), "선별 근거": " · ".join(why) or "제목·태그 기준",
             "점수": "", "링크": it.get("url", ""), "공고 ID": cid or "—", "발견일": today.isoformat()}
        for ex in main + past + added:
            if ex["회사"] == comp and ex["서류마감(D-n)"][:10] == d["서류마감(D-n)"][:10] and dl is not None and ex["공고 ID"] != d["공고 ID"]:
                same_firm.append(f"{comp} {title} ↔ {ex['공고']}")
        added.append(d)
        if cid:
            seen.add(cid)
    res = {"added": len(added), "stats": stats, "same_posting_maybe": same_firm, "more_exists": stats["상한 초과"] > 0,
           "rows": [{"id": d["공고 ID"], "company": d["회사"], "title": d["공고"], "direction": d["방향"], "deadline": d["서류마감(D-n)"]} for d in added]}
    if a.dry:
        res["dry"] = True
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if added:
        save(added + main, past)
    log_line(f"수집 후보 {len(items)}건 → 추가 {len(added)} · 중복 {stats['중복']} · 마감 지남 {stats['마감 지남']} · 경력 제외 {stats['경력 제외']} · 학력 제외 {stats['학력 제외']} · 제외 조건 {stats['제외 조건']}" + (" · 더 있음(상한 초과)" if res["more_exists"] else ""))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def cmd_expire(a):
    today = J.parse_date(a.today) if a.today else J.today_kst()
    main, past = load()
    moved, marked = 0, 0
    keep = []
    for d in main:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", d["서류마감(D-n)"])
        if m and d["상태"] in ("새로", "본문확보", "점수"):
            dl = J.parse_date(m.group(1))
            if dl < today:
                d["상태"] = "마감"
                marked += 1
            else:
                d["서류마감(D-n)"] = f"{dl.isoformat()} ({d_label(dl, today)})"
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", d["서류마감(D-n)"])
        if d["상태"] == "마감" and m and (today - J.parse_date(m.group(1))).days >= 7:
            past.append(d)
            moved += 1
        else:
            keep.append(d)
    if marked or moved:
        save(keep, past)
    print(f"마감으로 표시 {marked}건 · 후보함_지난으로 접음 {moved}건")
    return 0


def cmd_set_state(a):
    if a.state not in STATES:
        J.die(f"상태는 {STATES} 중 하나", 2)
    main, past = load()
    hit = [d for d in main if d["공고 ID"] == a.id]
    if not hit:
        print("그 공고 ID 후보가 없다")
        return 1
    hit[0]["상태"] = a.state
    save(main, past)
    print(f"{hit[0]['회사']} → {a.state}")
    return 0


def cmd_set_score(a):
    main, past = load()
    hit = [d for d in main if d["공고 ID"] == a.id]
    if not hit:
        print("그 공고 ID 후보가 없다")
        return 1
    hit[0]["점수"] = a.score
    hit[0]["상태"] = a.state or "점수"
    if a.deadline:                      # 본문에서 확인한 마감일(목록에는 없던 것). 잘못된 형식이면 고치지 않는다
        try:
            dl = J.parse_date(a.deadline)
            hit[0]["서류마감(D-n)"] = f"{dl.isoformat()} ({d_label(dl, J.today_kst())})"
            hit[0]["선별 근거"] = hit[0]["선별 근거"].replace("마감 여부 미확인", "마감 본문 확인").strip(" ·")
        except ValueError:
            print(f"마감일 형식이 아님(무시): {a.deadline}")
    save(main, past)
    print(f"{hit[0]['회사']} 점수 {a.score}")
    return 0


def cmd_top(a):
    """미리보기 점수를 낼 후보 K건: 상태 새로·본문확보 · 점수 없음. 방향 `일치`를 먼저, 모자라면 `약함`으로 채운다
    (약함도 사이트 검색에 걸린 공고다 — 제목에 검색어가 그대로 없을 뿐). 각 묶음 안에서는 마감 임박순, 마감 미정은 최근 발견순."""
    k = a.k if a.k is not None else read_conditions()["K"]
    main, _ = load()
    pool = [d for d in main if d["상태"] in ("새로", "본문확보") and not d["점수"].strip()]

    def deadline(d):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", d["서류마감(D-n)"])
        return J.parse_date(m.group(1)) if m else None
    dated = sorted((d for d in pool if deadline(d)), key=lambda d: (deadline(d), d["공고 ID"]))          # 마감 있는 것 먼저(임박순)
    undated = sorted((d for d in pool if not deadline(d)), key=lambda d: (d["발견일"], d["공고 ID"]), reverse=True)   # 미정은 최근 발견순
    pool = dated + undated
    pool = [d for d in pool if d["방향"].startswith("일치")] + [d for d in pool if not d["방향"].startswith("일치")]
    print(json.dumps([{"id": d["공고 ID"], "company": d["회사"], "title": d["공고"], "url": d["링크"], "deadline": d["서류마감(D-n)"],
                       "region": d["지역"]} for d in pool[:k]], ensure_ascii=False, indent=1))
    return 0


def cmd_list(a):
    main, past = load()
    rows = [d for d in main if not a.state or d["상태"] == a.state]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for i, d in enumerate(rows, 1):
            print(f"{i}. [{d['상태']}] {d['회사']} · {d['공고']} · {d['방향']} · {d['서류마감(D-n)']} · 점수 {d['점수'] or '—'} · {d['공고 ID']}")
        if not rows:
            print("(후보 없음)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("conditions")
    p = sub.add_parser("ingest"); p.add_argument("file"); p.add_argument("--dry", action="store_true"); p.add_argument("--today")
    p = sub.add_parser("expire"); p.add_argument("--today")
    p = sub.add_parser("set-state"); p.add_argument("--id", required=True); p.add_argument("--state", required=True)
    p = sub.add_parser("set-score"); p.add_argument("--id", required=True); p.add_argument("--score", required=True); p.add_argument("--state"); p.add_argument("--deadline")
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true"); p.add_argument("--state")
    p = sub.add_parser("top"); p.add_argument("--k", type=int)
    a = ap.parse_args()
    return {"conditions": cmd_conditions, "ingest": cmd_ingest, "expire": cmd_expire, "set-state": cmd_set_state,
            "set-score": cmd_set_score, "list": cmd_list, "top": cmd_top}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
