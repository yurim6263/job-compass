#!/usr/bin/env python3
"""파일 하나에서 글자를 뽑아 추출본(md)을 만든다. 손으로 옮기지 않고 도구로 뽑는다.

쓰는 법:
  python -I -X utf8 extract_text.py <파일> --out-dir <폴더> [--copy-original] [--max-rows 20]
  python -I -X utf8 extract_text.py <파일> --stdout          # 파일을 만들지 않고 화면에만(증명서 사실 확인용)

형식: .md .txt .csv → 그대로 / .docx .pptx → 압축 안 XML(zipfile) / .xlsx → openpyxl /
      .pdf → pypdf / .ipynb → 마크다운 셀 + 출력 요약(코드 셀 제외) /
      .hwp .hwpx → --hwp-convert 를 주면 한글(COM)로 PDF 변환 후 pypdf(hwp_to_pdf.ps1), 아니면 hwp5txt 가 있을 때만
  python -I -X utf8 extract_text.py --hwp-check   # 한글 자동 조작이 되는지만 확인

규칙(기획 01 §3):
  - 비밀값·개인정보 줄은 '[가림: 종류]'로 바꿔서 쓴다. 이 검사에 걸린 문서는 원본 복사를 하지 않는다.
  - 이름이 같은 파일이 이미 있으면 멈춘다(덮어쓰지 않음). 원본 복사는 20MB 이하만, 복사 뒤 바이트 비교(cmp)로 확인.
  - 글자 없는 PDF·읽지 못한 hwp는 파일을 만들지 않고 종료 코드로 알린다.

종료 코드: 0 성공 / 2 지원하지 않는 형식 / 3 글자 없는 PDF(이미지형 의심) / 4 읽지 못한 hwp /
          5 같은 이름 파일이 있어 멈춤 / 6 읽는 중 오류
마지막 줄에 결과를 JSON 한 줄로 낸다: {"out","original","sha","redacted","note"}
"""
import argparse
import filecmp
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_common as jc  # noqa: E402

