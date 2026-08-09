#!/usr/bin/env python3
"""카카오워크(Kakao Work) 봇으로 태양광 브리프 결과를 발송한다.

표준 라이브러리만 사용한다. 설치 의존성 없음.

필요한 환경변수
  KAKAOWORK_APP_KEY        봇 앱 키 (필수).
  KAKAOWORK_EMAIL          수신자 카카오워크 계정 이메일.
  KAKAOWORK_CONVERSATION_ID
                           대화방 ID. 지정하면 이메일보다 우선한다.
                           (그룹 대화방에 보낼 때 사용)

사용 예
  # 갱신 있음
  python3 scripts/kakaowork_send.py --status changed \
      --url "https://claude.ai/code/artifact/9fab..." --text-file summary.md

  # 변동 없음
  python3 scripts/kakaowork_send.py --status unchanged \
      --text "법령 3건 · 기업 4건 · 기술 3건 확인, 리포트 반영 대상 없음"

  # 실제 발송 없이 페이로드만 확인
  python3 scripts/kakaowork_send.py --status changed --text "테스트" --dry-run
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.kakaowork.com"
TIMEOUT = 20
RETRY_DELAYS = (2, 4, 8, 16)

# 카카오워크 텍스트 블록 1개의 상한. 넘으면 잘라서 보낸다.
TEXT_BLOCK_LIMIT = 500


def build_ssl_context():
    """에이전트 프록시가 TLS를 재종단하므로 CA 번들을 명시적으로 찾아 붙인다."""
    for path in (
        os.environ.get("SSL_CERT_FILE"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        "/root/.ccr/ca-bundle.crt",
    ):
        if path and os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def api_call(method, path, app_key, payload=None):
    """카카오워크 API 호출. (status_code, body_dict) 반환."""
    url = API_BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + app_key)
    req.add_header("Content-Type", "application/json; charset=utf-8")

    ctx = build_ssl_context()
    last_err = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = {"raw": body}
            # 4xx는 재시도해도 같은 결과다. 즉시 반환한다.
            if 400 <= e.code < 500:
                return e.code, parsed
            last_err = "HTTP %s %s" % (e.code, body[:300])
        except urllib.error.URLError as e:
            reason = str(e.reason)
            # 프록시 정책 차단은 재시도 대상이 아니다.
            if "403" in reason or "CONNECT" in reason.upper():
                raise SystemExit(
                    "카카오워크 API(api.kakaowork.com) 접속이 이그레스 정책에서 차단되었습니다.\n"
                    "환경 설정의 네트워크 허용 목록에 api.kakaowork.com 을 추가해야 합니다.\n"
                    "원인: " + reason
                )
            last_err = reason
        except (ssl.SSLError, OSError) as e:
            last_err = str(e)

        if attempt < len(RETRY_DELAYS):
            time.sleep(RETRY_DELAYS[attempt])

    raise SystemExit("카카오워크 API 호출 실패: " + str(last_err))


def chunk(text, limit=TEXT_BLOCK_LIMIT):
    """긴 본문을 블록 상한에 맞춰 줄 단위로 나눈다."""
    blocks, buf = [], ""
    for line in text.splitlines():
        # 한 줄 자체가 상한을 넘으면 그 줄만 강제로 자른다.
        while len(line) > limit:
            if buf:
                blocks.append(buf)
                buf = ""
            blocks.append(line[:limit])
            line = line[limit:]
        if len(buf) + len(line) + 1 > limit:
            blocks.append(buf)
            buf = line
        else:
            buf = line if not buf else buf + "\n" + line
    if buf:
        blocks.append(buf)
    return blocks or [""]


def build_blocks(status, title, body, url, date):
    changed = status == "changed"
    blocks = [
        {
            "type": "header",
            "text": title or ("태양광 브리프 갱신" if changed else "태양광 브리프 · 변동 없음"),
            "style": "blue" if changed else "yellow",
        }
    ]
    if date:
        blocks.append(
            {
                "type": "description",
                "term": "기준일",
                "content": {"type": "text", "text": date, "markdown": False},
                "accent": True,
            }
        )
    blocks.append({"type": "divider"})
    for part in chunk(body):
        blocks.append({"type": "text", "text": part, "markdown": True})
    if url:
        blocks.append(
            {
                "type": "button",
                "text": "리포트 열기",
                "style": "primary" if changed else "default",
                "action_type": "open_system_browser",
                "value": url,
            }
        )
    return blocks


def main():
    p = argparse.ArgumentParser(description="카카오워크로 태양광 브리프 결과 발송")
    p.add_argument("--status", choices=["changed", "unchanged"], required=True)
    p.add_argument("--title", default="")
    p.add_argument("--text", default="")
    p.add_argument("--text-file", default="")
    p.add_argument("--url", default="")
    p.add_argument("--date", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            body = f.read().strip()
    elif args.text:
        body = args.text.strip()
    elif not sys.stdin.isatty():
        body = sys.stdin.read().strip()
    else:
        body = ""
    if not body:
        raise SystemExit("본문이 비어 있습니다. --text / --text-file / stdin 중 하나로 넘기세요.")

    blocks = build_blocks(args.status, args.title, body, args.url, args.date)
    # 알림 목록과 푸시에 뜨는 대체 문구.
    fallback = (args.title or blocks[0]["text"]) + " — " + body.splitlines()[0]

    conversation_id = os.environ.get("KAKAOWORK_CONVERSATION_ID", "").strip()
    email = os.environ.get("KAKAOWORK_EMAIL", "").strip()
    if conversation_id:
        path, payload = "/v1/messages.send", {"conversation_id": conversation_id}
    elif email:
        path, payload = "/v1/messages.send_by_email", {"email": email}
    elif args.dry_run:
        # 키가 없어도 페이로드 모양은 확인할 수 있어야 한다.
        path, payload = "/v1/messages.send_by_email", {"email": "<KAKAOWORK_EMAIL 미설정>"}
    else:
        raise SystemExit("KAKAOWORK_CONVERSATION_ID 또는 KAKAOWORK_EMAIL 을 설정해야 합니다.")
    payload["text"] = fallback[:200]
    payload["blocks"] = blocks

    if args.dry_run:
        print("POST " + API_BASE + path)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    app_key = os.environ.get("KAKAOWORK_APP_KEY", "").strip()
    if not app_key:
        raise SystemExit("KAKAOWORK_APP_KEY 가 설정되어 있지 않습니다.")

    code, res = api_call("POST", path, app_key, payload)
    if res.get("success"):
        print("카카오워크 발송 완료 (%s)" % path)
        return
    err = res.get("error") or res
    raise SystemExit("카카오워크 발송 실패 [HTTP %s] %s" % (code, json.dumps(err, ensure_ascii=False)))


if __name__ == "__main__":
    main()
