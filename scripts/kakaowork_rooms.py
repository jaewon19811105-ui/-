#!/usr/bin/env python3
"""카카오워크 대화방을 조회하고, 단체 대화방을 열어 conversation_id 를 얻는다.

`KAKAOWORK_CONVERSATION_ID` 에 넣을 값을 찾기 위한 보조 도구다. 발송 자체는
kakaowork_send.py 가 한다.

필요한 환경변수
  KAKAOWORK_APP_KEY   봇 앱 키

사용 예
  # 봇이 참여 중인 대화방 목록
  python3 scripts/kakaowork_rooms.py rooms

  # 워크스페이스 구성원 목록 (이메일 → user_id 확인용)
  python3 scripts/kakaowork_rooms.py users

  # 단체 대화방 열기 (없으면 새로 생성, 있으면 기존 방 반환)
  python3 scripts/kakaowork_rooms.py open a@corp.com b@corp.com
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.kakaowork.com"
TIMEOUT = 20


def build_ssl_context():
    for path in (
        os.environ.get("SSL_CERT_FILE"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        "/root/.ccr/ca-bundle.crt",
    ):
        if path and os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def api(method, path, payload=None):
    app_key = os.environ.get("KAKAOWORK_APP_KEY", "").strip()
    if not app_key:
        raise SystemExit("KAKAOWORK_APP_KEY 가 설정되어 있지 않습니다.")

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(API_BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + app_key)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=build_ssl_context()) as res:
            body = json.loads(res.read().decode("utf-8"))
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        if "403" in reason or "CONNECT" in reason.upper():
            raise SystemExit(
                "api.kakaowork.com 접속이 이그레스 정책에서 차단되었습니다.\n원인: " + reason
            )
        raise SystemExit("카카오워크 API 호출 실패: " + reason)
    if not body.get("success"):
        raise SystemExit(
            "카카오워크 API 오류: " + json.dumps(body.get("error") or body, ensure_ascii=False)
        )
    return body


def emails_of(user):
    return [i["value"] for i in (user.get("identifications") or []) if i.get("type") == "email"]


def cmd_rooms():
    body = api("GET", "/v1/conversations.list?limit=100")
    rooms = body.get("conversations") or []
    if not rooms:
        print("봇이 참여 중인 대화방이 없습니다.")
        return
    print("%-20s %-6s %-5s %s" % ("conversation_id", "type", "인원", "이름"))
    for r in rooms:
        print(
            "%-20s %-6s %-5s %s"
            % (r["id"], r.get("type", ""), r.get("users_count", ""), r.get("name", ""))
        )
    print("\n단체 대화방의 conversation_id 를 KAKAOWORK_CONVERSATION_ID 에 넣으세요.")


def cmd_users():
    body = api("GET", "/v1/users.list?limit=100")
    users = body.get("users") or []
    print("%-12s %-10s %-12s %s" % ("user_id", "이름", "상태", "이메일"))
    for u in users:
        print(
            "%-12s %-10s %-12s %s"
            % (u["id"], u.get("name", ""), u.get("status", ""), ", ".join(emails_of(u)))
        )


def cmd_open(emails):
    if len(emails) < 2:
        raise SystemExit("단체 대화방을 만들려면 이메일을 2개 이상 지정하세요.")

    body = api("GET", "/v1/users.list?limit=100")
    by_email = {}
    for u in body.get("users") or []:
        for em in emails_of(u):
            by_email[em.lower()] = u

    user_ids, missing = [], []
    for em in emails:
        u = by_email.get(em.lower())
        if u:
            user_ids.append(int(u["id"]))
            print("확인: %s -> %s (%s)" % (em, u["id"], u.get("name", "")))
        else:
            missing.append(em)
    if missing:
        raise SystemExit(
            "워크스페이스에서 찾을 수 없는 이메일: " + ", ".join(missing)
            + "\n`users` 명령으로 실제 계정 이메일을 확인하세요."
        )

    res = api("POST", "/v1/conversations.open", {"user_ids": user_ids})
    conv = res.get("conversation") or {}
    print("\n대화방 준비 완료")
    print("  conversation_id : %s" % conv.get("id"))
    print("  이름            : %s" % conv.get("name"))
    print("  종류 / 인원     : %s / %s" % (conv.get("type"), conv.get("users_count")))
    print("\n환경변수에 아래 한 줄을 넣으세요 (KAKAOWORK_EMAIL 보다 우선 적용됩니다).")
    print("  KAKAOWORK_CONVERSATION_ID=%s" % conv.get("id"))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("rooms", "users", "open"):
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "rooms":
        cmd_rooms()
    elif cmd == "users":
        cmd_users()
    else:
        cmd_open(sys.argv[2:])


if __name__ == "__main__":
    main()
