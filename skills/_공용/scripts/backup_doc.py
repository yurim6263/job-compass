#!/usr/bin/env python3
"""볼트 문서를 고치기 전에 수정 전 사본을 `Areas/취업/_백업/<폴더>/` 에 남긴다. 볼트 루트에서 실행한다.

쓰는 법:
  python -I -X utf8 backup_doc.py <파일> [--dir 경험문서]
  → `Areas/취업/_백업/경험문서/<파일이름>.bak-YYYYMMDD-HHMMSS` 를 만들고 그 경로를 출력한다.
    가장 최근 사본과 내용이 같으면 새로 만들지 않고 "이미 같은 사본이 있음"으로 그 경로를 출력한다.
    wiki/ 폴더에 사본 파일이 쌓이지 않게 하려는 것이다. 자동 삭제는 하지 않는다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--dir", default="경험문서")
    a = ap.parse_args()
    p = Path(a.file)
    if not p.is_file():
        print(f"파일이 없다: {p}")
        return 2
    before = set(J.BACKUP_DIR.joinpath(a.dir).glob(f"{p.name}.bak-*")) if J.BACKUP_DIR.joinpath(a.dir).exists() else set()
    dst = J.backup_file(p, subdir=a.dir)
    print(("이미 같은 사본이 있음: " if dst in before else "사본 만듦: ") + str(dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
