"""위젯의 화면과 상관없는 부분: JSON 읽기·요약·열 대상 만들기. PySide6 없이 시험할 수 있게 표준 라이브러리만 쓴다.

위젯은 볼트의 `Areas/취업/_widget/오늘 현황.json`을 **읽기만** 한다(docs/widget-plan.md §5).
"""
import json
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

STATUS_REL = Path("Areas/취업/_widget/오늘 현황.json")
SUPPORTED_SCHEMA = 1
STALE_HOURS = 24


def status_path(vault):
    return Path(vault) / STATUS_REL


def load_status(vault):
    """(data, problem). problem 이 있으면 data 는 None 일 수 있다. 예외를 밖으로 던지지 않는다."""
    if not vault:
        return None, "볼트 폴더를 아직 고르지 않았습니다"
    p = status_path(vault)
    if not p.exists():
        return None, "오늘 현황 파일이 아직 없습니다 — 볼트에서 /job-flow 를 한 번 실행하세요"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "오늘 현황 파일을 읽지 못했습니다(쓰는 중일 수 있음 — 잠시 뒤 다시 읽습니다)"
    if not isinstance(data, dict):
        return None, "오늘 현황 파일 형식이 다릅니다"
    schema = data.get("schema", 0)
    if schema > SUPPORTED_SCHEMA:
        return data, "job-compass가 위젯보다 새 판입니다 — 위젯을 업데이트하세요(아는 칸만 보여 줍니다)"
    return data, None


def _parse_time(s):
    try:
        t = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return t.replace(tzinfo=None)


def summarize(data, now=None):
    """창 맨 위·배지·상태 줄에 쓸 값"""
    now = now or datetime.now()
    c = (data or {}).get("counts", {}) or {}
    urgent, overdue = int(c.get("urgent", 0) or 0), int(c.get("overdue", 0) or 0)
    new_today = int(c.get("new_candidates_today", 0) or 0)
    gen = _parse_time((data or {}).get("generated_at"))
    scan = (data or {}).get("last_scan") or None
    notes = []
    if gen is None:
        notes.append(("warn", "오늘 현황을 만든 시각을 모릅니다"))
    elif now - gen > timedelta(hours=STALE_HOURS):
        notes.append(("warn", f"오늘 현황이 {gen.strftime('%m/%d %H:%M')} 기준입니다 — 오늘 수집 기록이 없습니다"))
    if scan and int(scan.get("code", 0) or 0) != 0:
        notes.append(("error", f"마지막 수집({scan.get('at', '?')})이 실패했습니다 — `_scan-log.md`를 보세요"))
    for w in (data or {}).get("warnings", []) or []:
        notes.append(("warn", str(w)))
    return {"badge": urgent + overdue + new_today, "urgent": urgent, "overdue": overdue, "new_today": new_today,
            "new_total": int(c.get("new_candidates", 0) or 0), "wait_result": int(c.get("wait_result", 0) or 0),
            "in_progress": int(c.get("in_progress", 0) or 0), "notion_pending": int(c.get("notion_pending", 0) or 0), "filtered_today": int(c.get("filtered_today", 0) or 0),
            "notion": (data or {}).get("notion", "off"),
            "generated": gen.strftime("%m/%d %H:%M") if gen else "?",
            "last_scan": (f"{scan.get('at', '?')[5:].replace('-', '/')} " + ("성공" if int(scan.get("code", 0) or 0) == 0 else "실패"))
                         if scan else "기록 없음",
            "notes": notes}


def mood(summary):
    """아이콘 표정: 수집 실패 > 마감 임박(지난 것 포함) > 오늘 새 후보 > 새 소식 없음(쿨쿨)"""
    if any(level == "error" for level, _ in summary.get("notes", [])):
        return "fail"
    if summary.get("urgent") or summary.get("overdue"):
        return "urgent"
    if summary.get("new_today"):
        return "new"
    return "sleep"


