"""틱톡 앱 심사 데모용 로컬 백엔드.

designgym.co.kr에 올린 데모 페이지(tiktok-demo.html)가 이 서버를 호출한다.
client_secret을 브라우저에 노출하지 않기 위한 최소 프록시.
Chrome은 https 페이지 → http://localhost 요청을 혼합콘텐츠 예외로 허용한다.

실행: cd tiktok-review-demo && python3 server.py  (포트 8787)
"""
import os
import json
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = {}
with open(os.path.join(BASE, ".env")) as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            ENV[k] = v

ALLOWED_ORIGIN = "https://designgym.co.kr"
TT = "https://open.tiktokapis.com"


def tt_request(path, data=None, token=None, method=None):
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data).encode()
    req = urllib.request.Request(TT + path, data=body, headers=headers, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:2000]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        payload = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self._send({})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        if self.path == "/api/token":
            body = self._read_json()
            form = urllib.parse.urlencode({
                "client_key": ENV["TT_CLIENT_KEY"],
                "client_secret": ENV["TT_CLIENT_SECRET"],
                "code": body.get("code", ""),
                "grant_type": "authorization_code",
                "redirect_uri": ENV["TT_REDIRECT_URI"],
            }).encode()
            req = urllib.request.Request(
                TT + "/v2/oauth/token/", data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self._send(json.load(r))
            except urllib.error.HTTPError as e:
                self._send({"http_error": e.code, "body": e.read().decode()[:2000]}, 500)
            return

        if self.path == "/api/publish":
            body = self._read_json()
            token = body.get("access_token", "")
            payload = {
                "media_type": "PHOTO",
                "post_mode": "DIRECT_POST",
                "post_info": {
                    "title": body.get("title", ""),
                    "description": body.get("description", ""),
                    "privacy_level": body.get("privacy_level", "SELF_ONLY"),
                    "disable_comment": not body.get("allow_comment", True),
                    "auto_add_music": True,
                    "brand_content_toggle": bool(body.get("branded_content", False)),
                    "brand_organic_toggle": bool(body.get("your_brand", False)),
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_images": body.get("photo_images", []),
                    "photo_cover_index": 0,
                },
            }
            if body.get("is_aigc") is True:
                payload["post_info"]["is_aigc"] = True
            self._send(tt_request("/v2/post/publish/content/init/", payload, token))
            return

        if self.path == "/api/status":
            body = self._read_json()
            self._send(tt_request("/v2/post/publish/status/fetch/",
                                  {"publish_id": body.get("publish_id", "")},
                                  body.get("access_token", "")))
            return

        self._send({"error": "unknown endpoint"}, 404)

    def do_GET(self):
        if self.path.startswith("/api/userinfo"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            token = (qs.get("token") or [""])[0]
            self._send(tt_request("/v2/user/info/?fields=open_id,union_id,avatar_url,display_name", token=token, method="GET"))
            return
        self._send({"ok": True, "service": "designgym tiktok demo backend"})

    def log_message(self, fmt, *args):
        print("[demo]", fmt % args)


if __name__ == "__main__":
    print("데모 백엔드 시작: http://localhost:8787 (허용 오리진: %s)" % ALLOWED_ORIGIN)
    HTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
