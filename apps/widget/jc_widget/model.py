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
            "in_progress": int(c.get("in_progress", 0) or 0), "notion_pending": int(c.get("notion_pending", 0) or 0),
            "notion": (data or {}).get("notion", "off"),
            "generated": gen.strftime("%m/%d %H:%M") if gen else "?",
            "last_scan": (f"{scan.get('at', '?')[5:].replace('-', '/')} " + ("성공" if int(scan.get("code", 0) or 0) == 0 else "실패"))
                         if scan else "기록 없음",
            "notes": notes}


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


def safe_web_link(link):
    """공고 열기는 http(s) 주소만"""
    link = (link or "").strip().strip("<>")
    return link if link.startswith(("http://", "https://")) else None