def tab_view(summary, has_data=True):
    """화면 끝 탭·작업 표시줄에 보일 것: (상태, 점 안 글자, 첫 줄, 둘째 줄). 상태 = none|new|urgent|fail"""
    if not has_data:
        return "fail", "!", "현황을 못 읽음", "볼트 폴더·오늘 현황 확인"
    m = mood(summary)
    state = "none" if m == "sleep" else m
    urgent = summary.get("urgent", 0) + summary.get("overdue", 0)
    if state == "fail":
        mark, first = "!", "수집 실패"
    elif state == "urgent":
        mark, first = str(min(urgent, 99)), f"마감 임박 {urgent}" + (f" · 새 후보 {summary['new_today']}" if summary.get("new_today") else "")
    elif state == "new":
        mark, first = str(min(summary["new_today"], 99)), f"새 후보 {summary['new_today']}"
    else:
        mark, first = None, "새 소식 없음"
    second = f"진행 중 {summary.get('in_progress', 0)} · 수집 {summary.get('last_scan', '기록 없음')}"
    return state, mark, first, second


STEP_NAMES = ["공고", "점수", "조사", "자소서", "방어맵", "면접"]


def _days(deadline, today):
    try:
        return (datetime.strptime(deadline, "%Y-%m-%d").date() - today).days
    except (TypeError, ValueError):
        return None


def _score(score_text):
    """'62 🟡 🚫경력 필수' → (62, '🚫경력 필수'), '미산출 …' → (None, '미산출'), '' → (None, '')"""
    t = (score_text or "").strip()
    gate = ""
    if "🚫" in t:
        gate = "🚫" + t.split("🚫", 1)[1].strip()
    head = t.split()[0] if t else ""
    if head.isdigit():
        return int(head), gate
    return None, ("미산출" if t.startswith("미산출") else gate)


def step_done(v):
    v = (v or "").strip()
    return bool(v) and not v.startswith("✗") and v not in ("링크 끊김", "점수없음")


def panel_view(data, summary, today=None, max_cands=3, max_prog=4, max_actions=2):
    """현황 창(A안)에 그릴 내용. 화면과 상관없는 정리만 한다(시험 가능)."""
    today = today or datetime.now().date()
    d = data or {}
    s = summary
    urgent_n = s.get("urgent", 0) + s.get("overdue", 0)
    stats = [("마감 임박", urgent_n, "amber", urgent_n > 0),
             ("오늘 새 후보", s.get("new_today", 0), "coral", s.get("new_today", 0) > 0),
             ("진행 중", s.get("in_progress", 0), "blue", False)]
    alerts = []
    for i in d.get("overdue", []):
        alerts.append(("red", f"마감 지남 · {i.get('company', '')} — 아직 지원 전 [{i.get('state', '')}]"))
    for i in d.get("wait_result", []):
        alerts.append(("amber", f"결과 확인 · {i.get('company', '')} — 마감이 지났어요"))
    for i in sorted(d.get("urgent", []), key=lambda x: x.get("deadline") or "9999")[:1]:
        n = _days(i.get("deadline"), today)
        dl = ("D-day" if n == 0 else f"D-{n}") if n is not None and n >= 0 else "마감 임박"
        alerts.append(("amber", f"{i.get('company', '')} 서류마감 {dl} — {i.get('state', '')}"))
    cands = []
    for c in d.get("new_candidates", [])[:max_cands]:
        sc, gate = _score(c.get("score"))
        cands.append({"company": c.get("company", ""), "title": c.get("title") or c.get("direction", ""), "score": sc,
                      "gate": gate, "deadline": d_label(c.get("deadline"), today), "link": safe_web_link(c.get("link"))})
    prog = []
    for i in d.get("in_progress", [])[:max_prog]:
        n = _days(i.get("deadline"), today)
        tone = "red" if n is not None and n < 0 else ("amber" if n is not None and n <= 7 else "grey")
        st = i.get("steps") or {}
        prog.append({"company": i.get("company", ""), "state": i.get("state", ""), "deadline": d_label(i.get("deadline"), today),
                     "tone": tone, "steps": [step_done(st.get(k)) for k in STEP_NAMES],
                     "steps_tip": " · ".join(f"{k} {st.get(k, '—')}" for k in STEP_NAMES), "doc": i.get("doc")})
    actions = [f"{a.get('company', '')} — {str(a.get('do', '')).replace('`', '')}" for a in d.get("next_actions", [])[:max_actions]]
    scan = s.get("last_scan", "기록 없음")
    foot = f"수집 {scan}" + (f" · 노션 {'켜짐' if s.get('notion') == 'on' else '꺼짐'}")
    if s.get("notion_pending"):
        foot += f" · 밀린 반영 {s['notion_pending']}"
    files = d.get("files") or {}
    return {"stats": stats, "alerts": alerts[:3], "cands": cands, "more": max(0, s.get("new_total", 0) - len(cands)),
            "prog": prog, "prog_more": max(0, len(d.get("in_progress", [])) - len(prog)), "actions": actions,
            "foot": foot, "files": {k: files.get(k) for k in ("candidates", "today", "ledger")},
            "filtered": s.get("filtered_today", 0),
            "notes": s.get("notes", []), "generated": s.get("generated", "?")}


