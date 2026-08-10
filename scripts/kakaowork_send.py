#!/usr/bin/env python3
"""카카오워크(Kakao Work) 봇으로 태양광 브리프 결과를 발송한다.

본문(블록 메시지)을 보내고, --pdf 를 주면 PDF를 **파일 첨부**로 이어서 보낸다.
표준 라이브러리만 사용한다. 설치 의존성 없음.

필요한 환경변수
  KAKAOWORK_APP_KEY        봇 앱 키 (필수).
  KAKAOWORK_CONVERSATION_ID
                           대화방 ID. 단체 대화방으로 보낼 때 사용하며 이메일보다 우선한다.
  KAKAOWORK_EMAIL          수신자 카카오워크 계정 이메일. 1:1 대화방을 열어 보낸다.

사용 예
  # 갱신 있음 + PDF 첨부
  python3 scripts/kakaowork_send.py --status changed \
      --text-file summary.md --pdf reports/solar-brief-2026.pdf

  # 변동 없음
  python3 scripts/kakaowork_send.py --status unchanged \
      --text "법령 3건 · 기업 4건 · 기술 3건 확인, 리포트 반영 대상 없음"

  # 실제 발송 없이 페이로드만 확인
  python3 scripts/kakaowork_send.py --status changed --text "테스트" --dry-run
"""

import argparse
import json
import mimetypes
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.kakaowork.com"
TIMEOUT = 20
UPLOAD_TIMEOUT = 300
RETRY_DELAYS = (2, 4, 8, 16)

# 카카오워크 텍스트 블록 1개의 상한. 넘으면 잘라서 보낸다.
TEXT_BLOCK_LIMIT = 500
# conversations.upload 의 file 형식 상한 (약 1GB).
UPLOAD_SIZE_LIMIT = 1_050_000_000


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


def api_call(method, path, app_key, payload=None, body=None, content_type=None, timeout=TIMEOUT):
    """카카오워크 API 호출. (status_code, body_dict) 반환.

    payload 를 주면 JSON으로, body/content_type 을 주면 그대로 보낸다(멀티파트용).
    """
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        content_type = "application/json; charset=utf-8"

    req = urllib.request.Request(API_BASE + path, data=body, method=method)
    req.add_header("Authorization", "Bearer " + app_key)
    if content_type:
        req.add_header("Content-Type", content_type)

    ctx = build_ssl_context()
    last_err = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = {"raw": raw}
            # 4xx는 재시도해도 같은 결과다. 즉시 반환한다.
            if 400 <= e.code < 500:
                return e.code, parsed
            last_err = "HTTP %s %s" % (e.code, raw[:300])
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


def ok(code, res, what):
    if res.get("success"):
        return res
    err = res.get("error") or res
    raise SystemExit("%s 실패 [HTTP %s] %s" % (what, code, json.dumps(err, ensure_ascii=False)))


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


def build_blocks(status, title, body, date):
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
    return blocks


def resolve_conversation_id(app_key):
    """대화방 ID를 정한다. 첨부 업로드가 대화방 ID를 요구하므로 항상 필요하다."""
    cid = os.environ.get("KAKAOWORK_CONVERSATION_ID", "").strip()
    if cid:
        return cid

    email = os.environ.get("KAKAOWORK_EMAIL", "").strip()
    if not email:
        raise SystemExit("KAKAOWORK_CONVERSATION_ID 또는 KAKAOWORK_EMAIL 을 설정해야 합니다.")

    query = urllib.parse.urlencode({"email": email})
    code, res = api_call("GET", "/v1/users.find_by_email?" + query, app_key)
    user = ok(code, res, "사용자 조회").get("user") or {}
    if not user.get("id"):
        raise SystemExit("카카오워크에서 이메일을 찾지 못했습니다: " + email)

    code, res = api_call("POST", "/v1/conversations.open", app_key, {"user_id": int(user["id"])})
    return (ok(code, res, "대화방 열기").get("conversation") or {})["id"]


def encode_multipart(fields, files):
    """multipart/form-data 본문을 만든다. (body, content_type) 반환.

    fields: [(name, value)], files: [(name, filename, content_type, bytes)]
    """
    boundary = "----kakaowork" + os.urandom(16).hex()
    out = []
    for name, value in fields:
        out.append(("--" + boundary).encode())
        out.append(('Content-Disposition: form-data; name="%s"' % name).encode())
        out.append(b"")
        out.append(str(value).encode("utf-8"))
    for name, filename, ctype, data in files:
        out.append(("--" + boundary).encode())
        out.append(
            (
                'Content-Disposition: form-data; name="%s"; filename="%s"' % (name, filename)
            ).encode("utf-8")
        )
        out.append(("Content-Type: " + ctype).encode())
        out.append(b"")
        out.append(data)
    out.append(("--" + boundary + "--").encode())
    out.append(b"")
    return b"\r\n".join(out), "multipart/form-data; boundary=" + boundary


