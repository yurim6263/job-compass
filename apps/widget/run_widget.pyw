"""job-compass 알림 아이콘 실행 파일. `pythonw run_widget.pyw`로 창 없이 켠다.
(파이썬 `-I`는 쓰지 않는다 — 사용자 폴더에 설치한 PySide6를 못 찾는다.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jc_widget.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
