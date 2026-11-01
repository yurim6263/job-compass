#!/usr/bin/env python3
"""들일 자료의 범위를 훑어 '들일 것 / 건너뛸 것 / 저장소'로 나눠 보여 준다. 아무것도 쓰지 않는다(읽기 전용).

쓰는 법:
  python -I -X utf8 scan_inputs.py <폴더 또는 파일> [<폴더 또는 파일> ...] --me a,b [--json 결과.json]
  (--json 에 파일 이름만 주면 `Areas/취업/_scan-cache/intake/` 에 만든다. 볼트 루트에는 임시 파일을 두지 않는다)

하는 일(기획 01 §3 단계 1~3):
  - 폴더를 훑는다. git 저장소(.git 있는 폴더)는 한 덩어리로 보고 작성자 구성으로 origin 후보를 낸다.
  - 건너뛸 것: node_modules·build·압축·모델 파일·이미지·~$·handoff_* 등과 비밀 파일 이름(.env 등). 이유를 적는다.
  - `개인정보/` 같은 폴더는 안의 파일 이름도 적지 않고 개수만 센다.
  - 들일 파일은 내용을 첫 200KB까지 훑어 비밀·개인정보 의심 줄 수를 센다(걸린 값은 출력하지 않는다).
  - 저장소 안에 있는 비밀 파일·빌드 폴더도 '건너뜀'으로 보고한다(저장소는 복사하지 않지만 있다는 사실은 알린다).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_common as jc  # noqa: E402

KIND = {".md": "text", ".txt": "text", ".csv": "text", ".json": "text",
        ".docx": "워드", ".pptx": "ppt", ".pdf": "pdf", ".xlsx": "엑셀", ".ipynb": "노트북",
        ".hwp": "hwp", ".hwpx": "hwp"}
EXTRACTABLE = {".md", ".txt", ".csv", ".docx", ".pptx", ".pdf", ".xlsx", ".ipynb", ".hwp", ".hwpx"}
SNIFF_BYTES = 200 * 1024
SCAN_CACHE = Path("Areas/취업/_scan-cache/intake")   # 임시 결과 폴더(지워도 됨). `.claude/` 밖: 무인 실행에서 `.claude/` 쓰기가 막힘


def sniff(path):
    """깨끗한 글자 파일만 내용 검사. 그 밖의 형식은 추출 단계에서 검사한다."""
    if path.suffix.lower() not in (".md", ".txt", ".csv"):
        return None
    try:
        text = path.read_bytes()[:SNIFF_BYTES].decode("utf-8", errors="replace")
    except OSError:
        return None
    hits = jc.scan_text(text)
    return {"비밀값": sum(1 for _, k in hits if k == "비밀값"), "개인정보": sum(1 for _, k in hits if k == "개인정보")}


def git_brief(repo, me):
    script = Path(__file__).resolve().parent / "git_summary.py"
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(script), str(repo), "--me", ",".join(me), "--brief"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": (r.stderr or r.stdout).strip()[:200]}


def walk(root, me, out, in_repo=False):
    """root 아래를 훑는다. in_repo 이면 '건너뜀' 보고만 하고 들일 파일은 모으지 않는다."""
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.is_dir():
            if p.name in jc.PRIVACY_DIRS:
                n = sum(1 for _ in p.rglob("*") if _.is_file())
                out["skipped"].append({"path": str(p), "reason": f"개인정보 폴더 — 파일 {n}개 건너뜀(이름도 적지 않음)"})
                continue
            if p.name in jc.SKIP_DIRS:
                if p.name != ".git":
                    n = sum(1 for _ in p.rglob("*") if _.is_file())
                    out["skipped"].append({"path": str(p), "reason": f"제외 폴더({p.name}) — 파일 {n}개"})
                continue
            if (p / ".git").exists() and not in_repo:
                brief = git_brief(p, me)
                out["repos"].append({"path": str(p), **brief})
                walk(p, me, out, in_repo=True)
                continue
            walk(p, me, out, in_repo)
        elif p.is_file():
            why = jc.skip_reason(p)
            if why:
                out["skipped"].append({"path": str(p), "reason": why})
            elif in_repo:
                continue          # 저장소 안의 일반 파일은 git_summary가 맡는다
            else:
                ext = p.suffix.lower()
                if ext not in EXTRACTABLE:
                    out["skipped"].append({"path": str(p), "reason": f"지원하지 않는 형식({ext or '확장자 없음'})"})
                    continue
                item = {"path": str(p), "kind": KIND.get(ext, "기타"), "size": p.stat().st_size,
                        "size_h": jc.fmt_size(p.stat().st_size), "sha": jc.sha256_file(p)}
                if ext in (".hwp", ".hwpx"):
                    item["note"] = "hwp — 한글이 있으면 동의 후 PDF 변환(--hwp-convert), 없으면 미수집(PDF 요청)"
                s = sniff(p)
                if s:
                    item["sniff"] = s
                out["files"].append(item)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--me", default="")
    ap.add_argument("--json")
    opt = ap.parse_args()
    me = [x.strip() for x in opt.me.split(",") if x.strip()]
    out = {"files": [], "repos": [], "skipped": []}
    for s in opt.paths:
        p = Path(s)
        if not p.exists():
            out["skipped"].append({"path": s, "reason": "경로가 없음"})
        elif p.is_file():
            why = jc.skip_reason(p)
            if why:
                out["skipped"].append({"path": s, "reason": why})
            else:
                ext = p.suffix.lower()
                out["files"].append({"path": s, "kind": KIND.get(ext, "기타"), "size": p.stat().st_size,
                                     "size_h": jc.fmt_size(p.stat().st_size), "sha": jc.sha256_file(p), "sniff": sniff(p)})
        elif (p / ".git").exists():
            out["repos"].append({"path": str(p), **git_brief(p, me)})
            walk(p, me, out, in_repo=True)
        else:
            walk(p, me, out)

    if opt.json:
        jp = Path(opt.json)
        if len(jp.parts) == 1:   # 파일 이름만 줬으면 볼트 루트에 흩어지지 않게 임시 폴더로 보낸다(무인 실행에서 지울 수 없는 파일이 생기는 것을 막음)
            jp = SCAN_CACHE / jp.name
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"(결과 JSON: {jp})")

    print(f"# 범위 확인 — 들일 파일 {len(out['files'])}개 · 저장소 {len(out['repos'])}개 · 건너뜀 {len(out['skipped'])}건\n")
    print("## 들일 파일\n\n| 경로 | 형태 | 크기 | 비밀·개인정보 의심 줄 | 메모 |\n|---|---|---|---|---|")
    for f in out["files"]:
        s = f.get("sniff") or {}
        flag = f"비밀 {s.get('비밀값', 0)} · 개인 {s.get('개인정보', 0)}" if s else "(추출 때 검사)"
        print(f"| {f['path']} | {f['kind']} | {f['size_h']} | {flag} | {f.get('note', '')} |")
    print("\n## 저장소\n\n| 경로 | 원격 | 커밋 | 작성자(커밋) | 내 커밋 | 앞선 브랜치 | 기간 | origin 후보 |\n|---|---|---|---|---|---|---|---|")
    for r in out["repos"]:
        if "error" in r:
            print(f"| {r['path']} | (오류: {r['error']}) | | | | | | |")
            continue
        au = ", ".join(f"{k}({v})" for k, v in r["authors"].items())
        ah = ", ".join(f"{k}+{v}" for k, v in r["ahead"].items()) or "-"
        print(f"| {r['path']} | {r['remote']} | {r['commits']} | {au} | {r['mine']} | {ah} | {r['first']}~{r['last']} | {r['origin_hint']} |")
    print("\n## 건너뜀\n\n| 경로 | 이유 |\n|---|---|")
    for s in out["skipped"]:
        print(f"| {s['path']} | {s['reason']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
