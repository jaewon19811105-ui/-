# 카카오워크 자동 발송 설정

「태양광정보」 루틴이 매일 실행 결과를 카카오워크로 보내도록 하는 설정 절차입니다.
아래 3가지를 모두 마쳐야 발송이 됩니다.

| # | 할 일 | 하는 곳 | 누가 |
|---|---|---|---|
| 1 | 봇 앱 키 발급 | 카카오워크 관리자 | 워크스페이스 관리자 |
| 2 | `api.kakaowork.com` 도메인 허용 | claude.ai/code 환경 선택기 → 환경 설정 대화상자 | 계정 소유자 |
| 3 | 환경변수(`KAKAOWORK_*`) 등록 | 위와 같은 대화상자 | 계정 소유자 |

---

## 1. 봇 앱 키 발급

1. 카카오워크 웹/PC에서 **관리자** 진입 (워크스페이스 관리자 권한 필요)
2. **앱 관리 → 앱 추가** 로 새 앱을 만든다 (이름 예: `태양광 브리프`)
3. 만든 앱에서 **봇(Bot) 사용** 을 켜고 **활성화** 한다
4. **App Key** 를 복사한다 — 이것이 `KAKAOWORK_APP_KEY` 값이다

> 봇이 비활성 상태면 API 호출은 성공해도 메시지가 도착하지 않습니다. 활성화 여부를
> 반드시 확인하세요.

**수신 대상 지정 방법 두 가지**

