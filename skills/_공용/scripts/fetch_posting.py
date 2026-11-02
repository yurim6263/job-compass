#!/usr/bin/env python3
"""공고 1건의 원본 HTML을 받아 보이는 글자만 txt로 뽑는다. 볼트 루트에서 실행한다. 표준 라이브러리만 쓴다.

쓰는 법:
  python -I -X utf8 fetch_posting.py <공고 ID> [--url <공고 주소>] [--out-dir Areas/취업/_scan-cache]
    공고 ID: jobkorea:N · saramin:N (주소를 알아서 만든다) · 그 밖은 --url 필수(같은 호스트의 주소만 받는다)
  결과: <out-dir>/<이름>/ 에 원본 html(받은 그대로)과 txt, 마지막 줄에 JSON 한 줄
        {"id","dir","files":[{"kind","status","html","txt","chars"}],"body_likely":bool,"deadline_hint":"YYYY-MM-DD"|"상시"|null,"career":"경력 3년이상"|null,"note"}
        요약 txt 맨 위에는 사이트 요약 칸(설명 메타: 경력·학력·마감일 등)을 `요약 칸:` 줄로 그대로 붙인다
  종료 코드: 0 받음(본문 여부는 body_likely) / 3 받지 못함(403·404·연결 실패) / 2 입력 오류

왜 있나: 무인 실행(예약 스캔)에서는 셸 변수·복합 명령이 막혀 curl+perl 여러 단계가 끊긴다. 이 스크립트는 한 줄 명령으로 같은 일을 한다.
규칙:
  - 사람이 보는 정도로만: 한 번에 공고 1건(요약 + 상세요강 최대 2요청), 요청 사이 1초.
  - 본문 속 링크는 따라가지 않는다. 사이트별로 정해진 상세요강 주소만 받는다(fetch-and-raw.md 1단계와 같음).
  - 글자는 고치지 않는다(태그·스크립트만 걷어 냄). 판단(본문인지·요건이 무엇인지)은 모델이 txt를 읽고 한다.
  - 쓰는 곳은 <out-dir>/<이름>/ 뿐이다. raw·wiki 는 만들지 않는다(정식 저장은 /job-posting).
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BODY_WORDS = ["자격", "담당", "업무", "우대", "모집", "전형", "근무", "지원 요건", "필수"]


def targets(pid, url):
    site, _, n = pid.partition(":")
    if site == "jobkorea" and n.isdigit():
        main = f"https://www.jobkorea.co.kr/Recruit/GI_Read/{n}"
        return main, [("요약", main), ("상세", f"https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno={n}")]
    if site == "saramin" and n.isdigit():
        main = f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={n}"
        return main, [("요약", f"https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={n}"),
                      ("상세", f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={n}&rec_seq=0")]
    if not url:
        raise ValueError("jobkorea:N · saramin:N 이 아니면 --url 이 필요하다")
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError("http(s) 주소가 아님")
    return url, [("요약", url)]


def get(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": referer})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e)[:80], b""


def decode(raw, ctype):
    m = re.search(r"charset=([\w-]+)", ctype, re.I) or re.search(rb"charset=[\"']?([\w-]+)", raw[:4000], re.I)
    cs = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)).lower() if m else "utf-8"
    if cs in ("euc-kr", "ks_c_5601-1987", "cp949"):
        cs = "cp949"
    try:
        return raw.decode(cs)
    except (LookupError, UnicodeDecodeError):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp949", errors="replace")


def to_text(s):
    """fetch-and-raw.md 의 perl 한 줄과 같은 규칙: 보이는 글자만, 글자는 바꾸지 않는다."""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<(script|style|noscript|template|svg|head|button|select|iframe)\b.*?</\1\s*>", "", s, flags=re.S | re.I)
    s = re.sub(r"<br\b[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<li\b[^>]*>", "\n- ", s, flags=re.I)
    s = re.sub(r"<h([1-6])\b[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", s, flags=re.I)
    s = re.sub(r"</?(p|div|tr|section|article|dt|dd|dl|table|ul|ol|h[1-6]|header|footer|nav|main|aside|form|figure|blockquote|pre|tbody|thead)\b[^>]*>",
               "\n", s, flags=re.I)
    s = re.sub(r"<t[dh]\b[^>]*>", " | ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t\r]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    s = re.sub(r"\n(?:[-|] ?\n)+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


def meta_summary(raw_html):
    """<head>의 설명 메타(사이트 요약 칸: 경력·학력·마감일 등). txt 맨 위에 그대로 붙인다(글자를 바꾸지 않음)."""
    out = []
    for m in re.finditer(r"<meta\b[^>]*(?:name|property)=[\"'](?:description|og:description)[\"'][^>]*>", raw_html, flags=re.I):
        c = re.search(r"content=[\"']([^\"']*)", m.group(0), flags=re.I)
        if c:
            v = html.unescape(c.group(1)).strip()
            if v and v not in out:
                out.append(v)
    return out


def iso_date(s):
    d = re.search(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})", s)
    return f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else None


def career_hint(metas):
    """사이트 요약 칸의 경력 값(예: '경력 3년이상'·'신입·경력'·'경력무관'·'경력'). 없으면 None"""
    for v in metas:
        m = re.search(r"경력\s*:\s*([^,]+)", v)
        if m:
            return m.group(1).strip() or None
    return None


def deadline_hint(metas, text):
    """마감일 힌트: 요약 칸의 `마감일 : …` → 본문의 `마감일` 바로 다음 줄. 'YYYY-MM-DD' · '상시' · None. 힌트일 뿐 — 모델이 txt에서 확인한다."""
    for v in metas:
        m = re.search(r"마감일\s*:\s*([^,]+)", v)
        if m:
            val = m.group(1).strip()
            return "상시" if "상시" in val else iso_date(val)
    m = re.search(r"마감일\s*\n+\s*([^\n]+)", text)
    if m:
        val = m.group(1)
        return "상시" if "상시" in val else iso_date(val)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--url")
    ap.add_argument("--out-dir", default="Areas/취업/_scan-cache")
    a = ap.parse_args()
    pid = a.id.strip()
    try:
        main_url, reqs = targets(pid, a.url)
    except ValueError as e:
        print(json.dumps({"id": pid, "error": str(e)}, ensure_ascii=False))
        return 2
    name = re.sub(r"[^\w.-]", "-", pid.replace(":", "-"))[:80]
    out = Path(a.out_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    files, texts, all_metas = [], [], []
    for i, (kind, url) in enumerate(reqs):
        if i:
            time.sleep(1)
        st, ctype, raw = get(url, main_url)
        rec = {"kind": kind, "status": st}
        if st == 200 and raw:
            suffix = "" if kind == "요약" else "-상세"
            hp, tp = out / f"{name}{suffix}.html", out / f"{name}{suffix}.txt"
            hp.write_bytes(raw)
            page = decode(raw, ctype)
            metas = meta_summary(page) if kind == "요약" else []
            head = "".join(f"요약 칸: {v}\n" for v in metas)
            t = (head + "\n" if head else "") + to_text(page)
            all_metas += metas
            tp.write_text(t, encoding="utf-8", newline="\n")
            texts.append(t)
            rec.update(html=str(hp), txt=str(tp), chars=len(t))
        elif st == 0:
            rec["error"] = ctype
        files.append(rec)
    got = [f for f in files if f["status"] == 200]
    joined = "\n".join(texts)
    hits = sum(1 for w in BODY_WORDS if w in joined)
    res = {"id": pid, "dir": str(out), "files": files, "body_likely": hits >= 2,
           "deadline_hint": deadline_hint(all_metas, joined) if joined else None,
           "career": career_hint(all_metas),
           "note": ("받음" if got else "받지 못함(" + ",".join(str(f["status"]) for f in files) + ")")
           + ("" if hits >= 2 else " · 본문 낱말이 적음 — 그림·스크립트 공고일 수 있음, 점수 없이 미산출")}
    print(json.dumps(res, ensure_ascii=False))
    return 0 if got else 3


if __name__ == "__main__":
    sys.exit(main())
