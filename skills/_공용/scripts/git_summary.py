#!/usr/bin/env python3
"""git 저장소 하나의 '메타'만 요약해 raw 폴더에 쓴다. 소스 코드는 읽지도 복사하지도 않는다.

쓰는 법:
  python -I -X utf8 git_summary.py <저장소 폴더> --out-dir <raw/내경험/깃허브/이름> --me a,b [--dry-run]
  python -I -X utf8 git_summary.py <저장소 폴더> --me a,b --brief      # 파일을 만들지 않고 한 줄 요약(JSON)만

만드는 것(--out-dir): 커밋요약.md · 작성자통계.md · 파일트리.md · README·docs의 md 문서 복사본
  - 작성자 통계는 사람별 커밋 수·기간·월별 수·'어느 최상위 폴더를 만졌는지'(변경 파일 수·줄 수). 성과 수치가 아니라 영역 판단용이다.
  - --me 의 이름들은 '나'로 표시한다. 어느 이름이 나인지는 사용자가 정한다(추정하지 않는다).
  - 비밀·개인정보가 걸린 문서는 복사하지 않고, 커밋 메시지는 걸린 줄만 가린다.
  - 이미 있는 파일은 덮어쓰지 않는다(있으면 멈추고 알림).
마지막에 결과를 JSON 한 줄로 낸다.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_common as jc  # noqa: E402

DOC_PATTERNS = ("README", "readme")
MAX_COMMITS_LISTED = 400


def git(repo, *args):
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=repo, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def collect(repo, me):
    remote = ""
    try:
        remote = git(repo, "remote", "get-url", "origin").strip()
    except RuntimeError:
        pass
    branch = git(repo, "branch", "--show-current").strip()
    branches = [b.strip().lstrip("* ").strip() for b in git(repo, "branch", "--format=%(refname:short)").splitlines()]
    base = "main" if "main" in branches else ("master" if "master" in branches else (branches[0] if branches else ""))
    ahead = {}
    for b in branches:
        if b != base and base:
            n = int(git(repo, "rev-list", "--count", f"{base}..{b}").strip() or 0)
            if n:
                ahead[b] = n

    commits = []
    for line in git(repo, "log", "--all", "--date=short", "--format=%h\x1f%ad\x1f%an\x1f%s").splitlines():
        h, d, a, s = line.split("\x1f", 3)
        commits.append({"hash": h, "date": d, "author": a, "subject": s})

    authors = defaultdict(lambda: {"commits": 0, "first": "9999", "last": "0000",
                                   "months": Counter(), "dirs": Counter(), "files": set(),
                                   "added": 0, "deleted": 0})
    cur = None
    for line in git(repo, "log", "--all", "--date=short", "--numstat", "--format=@@%an\x1f%ad").splitlines():
        if line.startswith("@@"):
            name, d = line[2:].split("\x1f")
            cur = authors[name]
            cur["commits"] += 1
            cur["first"] = min(cur["first"], d)
            cur["last"] = max(cur["last"], d)
            cur["months"][d[:7]] += 1
        elif line.strip() and cur is not None:
            parts = line.split("\t")
            if len(parts) == 3:
                add, dele, path = parts
                top = path.split("/")[0] if "/" in path else "(루트)"
                cur["dirs"][top] += 1
                cur["files"].add(path)
                cur["added"] += int(add) if add.isdigit() else 0
                cur["deleted"] += int(dele) if dele.isdigit() else 0

    tree = git(repo, "ls-files").splitlines()
    return {"remote": remote, "branch": branch, "base": base, "ahead": ahead, "commits": commits,
            "authors": authors, "tree": tree}


def origin_hint(info, me):
    """커밋 작성자 구성으로 origin '후보'만 낸다. 확정은 사용자."""
    a = info["authors"]
    mine = sum(v["commits"] for k, v in a.items() if k in me)
    others = {k: v["commits"] for k, v in a.items() if k not in me}
    if mine == 0:
        return "받은교재 후보(내 커밋 0)"
    if not others:
        return "본인작성 후보(작성자가 모두 나)"
    if len(others) == 1:
        k = next(iter(others))
        return f"미정 — 작성자 '{k}'({others[k]}커밋)가 내 다른 계정인지 확인 필요"
    return f"팀 후보(다른 작성자 {len(others)}명)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--out-dir")
    ap.add_argument("--me", default="")
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    opt = ap.parse_args()
    repo = Path(opt.repo)
    me = {x.strip() for x in opt.me.split(",") if x.strip()}
    if not (repo / ".git").exists():
        print(json.dumps({"error": "git 저장소가 아님"}, ensure_ascii=False))
        return 2
    info = collect(repo, me)
    a = info["authors"]
    brief = {
        "repo": str(repo), "remote": info["remote"], "branch": info["branch"], "base": info["base"],
        "ahead": info["ahead"], "commits": len(info["commits"]),
        "authors": {k: v["commits"] for k, v in sorted(a.items(), key=lambda kv: -kv[1]["commits"])},
        "mine": sum(v["commits"] for k, v in a.items() if k in me),
        "first": min((v["first"] for v in a.values()), default=""), "last": max((v["last"] for v in a.values()), default=""),
        "origin_hint": origin_hint(info, me),
    }
    if opt.brief or not opt.out_dir:
        print(json.dumps(brief, ensure_ascii=False))
        return 0

    out = Path(opt.out_dir)
    src = str(repo)
    head = lambda how, lim=None: jc.header(src, how, lim)  # noqa: E731
    files = {}

    # 커밋요약
    rows, redacted = [], 0
    for c in info["commits"][:MAX_COMMITS_LISTED]:
        subj = c["subject"]
        if jc.classify_line(subj):
            subj, redacted = "[가림: 비밀·개인정보 의심]", redacted + 1
        rows.append(f"| {c['date']} | {jc.md_cell(c['author'])} | {c['hash']} | {jc.md_cell(subj)} |")
    note = f"전체 {len(info['commits'])}커밋" + (f", 앞의 {MAX_COMMITS_LISTED}개만 실음" if len(info["commits"]) > MAX_COMMITS_LISTED else "")
    files["커밋요약.md"] = (head("git log --all 요약(소스 코드는 읽지 않음)", "커밋 메시지 줄 중 비밀·개인정보 의심은 가림")
                         + f"# 커밋 요약\n\n- 원격 주소: {info['remote'] or '(없음)'}\n- 현재 브랜치: {info['branch']}\n"
                         + (f"- 기준 브랜치({info['base']})보다 앞선 브랜치: " + ", ".join(f"{b}(+{n}커밋)" for b, n in info["ahead"].items()) + "\n" if info["ahead"] else "")
                         + f"- {note}\n\n| 날짜 | 작성자 | 해시 | 메시지 |\n|---|---|---|---|\n" + "\n".join(rows) + "\n")
    # 작성자통계
    parts = [head("git log --numstat 집계", "커밋 수·변경 줄 수는 성과가 아니라 '어느 영역을 만졌는지' 보는 용도"),
             "# 작성자 통계\n\n"
             f"- 내 이름으로 지정된 작성자: {', '.join(sorted(me)) or '(지정 안 됨)'}\n- origin 후보: {brief['origin_hint']}\n\n"
             "| 작성자 | 나 | 커밋 | 첫 커밋 | 마지막 커밋 | 변경 파일 수 | 추가 줄 | 삭제 줄 |\n|---|---|---|---|---|---|---|---|\n"]
    for k, v in sorted(a.items(), key=lambda kv: -kv[1]["commits"]):
        parts.append(f"| {jc.md_cell(k)} | {'O' if k in me else ''} | {v['commits']} | {v['first']} | {v['last']} | {len(v['files'])} | {v['added']} | {v['deleted']} |\n")
    parts.append("\n## 작성자별 월별 커밋 수\n\n")
    for k, v in sorted(a.items(), key=lambda kv: -kv[1]["commits"]):
        parts.append(f"- {k}: " + ", ".join(f"{m} {n}" for m, n in sorted(v["months"].items())) + "\n")
    parts.append("\n## 작성자별로 만진 최상위 폴더(변경 파일 건수 합)\n\n")
    for k, v in sorted(a.items(), key=lambda kv: -kv[1]["commits"]):
        parts.append(f"- {k}: " + ", ".join(f"{d} {n}" for d, n in v["dirs"].most_common()) + "\n")
    files["작성자통계.md"] = "".join(parts)
    # 파일트리(2단계)
    seen = Counter()
    for p in info["tree"]:
        seen["/".join(p.split("/")[:2])] += 1
    files["파일트리.md"] = (head("git ls-files 를 2단계까지 묶음") + "# 파일 트리 (2단계, 괄호는 파일 수)\n\n"
                         + "\n".join(f"- {k} ({n})" for k, n in sorted(seen.items())) + "\n")
    # 문서 복사(README, docs/**/*.md)
    skipped_docs = []
    for p in info["tree"]:
        low = p.lower()
        is_doc = (p.split("/")[-1].startswith(DOC_PATTERNS) and low.endswith(".md")) or (low.startswith("docs/") and low.endswith(".md"))
        if not is_doc:
            continue
        text = git(repo, "show", f"HEAD:{p}")
        if jc.scan_text(text):
            skipped_docs.append(p)
            continue
        files["문서/" + p.replace("/", "__")] = jc.header(f"{src} 의 {p}(HEAD)", "git show 로 문서 복사", None) + text

    result = {"out_dir": str(out), "written": [], "skipped_docs_secret": skipped_docs, "redacted_commit_subjects": redacted,
              "brief": brief}
    for rel, text in files.items():
        dst = out / rel
        if dst.exists():
            result["conflict"] = str(dst)
            print(json.dumps(result, ensure_ascii=False))
            return 5
    if not opt.dry_run:
        for rel, text in files.items():
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8", newline="\n")
            result["written"].append(str(dst))
    else:
        result["written"] = [str(out / r) for r in files]
        result["dry_run"] = True
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
