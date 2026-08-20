"""힉스필드 MCP용 OAuth 토큰을 발급받는다 (1회만 실행).

배경(2026-08-20): 틱톡 게시는 힉스필드 MCP에만 있고, 그동안 이 MCP를 부를 수 있는 건
claude.ai 클라우드 세션뿐이었다. 그런데 그 세션이 예고 없이 죽어서 8/17~8/19 3일 연속
미발행이 났다(이슈 #10·11·12). MCP 엔드포인트는 그냥 OAuth로 보호된 HTTP(JSON-RPC)라서,
갱신토큰만 있으면 GitHub Actions(안 죽는 인프라)에서 직접 호출할 수 있다.

사용:
  python3 hf_auth.py            # 브라우저 1회 승인 → refresh_token 출력
  python3 hf_auth.py --refresh  # 저장된 refresh_token으로 access_token 발급 테스트
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

AS = "https://mcp.higgsfield.ai"
REGISTER = f"{AS}/oauth2/register"
AUTHORIZE = f"{AS}/oauth2/authorize"
TOKEN = f"{AS}/oauth2/token"
REDIRECT = "http://127.0.0.1:8765/callback"
SCOPE = "openid email offline_access"
STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hf_oauth.json")


def post_json(url, data, form=False):
    if form:
        body = urllib.parse.urlencode(data).encode()
        ct = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(data).encode()
        ct = "application/json"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ct}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise SystemExit(f"토큰 요청 실패 {e.code}: {detail}")


def register_client():
    return post_json(REGISTER, {
        "client_name": "designgym-tiktok-publisher",
        "redirect_uris": [REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    })


class Catcher(http.server.BaseHTTPRequestHandler):
    code = None
    error = None

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        # 승인 전 프리플라이트/오배송 요청이 먼저 닿아도 code가 올 때까지 계속 받는다
        if q.get("code"):
            Catcher.code = q["code"][0]
        elif q.get("error") or q.get("error_description"):
            Catcher.error = (q.get("error_description") or q.get("error"))[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "인증 완료 — 이 창을 닫으셔도 됩니다." if Catcher.code else f"실패: {Catcher.error}"
        self.wfile.write(f"<html><body style='font:16px sans-serif;padding:40px'>{msg}</body></html>".encode())

    def log_message(self, *a):
        pass


def login():
    client = register_client()
    cid = client["client_id"]
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    url = AUTHORIZE + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": REDIRECT,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": "https://mcp.higgsfield.ai/mcp",
    })

    srv = http.server.HTTPServer(("127.0.0.1", 8765), Catcher)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("브라우저에서 힉스필드 로그인/승인을 진행하세요:")
    print(url)
    webbrowser.open(url)

    for _ in range(600):
        if Catcher.code:
            break
        threading.Event().wait(0.5)
    srv.shutdown()
    srv.server_close()

    if not Catcher.code:
        raise SystemExit(f"인증 실패: {Catcher.error}")

    tok = post_json(TOKEN, {
        "grant_type": "authorization_code",
        "code": Catcher.code,
        "redirect_uri": REDIRECT,
        "client_id": cid,
        "code_verifier": verifier,
        "resource": "https://mcp.higgsfield.ai/mcp",
    }, form=True)

    data = {"client_id": cid, "refresh_token": tok.get("refresh_token"),
            "access_token": tok.get("access_token")}
    with open(STORE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(STORE, 0o600)
    print(f"\n저장 완료 → {STORE}")
    print(f"refresh_token 있음: {bool(tok.get('refresh_token'))}")
    print(f"만료(초): {tok.get('expires_in')}")


def refresh():
    d = json.load(open(STORE))
    tok = post_json(TOKEN, {
        "grant_type": "refresh_token",
        "refresh_token": d["refresh_token"],
        "client_id": d["client_id"],
        "resource": "https://mcp.higgsfield.ai/mcp",
    }, form=True)
    if tok.get("refresh_token"):
        d["refresh_token"] = tok["refresh_token"]
    d["access_token"] = tok["access_token"]
    with open(STORE, "w") as f:
        json.dump(d, f, indent=2)
    print(f"갱신 성공, 만료(초): {tok.get('expires_in')}")
    return tok["access_token"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    refresh() if a.refresh else login()
