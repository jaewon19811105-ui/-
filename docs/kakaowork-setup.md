# 카카오워크 자동 발송 설정

「태양광정보」 루틴이 매일 실행 결과를 카카오워크로 보내도록 하는 설정 절차입니다.
아래 3가지를 모두 마쳐야 발송이 됩니다.

| # | 할 일 | 하는 곳 | 누가 |
|---|---|---|---|
| 1 | 봇 앱 키 발급 | 카카오워크 관리자 | 워크스페이스 관리자 |
| 2 | 환경변수 등록 | claude.ai/code 환경 설정 | 계정 소유자 |
| 3 | `api.kakaowork.com` 도메인 허용 | claude.ai/code 환경 설정 | 계정 소유자 |

---

## 1. 봇 앱 키 발급

1. 카카오워크 웹/PC에서 **관리자** 진입 (워크스페이스 관리자 권한 필요)
2. **앱 관리 → 앱 추가** 로 새 앱을 만든다 (이름 예: `태양광 브리프`)
3. 만든 앱에서 **봇(Bot) 사용** 을 켜고 **활성화** 한다
4. **App Key** 를 복사한다 — 이것이 `KAKAOWORK_APP_KEY` 값이다

> 봇이 비활성 상태면 API 호출은 성공해도 메시지가 도착하지 않습니다. 활성화 여부를
> 반드시 확인하세요.

**수신 대상 지정 방법 두 가지**

- **개인 DM (권장)** — `KAKAOWORK_EMAIL` 에 본인의 카카오워크 계정 이메일을 넣으면
  봇이 1:1 대화로 보냅니다. 별도 초대 불필요.
- **그룹 대화방** — 해당 대화방에 봇을 초대한 뒤 `KAKAOWORK_CONVERSATION_ID` 에
  대화방 ID를 넣습니다. 두 값이 모두 있으면 `KAKAOWORK_CONVERSATION_ID` 가 우선합니다.

---

## 2. 환경변수 등록

루틴은 매 실행마다 **새 컨테이너**에서 돌기 때문에, 키를 로컬 셸에 export 해두는 것으로는
안 됩니다. 반드시 환경(Environment) 설정에 저장해야 합니다.

1. <https://claude.ai/code> → **Environments** → 이 루틴이 쓰는 환경
   (`env_01VnTCq9DzzUucM349KXKGby`) 선택
2. **Environment variables** 에 추가:

   | 이름 | 값 |
   |---|---|
   | `KAKAOWORK_APP_KEY` | 1번에서 복사한 App Key |
   | `KAKAOWORK_EMAIL` | 수신할 카카오워크 계정 이메일 |
   | `KAKAOWORK_CONVERSATION_ID` | (그룹방에 보낼 때만) 대화방 ID |

App Key는 비밀값입니다. 리포지토리 파일이나 커밋 메시지, 루틴 프롬프트에 절대 적지 마세요.

---

## 3. 도메인 허용 (필수)

현재 이 환경의 이그레스 정책은 `api.kakaowork.com` 을 **403으로 차단**합니다.
확인된 프록시 로그:

```
connect_rejected  gateway answered 403 to CONNECT  host: api.kakaowork.com:443
```

같은 환경 설정 화면의 **Network access** 에서 `api.kakaowork.com` 을 허용 목록에 추가하거나,
네트워크 정책을 더 넓은 설정으로 바꿔야 합니다. 이 단계를 건너뛰면 스크립트는 다음
메시지를 남기고 실패합니다.

```
카카오워크 API(api.kakaowork.com) 접속이 이그레스 정책에서 차단되었습니다.
```

관련 문서: <https://code.claude.com/docs/en/claude-code-on-the-web>

---

## 4. 확인

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
| `--date` | 기준일 표시 |
| `--dry-run` | 발송하지 않고 페이로드만 출력 |

네트워크 오류는 2·4·8·16초 백오프로 4회 재시도하고, 4xx 응답과 프록시 정책 차단(403)은
재시도 없이 즉시 실패합니다.

---

## 자주 나는 오류

| 증상 | 원인 / 조치 |
|---|---|
| `이그레스 정책에서 차단` | 3번 도메인 허용 누락 |
| `KAKAOWORK_APP_KEY 가 설정되어 있지 않습니다` | 2번 환경변수 누락 (로컬 export는 루틴에 반영되지 않음) |
| HTTP 401 / `invalid_token` | App Key 오타, 또는 앱 삭제·재발급됨 |
| HTTP 400 `invalid_parameter` (email) | 카카오워크에 없는 이메일. 워크스페이스 계정 이메일이어야 함 |
| 호출은 성공(`success: true`)인데 메시지가 안 옴 | 봇이 비활성 상태거나, 그룹방에 봇이 초대되지 않음 |
