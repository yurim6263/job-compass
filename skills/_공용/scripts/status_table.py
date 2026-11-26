#!/usr/bin/env python3
"""현황표 `Areas/취업/지원 현황.md` 읽기·검사·행 추가. 볼트 루트에서 실행한다.

쓰는 법:
  python -I -X utf8 status_table.py check                       # 열·구분선·칸 수 검사(쓰지 않음)
  python -I -X utf8 status_table.py list [--json]               # 행 목록
  python -I -X utf8 status_table.py find --id jobkorea:123      # 공고 ID로 행 찾기(없으면 종료 코드 1)
  python -I -X utf8 status_table.py find --company A사 --job "…" # 회사·직무가 같은 행 후보
  python -I -X utf8 status_table.py add --company A사 --job 제조AI --link "[[채용공고_A사 …\\|…]]" --id jobkorea:123 \\
        --channel 잡코리아 --deadline 2026-11-14 --type 신입 --memo "2026-10-31 분석 — [[…\\|지원 준비]]" \\
        --fit "74 🟡" --region 서울
  python -I -X utf8 status_table.py update-fit --id jobkorea:123 [--fit "80 🟢"] [--region 서울] [--memo-add "재분석 …"]
  (공고 ID가 `—`인 행은 --id 대신 --company [--job] 로 지정한다. 같은 조건의 행이 둘 이상이면 고르지 않고 종료 코드 5)
  python -I -X utf8 status_table.py set-status --id jobkorea:123 --state 지원완료 [--note "제출함"] [--allow-back]
                                                                  # 진행상태 갱신(임시 — /job-flow가 배포되면 그쪽이 맡는다)
  python -I -X utf8 status_table.py undo-status [--apply]         # 방금 한 set-status 한 번을 취소(기본은 미리보기). 실수 취소 전용
  python -I -X utf8 status_table.py migrate [--apply] [--rewrite-header]   # 10열 옛 표 → 13열 (기본은 미리보기)
  python -I -X utf8 status_table.py expire [--apply] [--today YYYY-MM-DD]  # 마감 지난 미제출 행 정리(/job-flow가 호출). 기본은 미리보기
  python -I -X utf8 status_table.py undo-expire [--apply] [--id 공고ID]    # 가장 최근 expire --apply 를 되돌림
  마감 정리(2026-11-17 사용자 결정): 마감 다음 날부터. Not started·일정 + 자소서 항목 정리 → 지원취소 + 메모 "마감 지남(미지원)".
  인적사항 입력완료·자소서 작성중·자소서 작성 완료는 제출했을 수 있어 바꾸지 않고 알린다. 지원완료 이후·마감일 없는 행은 건드리지 않는다.

규칙(기획 00 §2, 02 §4):
  - 행 **추가**는 /job-posting. `update-fit`은 그 공고를 다시 분석했을 때 적합도·지역·메모(끝에 덧붙이기)만 바꾼다.
    진행상태·상태일·최종 단계를 바꾸는 `set-status`는 /job-flow의 몫이다. /job-flow가 아직 없는 볼트에서만 /job-posting이 임시로 쓴다.
  - 같은 공고 ID 행이 있으면 추가하지 않는다(종료 코드 3, 기존 행을 보여 줌).
  - 값 목록(진행상태·직무·유형·지역)이 어긋나면 쓰지 않는다. 쓰기 전 `Areas/취업/_백업/`에 사본을 남긴다.
  - 표가 깨져 있으면(열 수·구분선) 쓰지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

UNDO_FIELDS = ("진행상태", "상태일", "최종 단계", "메모")
UNDO_FILE = J.BACKUP_DIR / "마지막 상태변경.json"   # set-status 직전 값 기록(한 단계 취소용)


def load():
    t = J.Table()
    return t


def need_ok(t, allow_missing=False):
    if t.head_idx is None:
        if allow_missing:
            return
        J.die("현황표가 없다.", 2)
    probs = t.problems()
    if probs:
        J.die("현황표 형식 문제 — 쓰지 않는다:\n- " + "\n- ".join(probs), 2)


def show_row(d):
    return " | ".join(f"{k}={d[k]}" for k in ("기업명", "직무", "진행상태", "서류마감", "공고 ID", "적합도") if d.get(k))



def pick_row(rows, id_=None, company=None, job=None):
    """수정 대상 행 하나를 고른다. 공고 ID가 없는 행(`—`)은 ID로 고르지 않고 회사(+직무)로만 고른다. 둘 이상이면 고르지 않는다."""
    if id_ and id_.strip() not in ("", "—"):
        hit = [d for d in rows if d["공고 ID"].strip() == id_.strip()]
    elif company:
        hit = [d for d in rows if d["기업명"] == company and (not job or d["직무"] == job)]
    else:
        return None, "공고 ID가 없는 행(`—`)은 --company(필요하면 --job)로 지정해야 한다"
    if not hit:
        return None, "그런 행이 없다"
    if len(hit) > 1:
        return None, "해당하는 행이 둘 이상이다 — 공고 ID·직무로 하나를 고르게 해야 한다:\n" + "\n".join("  " + show_row(d) for d in hit)
    return hit[0], None


def cmd_check(a):
    t = load()
    if t.head_idx is None:
        print("현황표 없음(첫 행 추가 때 만들어짐)")
        return 0
    probs = t.problems()
    if probs:
        print("문제:\n- " + "\n- ".join(probs))
        return 1
    n = len(t.rows)
    bad_state = [d["기업명"] for d in t.as_dicts() if d["진행상태"] not in J.STATES]
    bad_fit = [d["기업명"] for d in t.as_dicts() if not J.fit_ok(d["적합도"])]
    print(f"정상: 13열, {n}행")
    if bad_state:
        print("진행상태 값이 목록 밖인 행: " + ", ".join(bad_state))
    if bad_fit:
        print("적합도 형식이 다른 행: " + ", ".join(bad_fit))
    return 0


def cmd_list(a):
    t = load()
    need_ok(t)
    rows = t.as_dicts()
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for i, d in enumerate(rows, 1):
            print(f"{i}. {show_row(d)}")
        if not rows:
            print("(행 없음)")
    return 0


def cmd_find(a):
    t = load()
    if t.head_idx is None:
        print("없음(현황표 없음)")
        return 1
    need_ok(t)
    rows = t.as_dicts()
    hits = []
    if a.id:
        hits = [d for d in rows if d["공고 ID"].strip() == a.id.strip()]
    elif a.company:
        hits = [d for d in rows if d["기업명"] == a.company and (not a.job or d["직무"] == a.job)]
    if not hits:
        print("없음")
        return 1
    for d in hits:
        print(json.dumps(d, ensure_ascii=False))
    return 0


def check_values(d):
    errs = []
    if d["진행상태"] not in J.STATES:
        errs.append(f"진행상태 `{d['진행상태']}`가 목록 밖")
    if d["직무"] not in J.JOBS:
        errs.append(f"직무 `{d['직무']}`가 목록 밖(제조AI · CBM시스템개발자 · MES · LLM응용 · 데이터 · 기타 중 하나, 모르면 사용자에게 묻기)")
    if d["유형"] and d["유형"] not in J.TYPES:
        errs.append(f"유형 `{d['유형']}`가 목록 밖(안 맞으면 비움)")
    if d["서류마감"]:
        try:
            J.parse_date(d["서류마감"])
        except ValueError:
            errs.append("서류마감은 YYYY-MM-DD")
    if d["지역"] and d["지역"] not in J.REGIONS:
        errs.append(f"지역 `{d['지역']}`가 목록 밖({' · '.join(J.REGIONS)})")
    if not J.fit_ok(d["적합도"]):
        errs.append("적합도 형식은 `74 🟡` 또는 `미산출`")
    if d["최종 단계"] and d["최종 단계"] not in J.STATES:
        errs.append("최종 단계가 목록 밖")
    if not d["기업명"]:
        errs.append("기업명 필요")
    return errs


def cmd_add(a):
    t = load()
    if t.head_idx is not None:
        need_ok(t)
    rows = t.as_dicts() if t.head_idx is not None else []
    if a.id and a.id != "—":
        dup = [d for d in rows if d["공고 ID"].strip() == a.id.strip()]
    else:
        dup = [d for d in rows if d["공고 ID"].strip() in ("", "—") and d["기업명"] == a.company and d["직무"] == a.job]
    if a.id and a.id != "—" or dup:
        if dup:
            print("같은 공고 ID 행이 이미 있다 — 추가하지 않음:\n" + json.dumps(dup[0], ensure_ascii=False))
            return 3
    today = J.today_kst().isoformat()
    d = {"기업명": a.company, "직무": a.job, "진행상태": "Not started", "유형": a.type or "", "서류마감": a.deadline or "",
         "공고": a.link or "", "공고 ID": a.id or "—", "채널": a.channel or "", "상태일": today, "메모": a.memo or "",
         "적합도": a.fit or "", "지역": a.region or "", "최종 단계": "Not started"}
    errs = check_values(d)
    if errs:
        print("쓰지 않음:\n- " + "\n- ".join(errs))
        return 2
    if t.head_idx is None and Path(J.FILE_TABLE).exists():
        J.die("현황표 파일은 있는데 표를 못 찾았다. 쓰지 않는다.", 2)
    rows.append(d)
    t.save(rows)
    print(f"추가함: {show_row(d)} (총 {len(rows)}행)")
    return 0


def cmd_update_fit(a):
    t = load()
    need_ok(t)
    rows = t.as_dicts()
    d, err = pick_row(rows, a.id, a.company, a.job)
    if err:
        print(err)
        return 5
    if a.fit is not None:
        d["적합도"] = a.fit
    if a.region is not None:
        d["지역"] = a.region
    if a.memo_add:
        add = a.memo_add.strip().lstrip("·").strip()          # 앞의 구분자(` · `)는 스크립트가 붙인다
        d["메모"] = (d["메모"] + " · " if d["메모"] else "") + add
    errs = check_values(d)
    if errs:
        print("쓰지 않음:\n- " + "\n- ".join(errs))
        return 2
    t.save(rows)
    print(f"고침(적합도·지역·메모만): {show_row(d)}")
    return 0


def cmd_set_status(a):
    t = load()
    need_ok(t)
    rows = t.as_dicts()
    d, err = pick_row(rows, a.id, a.company, a.job)
    if err:
        print(err)
        return 5
    new, cur = a.state, d["진행상태"]
    if new not in J.STATES:
        print(f"진행상태 `{new}`가 목록 밖")
        return 2
    if cur in J.CLOSED:
        print(f"`{cur}` 행은 덮어쓰지 않는다")
        return 4
    if new == cur:
        print("같은 상태 — 바꾸지 않음")
        return 0
    if new in J.STAGE_ORDER and cur in J.STAGE_ORDER and J.STAGE_ORDER.index(new) < J.STAGE_ORDER.index(cur) and not a.allow_back:
        print(f"상태는 뒤로 가지 않는다({cur} → {new} 거부). 사용자가 되돌리기를 확인했을 때만 --allow-back")
        return 4
    final = d["최종 단계"] or (cur if cur in J.STAGE_ORDER else "")
    if new in J.STAGE_ORDER:
        if not final or final not in J.STAGE_ORDER or J.STAGE_ORDER.index(new) > J.STAGE_ORDER.index(final):
            final = new
    before = {k: d[k] for k in UNDO_FIELDS}
    d["진행상태"], d["상태일"], d["최종 단계"] = new, J.today_kst().isoformat(), final
    note = f"{J.today_kst().isoformat()} {a.note or new}"
    d["메모"] = (d["메모"] + " · " if d["메모"] else "") + note
    t.save(rows)
    UNDO_FILE.write_text(json.dumps({"기업명": d["기업명"], "직무": d["직무"], "공고 ID": d["공고 ID"],
                                    "before": before, "after": {k: d[k] for k in UNDO_FIELDS}},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"고침: {d['기업명']} {cur} → {new} (최종 단계 {final})")
    return 0


def cmd_undo_status(a):
    """직전 set-status 한 번만 되돌린다(진행상태·상태일·최종 단계·메모 4칸). 그 뒤 그 행의 4칸이 바뀌었으면 거부한다."""
    if not UNDO_FILE.exists():
        print("되돌릴 기록이 없다(직전 set-status 기록 없음). 상태를 뒤로 옮기려면 set-status --allow-back")
        return 4
    rec = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
    t = load()
    need_ok(t)
    rows = t.as_dicts()
    d, err = pick_row(rows, rec["공고 ID"], rec["기업명"], rec["직무"])
    if err:
        print("기록된 행을 찾지 못했다: " + err)
        return 5
    if any(d[k] != rec["after"][k] for k in UNDO_FIELDS):
        print("그 행이 직전 변경 뒤에 또 바뀌었다 — 자동으로 되돌리지 않는다. 현황표를 보고 직접 고치거나 set-status --allow-back")
        return 4
    print(f"되돌릴 행: {show_row(d)}")
    for k in UNDO_FIELDS:
        if d[k] != rec["before"][k]:
            print(f"  {k}: {d[k] or '(빈칸)'} → {rec['before'][k] or '(빈칸)'}")
    if not a.apply:
        print("미리보기만 했다. 되돌리려면 --apply (수정 전 사본을 먼저 남긴다).")
        return 0
    for k in UNDO_FIELDS:
        d[k] = rec["before"][k]
    t.save(rows)
    UNDO_FILE.unlink()
    print("되돌림(사본은 Areas/취업/_백업/). 한 번만 되돌릴 수 있다.")
    return 0


def expire_scan(rows, today):
    """마감(서류마감)이 오늘보다 앞선 지원 전 행을 둘로 나눈다. 마감일이 없거나 읽을 수 없으면 건드리지 않는다."""
    auto, ask = [], []
    for d in rows:
        st = d["진행상태"]
        if st in J.CLOSED or st not in J.PRE_APPLY or not d["서류마감"].strip():
            continue
        try:
            dl = J.parse_date(d["서류마감"])
        except ValueError:
            continue
        if dl >= today:
            continue
        (auto if st in J.EXPIRE_AUTO else ask).append((d, dl))
    return auto, ask


def cmd_expire(a):
    """마감이 지났는데 제출하지 않은 행을 정리한다.
    지원 준비가 거의 없던 행(Not started·일정 + 자소서 항목 정리)은 `지원취소` + 메모 "마감 지남(미지원)"로 바꾸고,
    작성 중이던 행(인적사항 입력완료·자소서 작성중·자소서 작성 완료)은 제출했을 수 있어 바꾸지 않고 알리기만 한다.
    기본은 미리보기, --apply 일 때만 쓴다(수정 전 사본은 Areas/취업/_백업/)."""
    t = load()
    if t.head_idx is None:
        print("현황표 없음 — 할 일 없음")
        return 0
    need_ok(t)
    today = J.parse_date(a.today) if a.today else J.today_kst()
    rows = t.as_dicts()
    auto, ask = expire_scan(rows, today)
    print(f"기준일 {today.isoformat()} · 마감 지난 지원 준비 행: 자동 정리 대상 {len(auto)}건 · 제출 여부 확인 필요 {len(ask)}건")
    for d, dl in auto:
        print(f"  자동 정리: {d['기업명']} · {d['직무']} · [{d['진행상태']}] · 마감 {dl.isoformat()} → 지원취소 + 메모 \"{J.EXPIRE_MEMO}\"")
    for d, dl in ask:
        print(f"  확인 필요: {d['기업명']} · {d['직무']} · [{d['진행상태']}] · 마감 {dl.isoformat()} — 제출했으면 지원완료, 안 했으면 지원취소")
    if not auto:
        return 0
    if not a.apply:
        print("미리보기만 했다. 정리하려면 --apply (수정 전 사본을 먼저 남긴다).")
        return 0
    items = []
    for d, dl in auto:
        before = {k: d[k] for k in UNDO_FIELDS}
        d["진행상태"], d["상태일"] = "지원취소", today.isoformat()
        d["메모"] = (d["메모"] + " · " if d["메모"] else "") + f"{today.isoformat()} {J.EXPIRE_MEMO}"
        items.append({"기업명": d["기업명"], "직무": d["직무"], "공고 ID": d["공고 ID"],
                      "before": before, "after": {k: d[k] for k in UNDO_FIELDS}})
    t.save(rows)
    rec = {"date": today.isoformat(), "items": items}
    if J.EXPIRE_FILE.exists():
        try:
            old = json.loads(J.EXPIRE_FILE.read_text(encoding="utf-8"))
            if old.get("date") == rec["date"]:
                rec["items"] = old.get("items", []) + items
        except (ValueError, OSError):
            pass
    J.EXPIRE_FILE.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"정리함: {len(auto)}건 → 지원취소(사본은 Areas/취업/_백업/). 잘못 정리했으면 undo-expire")
    return 0


def cmd_undo_expire(a):
    """가장 최근 expire --apply 가 바꾼 행을 되돌린다(진행상태·상태일·최종 단계·메모). 그 뒤 그 행이 또 바뀌었으면 건너뛴다."""
    if not J.EXPIRE_FILE.exists():
        print("되돌릴 기록이 없다(최근 마감 정리 기록 없음)")
        return 4
    rec = json.loads(J.EXPIRE_FILE.read_text(encoding="utf-8"))
    t = load()
    need_ok(t)
    rows = t.as_dicts()
    todo = []
    for it in rec.get("items", []):
        if a.id and it["공고 ID"] != a.id:
            continue
        d, err = pick_row(rows, it["공고 ID"], it["기업명"], it["직무"])
        if err:
            print(f"건너뜀 — {it['기업명']}: {err}")
            continue
        if any(d[k] != it["after"][k] for k in UNDO_FIELDS):
            print(f"건너뜀 — {it['기업명']}: 정리 뒤에 또 바뀌었다")
            continue
        todo.append((d, it))
    if not todo:
        print("되돌릴 행이 없다")
        return 4
    for d, it in todo:
        print(f"되돌릴 행: {d['기업명']} · 진행상태 {d['진행상태']} → {it['before']['진행상태']}")
    if not a.apply:
        print("미리보기만 했다. 되돌리려면 --apply (수정 전 사본을 먼저 남긴다).")
        return 0
    for d, it in todo:
        for k in UNDO_FIELDS:
            d[k] = it["before"][k]
    t.save(rows)
    left = [it for it in rec.get("items", []) if not any(it is x for _, x in todo)]
    if left:
        rec["items"] = left
        J.EXPIRE_FILE.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    else:
        J.EXPIRE_FILE.unlink()
    print(f"되돌림: {len(todo)}건(사본은 Areas/취업/_백업/)")
    return 0


def cmd_migrate(a):
    t = load()
    if t.head_idx is None:
        print("현황표 없음")
        return 1
    if t.cols == J.COLUMNS:
        print("이미 13열 — 할 일 없음")
        return 0
    if t.cols != J.OLD_COLUMNS:
        J.die(f"알 수 없는 열 구성: {t.cols}", 2)
    rows = []
    for r in t.rows:
        r = r + [""] * (10 - len(r))
        d = dict(zip(J.OLD_COLUMNS, r))
        d["적합도"], d["지역"] = "", ""
        d["최종 단계"] = d["진행상태"] if d["진행상태"] in J.STATES else ""
        rows.append(d)
    head_lines = [ln for ln in t.lines[: t.head_idx]]
    header_note = []
    stale = [ln for ln in head_lines if ln.startswith(">") and ("자리표시" in ln or "[여기에" in ln or "Notion" in ln)]
    if stale:
        header_note.append("머리말에 옛 문구가 있다(직무 자리표시자·Notion 문구 등): " + str(len(stale)) + "줄")
    print(f"10열 → 13열: {len(rows)}행 변환. 새 3열(적합도·지역)은 비우고 최종 단계는 현재 진행상태로 채움. "
          + ("; ".join(header_note) if header_note else "머리말은 그대로 둠"))
    if not a.apply:
        print("미리보기만 했다. 적용하려면 --apply (백업 사본을 먼저 남긴다).")
        return 0
    t.save(rows, head_lines=J.HEADER.splitlines() if a.rewrite_header else None)
    print("적용함(사본은 Areas/취업/_백업/)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("find"); p.add_argument("--id"); p.add_argument("--company"); p.add_argument("--job")
    p = sub.add_parser("add")
    for k in ("company", "job", "link", "id", "channel", "deadline", "type", "memo", "fit", "region"):
        p.add_argument("--" + k)
    p = sub.add_parser("update-fit"); p.add_argument("--id"); p.add_argument("--company"); p.add_argument("--job"); p.add_argument("--fit"); p.add_argument("--region"); p.add_argument("--memo-add")
    p = sub.add_parser("set-status"); p.add_argument("--id"); p.add_argument("--company"); p.add_argument("--job"); p.add_argument("--state", required=True); p.add_argument("--note"); p.add_argument("--allow-back", action="store_true")
    p = sub.add_parser("undo-status"); p.add_argument("--apply", action="store_true")
    p = sub.add_parser("migrate"); p.add_argument("--apply", action="store_true"); p.add_argument("--rewrite-header", action="store_true")
    p = sub.add_parser("expire"); p.add_argument("--apply", action="store_true"); p.add_argument("--today")
    p = sub.add_parser("undo-expire"); p.add_argument("--apply", action="store_true"); p.add_argument("--id")
    a = ap.parse_args()
    if a.cmd == "add" and (not a.company or not a.job):
        J.die("--company 와 --job 이 필요하다", 2)
    return {"check": cmd_check, "list": cmd_list, "find": cmd_find, "add": cmd_add,
            "update-fit": cmd_update_fit, "set-status": cmd_set_status, "undo-status": cmd_undo_status, "migrate": cmd_migrate,
            "expire": cmd_expire, "undo-expire": cmd_undo_expire}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
