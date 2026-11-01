#!/usr/bin/env python3
"""마감 캘린더(md) + `.ics` 만들기, 일정 추가. 볼트 루트에서 실행한다.

쓰는 법:
  python -I -X utf8 calendar_export.py build [--today YYYY-MM-DD]        # 마감 캘린더.md 와 내보내기/지원 마감.ics 를 새로 만든다(덮어쓰기 허용 — 사본)
  python -I -X utf8 calendar_export.py add-event --company A사 --kind 면접 --date 2026-11-20 [--time 14:00] [--place …] [--memo …]
                                                                          # Areas/취업/일정.md 에 한 줄 추가(사용자가 말했거나 공고에 적힌 일정만)

입력: 현황표(`지원 현황.md`) + `Areas/취업/일정.md`(기업명 · 종류 · 날짜 · 시간 · 장소/링크 · 메모).
날짜는 항상 KST 오늘로 확정해 D-n 을 계산한다(--today 는 시험용).

구획(기획 02 §5-2): ① 지난 마감(미처리) ② 이번 주 ③ 다음 주 ④ 이번 달 ⑤ 마감일 미정·조기 마감 가능 ⑥ 면접·시험 일정 (+ 그 이후)
  - 지원 전 상태(Not started … 자소서 작성 완료)인 행만 서류마감 구획에 든다. 지원완료 이후는 서류마감 구획에서 빠지고 일정만 남는다.
  - 최종합·불합·지원취소는 어디에도 넣지 않는다.
  - 주는 월요일~일요일 기준.
.ics: 서류마감(종일)·일정(시간 있으면 시간 지정). 고정 UID(공고 ID 기반, 영문·숫자만. 한글이 섞인 키는 해시를 붙임), 알림 D-3·D-1, 줄바꿈 CRLF.
      같은 파일을 다시 가져올 때 중복되는지는 앱마다 다르다(미시험 — DEV-STATUS 참고).
"""
import argparse
import hashlib
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

SCHEDULE = Path("Areas/취업/일정.md")
OUT_MD = Path("Areas/취업/마감 캘린더.md")
OUT_ICS = Path("Areas/취업/내보내기/지원 마감.ics")
KINDS = ["서류 발표", "역량검사", "인적성", "면접", "코딩테스트", "과제", "기타"]
SCHED_COLS = ["기업명", "종류", "날짜", "시간", "장소/링크", "메모"]
EARLY = re.compile(r"(조기\s*마감|채용\s*시\s*마감|수시\s*채용|상시)")


def read_schedule():
    if not SCHEDULE.exists():
        return []
    rows, cols = [], None
    for ln in SCHEDULE.read_text(encoding="utf-8").splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        cells = J.split_row(ln)
        if cols is None:
            if "기업명" in cells and "날짜" in cells:
                cols = cells
            continue
        if re.match(r"^[\s:-]+$", "".join(cells)):
            continue
        d = {c: (cells[i] if i < len(cells) else "") for i, c in enumerate(cols)}
        if d.get("날짜"):
            rows.append(d)
    return rows


def d_label(d, today):
    n = (d - today).days
    return f"D-{n}" if n > 0 else ("D-day" if n == 0 else f"D+{-n}")


def link_name(cell):
    """[[a\\|b]] → b, [[a]] → a"""
    m = re.match(r"^\[\[(.+?)\]\]$", cell.strip())
    if not m:
        return cell.strip()
    inner = m.group(1).replace("\\|", "|")
    return inner.split("|")[-1]


def row_line(d, today, r):
    gate = " 🚫" + r["적합도"].split("🚫", 1)[1].strip() if "🚫" in r.get("적합도", "") else ""
    fit = r["적합도"].split("🚫")[0].strip() or "—"
    parts = [f"{r['기업명']} {r['직무']}", link_name(r["공고"]) if r["공고"] else "", f"[{r['진행상태']}]", f"적합도 {fit}{gate}"]
    return f"- **{d_label(d, today)} ({J.weekday_ko(d)}) {d.strftime('%m-%d')}** · " + " · ".join(x for x in parts if x)


