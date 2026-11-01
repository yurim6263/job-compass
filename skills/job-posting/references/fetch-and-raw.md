# 1~2단계: 가져오기 · raw 저장

경로는 볼트 루트 기준이고 명령은 볼트 루트에서 돌린다. `P/` = `Projects/SecondBrain/`. 임시 파일은 `Areas/취업/_scan-cache/posting/`(이하 `T/`)에 둔다 — **명령에는 줄이지 않은 경로를 쓴다.**
이 단계의 도구는 `curl` · `perl` · `sed` · `cp` · `cmp` · `iconv`와 Read · Grep · Glob뿐이다(스크립트를 새로 짜지 않는다).

## 1. 가져오기 — 원본 파일은 curl, 글자는 줄 범위로
**WebFetch로 raw를 만들지 않는다.** WebFetch는 모델이 다시 쓴 요약을 돌려주므로 "원문"이 아니다. raw에는 ① 받은 원본 파일 그대로(HTML·그림·PDF)와 ② 원본에서 공고 부분 줄을 **그대로 복사한 md**를 둔다. 손으로 옮겨 적는 것은 그림·PDF 공고뿐이고, 그때는 머리에 옮겨 적었다고 밝힌다.
`<이름>` = 공고 ID의 `:`를 `-`로(`saramin-55314388`). 모르는 사이트는 `url-<호스트>`.

1. **받기**
   ```
   mkdir -p Areas/취업/_scan-cache/posting
   curl -sSL --compressed --max-time 30 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" -H "Accept-Language: ko-KR,ko;q=0.9" -o "Areas/취업/_scan-cache/posting/<이름>.html" -w "%{http_code} %{content_type} %{url_effective}\n" "<URL>"
   ```
   - **사이트별로 같이 받을 주소**(본문이 공고 주소가 아닌 곳에 있다). 같은 curl에 `-e "<공고 URL>"`(Referer)을 붙인다:
     - 잡코리아 — 상세요강 `https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno=N` → `T/<이름>-상세.html`. 공고 주소에는 메뉴·요약뿐이다.
     - 사람인 — 공고 주소 대신 요약 `https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=N`을 `<이름>.html`로(relay 주소는 메뉴 글자만 온다), 상세요강 `https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx=N&rec_seq=0` → `<이름>-상세.html`.
     - 그 밖 — 받은 HTML에서 Grep `<iframe[^>]+src="[^"]+"`로 iframe 주소를 찾아 **같은 사이트 것만** 같은 방식으로 `<이름>-상세.html`.
   - 출력 첫 칸(상태 코드)이 `200`이 아니면 — `403` 막힘, `404` 내려간 공고 — 5번으로. 둘째 칸이 `application/pdf`면 받은 게 PDF다 — `<이름>.pdf`로 다시 받고 4번으로.
2. **글자 뽑기** — 받은 HTML마다(`-상세.html`도 `-상세.txt`로). 태그·스크립트를 걷어내고 보이는 글자만 남기며 글자는 바꾸지 않는다:
   ```
   perl -CSD -0777 -ne 's/<!--.*?-->//gs; s/<(script|style|noscript|template|svg|head|button|select|iframe)\b.*?<\/\1\s*>//gis; s/<br\b[^>]*>/\n/gi; s/<li\b[^>]*>/\n- /gi; s/<h([1-6])\b[^>]*>/"\n"."#" x $1 ." "/gie; s/<\/?(p|div|tr|section|article|dt|dd|dl|table|ul|ol|h[1-6]|header|footer|nav|main|aside|form|figure|blockquote|pre|tbody|thead)\b[^>]*>/\n/gi; s/<t[dh]\b[^>]*>/ | /gi; s/<[^>]+>//g; s/&nbsp;/ /g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/"/g; s/&#0*39;|&apos;/\x27/g; s/&#(\d+);/chr($1)/ge; s/&#x([0-9a-f]+);/chr(hex $1)/gie; s/&amp;/&/g; s/[ \t\r]+/ /g; s/ ?\n ?/\n/g; s/\n(?:[-|] ?\n)+/\n/g; s/\n{3,}/\n\n/g; print' "Areas/취업/_scan-cache/posting/<이름>.html" > "Areas/취업/_scan-cache/posting/<이름>.txt"
   ```
   - 글자가 깨지면(HTML 머리에 `charset=euc-kr`) 먼저 `iconv -f CP949 -t UTF-8 "Areas/취업/_scan-cache/posting/<이름>.html" > "Areas/취업/_scan-cache/posting/<이름>.utf8.html"` 하고 그 파일로 뽑는다. 원본은 그대로 둔다.
