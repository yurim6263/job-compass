"""job-compass 공용 도구: 비밀·개인정보 검사, 건너뛸 이름 규칙, 해시, 머리말.

스크립트들이 `import jc_common` 으로 쓴다(python -I 로 실행해도 되도록 각 스크립트가 자기 폴더를 경로에 넣는다).
표준 라이브러리만 쓴다. 검사 결과에는 걸린 값 자체를 절대 담지 않는다(줄 번호와 종류만).
"""
import fnmatch
import hashlib
import re
from datetime import date
from pathlib import Path

# ---------- 건너뛰는 이름 ----------
# 이 폴더 안은 들어가지 않는다(저장소 안의 빌드·설치 폴더 포함)
SKIP_DIRS = {
    "node_modules", "build", "dist", ".next", ".venv", "venv", "__pycache__", "__MACOSX",
    ".idea", ".vscode", ".pytest_cache", ".git", "zip보관", "옵시디언", "obsidian_자동화_확장",
}
# 폴더 이름만 세고 안은 보지 않는다(개인정보): 파일 이름도 보고서에 적지 않는다
PRIVACY_DIRS = {"개인정보", "연구원서류"}
# 파일 이름 패턴 → 건너뛰는 이유
SKIP_FILE_PATTERNS = [
    ("desktop.ini", "시스템 파일"), ("Thumbs.db", "시스템 파일"), (".DS_Store", "시스템 파일"),
    ("~$*", "문서 편집 중 잠금 파일"), ("*.lnk", "바로가기"),
    ("*.zip", "압축 파일(원하면 풀어서 다시 지정)"), ("*.7z", "압축 파일"), ("*.rar", "압축 파일"),
    ("*.pt", "모델 가중치"), ("*.pth", "모델 가중치"), ("*.ckpt", "모델 가중치"), ("*.onnx", "모델 가중치"),
    ("*.exe", "설치·실행 파일"), ("*.dll", "설치·실행 파일"), ("*.msi", "설치·실행 파일"),
    ("*수험표*", "새 사실 없이 개인정보만 있음"), ("*응시확인서*", "새 사실 없이 개인정보만 있음"),
    ("*접수확인서*", "새 사실 없이 개인정보만 있음"),
    ("handoff_*", "인수인계 메모(계정·비밀번호 언급 가능) — 기본 제외"),
]
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".mp4", ".mov", ".avi"}
# 이름만으로 비밀 파일로 보는 것(내용은 읽지 않는다). 예시 파일(*.example.env 등)은 제외
ENV_ALLOW = ("example", "sample", "template")


def name_block_reason(path):
    """파일 이름만 보고 '들이지 않을' 이유를 돌려준다. 없으면 None."""
    n = Path(path).name.lower()
    stem_parts = n.split(".")
    is_env = n == ".env" or n.startswith(".env.") or n.endswith(".env")
    if is_env and not any(a in n for a in ENV_ALLOW):
        return "비밀 파일(.env)"
    if n.endswith((".pem", ".key", ".pfx", ".p12")) or n in ("id_rsa", "id_ed25519"):
        return "비밀 파일(키)"
    if "credential" in n or "recovery-codes" in n or "recovery_codes" in n:
        return "비밀 파일(자격 증명)"
    if "secret" in stem_parts[0] and n.endswith((".json", ".yaml", ".yml", ".txt", ".env")):
        return "비밀 파일 의심(secret)"
    return None


def skip_reason(path):
    """들이지 않을 파일이면 이유, 아니면 None. 비밀 이름 규칙 포함."""
    p = Path(path)
    r = name_block_reason(p)
    if r:
        return r
    for pat, why in SKIP_FILE_PATTERNS:
        if fnmatch.fnmatch(p.name, pat):
            return why
    if p.suffix.lower() in IMAGE_EXT:
        return "이미지·영상(글자 추출 대상 아님 — 증명서 사진은 사용자가 지시하면 눈으로 읽기)"
    return None


# ---------- 내용 검사 ----------
PLACEHOLDER = re.compile(r"(여기에|your[_-]|xxxx|example|changeme|<[^>]*>|\*{4,}|\.\.\.)", re.I)

KEYVAL = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|secret|access[_-]?key|private[_-]?key|token|passwd|password|pwd)\b"
    r"\s*[:=]\s*[\"']?([^\s\"',;]{6,})")
KO_PASSWORD = re.compile(r"(비밀번호|비번|패스워드)\s*[:：=]\s*(\S+)")
TOKEN_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), re.compile(r"\bxox[abp]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}"),
]
RRN = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
PHONE = re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
KO_ID_LINES = re.compile(
    r"(학\s*번|증명서\s*번호|발급\s*번호|자격\s*번호|수험\s*번호|등록\s*번호|성\s*명|이\s*름|주\s*소|연락처|전화)\s*[:：]\s*\S+")


def classify_line(line):
    """한 줄에서 걸린 종류 목록. 값은 돌려주지 않는다. 종류: 비밀값 / 개인정보"""
    kinds = []
    for m in KEYVAL.finditer(line):
        if not PLACEHOLDER.search(m.group(2)):
            kinds.append("비밀값")
            break
    if "비밀값" not in kinds:
        for m in KO_PASSWORD.finditer(line):
            if not PLACEHOLDER.search(m.group(2)):
                kinds.append("비밀값")
                break
    if "비밀값" not in kinds and any(p.search(line) for p in TOKEN_PATTERNS):
        kinds.append("비밀값")
    if RRN.search(line) or PHONE.search(line) or EMAIL.search(line) or KO_ID_LINES.search(line):
        kinds.append("개인정보")
    return kinds


def scan_text(text):
    """[(줄번호, 종류)]"""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for k in classify_line(line):
            out.append((i, k))
    return out


def redact_text(text):
    """걸린 줄을 '[가림: 종류]'로 바꾼 글과 {종류: 줄 수}를 돌려준다. 줄 앞의 항목 이름은 남긴다."""
    counts = {}
    lines = []
    for line in text.splitlines():
        kinds = classify_line(line)
        if kinds:
            for k in kinds:
                counts[k] = counts.get(k, 0) + 1
            head = re.split(r"[:：=]", line, maxsplit=1)[0].strip() if re.search(r"[:：=]", line) else ""
            lines.append(f"{head}: [가림: {'·'.join(kinds)}]" if head else f"[가림: {'·'.join(kinds)}]")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), counts


# ---------- 기타 ----------
def sha256_file(path, n=12):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def sha256_bytes(b, n=12):
    return hashlib.sha256(b).hexdigest()[:n]


def today():
    return date.today().isoformat()


def header(source, how, limits=None, sha=None):
    """추출본 머리: 출처 · 수집일 · 어떻게 · 원 경로 (+ 한계, 원본 해시)."""
    lines = [f"> 출처: {source}", f"> 수집일: {today()}", f"> 어떻게: {how}", f"> 원 경로: {source}"]
    if sha:
        lines.append(f"> 원본 해시(sha256 앞 12자): {sha}")
    if limits:
        lines.append(f"> 한계: {limits}")
    return "\n".join(lines) + "\n\n"


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")
