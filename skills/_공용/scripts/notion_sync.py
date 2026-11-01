#!/usr/bin/env python3
"""Notion 반영의 '계산' 부분. 볼트 루트에서 실행한다. Notion을 직접 부르지 않는다(쓰기는 모델이 Notion 도구로, 이 스크립트는 무엇을 올릴지 정한다).

쓰는 법:
  python -I -X utf8 notion_sync.py schema [--table 지원현황]          # 표 6개의 기대 칸(이름·종류·선택지) — 새 볼트에서 표를 만들거나 실제 표와 대조할 때
  python -I -X utf8 notion_sync.py status                              # 설정(on/off)·연결된 표·매핑 수·밀린 반영 수 (JSON)
  python -I -X utf8 notion_sync.py link --table 지원현황 --ds collection://…   [--hub <상위 페이지 주소>]
  python -I -X utf8 notion_sync.py plan --table 지원현황|수집공고|경험정리 [--key K] [--min-score N] [--today YYYY-MM-DD]
        # 볼트에서 올릴 줄을 만들고 매핑과 비교해 action(create/update/same)을 붙인다
  python -I -X utf8 notion_sync.py check --table 회사조사|자소서|면접연습|… --key K --props 값.json [--today …]
        # 모델이 만든 칸 값을 선택지·형식으로 검사하고 action 을 붙인다(판단이 들어가는 표용)
  python -I -X utf8 notion_sync.py record --table T --key K --page <노션 페이지 주소> --hash H
  python -I -X utf8 notion_sync.py lookup --table T --key K            # 매핑에서 페이지 주소
  python -I -X utf8 notion_sync.py pending add --table T --key K --why 이유 | pending list | pending clear [--table T --key K]
  python -I -X utf8 notion_sync.py diff --notion 노션행.json              # 노션에서 가져온 지원 현황 행과 볼트 현황표 비교(고르지 않음)

규칙(기획 06 + 2026-11-02 사용자 결정 "표 6개로 나눔"):
  - 볼트 → Notion 한 방향이 기본. Notion → 볼트는 diff 로 차이만 보여 준다(반영은 /job-flow 가 사용자 확인 뒤).
  - 올리지 않는 것: 현황표 `메모`, 점수 계산 내역, 근거 표, 방어 맵, 답변 전문, 인적사항, raw 원본.
  - 연결 정보(`_notion-연결.md`)·매핑(`_notion-매핑.md`)·밀린 반영(`_notion-대기.md`)은 볼트 `Areas/취업/`에만 둔다(저장소에 넣지 않는다).
  - 밀린 반영에는 내용을 복사하지 않고 "무엇을"만 적는다.
  - 이 스크립트가 쓰는 파일은 위 세 파일뿐이다.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

AREA = Path("Areas/취업")
SETTING = AREA / "설정.md"
F_LINK = AREA / "_notion-연결.md"
F_MAP = AREA / "_notion-매핑.md"
F_PEND = AREA / "_notion-대기.md"
CAND = AREA / "공고 후보함.md"
WIKI = Path("Projects/SecondBrain/wiki")
RAW_POSTINGS = Path("Projects/SecondBrain/raw/채용공고")

SKIP_HASH = {"date:볼트 반영일:start"}       # 날마다 바뀌는 값은 '같음' 판정에서 뺀다
CARD_TAGS = ["제조AI", "설비데이터", "예지보전", "CBM", "시계열예측", "ML/DL", "LLM응용", "데이터파이프라인", "프론트/웹"]

# 표 이름 → 칸 정의. 종류: title/text/select/multi/date/number/percent/url/relation
TABLES = {
    "지원현황": {"name": "📋 지원 현황", "title": "기업명", "props": {
        "기업명": ("title",), "직무": ("select", J.JOBS), "진행상태": ("select", J.STATES), "유형": ("select", J.TYPES),
        "서류마감": ("date",), "적합도": ("number",), "적합도 등급": ("select", ["🟢", "🟡", "🔴", "미산출"]),
        "지역": ("select", J.REGIONS), "공고 링크": ("url",), "공고 ID": ("text",), "채널": ("text",), "상태일": ("date",),
        "최종 단계": ("text",), "볼트 반영일": ("date",)}},
    "수집공고": {"name": "🔎 수집 공고", "title": "공고 제목", "props": {
        "공고 제목": ("title",), "회사": ("text",), "링크": ("url",), "마감": ("date",), "미리보기 점수": ("number",),
        "출처": ("select", ["잡코리아", "사람인", "기타"]), "수집일": ("date",), "상태": ("select", ["새로", "지원예정", "건너뜀", "마감"]),
        "공고 ID": ("text",)}},
    "회사조사": {"name": "🏢 회사 조사", "title": "회사", "props": {
        "회사": ("title",), "조사일": ("date",), "지원 판단": ("select", ["지원 권장", "조건부 지원", "신중 검토"]),
        "키워드 반영 가능률": ("percent",), "지원 현황": ("relation", "지원현황"), "볼트 반영일": ("date",)}},
    "자소서": {"name": "✍️ 자소서", "title": "제목", "props": {
        "제목": ("title",), "상태": ("select", ["작성중", "완료"]), "키워드 반영률": ("percent",), "문항 수": ("number",),
        "지원 현황": ("relation", "지원현황"), "볼트 반영일": ("date",)}},
    "면접연습": {"name": "🎤 면접 연습", "title": "제목", "props": {
        "제목": ("title",), "날짜": ("date",), "종류": ("select", ["인성", "기술", "컬처핏", "AI 역량검사", "실전 후기"]),
        "통과율": ("percent",), "반복 약점": ("text",), "지원 현황": ("relation", "지원현황"), "볼트 반영일": ("date",)}},
    "경험정리": {"name": "🧩 경험 정리", "title": "카드 제목", "props": {
        "카드 제목": ("title",), "카드 ID": ("text",), "프로젝트": ("text",), "기간": ("text",), "직무 태그": ("multi", CARD_TAGS),
        "한 줄 요약": ("text",), "근거 상태": ("select", ["근거 있음", "일부 확인 필요"]), "볼트 반영일": ("date",)}},
}
SCAN_STATE = {"새로": "새로", "본문확보": "새로", "점수": "새로", "지원예정": "지원예정", "건너뜀": "건너뜀", "마감": "마감"}


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


# ---------- 볼트의 작은 표 파일 ----------
def read_md_table(path):
    if not path.exists():
        return []
    cols, rows = None, []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        c = J.split_row(ln)
        if cols is None:
            cols = c
            continue
        if re.match(r"^[\s:-]+$", "".join(c)):
            continue
        rows.append({k: (c[i] if i < len(c) else "") for i, k in enumerate(cols)})
    return rows


def write_md_table(path, head, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    L = [head, "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    L += ["| " + " | ".join(J.cell(r.get(k, "")) for k in cols) + " |" for r in rows]
    path.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


MAP_COLS = ["표", "키", "노션 페이지", "올린 날", "지문"]
MAP_HEAD = "# Notion 매핑\n\n> notion_sync.py 가 쓴다. 볼트의 한 건(키)과 Notion 페이지의 짝. 지워져도 다음 반영 때 키로 다시 찾는다(중복을 만들지 않게 먼저 확인)."
LINK_COLS = ["표", "데이터 소스"]
LINK_HEAD = "# Notion 연결\n\n> notion_sync.py link 가 쓴다. 이 볼트의 내용을 올릴 Notion 표. 개인 Notion 주소라 저장소에 넣지 않는다."
PEND_COLS = ["날짜", "표", "키", "이유"]
PEND_HEAD = "# Notion 밀린 반영\n\n> `notion: on`인데 연결이 안 돼 못 올린 건. 내용은 복사하지 않는다(볼트가 원본). 다음 연결 때 \"밀린 반영 N건\"으로 묻는다."


def notion_setting():
    for r in read_md_table(SETTING):
        k = (r.get("항목") or next(iter(r.values()), "")).strip()
        if k == "notion":
            return (r.get("값") or "").strip() or "off"
    return "off"


def links():
    hub = ""
    if F_LINK.exists():
        m = re.search(r"^상위 페이지:\s*(\S+)", F_LINK.read_text(encoding="utf-8"), flags=re.M)
        hub = m.group(1) if m else ""
    return {r["표"]: r["데이터 소스"] for r in read_md_table(F_LINK) if r.get("표")}, hub


def mapping():
    return {(r["표"], r["키"]): r for r in read_md_table(F_MAP)}


def props_hash(props):
    core = {k: v for k, v in props.items() if k not in SKIP_HASH}
    return hashlib.sha1(json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


# ---------- 값 정리 ----------
def fit_split(fit):
    """`74 🟡 🚫석사 이상 필수` → (74, '🟡'), `미산출` → (None, '미산출')"""
    f = (fit or "").strip()
    if not f:
        return None, None
    if f.startswith("미산출"):
        return None, "미산출"
    m = re.match(r"^(\d{1,3})\s*(🟢|🟡|🔴)?", f)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def iso(s):
    try:
        return J.parse_date(s.strip()).isoformat() if s and s.strip() else None
    except ValueError:
        return None


def posting_url(pid):
    """공고 ID → 원문 주소. raw 의 `출처:` 줄을 먼저 보고, 없으면 ID 형식으로 만든다."""
    pid = (pid or "").strip()
    if not pid or pid == "—":
        return None
    if RAW_POSTINGS.exists():
        for f in RAW_POSTINGS.glob("*.md"):
            try:
                head = f.read_text(encoding="utf-8").splitlines()[:20]
            except OSError:
                continue
            if any(re.search(r"공고 ID:\s*" + re.escape(pid) + r"(\s|$|\))", ln) for ln in head):
                for ln in head:
                    m = re.search(r"출처:\s*(https?://\S+)", ln)
                    if m:
                        return m.group(1).rstrip(")>")
    site, _, n = pid.partition(":")
    return {"jobkorea": f"https://www.jobkorea.co.kr/Recruit/GI_Read/{n}",
            "saramin": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={n}",
            "wanted": f"https://www.wanted.co.kr/wd/{n}"}.get(site) or (f"https://{n}" if site == "url" else None)


def status_key(r):
    pid = r["공고 ID"].strip()
    return pid if pid and pid != "—" else f"{r['기업명']}|{r['직무']}"


def put(props, k, v):
    if v is None or v == "" or v == []:
        return           # 비어 있음 = 모름. Notion 값을 지우지 않는다(기획 06 §6-3)
    props[k] = v


def put_date(props, name, v):
    if v:
        props[f"date:{name}:start"] = v
        props[f"date:{name}:is_datetime"] = 0


# ---------- 볼트 → 줄 ----------
def rows_status(today):
    t = J.Table()
    if t.head_idx is None:
        return []
    if t.problems():
        die("현황표 형식 문제: " + "; ".join(t.problems()) + " — 먼저 /job-flow 로 고친다", 3)
    items = []
    for r in t.as_dicts():
        p = {}
        put(p, "기업명", r["기업명"])
        put(p, "직무", r["직무"] if r["직무"] in J.JOBS else None)
        put(p, "진행상태", r["진행상태"] if r["진행상태"] in J.STATES else None)
        put(p, "유형", r["유형"] if r["유형"] in J.TYPES else None)
        put_date(p, "서류마감", iso(r["서류마감"]))
        sc, grade = fit_split(r["적합도"])
        put(p, "적합도", sc)
        put(p, "적합도 등급", grade)
        put(p, "지역", r["지역"] if r["지역"] in J.REGIONS else None)
        put(p, "공고 링크", posting_url(r["공고 ID"]))
        put(p, "공고 ID", r["공고 ID"] if r["공고 ID"] not in ("", "—") else None)
        put(p, "채널", r["채널"])
        put_date(p, "상태일", iso(r["상태일"]))
        put(p, "최종 단계", r["최종 단계"])
        put_date(p, "볼트 반영일", today.isoformat())
        items.append({"key": status_key(r), "props": p})
    return items


def rows_candidates(today, min_score):
    if not CAND.exists():
        return []
    items = []
    for r in read_md_table_all(CAND):
        st = r.get("상태", "")
        sc, _ = fit_split(r.get("점수", ""))
        if min_score is not None and (sc is None or sc < min_score):
            continue
        pid = r.get("공고 ID", "").strip()
        link = (r.get("링크", "").strip() or posting_url(pid) or "").strip("<>")
        key = pid if pid and pid != "—" else link
        if not key:
            continue
        p = {}
        put(p, "공고 제목", r.get("공고", "").strip() or r.get("회사", ""))
        put(p, "회사", r.get("회사", ""))
        put(p, "링크", link if link.startswith("http") else None)
        dl = re.match(r"(\d{4}-\d{2}-\d{2})", r.get("서류마감(D-n)", "").strip())
        put_date(p, "마감", dl.group(1) if dl else None)
        put(p, "미리보기 점수", sc)
        src = "잡코리아" if pid.startswith("jobkorea:") else ("사람인" if pid.startswith("saramin:") else "기타")
        put(p, "출처", src)
        put_date(p, "수집일", iso(r.get("발견일", "")))
        put(p, "상태", SCAN_STATE.get(st))
        put(p, "공고 ID", pid if pid and pid != "—" else None)
        items.append({"key": key, "props": p})
    return items


def read_md_table_all(path):
    """머리줄이 여러 번 나오는 파일(후보함: 후보 + 후보함_지난)을 모두 읽는다"""
    cols, rows = None, []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        c = J.split_row(ln)
        if "상태" in c and "회사" in c:
            cols = c
            continue
        if cols is None or re.match(r"^[\s:-]+$", "".join(c)):
            continue
        rows.append({k: (c[i] if i < len(c) else "") for i, k in enumerate(cols)})
    return rows


CARD_HEAD = re.compile(r"^###\s+(exp-\d{8}-\d{2})\s+(.*)$")
FIELD = re.compile(r"^-\s+([a-z_]+):\s*(.*)$")


def rows_cards(today):
    items = []
    if not WIKI.exists():
        return items
    for f in sorted(WIKI.glob("내경험_*.md")):
        if f.name == "내경험_자료목록.md":
            continue
        text = f.read_text(encoding="utf-8")
        h1 = re.search(r"^#\s+(.+)$", text, flags=re.M)
        project = h1.group(1).strip() if h1 else f.stem[len("내경험_"):]
        cur = None
        cards = []
        for ln in text.splitlines():
            m = CARD_HEAD.match(ln)
            if m:
                cur = {"id": m.group(1), "head": m.group(2).strip(), "f": {}}
                cards.append(cur)
                continue
            if ln.startswith("#"):
                cur = None
                continue
            if cur is not None:
                fm = FIELD.match(ln)
                if fm and fm.group(1) not in cur["f"]:
                    cur["f"][fm.group(1)] = fm.group(2).strip()
        for c in cards:
            f_ = c["f"]
            if f_.get("origin", "") == "받은교재":
                continue
            tags = [t.strip() for t in re.sub(r"[\[\]]", "", f_.get("job_link_tags", "")).split(",") if t.strip() in CARD_TAGS]
            fact = f_.get("fact_status", "")
            p = {}
            put(p, "카드 제목", c["head"])
            put(p, "카드 ID", c["id"])
            put(p, "프로젝트", project)
            put(p, "기간", f_.get("period") or None)
            put(p, "직무 태그", tags)
            put(p, "한 줄 요약", f_.get("title"))
            put(p, "근거 상태", "근거 있음" if fact == "자료확인" else ("일부 확인 필요" if fact else None))
            put_date(p, "볼트 반영일", today.isoformat())
            items.append({"key": c["id"], "props": p})
    return items


# ---------- 검사 ----------
def validate(table, props):
    spec = TABLES[table]["props"]
    errs = []
    for k, v in props.items():
        base = k.split(":")[1] if k.startswith("date:") else k
        if base not in spec:
            errs.append(f"`{base}`는 {TABLES[table]['name']}의 칸이 아님")
            continue
        kind = spec[base]
        if kind[0] == "select" and v not in kind[1]:
            errs.append(f"`{base}` 값 `{v}`가 선택지 밖")
        elif kind[0] == "multi" and (not isinstance(v, list) or any(x not in kind[1] for x in v)):
            errs.append(f"`{base}` 값 {v}에 선택지 밖 낱말")
        elif kind[0] in ("number", "percent") and not isinstance(v, (int, float)):
            errs.append(f"`{base}`는 숫자여야 함")
        elif kind[0] == "percent" and not (0 <= v <= 1):
            errs.append(f"`{base}`는 0~1 사이(예: 0.72)")
        elif kind[0] == "date" and k.endswith(":start") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            errs.append(f"`{base}` 날짜 형식(YYYY-MM-DD)")
        elif kind[0] == "url" and not str(v).startswith("http"):
            errs.append(f"`{base}`는 http 주소")
    if TABLES[table]["title"] not in props:
        errs.append(f"제목 칸 `{TABLES[table]['title']}`이 비어 있음")
    return errs


def attach_action(table, items, maps):
    for it in items:
        it["hash"] = props_hash(it["props"])
        m = maps.get((table, it["key"]))
        if not m:
            it["action"] = "create"
        else:
            it["page"] = m["노션 페이지"]
            it["action"] = "same" if m["지문"] == it["hash"] else "update"
    return items


# ---------- 명령 ----------
def cmd_schema(a):
    tabs = [a.table] if a.table else list(TABLES)
    res = {}
    for t in tabs:
        spec = TABLES[t]
        res[t] = {"name": spec["name"], "title": spec["title"],
                  "props": {k: {"type": v[0], **({"options": v[1]} if v[0] in ("select", "multi") else {}),
                                **({"relation_to": v[1]} if v[0] == "relation" else {})} for k, v in spec["props"].items()}}
    out(res)
    return 0


def cmd_status(a):
    lk, hub = links()
    maps = mapping()
    pend = read_md_table(F_PEND)
    out({"notion": notion_setting(), "hub": hub or None, "linked": lk,
         "missing_tables": [t for t in TABLES if t not in lk],
         "mapped": {t: sum(1 for (tt, _) in maps if tt == t) for t in TABLES},
         "pending": len(pend), "first_sync_done": bool(maps)})
    return 0


def cmd_link(a):
    if a.table not in TABLES:
        die(f"표 이름은 {', '.join(TABLES)} 중 하나")
    if not a.ds.startswith("collection://"):
        die("데이터 소스는 collection://… 형식(Notion fetch 결과의 <data-source url>)")
    rows = [r for r in read_md_table(F_LINK) if r.get("표") != a.table] + [{"표": a.table, "데이터 소스": a.ds}]
    _, hub = links()
    hub = a.hub or hub
    head = LINK_HEAD + (f"\n\n상위 페이지: {hub}" if hub else "")
    write_md_table(F_LINK, head, LINK_COLS, sorted(rows, key=lambda r: list(TABLES).index(r["표"])))
    print(f"연결 기록: {a.table} → {a.ds}")
    return 0


def cmd_plan(a):
    today = J.parse_date(a.today) if a.today else J.today_kst()
    if a.table == "지원현황":
        items = rows_status(today)
    elif a.table == "수집공고":
        items = rows_candidates(today, a.min_score)
    elif a.table == "경험정리":
        items = rows_cards(today)
    else:
        die("plan 은 지원현황·수집공고·경험정리만. 판단이 들어가는 표는 check 를 쓴다")
    if a.key:
        items = [i for i in items if i["key"] == a.key]
    bad = [(i["key"], e) for i in items for e in validate(a.table, i["props"])]
    items = attach_action(a.table, items, mapping())
    lk, _ = links()
    out({"table": a.table, "data_source": lk.get(a.table), "counts": {x: sum(1 for i in items if i["action"] == x) for x in ("create", "update", "same")},
         "problems": [f"{k}: {e}" for k, e in bad], "items": items})
    return 0


def cmd_check(a):
    if a.table not in TABLES:
        die(f"표 이름은 {', '.join(TABLES)} 중 하나")
    try:
        props = json.loads(Path(a.props).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"값 JSON을 읽지 못함: {e}")
    today = J.parse_date(a.today) if a.today else J.today_kst()
    if "볼트 반영일" in TABLES[a.table]["props"]:
        put_date(props, "볼트 반영일", today.isoformat())
    rel = [k for k, v in TABLES[a.table]["props"].items() if v[0] == "relation"]
    maps = mapping()
    notes = []
    for k in rel:
        if k in props and isinstance(props[k], str):       # 키를 주면 매핑에서 페이지 주소로 바꾼다
            m = maps.get((TABLES[a.table]["props"][k][1], props[k]))
            if m:
                props[k] = [m["노션 페이지"]]
            else:
                notes.append(f"`{k}` 연결 대상 `{props[k]}`가 아직 Notion에 없음 — 연결 없이 올리거나 지원 현황을 먼저 올린다")
                del props[k]
    errs = validate(a.table, {k: v for k, v in props.items() if k not in rel})
    item = attach_action(a.table, [{"key": a.key, "props": props}], maps)[0]
    lk, _ = links()
    out({"table": a.table, "data_source": lk.get(a.table), "ok": not errs, "problems": errs, "notes": notes, **item})
    return 0 if not errs else 4


def cmd_record(a):
    if a.table not in TABLES:
        die(f"표 이름은 {', '.join(TABLES)} 중 하나")
    if not re.match(r"^https://(www\.|app\.)?notion\.(so|com)/", a.page):
        die("Notion 페이지 주소가 아님")
    a.page = a.page.split("?")[0].split("#")[0]          # `?pvs=…` 같은 보기 값은 떼고 저장
    rows = [r for r in read_md_table(F_MAP) if not (r.get("표") == a.table and r.get("키") == a.key)]
    rows.append({"표": a.table, "키": a.key, "노션 페이지": a.page, "올린 날": J.today_kst().isoformat(), "지문": a.hash})
    write_md_table(F_MAP, MAP_HEAD, MAP_COLS, rows)
    # 올렸으면 밀린 반영에서 지운다
    pend = read_md_table(F_PEND)
    left = [r for r in pend if not (r.get("표") == a.table and r.get("키") == a.key)]
    if len(left) != len(pend):
        write_md_table(F_PEND, PEND_HEAD, PEND_COLS, left)
    print(f"매핑 기록: {a.table} · {a.key}")
    return 0


def cmd_lookup(a):
    m = mapping().get((a.table, a.key))
    if not m:
        print("없음")
        return 1
    print(m["노션 페이지"])
    return 0


def cmd_pending(a):
    rows = read_md_table(F_PEND)
    if a.op == "list":
        out({"pending": rows})
        return 0
    if a.op == "add":
        if not (a.table and a.key and a.why):
            die("pending add 는 --table --key --why 모두 필요")
        if a.table not in TABLES:
            die(f"표 이름은 {', '.join(TABLES)} 중 하나")
        if any(r.get("표") == a.table and r.get("키") == a.key for r in rows):
            print("이미 밀린 반영 목록에 있음")
            return 0
        rows.append({"날짜": J.today_kst().isoformat(), "표": a.table, "키": a.key, "이유": a.why[:80]})
    else:   # clear
        rows = [r for r in rows if a.table and not (r.get("표") == a.table and (not a.key or r.get("키") == a.key))]
    write_md_table(F_PEND, PEND_HEAD, PEND_COLS, rows)
    print(f"밀린 반영 {len(rows)}건")
    return 0


def cmd_diff(a):
    try:
        notion_rows = json.loads(Path(a.notion).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"노션 행 JSON을 읽지 못함: {e}")
    t = J.Table()
    vault = {status_key(r): r for r in t.as_dicts()} if t.head_idx is not None else {}
    by_company = {}
    for r in vault.values():
        by_company.setdefault(r["기업명"], []).append(r)
    diffs, only_notion = [], []
    for n in notion_rows:
        pid = (n.get("공고 ID") or "").strip()
        v = vault.get(pid) if pid else None
        if v is None:
            cand = by_company.get(n.get("기업명", ""), [])
            cand = [c for c in cand if not n.get("직무") or c["직무"] == n.get("직무")]
            v = cand[0] if len(cand) == 1 else None
        if v is None:
            only_notion.append({k: n.get(k) for k in ("기업명", "직무", "진행상태", "서류마감")})
            continue
        for col in ("진행상태", "서류마감", "직무"):
            nv = (n.get(col) or "").strip()
            vv = (iso(v[col]) or "") if col == "서류마감" else v[col].strip()
            if nv and nv != vv:                               # Notion 쪽이 비어 있으면 차이로 보지 않는다
                bad = col == "진행상태" and nv not in J.STATES
                diffs.append({"key": status_key(v), "기업명": v["기업명"], "칸": col, "볼트": vv, "노션": nv,
                              **({"주의": "진행상태 값 목록 밖"} if bad else {})})
    out({"diffs": diffs, "only_in_notion": only_notion})
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("schema"); p.add_argument("--table", choices=list(TABLES))
    sub.add_parser("status")
    p = sub.add_parser("link"); p.add_argument("--table", required=True); p.add_argument("--ds", required=True); p.add_argument("--hub")
    p = sub.add_parser("plan"); p.add_argument("--table", required=True); p.add_argument("--key"); p.add_argument("--min-score", type=int); p.add_argument("--today")
    p = sub.add_parser("check"); p.add_argument("--table", required=True); p.add_argument("--key", required=True); p.add_argument("--props", required=True); p.add_argument("--today")
    p = sub.add_parser("record"); p.add_argument("--table", required=True); p.add_argument("--key", required=True); p.add_argument("--page", required=True); p.add_argument("--hash", required=True)
    p = sub.add_parser("lookup"); p.add_argument("--table", required=True); p.add_argument("--key", required=True)
    p = sub.add_parser("pending"); p.add_argument("op", choices=["add", "list", "clear"]); p.add_argument("--table"); p.add_argument("--key"); p.add_argument("--why")
    p = sub.add_parser("diff"); p.add_argument("--notion", required=True)
    a = ap.parse_args()
    return {"schema": cmd_schema, "status": cmd_status, "link": cmd_link, "plan": cmd_plan, "check": cmd_check,
            "record": cmd_record, "lookup": cmd_lookup, "pending": cmd_pending, "diff": cmd_diff}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