MAX_COPY = 20 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class Unreadable(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def md_table(rows):
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [list(r) + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(jc.md_cell(c) for c in rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(jc.md_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out) + "\n"


def read_docx(path, _opt):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(f"{W}body")
    parts = []

    def para_text(p):
        s = []
        for el in p.iter():
            if el.tag == f"{W}t" and el.text:
                s.append(el.text)
            elif el.tag in (f"{W}tab",):
                s.append("\t")
            elif el.tag in (f"{W}br",):
                s.append("\n")
        return "".join(s).strip()

    for child in body:
        if child.tag == f"{W}p":
            t = para_text(child)
            if t:
                parts.append(t + "\n")
        elif child.tag == f"{W}tbl":
            rows = []
            for tr in child.iter(f"{W}tr"):
                rows.append([" ".join(para_text(p) for p in tc.iter(f"{W}p")).strip() for tc in tr.findall(f"{W}tc")])
            parts.append(md_table(rows))
    return "\n".join(parts), "docx 압축을 풀어 본문 XML에서 글자 추출", "이미지·도형·머리글·바닥글 안 글자는 없음. 제목 서식은 구분하지 않음"


def read_pptx(path, _opt):
    import re
    with zipfile.ZipFile(path) as z:
        names = z.namelist()

        def num(n):
            return int(re.search(r"(\d+)\.xml$", n).group(1))

        slides = sorted([n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)], key=num)
        notes = {num(n): n for n in names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)}
        out = []
        for n in slides:
            i = num(n)
            root = ET.fromstring(z.read(n))
            paras = ["".join(t.text or "" for t in p.iter(f"{A}t")) for p in root.iter(f"{A}p")]
            out.append(f"## 슬라이드 {i}\n\n" + "\n".join(f"- {t}" for t in paras if t.strip()) + "\n")
            if i in notes:
                nroot = ET.fromstring(z.read(notes[i]))
                npar = ["".join(t.text or "" for t in p.iter(f"{A}t")) for p in nroot.iter(f"{A}p")]
                ntext = " ".join(t for t in npar if t.strip())
                if ntext:
                    out.append(f"> 발표자 노트: {ntext}\n")
    return "\n".join(out), "pptx 압축을 풀어 슬라이드 XML에서 글자 추출", "슬라이드 이미지·도형 안 그림 글자는 없음"


def read_xlsx(path, opt):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        total = 0
        for r in ws.iter_rows(values_only=True):
            if all(c is None for c in r):
                continue
            total += 1
            if len(rows) <= opt.max_rows:
                rows.append(["" if c is None else str(c) for c in r])
        out.append(f"## 시트: {ws.title}\n\n- 열 이름(첫 행): {', '.join(rows[0]) if rows else '(비어 있음)'}\n"
                   f"- 행 수(첫 행 포함, 빈 행 제외): {total}\n- 아래는 상위 {min(len(rows), opt.max_rows + 1)}행\n\n{md_table(rows)}")
    return "\n".join(out), "openpyxl로 시트별 표를 md로 변환", "수식·서식은 없음(저장된 계산 값만). 상위 행만 실음"


def read_pdf(path, _opt):
    from pypdf import PdfReader
    r = PdfReader(str(path))
    pages = [(p.extract_text() or "").strip() for p in r.pages]
    total = sum(len(t) for t in pages)
    if total < 10 * max(1, len(pages)):      # 쪽당 10자 미만이면 글자가 없다고 본다
        raise Unreadable(3, f"글자가 거의 없음({total}자, {len(pages)}쪽) — 이미지형 PDF 의심")
    text = "\n".join(f"## 쪽 {i}\n\n{t}\n" for i, t in enumerate(pages, 1))
    return text, "pypdf로 쪽별 글자 추출", "표·토글이 풀려 보일 수 있음. PDF 변환본"


def read_ipynb(path, _opt):
    nb = json.loads(Path(path).read_text(encoding="utf-8"))
    out, code_n = [], 0
    for c in nb.get("cells", []):
        src = "".join(c.get("source", []))
        if c["cell_type"] == "markdown":
            out.append(src + "\n")
        elif c["cell_type"] == "code":
            code_n += 1
            for o in c.get("outputs", []):
                t = "".join(o.get("text", [])) if o.get("output_type") == "stream" else \
                    "".join(o.get("data", {}).get("text/plain", []))
                if t.strip():
                    out.append("> 출력: " + " ".join(t.split())[:500] + "\n")
    out.append(f"\n(코드 셀 {code_n}개는 들이지 않음)\n")
    return "\n".join(out), "노트북의 마크다운 셀과 코드 셀 출력 요약만 추출", "코드 셀 본문·그림 출력은 없음. 출력은 500자까지"


HWP_PS = Path(__file__).resolve().parent / "hwp_to_pdf.ps1"
HWP_CACHE = Path("Areas/취업/_scan-cache/intake/hwp-pdf")


def run_hwp_ps(args, timeout):
    """hwp_to_pdf.ps1 을 부르고 (종료 코드, 마지막 줄 JSON)을 돌려준다. PowerShell 이 없으면 (2, {})."""
    ps = shutil.which("powershell") or shutil.which("powershell.exe")
    if not ps or not HWP_PS.exists():
        return 2, {"ok": False, "note": "PowerShell 또는 hwp_to_pdf.ps1 없음"}
    try:
        r = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HWP_PS)] + args,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 7, {"ok": False, "note": "변환 스크립트가 끝나지 않음"}
    lines = [ln for ln in r.stdout.strip().splitlines() if ln.strip()]
    try:
        info = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        info = {"note": lines[-1] if lines else r.stderr.strip()[:200]}
    return r.returncode, info


def hwp_via_hancom(path, opt):
    """한글(COM)로 PDF를 만든 뒤 pypdf로 읽는다. 원본은 읽기만 하고, PDF는 임시 폴더(--hwp-cache)에 둔다."""
    cache = Path(opt.hwp_cache)
    pdf = cache / f"{jc.sha256_file(path)[:12]}_{Path(path).name}.pdf"   # 내용이 같으면 같은 이름 → 다시 돌리면 재사용
    if not pdf.exists():
        code, info = run_hwp_ps(["-Src", str(path), "-Out", str(pdf), "-TimeoutSeconds", str(opt.hwp_timeout)],
                                timeout=opt.hwp_timeout + 40)
        if code != 0 or not pdf.exists():
            raise Unreadable(4, f"한글로 PDF 변환 실패: {info.get('note', '')} — PDF로 저장해 달라고 요청")
    try:
        text, _how, _lim = read_pdf(pdf, opt)
    except Unreadable:
        raise Unreadable(4, "한글로 PDF는 만들었지만 글자가 거의 없음(그림만 있는 문서일 수 있음) — 내용을 붙여넣어 달라고 요청")
    return (text, "한글(COM)로 PDF 변환 → pypdf로 쪽별 글자 추출",
            f"그림 속 글자는 없음. 표는 칸 구분 없이 줄글로 풀림. 변환 PDF: {pdf.as_posix()}")


