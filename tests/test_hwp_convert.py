"""hwp → PDF 변환(한글 COM) 시험.

한글이 설치되지 않은 PC에서는 실제 변환 시험을 건너뛴다(skip). 그래도 "실패하면 아무것도 만들지 않는다"는 시험은 어디서나 돈다.
시험용 hwp는 가상 문장과 2×2 표만 넣어 임시 폴더에 새로 만든다(실제 문서는 쓰지 않는다).
"""
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from helpers import SCRIPTS, VaultCase

HWP_PS = SCRIPTS / "hwp_to_pdf.ps1"

MAKE_SAMPLE = r"""
param([string]$Out)
$h = New-Object -ComObject HWPFrame.HwpObject
function T($t) { $h.HAction.GetDefault('InsertText', $h.HParameterSet.HInsertText.HSet) | Out-Null; $h.HParameterSet.HInsertText.Text = $t; $h.HAction.Execute('InsertText', $h.HParameterSet.HInsertText.HSet) | Out-Null }
T '가상 시험 문서(가상프로젝트A).'
$h.HAction.Run('BreakPara') | Out-Null
$p = $h.HParameterSet
$h.HAction.GetDefault('TableCreate', $p.HTableCreation.HSet) | Out-Null
$p.HTableCreation.Rows = 2; $p.HTableCreation.Cols = 2; $p.HTableCreation.WidthType = 2; $p.HTableCreation.HeightType = 0
$h.HAction.Execute('TableCreate', $p.HTableCreation.HSet) | Out-Null
T '지표'; $h.HAction.Run('TableRightCell') | Out-Null; T '값'; $h.HAction.Run('TableRightCell') | Out-Null
T 'RMSE'; $h.HAction.Run('TableRightCell') | Out-Null; T '12.34'
$fmt = if ($Out.ToLower().EndsWith('.hwpx')) { 'HWPX' } else { 'HWP' }
$ok = $h.SaveAs($Out, $fmt, '')
$h.Clear(1) | Out-Null; $h.Quit()
if ($ok) { exit 0 } else { exit 1 }
"""


def powershell(args, timeout=120):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def hancom_available():
    try:
        return powershell(["-File", str(HWP_PS), "-Check"], timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def hwp_pids():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Hwp.exe", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {ln.split('","')[1] for ln in r.stdout.splitlines() if ln.startswith('"Hwp')}


HANCOM = hancom_available()


class HwpWithoutHancomTest(VaultCase):
    def test_check_reports_json(self):
        r = self.run_script("extract_text.py", "--hwp-check")
        self.assertIn(r.code, (0, 2), r.text)
        self.assertIn("hancom", json.loads(r.out.strip().splitlines()[-1]))

    def test_broken_hwp_with_convert_creates_nothing(self):
        self.path("in").mkdir()
        (self.path("in") / "x.hwp").write_bytes(bytes(range(256)) * 16)
        r = self.run_script("extract_text.py", "in/x.hwp", "--out-dir", "out", "--hwp-convert", "--hwp-timeout", "30")
        self.assertEqual(r.code, 4, r.text)
        self.assertFalse(self.path("out").exists() and any(self.path("out").iterdir()))
        cache = self.path("Areas/취업/_scan-cache/intake/hwp-pdf")
        self.assertFalse(cache.exists() and any(cache.glob("*.pdf")), "실패하면 PDF도 남기지 않는다")


@unittest.skipUnless(HANCOM, "한글(COM)이 없어 실제 변환 시험은 건너뜀")
class HwpConvertTest(VaultCase):
    @classmethod
    def setUpClass(cls):
        cls._src = tempfile.TemporaryDirectory(prefix="jc-hwp-")
        d = Path(cls._src.name)
        ps1 = d / "make.ps1"
        ps1.write_text(MAKE_SAMPLE, encoding="utf-8-sig")
        cls.samples = {}
        for name in ("표문서.hwp", "새형식.hwpx"):
            out = d / name
            r = powershell(["-STA", "-File", str(ps1), "-Out", str(out)])
            if r.returncode != 0 or not out.exists():
                raise unittest.SkipTest(f"시험용 {name}를 만들지 못함: {r.stdout}{r.stderr}")
            cls.samples[name] = out
        time.sleep(3)

    @classmethod
    def tearDownClass(cls):
        cls._src.cleanup()

    def test_table_text_comes_through_and_original_kept(self):
        before = hwp_pids()
        src = self.samples["표문서.hwp"]
        r = self.run_script("extract_text.py", src, "--out-dir", "out", "--copy-original", "--hwp-convert")
        self.assertEqual(r.code, 0, r.text)
        md = self.read("out/표문서.hwp.md")
        self.assertIn("RMSE", md)
        self.assertIn("12.34", md)
        self.assertIn("한글(COM)로 PDF 변환", md)
        self.assertEqual(self.path("out/표문서.hwp").read_bytes(), src.read_bytes(), "원본 hwp 복사본은 그대로")
        pdfs = list(self.path("Areas/취업/_scan-cache/intake/hwp-pdf").glob("*.pdf"))
        self.assertEqual(len(pdfs), 1, "변환 PDF는 임시 폴더에만")
        # 다시 돌리면 같은 PDF를 재사용(새로 변환하지 않음)
        mtime = pdfs[0].stat().st_mtime
        r = self.run_script("extract_text.py", src, "--out-dir", "out2", "--hwp-convert")
        self.assertEqual(r.code, 0, r.text)
        self.assertEqual(pdfs[0].stat().st_mtime, mtime)
        self.assertEqual(hwp_pids() - before, set(), "변환이 띄운 한글 프로세스가 남지 않는다")

    def test_hwpx(self):
        r = self.run_script("extract_text.py", self.samples["새형식.hwpx"], "--out-dir", "out", "--hwp-convert")
        self.assertEqual(r.code, 0, r.text)
        self.assertIn("12.34", self.read("out/새형식.hwpx.md"))

    def test_ps_refuses_to_overwrite_pdf(self):
        out = self.path("x.pdf")
        out.write_bytes(b"%PDF-1.4 existing")
        r = powershell(["-File", str(HWP_PS), "-Src", str(self.samples["표문서.hwp"]), "-Out", str(out)])
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertEqual(out.read_bytes(), b"%PDF-1.4 existing")


if __name__ == "__main__":
    unittest.main()
