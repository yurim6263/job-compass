#!/usr/bin/env python3
"""간단한 markdown → .docx 내보내기(표준 라이브러리 zipfile만). 볼트 루트에서 실행한다.

쓰는 법:
  python -I -X utf8 docx_export.py <입력.md> <출력.docx> [--section 최종] [--note "사본 — 정본은 …"]

지원: `#`·`##`·`###` 제목(굵게·크게) · 일반 문단 · `- ` 목록(• 로) · `|` 표 · 빈 줄로 문단 나눔.
무시: `<!-- -->` 주석 · frontmatter(`---`) · `>` 인용(메모) 줄.
머리에 "사본 — 정본은 …, 생성일 YYYY-MM-DD"를 적는다. 출력 파일은 덮어써도 되는 사본이다(`Areas/취업/내보내기/`).
※ 최소 구조로 만든다. Word에서 열리는지는 이 저장소에서 아직 시험하지 않았다(글자는 압축 안 XML에서 읽힘을 확인). 서식이 필요하면 `docx` 스킬을 쓴다.
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jc_job as J  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def para(text, bold=False, size=None):
    rpr = ""
    if bold or size:
        rpr = "<w:rPr>" + ("<w:b/>" if bold else "") + (f'<w:sz w:val="{size}"/>' if size else "") + "</w:rPr>"
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def md_to_body(md):
    out, rows = [], []

    def flush():
        nonlocal rows
        if rows:
            def cell(c, bold):
                rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
                return f'<w:tc><w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(c)}</w:t></w:r></w:p></w:tc>'
            trs = "".join("<w:tr>" + "".join(cell(c, i == 0) for c in r) + "</w:tr>" for i, r in enumerate(rows))   # 첫 줄(머리)은 굵게
            line = lambda side: f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
            pr = ("<w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/><w:tblBorders>"
                  + "".join(line(s) for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + "</w:tblBorders></w:tblPr>")
            ncols = max(len(r) for r in rows)
            grid = "<w:tblGrid>" + "".join('<w:gridCol w:w="2000"/>' for _ in range(ncols)) + "</w:tblGrid>"
            out.append(f"<w:tbl>{pr}{grid}{trs}</w:tbl>")
            rows = []

    for ln in md.splitlines():
        s = ln.rstrip()
        if s.lstrip().startswith("|"):
            cells = J.split_row(s)
            if re.match(r"^[\s:-]+$", "".join(cells)):
                continue
            rows.append([c.replace("\\|", "|") for c in cells])
            continue
        flush()
        t = s.strip()
        if not t or t.startswith((">", "<!--")) or t == "---":
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", t)
        if m:
            out.append(para(m.group(2), bold=True, size={1: 36, 2: 30, 3: 26}[len(m.group(1))]))
        elif t.startswith(("- ", "* ")):
            out.append(para("• " + t[2:]))
        else:
            out.append(para(re.sub(r"[*_`]", "", t)))
    flush()
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--section")
    ap.add_argument("--note")
    a = ap.parse_args()
    md = Path(a.src).read_text(encoding="utf-8")
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    if a.section:
        m = re.search(rf"^##\s+{re.escape(a.section)}.*$", md, flags=re.M)
        if not m:
            sys.exit(f"`## {a.section}` 절을 찾지 못했다")
        rest = md[m.end():]
        n = re.search(r"^##\s+(?!#)", rest, flags=re.M)
        md = rest[: n.start()] if n else rest
    note = a.note or f"사본 — 정본은 {Path(a.src).name}, 생성일 {J.today_kst().isoformat()}"
    body = para(note, size=18) + md_to_body(md)
    doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>'
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    dst = Path(a.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
    print(f"만듦: {dst} (문단 {body.count('<w:p>')}개, 표 {body.count('<w:tbl>')}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