3. **txt를 Read로 연다.** 줄 번호로 2단계에서 쓸 범위를 고른다.
   - **공고 본문이 있나** — 자격 요건·담당 업무·우대·모집 부문·전형·근무 조건 중 둘 이상, 그중 자격이나 업무가 하나는 있으면 있는 것이다(표지 이름이 "이런 분을 찾아요"여도 본문이면 본문). **글자 수로 판단하지 않는다**(메뉴 글자만으로 천 자가 넘기도 한다). 없으면 4·5번.
   - 본문에 사이트 메뉴·추천 공고·푸터가 섞여 있다 — 회사명·공고 제목·요약 칸·상세요강 같은 공고 부분만 고른다.
   - 요약 칸(경력·학력·급여·마감)과 상세요강이 다르면 상세요강을 기준으로 하고 wiki `## 자료 간 차이`에 적는다(볼트 규칙 10).
4. **본문이 그림·PDF인 공고**(큰 회사 공채, 사람인에 흔하다)
   - 그림 — 상세 HTML에서 Grep `<img[^>]+>`로 `src`·`data-src` 주소를 찾아, 로고·아이콘·배너 말고 본문 그림을 curl로(`-e` 붙여) `T/<이름>-그림-N.<확장자>`로 받고 Read로 본다. **세로로 아주 긴 그림은 Read가 줄여 보여 글자가 안 읽힌다** — 그러면 5번의 PDF로.
   - PDF — Read로 연다(공고 주소가 PDF, 첨부 PDF, 사용자가 저장한 PDF). 첨부 링크는 Grep `href="[^"]+\.(pdf|hwp|hwpx|docx?)"`로 찾는다. **HWP는 못 연다** — PDF로 바꿔 달라고 한다.
   - 읽은 글자를 보이는 그대로 `T/<이름>-옮김.txt`에 Write — 고치거나 다듬지 않는다. 그림·PDF를 읽어 옮겨 적은 것이라 틀릴 수 있다 — **raw로 넣기 전에 사용자에게 보여 주고 확인받는다.**
5. **링크로 안 되는 공고** — `403`·`404`·화면을 스크립트로 나중에 그리는 채용 페이지(txt에 메뉴뿐)·로그인해야 보이는 공고·너무 긴 그림. 사용자에게 둘 중 하나를 부탁한다:
   - 브라우저에서 공고를 열고 `Ctrl+P` → 대상 "PDF로 저장" → 저장한 PDF 경로를 알려 달라(화면에 보이는 그대로 담긴다). 받으면 4번 PDF.
   - 공고 글을 붙여넣어 달라 — 받은 글을 손대지 않고 `T/<오늘>-붙여넣기.txt`에 Write.
   - 404면 공고가 내려갔을 수 있다고 먼저 말한다. 어느 경우든 채워 넣지 않는다.
6. **게시 회사와 근무처** — 아웃소싱·파견·헤드헌터 공고는 공고를 낸 회사와 실제 근무처가 다르다. 공고에 적힌 대로 둘 다 기억해 wiki·현황표 메모에 쓴다. 회사 자체 채용 페이지에 같은 공고가 따로 있으면 그쪽이 원문이다 — 사용자에게 알린다.

## 2. raw 저장 — `P/raw/채용공고/<raw 파일명>.md` + 원본은 `P/raw/채용공고/원본/`
이름은 `_공용/references/naming.md`의 규칙. md는 txt의 줄 범위를 `sed`로 복사한다 — **손으로 옮겨 적지 않는다.** `-옮김.txt`·`-붙여넣기.txt`도 같은 방식이다.

