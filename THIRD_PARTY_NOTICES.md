# 참고한 프로젝트와 사용하는 오픈소스 (Third-party notices)

job-compass 자체는 [MIT 라이선스](LICENSE)입니다. 아래는 이 프로젝트가 방법과 구조를 참고했거나 실행에 쓰는 것들입니다. 라이선스 정보는 설치된 패키지 메타데이터(`importlib.metadata`)를 2026-10-30에 확인한 것이며, 정확한 조건은 각 프로젝트의 원문을 따릅니다. 이 문서는 법률 자문이 아닙니다.

## 참고한 프로젝트: jobstack

- 저장소: https://github.com/thesun4sky/jobstack (참고한 시점: 커밋 `69a59e2`, 2026-09-06, VERSION 1.1.0)
- 라이선스: MIT. 아래는 그 고지문입니다.

```
MIT License

Copyright (c) 2026 jobstack contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- job-compass의 스킬 문서와 스크립트는 이 프로젝트의 **방법과 구조(답변 판정 방식, 첨삭 단계, 마감 처리 규칙 등)를 참고해 다시 쓴 것**입니다. 가까이 따라간 목록·표가 있을 수 있어 위 고지문을 함께 둡니다.
- **문장 대조(2026-11-01)**: 위 커밋의 jobstack 글(문서·코드)과 이 저장소의 스킬 문서·스크립트를 공백·기호를 뺀 글자 기준으로 대조해, 같은 글자열이 14자 이상 이어지는 곳을 찾았습니다. 코드는 파이썬 기본 문구, 주소, 문서 머리말, 일반적인 브라우저 식별 문자열 정도만 겹쳤습니다. 한글 문장에서는 jobstack 문장과 거의 같던 곳이 있어 **이 저장소 문장으로 다시 썼습니다**: 문항 의도를 밝히는 안내 문장, 면접 중 딴소리에 대한 안내 문장, 비상장 기업의 재무 표 생략 문구, 꼬리질문 5가지 문장, 전형 방식 나열, 치환 테스트 설명(이름도 "바꿔 넣어 보기"로 바꿈). 다시 대조한 뒤 남은 겹침은 아래 "가까이 따라간 구조"의 목록·분류 이름(필드 이름, 단계 이름, 조사 항목 나열)뿐입니다. 자동 대조라서 의미가 같은 다른 표현은 잡지 못할 수 있습니다.
- **개념 수준에서 참고한 것**(문장은 새로 썼고, 2026-11-01에 위처럼 대조함): 경험 카드의 6단계·4분리·수치 폴백 기준 / 점수를 관측 가능한 개수로 계산해 결정적으로 만드는 규칙, 본문이 없으면 점수를 내지 않는 규칙, 마감 처리 규칙, 등급 구간 / 키워드 체크리스트의 O·모호·X 판정과 "팀원처럼" 조사 / 자소서의 7패턴 진단·5단계 첨삭·치환 테스트(이 저장소 문서에서는 "바꿔 넣어 보기")·글자수 게이트·방어 맵(미끼·꼬리질문) / 모의면접의 강도 3단계·질문 구성 비율·역질문 고정·꼬리질문 5세트·AI 역량검사 연습 구성 / 현황 관리의 7일 정체 알림·퍼널 통계·`지원취소`를 분모에서 빼는 규칙. **가까이 따라간 구조**(이름·목록은 같거나 비슷하게 두었습니다): 경험 카드의 6단계 이름(이름→문제→역할→바꾼 행동→검증 가능한 변화→직무 연결), 방어 맵 미끼 분류(수치·기술 선택·역할 범위·성과·갈등/판단), 꼬리질문이 5가지 틀이라는 구성, 기업 조사의 7개 키워드 출처 나열과 재무 지표 5개(부채비율·영업이익률·매출증가율·유동비율·ROE) 선택. 모호한 상투 표현을 경고하는 기능(`verify_cards.py`)은 jobstack의 "피해야 할 표현" 개념을 읽고, 표현 목록과 설명은 이 저장소에서 새로 정했습니다. 이 항목들은 이 저장소의 기획 단계에서 jobstack을 읽고 정리한 것에 근거하며, 이 저장소의 `references/` 문서는 그 개념을 이 프로젝트에 맞게 다시 쓴 것입니다.
- jobstack이 README에서 핵심 방법으로 소개하는 "결이요" 프레임워크의 출처·사용 조건은 **확인하지 못했습니다**(저장소에 출처 표기가 없음). 공개 전에 사용 여부를 다시 정합니다.

## 사용하는 외부 구성 요소

| 구성 요소 | 용도 | 라이선스 (확인한 것) |
| --- | --- | --- |
| openpyxl 3.1.5 | 엑셀 읽기·내보내기 | MIT |
| pypdf 6.19.0 | PDF 글자 추출 | BSD-3-Clause (설치본 `licenses/LICENSE` 원문 확인, 2026-10-31) |
| pyhwp 0.1b15 (`hwp5txt` 명령) | 한글(.hwp) 글자 추출 | **GNU AGPL v3 이상** — 이 저장소에 **포함하지 않고**, 사용자가 따로 설치해 명령으로만 호출하는 선택 도구로 다룹니다(포함·수정 배포 여부에 따라 조건이 달라지므로 공개 전 점검에서 다시 확인) |
| six 1.17.0, olefile 0.47, lxml 6.1.3 (pyhwp의 의존 패키지) | 위와 같음 | MIT / BSD / BSD-3-Clause |
| Python 3.12 | 실행 환경 | PSF License |

## 사용 환경

- Claude Code(Anthropic)의 스킬 형식으로 동작합니다. Claude, Anthropic, 그리고 이 문서에 언급된 서비스·회사 이름은 각 소유자의 상표입니다.