def notify_decision(prev, data, summary):
    """말풍선을 띄울지(docs/widget-plan.md §4). 반환: (메시지 또는 None, 새로 저장할 상태).
    - 같은 generated_at 으로는 한 번만. 처음 실행(이전 기록 없음)은 기준만 저장하고 띄우지 않는다.
    - 이전보다 늘어난 것만: 오늘 새 후보(날짜가 바뀌면 0부터) · 마감 임박 · 마감 지난 지원 전. 수집이 새로 실패하면 그것도.
    - 회사 이름은 넣지 않는다(화면 공유 중일 수 있음)."""
    d = data or {}
    gen = d.get("generated_at")
    cur = {"generated_at": gen, "today": d.get("today"), "new_today": summary.get("new_today", 0),
           "urgent": summary.get("urgent", 0), "overdue": summary.get("overdue", 0),
           "failed": any(level == "error" for level, _ in summary.get("notes", []))}
    prev = prev or {}
    if not gen or gen == prev.get("generated_at"):
        return None, prev
    if not prev.get("generated_at"):
        return None, cur
    base_new = prev.get("new_today", 0) if prev.get("today") == cur["today"] else 0
    parts = []
    if cur["urgent"] > prev.get("urgent", 0):
        parts.append(f"마감 임박 {cur['urgent']}건")
    if cur["overdue"] > prev.get("overdue", 0):
        parts.append(f"마감 지난 지원 전 {cur['overdue']}건")
    if cur["new_today"] > base_new:
        scores = [s for s in (_score(c.get("score"))[0] for c in d.get("new_candidates", [])) if s is not None]
        parts.append(f"새 후보 {cur['new_today'] - base_new}건" + (f"(최고 {max(scores)}점)" if scores else ""))
    if cur["failed"] and not prev.get("failed"):
        parts.append("자동 수집 실패")
    msg = " · ".join(parts) + " — 채용 현황을 확인하세요" if parts else None
    return msg, cur


def catchup_needed(data, now, last_trigger_day=None, scan_time="08:00", grace_min=20):
    """놓친 수집 보충이 필요한가(W4). 조건을 모두 만족할 때만 True:
    - 오늘 수집 기록(last_scan.at 의 날짜)이 없음 · 지금이 예약 시각 + grace_min 이후(작업 스케줄러의 자체 보충을 먼저 기다림)
    - 위젯이 오늘 이미 보충을 시작하지 않았음(last_trigger_day) — 하루 한 번만"""
    today = now.date().isoformat()
    if last_trigger_day == today:
        return False
    scan = (data or {}).get("last_scan") or {}
    if str(scan.get("at", ""))[:10] == today:
        return False
    try:
        hh, mm = (int(x) for x in scan_time.split(":"))
    except ValueError:
        hh, mm = 8, 0
    due = now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(minutes=grace_min)
    return now >= due