def send_file(app_key, conversation_id, path):
    """파일을 업로드하고 첨부 메시지로 보낸다. 업로드된 파일명·크기를 반환한다."""
    if not os.path.exists(path):
        raise SystemExit("첨부할 파일이 없습니다: " + path)
    size = os.path.getsize(path)
    if size == 0:
        raise SystemExit("첨부할 파일이 비어 있습니다: " + path)
    if size > UPLOAD_SIZE_LIMIT:
        raise SystemExit("파일이 업로드 상한(약 1GB)을 넘습니다: %s (%d bytes)" % (path, size))

    name = os.path.basename(path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()

    # 1단계: 사전 업로드. metas 는 attachments[] 와 순서·개수가 일치해야 한다.
    metas = json.dumps([{"file_name": name, "file_type": "file", "file_size": size}])
    body, content_type = encode_multipart(
        [("metas", metas)], [("attachments[]", name, ctype, data)]
    )
    code, res = api_call(
        "POST",
        "/v1/conversations/%s/upload" % conversation_id,
        app_key,
        body=body,
        content_type=content_type,
        timeout=UPLOAD_TIMEOUT,
    )
    uploaded = ok(code, res, "첨부파일 업로드").get("attachments") or []
    if not uploaded:
        raise SystemExit("업로드 응답에 attachment 정보가 없습니다.")
    attachment_id = int(uploaded[0]["attachment_id"])

    # 2단계: 업로드한 파일을 첨부 메시지로 전송한다.
    # 1시간 안에 첨부하지 않으면 업로드된 파일은 삭제된다.
    code, res = api_call(
        "POST",
        "/v1/messages.send_attachments",
        app_key,
        {
            "conversation_id": str(conversation_id),
            "type": "file",
            "attachment": {"attachment_id": attachment_id},
        },
    )
    ok(code, res, "첨부 메시지 전송")
    return name, size


def main():
    p = argparse.ArgumentParser(description="카카오워크로 태양광 브리프 결과 발송")
    p.add_argument("--status", choices=["changed", "unchanged"], required=True)
    p.add_argument("--title", default="")
    p.add_argument("--text", default="")
    p.add_argument("--text-file", default="")
    p.add_argument("--pdf", default="", help="첨부할 PDF 경로. 본문 다음에 파일로 전송된다")
    p.add_argument("--date", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            body_text = f.read().strip()
    elif args.text:
        body_text = args.text.strip()
    elif not sys.stdin.isatty():
        body_text = sys.stdin.read().strip()
    else:
        body_text = ""
    if not body_text:
        raise SystemExit("본문이 비어 있습니다. --text / --text-file / stdin 중 하나로 넘기세요.")

    blocks = build_blocks(args.status, args.title, body_text, args.date)
    # 알림 목록과 푸시에 뜨는 대체 문구.
    fallback = (args.title or blocks[0]["text"]) + " — " + body_text.splitlines()[0]

    if args.dry_run:
        print("POST %s/v1/messages.send" % API_BASE)
        print(
            json.dumps(
                {
                    "conversation_id": os.environ.get("KAKAOWORK_CONVERSATION_ID")
                    or "<실행 시 조회>",
                    "text": fallback[:200],
                    "blocks": blocks,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.pdf:
            print("\n그다음 첨부 전송:")
            print("  POST %s/v1/conversations/{id}/upload  (%s)" % (API_BASE, args.pdf))
            print("  POST %s/v1/messages.send_attachments  type=file" % API_BASE)
        return

    app_key = os.environ.get("KAKAOWORK_APP_KEY", "").strip()
    if not app_key:
        raise SystemExit("KAKAOWORK_APP_KEY 가 설정되어 있지 않습니다.")

    conversation_id = resolve_conversation_id(app_key)
    code, res = api_call(
        "POST",
        "/v1/messages.send",
        app_key,
        {"conversation_id": str(conversation_id), "text": fallback[:200], "blocks": blocks},
    )
    ok(code, res, "본문 메시지 전송")
    print("카카오워크 본문 발송 완료 (대화방 %s)" % conversation_id)

    if args.pdf:
        name, size = send_file(app_key, conversation_id, args.pdf)
        print("첨부 발송 완료: %s (%.1fMB)" % (name, size / 1024 / 1024))


if __name__ == "__main__":
    main()