def read_hwp(path, opt):
    if getattr(opt, "hwp_convert", False):
        return hwp_via_hancom(path, opt)
    exe = shutil.which("hwp5txt")
    if not exe:
        raise Unreadable(4, "hwp를 읽지 못함 — 한글이 있으면 --hwp-convert 로 PDF 변환, 없으면 PDF로 저장해 달라고 요청")
    r = subprocess.run([exe, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = r.stdout.strip()
    if r.returncode != 0 or len(text) < 30:
        raise Unreadable(4, "hwp에서 글자를 거의 못 뽑음 — PDF로 저장해 달라고 요청")
    return text, "pyhwp의 hwp5txt로 글자 추출", "표 안 글자는 <표> 자리표시로만 나옴. 그림만 있는 파일은 거의 빈 결과"


def read_text(path, _opt):
    return Path(path).read_text(encoding="utf-8", errors="replace"), "그대로 읽음", None


READERS = {".docx": read_docx, ".pptx": read_pptx, ".xlsx": read_xlsx, ".pdf": read_pdf,
           ".ipynb": read_ipynb, ".hwp": read_hwp, ".hwpx": read_hwp,
           ".md": read_text, ".txt": read_text, ".csv": read_text}


def safe_copy(src, dst):
    """덮어쓰지 않는 복사 + 바이트 비교."""
    dst = Path(dst)
    if dst.exists():
        raise Unreadable(5, f"같은 이름 파일이 이미 있음: {dst}")
    shutil.copy2(src, dst)
    if not filecmp.cmp(src, dst, shallow=False):
        raise Unreadable(6, f"복사본이 원본과 다름: {dst}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("--out-dir")
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--copy-original", action="store_true")
    ap.add_argument("--max-rows", type=int, default=20)
    ap.add_argument("--hwp-convert", action="store_true", help="hwp·hwpx를 한글(COM)로 PDF 변환해 읽는다(사용자 동의 후)")
    ap.add_argument("--hwp-cache", default=str(HWP_CACHE), help="변환 PDF를 둘 임시 폴더(볼트 기준)")
    ap.add_argument("--hwp-timeout", type=int, default=60)
    ap.add_argument("--hwp-check", action="store_true", help="한글 자동 조작이 되는지만 확인(0 가능 / 2 불가)")
    opt = ap.parse_args()

    if opt.hwp_check:
        code, info = run_hwp_ps(["-Check"], timeout=60)
        print(json.dumps({"hancom": code == 0, "note": info.get("note", "")}, ensure_ascii=False))
        return 0 if code == 0 else 2
    if not opt.src:
        ap.error("파일 경로가 필요함")

    src = Path(opt.src)
    ext = src.suffix.lower()
    res = {"out": None, "original": None, "sha": None, "redacted": {}, "note": ""}
    try:
        if not src.is_file():
            raise Unreadable(6, f"파일이 없음: {src}")
        r = jc.skip_reason(src)
        if r:
            raise Unreadable(2, f"들이지 않는 파일: {r}")
        if ext not in READERS:
            raise Unreadable(2, f"지원하지 않는 형식: {ext}")
        res["sha"] = jc.sha256_file(src)
        text, how, limits = READERS[ext](src, opt)
        clean_text, counts = jc.redact_text(text)
        res["redacted"] = counts
        if counts:
            limits = (limits + "; " if limits else "") + f"비밀·개인정보 의심 줄을 가림({sum(counts.values())}줄) — 원본은 복사하지 않음"
        is_text = ext in (".md", ".txt", ".csv")
        body = clean_text
        if not is_text or counts:
            body = jc.header(str(src), how, limits, res["sha"]) + clean_text
        if opt.stdout:
            sys.stdout.write(body)
            print("\n" + json.dumps(res, ensure_ascii=False))
            return 0
        if not opt.out_dir:
            raise Unreadable(6, "--out-dir 또는 --stdout 이 필요함")
        out_dir = Path(opt.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        # 글자 파일은 깨끗하면 원본 그대로 복사가 곧 추출본이다
        if is_text and not counts:
            dst = out_dir / src.name
            safe_copy(src, dst)
            res["out"] = str(dst)
            res["original"] = str(dst)
        else:
            dst = out_dir / (src.name + ".md")
            if dst.exists():
                raise Unreadable(5, f"같은 이름 파일이 이미 있음: {dst}")
            dst.write_text(body, encoding="utf-8", newline="\n")
            res["out"] = str(dst)
            if opt.copy_original and not counts and not is_text:
                if src.stat().st_size > MAX_COPY:
                    res["note"] = "원본이 20MB를 넘어 복사하지 않음(추출본만)"
                else:
                    odst = out_dir / src.name
                    safe_copy(src, odst)
                    res["original"] = str(odst)
            elif counts:
                res["note"] = "비밀·개인정보 의심 줄이 있어 원본은 복사하지 않음"
        print(json.dumps(res, ensure_ascii=False))
        return 0
    except Unreadable as e:
        res["note"] = str(e)
        print(json.dumps(res, ensure_ascii=False))
        return e.code
    except Exception as e:  # noqa: BLE001 - 읽는 중 오류는 종료 코드로 알린다
        res["note"] = f"읽는 중 오류: {type(e).__name__}: {e}"
        print(json.dumps(res, ensure_ascii=False))
        return 6


if __name__ == "__main__":
    sys.exit(main())