def d_label(deadline, today):
    try:
        d = datetime.strptime(deadline, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "마감 미정"
    n = (d - today).days
    return f"{d.strftime('%m/%d')} (" + (f"D-{n}" if n > 0 else ("D-day" if n == 0 else f"D+{-n}")) + ")"


def steps_text(steps):
    return " ".join(f"{k}{v}" for k, v in (steps or {}).items())


def tooltip(s):
    parts = []
    if s["urgent"]:
        parts.append(f"마감 임박 {s['urgent']}")
    if s["overdue"]:
        parts.append(f"마감 지난 지원 전 {s['overdue']}")
    if s["new_today"]:
        parts.append(f"오늘 새 후보 {s['new_today']}")
    return "취업 현황 — " + (" · ".join(parts) if parts else "새 소식 없음") + f" (수집 {s['last_scan']})"


def vault_file(vault, rel):
    """볼트 루트 기준 상대 경로 → 절대 경로. 볼트 밖을 가리키면(.. 등) None"""
    if not rel:
        return None
    base = Path(vault).resolve()
    p = (base / rel).resolve()
    try:
        p.relative_to(base)
    except ValueError:
        return None
    return p


def obsidian_uri(path):
    return "obsidian://open?path=" + urllib.parse.quote(str(path), safe="")


def default_position(size, screen):
    """기본 자리: 주 화면 오른쪽 끝에 붙여, 위에서 60% 높이(사용자 요청 2026-11-02: 기본은 화면 끝에 붙어 있게)"""
    w, h = size
    sx, sy, sw, sh = screen
    return sx + sw - w, sy + int(sh * 0.6) - h // 2


def clamp_position(pos, size, screens):
    """떠 있는 아이콘 위치 보정. pos=(x,y) 또는 None, size=(w,h), screens=[(x,y,w,h) 작업 영역, 첫째가 주 화면].
    아이콘이 어느 화면 안에도 온전히 들어 있지 않으면(모니터를 뺐거나 해상도가 바뀜) 기본 자리로 되돌린다."""
    w, h = size
    if pos is not None and None not in pos:
        x, y = int(pos[0]), int(pos[1])
        for sx, sy, sw, sh in screens:
            if sx <= x and sy <= y and x + w <= sx + sw and y + h <= sy + sh:
                return x, y
    return default_position(size, screens[0])


def panel_position(size, screen, anchor, side, gap=2):
    """현황 패널 자리. size=(w,h), screen=(x,y,w,h) 작업 영역, anchor=(탭 y, 탭 높이) 또는 None, side=탭이 붙은 쪽.
    가로: 탭과 같은 화면 끝에 딱 붙임. 세로: 탭 바로 위, 위쪽이 모자라면 탭 바로 아래, 그래도 안 되면 화면 안으로 맞춤."""
    w, h = size
    sx, sy, sw, sh = screen
    x = sx if side == "left" else sx + sw - w
    if anchor is None:
        return x, sy + sh - h
    ty, th = anchor
    y = ty - h - gap
    if y < sy:
        y = ty + th + gap
        if y + h > sy + sh:
            y = sy + sh - h
    return x, max(sy, y)


def dock_to_side(pos, size, screen):
    """놓은 자리에서 가까운 왼쪽·오른쪽 화면 끝에 붙인다(위아래 위치는 그대로, 화면 안으로만). screen=(x,y,w,h) 작업 영역"""
    x, y = pos
    w, h = size
    sx, sy, sw, sh = screen
    x = sx if (x + w / 2) < (sx + sw / 2) else sx + sw - w
    y = min(max(y, sy), sy + sh - h)
    return x, y


def safe_web_link(link):
    """공고 열기는 http(s) 주소만"""
    link = (link or "").strip().strip("<>")
    return link if link.startswith(("http://", "https://")) else None
