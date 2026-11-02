"""W4: 위젯에서 수집 시작. 위젯은 볼트를 고치지 않고, 이미 등록된 예약 작업(register_scan_task.ps1 이 만든 것)을 '지금 실행'시킨다.
그래서 계정(-ConfigDir)·허용 규칙·로그가 아침 예약 수집과 똑같다. 작업이 없으면 아무것도 하지 않는다.
"""
import subprocess
import sys

TASK_NAME = "job-compass-scan"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW — 검은 창이 번쩍이지 않게


def _ps(command, timeout=20):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=_NO_WINDOW)
        return r.returncode, (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def task_state(name=TASK_NAME):
    """'Running' · 'Ready' · 'Disabled' · None(등록 안 됨/알 수 없음). 상태 이름은 윈도우 언어와 상관없는 영어 값"""
    if sys.platform != "win32":
        return None
    code, out = _ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State")
    return out.splitlines()[-1].strip() if code == 0 and out else None


def run_task(name=TASK_NAME):
    """예약 작업을 지금 한 번 실행. (성공 여부, 이유)"""
    st = task_state(name)
    if st is None:
        return False, "예약 수집 작업이 등록돼 있지 않습니다(register_scan_task.ps1 로 등록)"
    if st == "Running":
        return False, "이미 수집 중입니다"
    if st == "Disabled":
        return False, "예약 수집 작업이 꺼져 있습니다"
    code, _ = _ps(f"Start-ScheduledTask -TaskName '{name}'")
    return (code == 0), ("수집을 시작했습니다" if code == 0 else "수집을 시작하지 못했습니다")