1. Glob으로 `P/raw/채용공고/<raw 파일명>.md`가 없는지 본다. 있으면 멈추고 보고한다(볼트 규칙 1).
2. 머리를 Write로 `T/<이름>-머리.md`에:
   ```
   # <공고 제목 원문> — <회사 원문 표기>

   - 출처: <URL | 사용자 붙여넣기 (원 링크 …) | 사용자가 저장한 PDF (원 링크 …)>
   - 공고 ID: <공고 ID>                         ← 붙여넣기라 없으면 이 줄을 뺀다
   - 수집일: YYYY-MM-DD (<사이트> 공고 본문. <어떻게>. 메뉴·광고·배너는 뺐다)
   - 원본: [[Projects/SecondBrain/raw/채용공고/원본/<raw 파일명>.html|<raw 파일명>.html]] · …   ← 받은 원본 전부
   - 요약 칸: <사이트 요약 칸을 ' · ' 로>          ← 있을 때만

   ```
   `<어떻게>`는 넷 중 하나: `페이지 글자를 줄 범위로 그대로 복사했다` · `공고 그림을 읽어 옮겨 적었다 — 틀릴 수 있다, 사용자 확인 YYYY-MM-DD` · `PDF를 읽어 옮겨 적었다 — 틀릴 수 있다, 사용자 확인 YYYY-MM-DD` · `사용자가 붙여넣은 글을 옮겼다`
3. **합치기** — 머리 + 고른 범위. 범위는 공고 제목 줄부터 공고 내용 끝까지, 메뉴·로그인·추천 공고·푸터는 밖으로, 중간에 끼어든 광고는 범위를 나눠 뺀다. 원문 순서대로, 겹치지 않게. **범위 안 글자는 하나도 고치지 않는다.**
   ```
   cat "Areas/취업/_scan-cache/posting/<이름>-머리.md" > "Areas/취업/_scan-cache/posting/<이름>-raw.md"
   sed -n '<시작>,<끝>p' "Areas/취업/_scan-cache/posting/<이름>.txt" >> "Areas/취업/_scan-cache/posting/<이름>-raw.md"
   sed -n '<시작>,<끝>p' "Areas/취업/_scan-cache/posting/<이름>-상세.txt" >> "Areas/취업/_scan-cache/posting/<이름>-raw.md"     ← 범위마다 한 줄
   ```
4. **넣기** — 덮어쓰지 않는 복사(`cp -n`) 뒤 `cmp`로 같은지 확인한다. `cmp`가 다르다고 하면 같은 이름 파일이 이미 있었던 것이다 — 멈추고 보고한다:
   ```
   mkdir -p "Projects/SecondBrain/raw/채용공고/원본"
   cp -n "Areas/취업/_scan-cache/posting/<이름>-raw.md" "Projects/SecondBrain/raw/채용공고/<raw 파일명>.md" && cmp "Areas/취업/_scan-cache/posting/<이름>-raw.md" "Projects/SecondBrain/raw/채용공고/<raw 파일명>.md"
   cp -n "Areas/취업/_scan-cache/posting/<이름>.html" "Projects/SecondBrain/raw/채용공고/원본/<raw 파일명>.html"
   ```
   `cp`가 `-n`에 경고를 내도 동작은 같다 — `cmp` 결과로 판단한다. 원본은 받은 것 전부: `-상세.html` → `<raw 파일명>-상세.html`, 그림 → `<raw 파일명>-그림-N.<확장자>`, PDF → `<raw 파일명>.pdf`(사용자가 저장한 PDF도 이 경로로). 각각 `cmp`로 확인한다.
5. raw md를 Read로 한 번 열어 제목·마감·자격 요건이 들어 있는지 본다. 빠졌으면 — 이미 쓴 raw는 못 고치므로 — 사용자에게 알리고 어떻게 할지 묻는다.
