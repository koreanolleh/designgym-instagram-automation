"""힉스필드 MCP용 OAuth 토큰을 발급받는다 (1회만 실행).

배경(2026-08-20): 틱톡 게시는 힉스필드 MCP에만 있고, 그동안 이 MCP를 부를 수 있는 건
claude.ai 클라우드 세션뿐이었다. 그런데 그 세션이 예고 없이 죽어서 8/17~8/19 3일 연속
미발행이 났다(이슈 #10·11·12). MCP 엔드포인트는 그냥 OAuth로 보호된 HTTP(JSON-RPC)라서,
갱신토큰만 있으면 GitHub Actions(안 죽는 인프라)에서 직접 호출할 수 있다.

사용:
  python3 hf_auth.py            # 브라우저 1회 승인 → GitHub Secrets에 심고 로컬 사본 삭제
  python3 hf_auth.py --keep     # 로컬에 토큰을 남긴다 (디버깅용, 평소 쓰지 말 것)

★ 갱신토큰은 GitHub Secrets 한 곳에만 둔다. 로컬에 사본을 남기고 나중에 그걸로 실행하면,
서버가 '이미 폐기된 토큰 재사용'으로 보고 **체인 전체를 무효화**한다 — 그러면 정상이던
Actions 쪽 토큰까지 같이 죽는다(2026-08-28에 실제로 이렇게 발행이 멈췄다).
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
# 2026-11-23: 8765 를 사장님의 다른 서버(bc-outreach/app.py)가 쓰고 있어 재인증이 막혔다.
# 클라이언트는 매번 새로 등록하므로 포트는 바꿔도 된다 — 막혀 있으면 환경변수로 넘긴다.
CALLBACK_PORT = int(os.environ.get("HF_CALLBACK_PORT", "8765"))
REDIRECT = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
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
    expect_state = None          # 이번 시도의 state. 다른 값이 오면 남의 탭이다.
    stale = 0

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        got_state = (q.get("state") or [None])[0]
        # ★ 2026-11-23: 예전 시도의 브라우저 탭이 열린 채로 남아 있다가 거기서 승인되면,
        # 그 코드가 새 서버로 들어와 "Client ID from this request does not match" 로 깨졌다.
        # 이번 시도의 state 와 다른 콜백은 받지 않는다 — 옛 탭이 흐름을 망치지 못하게.
        if got_state and Catcher.expect_state and got_state != Catcher.expect_state:
            Catcher.stale += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<html><body style='font:16px sans-serif;padding:40px'>"
                             "오래된 탭입니다 — 이 창은 닫고, 새로 연 승인 화면에서 진행하세요."
                             "</body></html>".encode())
            return
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


def login(keep_local=False):
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

    Catcher.code = Catcher.error = None
    Catcher.expect_state = state
    try:
        srv = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), Catcher)
    except OSError as e:
        raise SystemExit(f"콜백 포트 {CALLBACK_PORT} 를 못 엽니다 ({e}). "
                         f"다른 프로그램이 쓰고 있으면 HF_CALLBACK_PORT=8766 처럼 바꿔 주세요.")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("브라우저에서 힉스필드 로그인/승인을 진행하세요:")
    print(url)
    webbrowser.open(url)

    # 2026-11-23: 5분(600×0.5초)은 너무 짧았다. 사장님이 승인하기 전에 서버가 닫혀
    # "인증 실패: None" 으로 끝났고, 그 사이 열려 있던 옛 탭에서 승인하면 또 안 돌아온다.
    for _ in range(int(os.environ.get("HF_WAIT_SECONDS", "1800")) * 2):
        if Catcher.code:
            break
        threading.Event().wait(0.5)
    srv.shutdown()
    srv.server_close()

    if not Catcher.code:
        extra = (f" (옛 탭에서 온 콜백 {Catcher.stale}건을 무시했습니다 — 그 탭들을 닫고 "
                 f"새로 연 화면에서 승인하세요)") if Catcher.stale else ""
        raise SystemExit(f"인증 실패: {Catcher.error}{extra}")

    tok = post_json(TOKEN, {
        "grant_type": "authorization_code",
        "code": Catcher.code,
        "redirect_uri": REDIRECT,
        "client_id": cid,
        "code_verifier": verifier,
        "resource": "https://mcp.higgsfield.ai/mcp",
    }, form=True)

    rt = tok.get("refresh_token")
    if not rt:
        raise SystemExit("갱신토큰이 안 내려왔습니다 — offline_access 스코프를 확인하세요")

    if keep_local:
        with open(STORE, "w") as f:
            json.dump({"client_id": cid, "refresh_token": rt}, f, indent=2)
        os.chmod(STORE, 0o600)
        print(f"\n로컬 저장 → {STORE}  (★ 이걸로 발행 스크립트를 돌리지 말 것)")
        return

    seed_secrets(cid, rt)


def seed_secrets(cid, rt):
    """토큰을 GitHub Secrets에만 심고 로컬 사본은 남기지 않는다."""
    import subprocess
    for name, val in (("HF_CLIENT_ID", cid), ("HF_REFRESH_TOKEN", rt)):
        r = subprocess.run(["gh", "secret", "set", name, "--body", val],
                           capture_output=True, text=True,
                           cwd=os.path.dirname(os.path.abspath(__file__)))
        if r.returncode != 0:
            raise SystemExit(f"시크릿 {name} 설정 실패: {r.stderr[:300]}")
        print(f"GitHub Secret {name} 갱신 완료")
    # 로컬에는 토큰을 남기지 않는다 (재사용 감지로 체인이 죽는 사고 방지)
    with open(STORE, "w") as f:
        json.dump({"client_id": cid,
                   "note": "갱신토큰은 GitHub Secrets에만 있다. 로컬 실행 금지."}, f,
                  ensure_ascii=False, indent=2)
    os.chmod(STORE, 0o600)
    print(f"로컬 사본 제거 완료 → {STORE} (client_id만 남김)")


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
    ap.add_argument("--keep", action="store_true",
                    help="로컬에 토큰을 남긴다(디버깅용). 평소에는 쓰지 말 것")
    a = ap.parse_args()
    login(keep_local=a.keep)