def build(today):
    t = J.Table()
    rows = t.as_dicts() if t.head_idx is not None and not t.problems() else []
    sched = [s for s in read_schedule()]
    mon = today - timedelta(days=today.weekday())
    this_end = mon + timedelta(days=6)
    next_start, next_end = this_end + timedelta(days=1), this_end + timedelta(days=7)
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    overdue, wk, nxt, mon_, later, undated = [], [], [], [], [], []
    for r in rows:
        st = r["진행상태"]
        if st not in J.PRE_APPLY:
            continue
        if not r["서류마감"]:
            undated.append((r, "마감일 미정"))
            continue
        try:
            d = J.parse_date(r["서류마감"])
        except ValueError:
            undated.append((r, "마감일 형식 오류"))
            continue
        if d < today:
            overdue.append((d, r))
        elif d <= this_end:
            wk.append((d, r))
        elif d <= next_end:
            nxt.append((d, r))
        elif d <= month_end:
            mon_.append((d, r))
        else:
            later.append((d, r))
        if EARLY.search(r["메모"]):
            undated.append((r, "조기 마감 가능(메모)"))
    for lst in (overdue, wk, nxt, mon_, later):
        lst.sort(key=lambda x: (x[0], x[1]["기업명"]))

    closed_firms = {r["기업명"] for r in rows if r["진행상태"] in J.CLOSED}
    events = []
    for s in sched:
        try:
            d = J.parse_date(s["날짜"])
        except ValueError:
            continue
        if s["기업명"] in closed_firms:
            continue
        events.append((d, s))
    events.sort(key=lambda x: (x[0], x[1].get("시간", "")))
    upcoming = [e for e in events if e[0] >= today]
    past_ev = [e for e in events if e[0] < today]

    L = [f"기준일: {today.isoformat()} ({J.weekday_ko(today)}, KST)", "",
         "> 이 파일은 `지원 현황.md`와 `일정.md`에서 자동으로 만든 **사본**입니다. 고치지 마세요(다음에 만들 때 덮어씁니다).", "",
         "# 마감 캘린더", ""]

    def sec(title, items, fmt):
        L.append(f"## {title}")
        L.append("")
        if not items:
            L.append("- 없음")
        else:
            L.extend(fmt(x) for x in items)
        L.append("")

    sec("① 지난 마감(미처리)", overdue, lambda x: row_line(x[0], today, x[1]) + " — 마감이 지났는데 지원 전 상태")
    sec("② 이번 주", wk, lambda x: row_line(x[0], today, x[1]))
    sec("③ 다음 주", nxt, lambda x: row_line(x[0], today, x[1]))
    sec("④ 이번 달", mon_, lambda x: row_line(x[0], today, x[1]))
    if later:
        sec("그 이후", later, lambda x: row_line(x[0], today, x[1]))
    sec("⑤ 마감일 미정 · 조기 마감 가능", undated,
        lambda x: "- " + " · ".join(y for y in (f"{x[0]['기업명']} {x[0]['직무']}", link_name(x[0]["공고"]) if x[0]["공고"] else "", f"[{x[0]['진행상태']}]", x[1]) if y))
    sec("⑥ 면접 · 시험 일정", upcoming,
        lambda x: f"- **{d_label(x[0], today)} ({J.weekday_ko(x[0])}) {x[0].strftime('%m-%d')}"
                  f"{(' ' + x[1]['시간']) if x[1].get('시간') else ''}** · {x[1]['기업명']} · {x[1].get('종류', '')}"
                  f"{(' · ' + x[1]['장소/링크']) if x[1].get('장소/링크') else ''}{(' · ' + x[1]['메모']) if x[1].get('메모') else ''}")
    if past_ev:
        L.append(f"(지난 일정 {len(past_ev)}건은 위에서 뺐음)")
        L.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8", newline="\n")

    # ---- .ics
    def esc(s):
        return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    def fold(line):
        b = line.encode("utf-8")
        if len(b) <= 75:
            return line
        out, cur, n = [], "", 0
        for ch in line:
            w = len(ch.encode("utf-8"))
            if n + w > 74:
                out.append(cur)
                cur, n = " " + ch, 1 + w
            else:
                cur += ch
                n += w
        out.append(cur)
        return "\r\n".join(out)

    def uid_part(s):
        # UID는 영문·숫자만 쓴다(가져오기 앱이 한글 UID를 싫어할 수 있다). 한글이 섞인 키는 같은 입력이면 같은 값이 나오도록 짧은 해시를 붙인다.
        ascii_part = re.sub(r"[^0-9A-Za-z._-]+", "-", s).strip("-")
        if s.isascii():
            return ascii_part
        return (ascii_part + "-" if ascii_part else "") + hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seq = int(time.time())
    V = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//job-compass//KO", "CALSCALE:GREGORIAN", "X-WR-CALNAME:지원 마감",
         "BEGIN:VTIMEZONE", "TZID:Asia/Seoul", "BEGIN:STANDARD", "DTSTART:19700101T000000", "TZOFFSETFROM:+0900", "TZOFFSETTO:+0900",
         "TZNAME:KST", "END:STANDARD", "END:VTIMEZONE"]

    def alarms(desc):
        res = []
        for days in (3, 1):
            res += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(desc)}", f"TRIGGER:-P{days}D", "END:VALARM"]
        return res

    n_ev = 0
    for r in rows:
        if r["진행상태"] not in J.PRE_APPLY or not r["서류마감"]:
            continue
        try:
            d = J.parse_date(r["서류마감"])
        except ValueError:
            continue
        key = uid_part(r["공고 ID"] if r["공고 ID"] not in ("", "—") else f"{r['기업명']}-{r['직무']}")
        title = f"서류마감 · {r['기업명']} {r['직무']}"
        V += ["BEGIN:VEVENT", f"UID:jobcompass-{key}-deadline@job-compass", f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}",
              f"SEQUENCE:{seq}", f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
              f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}", f"SUMMARY:{esc(title)}",
              f"DESCRIPTION:{esc('진행상태 ' + r['진행상태'] + (' · 적합도 ' + r['적합도'] if r['적합도'] else ''))}"] + alarms(title) + ["END:VEVENT"]
        n_ev += 1
    for i, (d, s) in enumerate(upcoming):
        key = uid_part(f"{s['기업명']}-{s.get('종류', '')}-{d.isoformat()}-{s.get('시간', '')}")
        title = f"{s.get('종류', '일정')} · {s['기업명']}"
        V += ["BEGIN:VEVENT", f"UID:jobcompass-{key}@job-compass", f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}", f"SEQUENCE:{seq}"]
        tm = s.get("시간", "").strip()
        if re.match(r"^\d{1,2}:\d{2}$", tm):
            h, m = tm.split(":")
            start = datetime(d.year, d.month, d.day, int(h), int(m))
            end = start + timedelta(hours=1)
            V += [f"DTSTART;TZID=Asia/Seoul:{start.strftime('%Y%m%dT%H%M%S')}", f"DTEND;TZID=Asia/Seoul:{end.strftime('%Y%m%dT%H%M%S')}"]
        else:
            V += [f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}"]
        V += [f"SUMMARY:{esc(title)}"]
        extra = " · ".join(x for x in (s.get("장소/링크", ""), s.get("메모", "")) if x)
        if extra:
            V.append(f"DESCRIPTION:{esc(extra)}")
        V += alarms(title) + ["END:VEVENT"]
        n_ev += 1
    V.append("END:VCALENDAR")
    OUT_ICS.parent.mkdir(parents=True, exist_ok=True)
    OUT_ICS.write_bytes(("\r\n".join(fold(x) for x in V) + "\r\n").encode("utf-8"))
    print(f"만듦: {OUT_MD} · {OUT_ICS}\n기준일 {today} · 지난 마감 {len(overdue)} · 이번 주 {len(wk)} · 다음 주 {len(nxt)} · 이번 달 {len(mon_)} · 그 이후 {len(later)} · "
          f"마감일 미정 {len(undated)} · 일정 {len(upcoming)} · .ics 이벤트 {n_ev}")
    soon = [(d, r) for d, r in wk + overdue if (d - today).days <= 3]
    if soon:
        print("마감 3일 이내이거나 지난 지원 전 행: " + ", ".join(f"{r['기업명']}({d_label(d, today)})" for d, r in soon))
    return 0