- **단체 대화방** — `KAKAOWORK_CONVERSATION_ID` 에 대화방 ID를 넣습니다.
  아래 [단체 대화방으로 보내기](#단체-대화방으로-보내기) 참고.
- **개인 DM** — `KAKAOWORK_EMAIL` 에 본인의 카카오워크 계정 이메일을 넣으면
  봇이 1:1 대화로 보냅니다.

두 값이 모두 있으면 `KAKAOWORK_CONVERSATION_ID` 가 우선합니다.

---

## 2~3. 환경 설정 (환경변수 + 도메인 허용)

두 가지 모두 **같은 대화상자 하나**에서 처리합니다. 루틴은 매 실행마다 새 컨테이너에서
돌기 때문에, 로컬 셸에 `export` 해두는 것으로는 반영되지 않습니다.

### 환경 설정 대화상자 여는 법

**"Environments" 라는 설정 페이지나 전용 URL은 없습니다.** 환경 선택기로만 접근합니다.

1. <https://claude.ai/code> 접속
2. 메시지 입력창 **바로 윗줄**의 **구름 아이콘 버튼**(현재 환경 이름이 적혀 있음, 보통
   `Default`)을 클릭
3. 열린 메뉴의 **Cloud** 섹션에서 대상 환경(`env_01VnTCq9DzzUucM349KXKGby` = 이름 `Default`)
   위에 마우스를 올리면 오른쪽에 **설정(톱니) 아이콘**이 나타난다 → 클릭
4. 대화상자에 **Name / Network access / Environment variables / Setup script** 네 항목이 있다

### ① Network access — 도메인 허용

현재 이 환경은 **Trusted**(허용 목록 도메인만)이며 `api.kakaowork.com` 은 목록에 없어
**403으로 차단**됩니다. 확인된 프록시 로그:

```
connect_rejected  gateway answered 403 to CONNECT  host: api.kakaowork.com:443
```

1. **Network access** 를 **Custom** 으로 변경
2. **Allowed domains** 칸에 한 줄에 하나씩 입력:
   ```text
   api.kakaowork.com
   ```
3. **Also include default list of common package managers** 를 **반드시 체크**한다.
   체크하지 않으면 여기 적은 도메인만 허용되어 pip·npm 등 기존에 되던 접속이 끊긴다.

접근 수준은 None / Trusted / Full / Custom 네 가지다. `*.` 를 앞에 붙이면 하위 도메인
전체를 허용한다(`*.kakaowork.com`). GitHub 트래픽은 별도 프록시라 이 목록과 무관하다.

### ② Environment variables — 키 등록

같은 대화상자의 **Environment variables** 칸에 `.env` 형식으로 한 줄에 하나씩 적는다.

```text
KAKAOWORK_APP_KEY=발급받은_앱_키
KAKAOWORK_CONVERSATION_ID=단체_대화방_ID
```

1:1로 받으려면 `KAKAOWORK_CONVERSATION_ID` 대신 `KAKAOWORK_EMAIL=본인_이메일` 을 넣는다.
값에 `#` 이 들어가면 따옴표로 감싼다(감싸지 않으면 `#` 뒤가 주석으로 잘린다).

입력 후 저장한다.

> **보안 주의.** 클라우드 환경에는 전용 시크릿 저장소가 없습니다. 환경변수 값은 그 환경을
> 쓰는 사람이면 누구나 평문으로 읽을 수 있고, 공식 문서도 *"don't add API keys or other
> credentials"* 라고 경고합니다. 개인 계정의 개인 환경이라면 읽을 수 있는 사람은 본인뿐이지만,
> 그래도 (a) App Key는 카카오워크 메시지 발송 권한만 가진 최소 권한 키여야 하고,
> (b) 노출이 의심되면 즉시 재발급하십시오. 리포지토리 파일·커밋 메시지·루틴 프롬프트에는
> 절대 적지 마십시오.

### 반영 시점

세션은 **시작할 때 한 번** 환경 설정을 복사합니다. 따라서 저장 후:

- 이미 돌고 있는 세션에는 반영되지 않는다 (기존 값을 그대로 유지)
- 이후 새로 시작하는 세션부터 적용된다. 루틴은 매 실행마다 새 세션을 만들므로 다음
  08:00(KST) 실행부터 자동 반영된다
- 즉시 확인하려면 **새 세션을 열어서** 4번 확인 절차를 실행한다

관련 문서: <https://code.claude.com/docs/en/cloud-environments>

---

## 4. 확인

환경 설정 변경은 **새로 시작하는 세션**부터 적용됩니다. 설정을 저장한 세션에서 그대로
실행하면 여전히 실패하므로, 새 세션을 열고 확인하십시오.

세 단계를 마친 뒤 세션에서 다음을 실행합니다.

```bash
# 페이로드만 확인 (네트워크·키 불필요)
python3 scripts/kakaowork_send.py --status unchanged --text "설정 점검" --dry-run

# 실제 발송
python3 scripts/kakaowork_send.py --status unchanged \
  --title "태양광 브리프 · 연동 테스트" \
  --text "카카오워크 발송 설정이 정상 동작합니다." \
  --url "https://claude.ai/code/artifact/9fab249d-87e2-4450-bb0f-2e174c45eff4"
```

카카오워크에 메시지가 도착하면 완료입니다.

---

## 스크립트 사용법

`scripts/kakaowork_send.py` — 표준 라이브러리만 사용하며 설치 의존성이 없습니다.

| 옵션 | 설명 |
|---|---|
| `--status changed\|unchanged` | 필수. 헤더 색과 기본 제목이 달라집니다 (파랑 / 노랑) |
| `--title` | 헤더 문구 직접 지정 |
| `--text` / `--text-file` / stdin | 본문. 셋 중 하나. 500자 넘으면 줄 단위로 자동 분할 |
| `--url` | 하단 "리포트 열기" 버튼 링크 |
| `--pdf-url` | 하단 "PDF 보기" 버튼 링크 |
| `--date` | 기준일 표시 |
| `--dry-run` | 발송하지 않고 페이로드만 출력 |

네트워크 오류는 2·4·8·16초 백오프로 4회 재시도하고, 4xx 응답과 프록시 정책 차단(403)은
재시도 없이 즉시 실패합니다.

---

## 자주 나는 오류

| 증상 | 원인 / 조치 |
|---|---|
| `이그레스 정책에서 차단` | 도메인 허용 누락, 또는 설정 전에 시작된 세션에서 실행함 |
| `KAKAOWORK_APP_KEY 가 설정되어 있지 않습니다` | 환경변수 누락, 또는 설정 전에 시작된 세션에서 실행함 (로컬 export는 루틴에 반영되지 않음) |
| HTTP 401 / `invalid_token` | App Key 오타, 또는 앱 삭제·재발급됨 |
| HTTP 400 `invalid_parameter` (email) | 카카오워크에 없는 이메일. 워크스페이스 계정 이메일이어야 함 |
| 호출은 성공(`success: true`)인데 메시지가 안 옴 | 봇이 비활성 상태거나, 그룹방에 봇이 초대되지 않음 |

---

## PDF 발송에 대하여

카카오워크 봇 Open API에는 **파일 업로드 엔드포인트가 없습니다.** 다음 후보를 모두
확인했고 전부 `api_not_found` 를 반환합니다.

```
messages.upload_media  attachments.upload  files.upload
media.upload           messages.upload     conversations.upload
```

`file` 블록이 요구하는 `attachment_id` 를 봇이 만들어낼 방법이 없으므로, 봇 메시지에
PDF를 직접 첨부하는 것은 불가능합니다. 그래서 다음 방식을 씁니다.

1. `scripts/make_pdf.py` 로 리포트 HTML을 A4 PDF로 변환
2. `reports/solar-brief-2026.pdf` 로 공개 리포지토리에 커밋
3. 카카오워크 메시지에 「PDF 보기」 버튼을 붙여 아래 링크를 연다

```
https://github.com/jaewon19811105-ui/-/blob/HEAD/reports/solar-brief-2026.pdf
```

`blob/HEAD` 는 항상 기본 브랜치의 최신 파일을 가리키므로 링크가 고정됩니다. GitHub이
브라우저에서 PDF를 바로 렌더링하므로 모바일에서도 열립니다. 내려받기 링크가 필요하면
`https://raw.githubusercontent.com/jaewon19811105-ui/-/HEAD/reports/solar-brief-2026.pdf`
를 쓰면 됩니다.

### PDF 변환 스크립트

```bash
python3 scripts/make_pdf.py reports/solar-brief-2026.html reports/solar-brief-2026.pdf
```

헤드리스 Chromium(`/opt/pw-browsers/chromium`)을 씁니다. 원본 HTML에는 `@media print`
규칙이 없고 Chromium은 기본적으로 배경색을 인쇄하지 않으므로, 원본을 수정하지 않고
임시 복사본에 인쇄용 CSS(`print-color-adjust: exact`, 표·제목 페이지 분리 방지,
A4 여백, 마스트헤드 그리드 폭 조정)를 주입한 뒤 변환합니다.

---

## 단체 대화방으로 보내기

`scripts/kakaowork_rooms.py` 로 대화방 ID를 찾거나 새로 연다. 발송은 하지 않고 조회만
하는 보조 도구다.

```bash
# 워크스페이스 구성원 (이메일 → user_id)
python3 scripts/kakaowork_rooms.py users

# 봇이 참여 중인 대화방 목록
python3 scripts/kakaowork_rooms.py rooms

# 단체 대화방 열기 — 없으면 생성, 이미 있으면 기존 방을 그대로 반환
python3 scripts/kakaowork_rooms.py open a@corp.com b@corp.com
```

`open` 은 `conversations.open` 에 `user_ids` 를 복수로 넘긴다. 반환된
`conversation_id` 를 환경변수에 넣으면 그 방으로 발송된다.

```text
KAKAOWORK_CONVERSATION_ID=1006710354409588
```

`KAKAOWORK_EMAIL` 이 함께 있어도 `KAKAOWORK_CONVERSATION_ID` 가 우선하므로, 개인 DM에서
단체방으로 바꿀 때 이메일 줄을 지울 필요는 없다. 되돌리려면
`KAKAOWORK_CONVERSATION_ID` 줄만 지우면 된다.

**카카오워크에서 직접 만든 방에 보내려면** 그 방에 봇을 초대한 뒤 `rooms` 명령으로
`conversation_id` 를 확인한다. 봇이 참여하지 않은 방은 목록에 나오지 않는다.

봇이 쓸 수 없는 대화방 API도 있다. 아래는 모두 `api_not_found` 다.

```
conversations.create   conversations.invite   conversations.info   conversations.users
```

즉 봇은 **자기가 참여하는 방을 `conversations.open` 으로 여는 것만** 가능하고, 기존 방에
스스로를 초대하거나 방 이름을 바꿀 수는 없다.
