# job-compass 알림 아이콘 (위젯)

작업 표시줄 오른쪽 아래 알림 영역에 아이콘을 두고, job-compass가 볼트에 쓰는 `Areas/취업/_widget/오늘 현황.json`을 **읽기만** 해서
마감 임박·새 후보를 숫자로 보여 줍니다. 아이콘을 누르면 오늘 현황 창이 열리고, 버튼으로 Obsidian 문서나 공고 페이지를 엽니다.
기획: [`docs/widget-plan.md`](../../docs/widget-plan.md). 지금은 **W2**(알림 영역 아이콘 + 창 + 화면 끝 유리 탭)까지입니다.

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
- 디자인: 작업 표시줄은 선으로 된 나침반(작업 표시줄 테마에 따라 흰 선/검은 선), 화면 끝은 밝은 유리 캡슐 탭(검은 글씨). 상태 색: 새 후보 산호 · 마감 임박 주황 · 수집 실패 빨강 · 새 소식 없음은 색 없음.
- 화면 끝 탭: 처음엔 오른쪽 끝에 붙어 있고, 마우스를 올리면 늘어나며 요약 두 줄을 보여 줍니다. 새 소식이 늘면 3초 동안 펼쳐졌다 접힙니다. 끌면 끝을 따라 위아래로 옮겨지고(반대쪽 절반에 놓으면 반대 끝으로) 위치를 기억합니다. 우클릭: 현황 열기 · 탭 숨기기 · 위치 초기화(숨긴 탭은 알림 영역 아이콘 우클릭 → "화면 끝 탭 보이기").
- 오늘 현황이 하루 넘게 갱신되지 않았거나 마지막 수집이 실패했으면 창 위에 경고가 나옵니다.
- `python -I`로 켜지 마세요 — 사용자 폴더에 설치한 PySide6를 못 찾습니다.