def add_event(a):
    try:
        d = J.parse_date(a.date)
    except ValueError:
        J.die("날짜는 YYYY-MM-DD", 2)
    if a.time and not re.match(r"^\d{1,2}:\d{2}$", a.time):
        J.die("시간은 HH:MM", 2)
    kind = a.kind if a.kind in KINDS else "기타"
    line = "| " + " | ".join(J.cell(x) for x in (a.company, kind, d.isoformat(), a.time or "", a.place or "", a.memo or "")) + " |"
    if SCHEDULE.exists():
        cur = SCHEDULE.read_text(encoding="utf-8")
        if line in cur:
            print("이미 같은 줄이 있다 — 추가하지 않음")
            return 0
        J.backup_file(SCHEDULE)
        text = cur.rstrip("\n") + "\n" + line + "\n"
    else:
        text = ("# 일정\n\n> 서류 발표 · 역량검사 · 인적성 · 면접 같은 일정. 사용자가 말했거나 공고에 적힌 것만 적는다(추정 금지). "
                "`마감 캘린더`가 이 표를 읽는다.\n\n| " + " | ".join(SCHED_COLS) + " |\n|" + "---|" * len(SCHED_COLS) + "\n" + line + "\n")
    SCHEDULE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE.write_text(text, encoding="utf-8", newline="\n")
    print(f"추가함: {a.company} {kind} {d.isoformat()} {a.time or ''}".strip())
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build"); p.add_argument("--today")
    p = sub.add_parser("add-event")
    for k in ("company", "kind", "date", "time", "place", "memo"):
        p.add_argument("--" + k)
    a = ap.parse_args()
    if a.cmd == "build":
        return build(J.parse_date(a.today) if a.today else J.today_kst())
    if not (a.company and a.kind and a.date):
        J.die("--company --kind --date 가 필요하다", 2)
    return add_event(a)


if __name__ == "__main__":
    sys.exit(main())
