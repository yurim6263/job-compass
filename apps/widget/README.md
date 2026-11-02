# job-compass 알림 아이콘 (위젯)

작업 표시줄 오른쪽 아래 알림 영역에 아이콘을 두고, job-compass가 볼트에 쓰는 `Areas/취업/_widget/오늘 현황.json`을 **읽기만** 해서
마감 임박·새 후보를 숫자로 보여 줍니다. 아이콘을 누르면 오늘 현황 창이 열리고, 버튼으로 Obsidian 문서나 공고 페이지를 엽니다.
기획: [`docs/widget-plan.md`](../../docs/widget-plan.md). 지금은 **W1**(알림 영역 아이콘 + 창)까지입니다.

## 준비

```
pip install --user PySide6
```

## 자동으로 켜기(윈도우 시작 시) · 시작 메뉴

```
powershell -ExecutionPolicy Bypass -File apps\widget\install_autostart.ps1          # 미리보기
powershell -ExecutionPolicy Bypass -File apps\widget\install_autostart.ps1 -Apply   # 만들기 (지우기: -Remove -Apply)
```

시작 프로그램과 시작 메뉴에 "job-compass 알림" 바로가기를 만든다(내 계정만).

## 손으로 켜기

```
pythonw apps\widget\run_widget.pyw
```

처음 켜면 볼트 폴더를 고르라는 창이 뜹니다(나중에 아이콘 우클릭 → "볼트 폴더 바꾸기"). 설정은 `%APPDATA%\job-compass-widget\settings.json`에만 저장하고 볼트에는 아무것도 쓰지 않습니다.
끄려면 아이콘 우클릭 → "끝내기". 이미 켜져 있으면 두 번째 실행은 조용히 끝납니다.

- 숫자 배지 = 마감 임박 + 마감 지난 지원 전 + 오늘 새 후보
- 오늘 현황이 하루 넘게 갱신되지 않았거나 마지막 수집이 실패했으면 창 위에 경고가 나옵니다.
- `python -I`로 켜지 마세요 — 사용자 폴더에 설치한 PySide6를 못 찾습니다.
