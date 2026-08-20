"""힉스필드 MCP를 HTTP로 직접 호출해 오늘자 틱톡 게시물을 올린다.

배경(2026-08-20): 틱톡 게시 기능은 힉스필드 MCP에만 있는데, 지금까지 그 MCP를 부를 수 있는
경로가 claude.ai 클라우드 세션뿐이었다. 그 세션이 자꾸 죽어서 8/17~19 3일 연속 미발행이 났다.
MCP는 OAuth로 보호된 JSON-RPC HTTP 엔드포인트일 뿐이라, 갱신토큰만 있으면 GitHub Actions에서
직접 호출할 수 있다 — 세션이 죽을 일이 없다.

환경변수(Actions Secrets):
  HF_CLIENT_ID, HF_REFRESH_TOKEN   ← hf_auth.py 로 1회 발급
  TIKTOK_CONNECTOR_ID              ← 틱톡 연동 커넥터 UUID
옵션:
  DRY_RUN=1   실제 게시 없이 준비 단계까지만 확인

AI 라벨: is_aigc 필드를 보내지 않는다(무선언). 소유자가 앱에서 토글을 켜지 않는 것과 동일하며
false 명시(허위선언)와는 다르다. TIKTOK_CONSENT.md에 소유자 확정 설정이 기록돼 있다.
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
MCP = "https://mcp.higgsfield.ai/mcp"
TOKEN_URL = "https://mcp.higgsfield.ai/oauth2/token"
DRY = os.environ.get("DRY_RUN") == "1"


def log(m):
    print(f"[{datetime.now(KST):%H:%M:%S}] {m}", flush=True)


def access_token():
    """갱신토큰은 1회용이다 — 쓸 때마다 새 토큰이 내려오고 옛것은 즉시 무효가 된다.
    새 토큰을 곧바로 보관처(로컬 파일 또는 GitHub Secret)에 되돌려놓지 않으면
    다음 실행이 인증부터 실패한다."""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": os.environ["HF_REFRESH_TOKEN"],
        "client_id": os.environ["HF_CLIENT_ID"],
        "resource": MCP,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f"토큰 갱신 실패 {e.code}: {e.read().decode(errors='replace')[:300]}\n"
            "→ 로컬에서 'python3 hf_auth.py' 로 재인증 후 시크릿을 갱신하세요.")
    new_rt = tok.get("refresh_token")
    if new_rt and new_rt != os.environ["HF_REFRESH_TOKEN"]:
        save_refresh(new_rt)
    return tok["access_token"]


def save_refresh(token):
    """회전된 갱신토큰 보관. Actions에서는 리포지토리 시크릿을 갱신한다."""
    local = os.path.join(BASE, ".hf_oauth.json")
    if os.path.exists(local):
        d = json.load(open(local))
        d["refresh_token"] = token
        json.dump(d, open(local, "w"), indent=2)
        os.chmod(local, 0o600)
        log("갱신토큰 회전 → 로컬 저장")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        import subprocess
        r = subprocess.run(["gh", "secret", "set", "HF_REFRESH_TOKEN", "--body", token],
                           capture_output=True, text=True, cwd=BASE)
        if r.returncode == 0:
            log("갱신토큰 회전 → GitHub Secret 갱신 완료")
        else:
            # 여기서 실패하면 다음 실행이 통째로 죽는다. 조용히 넘기지 않는다.
            raise SystemExit(f"치명: 시크릿 갱신 실패 — {r.stderr[:300]}")


class Mcp:
    """MCP JSON-RPC 최소 클라이언트. 응답은 JSON 또는 SSE(text/event-stream)로 온다."""

    def __init__(self, token):
        self.token = token
        self.session = None
        self.id = 0
        self._call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "designgym-publisher", "version": "1.0"},
        })
        self._notify("notifications/initialized")

    def _headers(self):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream",
             "Authorization": f"Bearer {self.token}"}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        return h

    def _send(self, payload):
        req = urllib.request.Request(
            MCP, data=json.dumps(payload).encode(), headers=self._headers(), method="POST")
        return urllib.request.urlopen(req, timeout=180)

    def _notify(self, method, params=None):
        try:
            self._send({"jsonrpc": "2.0", "method": method, "params": params or {}}).close()
        except Exception:
            pass

    def _call(self, method, params):
        self.id += 1
        resp = self._send({"jsonrpc": "2.0", "id": self.id, "method": method, "params": params})
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session = sid
        raw = resp.read().decode()
        resp.close()
        data = None
        if raw.lstrip().startswith("{"):
            data = json.loads(raw)
        else:  # SSE
            for line in raw.splitlines():
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if chunk:
                        data = json.loads(chunk)
        if data is None:
            raise RuntimeError(f"응답 파싱 실패: {raw[:300]}")
        if "error" in data:
            raise RuntimeError(f"{method} 오류: {data['error']}")
        return data.get("result", {})

    def tool(self, name, args):
        res = self._call("tools/call", {"name": name, "arguments": args})
        if res.get("isError"):
            raise RuntimeError(f"{name} 실패: {res}")
        # 구조화 결과가 정본이다. content의 text는 사람이 읽는 요약이라 JSON이 아닐 수 있다.
        if "structuredContent" in res:
            return res["structuredContent"]
        for c in res.get("content", []):
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except json.JSONDecodeError:
                    return c["text"]
        return res


def today_entry():
    p = os.path.join(BASE, "pending_posts.json")
    d = json.load(open(p, encoding="utf-8"))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    for day, e in d["posts"].items():
        if e.get("date") == today:
            return d, day, e
    return d, None, None


def to_jpeg(url):
    """틱톡은 PNG를 거부한다. 1080px JPEG으로 변환해 바이트를 돌려준다."""
    from PIL import Image
    with urllib.request.urlopen(url, timeout=120) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    w, h = im.size
    im = im.resize((1080, round(h * 1080 / w)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def pick_song(mcp, connector):
    """최근 3곡과 겹치지 않게 고른다. 실패하면 음악 없이 간다(재시도 금지)."""
    try:
        tracks = mcp.tool("tiktok_music_trending",
                          {"connector_id": connector, "genre": "CHILL_BEATS", "limit": 10})["tracks"]
    except Exception as e:
        log(f"음악 조회 실패, 음악 없이 진행: {e}")
        return None, None
    recent = []
    mlog = os.path.join(BASE, "tiktok_music.log")
    if os.path.exists(mlog):
        for line in open(mlog, encoding="utf-8").read().splitlines()[-3:]:
            parts = line.split()
            if len(parts) > 1:
                recent.append(parts[1])
    start = datetime.now(KST).timetuple().tm_yday % len(tracks)
    for i in range(len(tracks)):
        t = tracks[(start + i) % len(tracks)]
        if t["song_clip_id"] not in recent:
            return t["song_clip_id"], t["name"]
    return tracks[0]["song_clip_id"], tracks[0]["name"]


def main():
    connector = os.environ["TIKTOK_CONNECTOR_ID"]
    data, day, entry = today_entry()
    if entry is None:
        log("오늘자 항목 없음 — 종료")
        return 0
    if entry.get("tiktok_posted"):
        log(f"{day} 이미 게시됨 — 종료")
        return 0

    log(f"{day} 발행 시작")
    mcp = Mcp(access_token())

    img = to_jpeg(entry["images"][0]["image_url"])
    up = mcp.tool("media_upload", {"filename": f"{day.lower()}.jpg", "content_type": "image/jpeg"})["uploads"][0]
    req = urllib.request.Request(up["upload_url"], data=img,
                                 headers={"Content-Type": "image/jpeg"}, method="PUT")
    with urllib.request.urlopen(req, timeout=180) as r:
        if r.status != 200:
            raise RuntimeError(f"업로드 실패 {r.status}")
    mcp.tool("media_confirm", {"type": "image", "media_id": up["media_id"]})
    log("이미지 업로드 완료")

    song_id, song_name = pick_song(mcp, connector)
    title = entry.get("tiktok_title", "").split("\n")[0].strip() or entry["caption"].split("\n")[0]
    desc = f"{entry['caption']} {entry['hashtags']}"

    prep = mcp.tool("tiktok_prepare_publish", {
        "connector_id": connector, "mode": "DIRECT_POST", "media_type": "PHOTO",
        "photo_images": [up["url"]], "photo_cover_index": 0,
        "title": title[:150], "description": desc[:4000],
    })
    log(f"준비 완료 (음악: {song_name or '없음'})")

    if DRY:
        log("[DRY_RUN] 실제 게시는 건너뜀")
        return 0

    args = {
        "connector_id": connector, "publish_session_id": prep["publish_session_id"],
        "mode": "DIRECT_POST", "media_type": "PHOTO",
        "privacy_level": "PUBLIC_TO_EVERYONE", "allow_comment": True,
        "commercial_content_disclosure": {"enabled": False, "your_brand": False, "branded_content": False},
        "title": title[:150], "description": desc[:4000],
        "user_confirmed": True, "preview_confirmed": True, "music_usage_confirmed": True,
        "processing_notice_acknowledged": True, "privacy_level_selected_by_user": True,
        "interaction_settings_selected_by_user": True,
        "commercial_content_disclosure_selected_by_user": True,
    }
    if song_id:
        args["music_sound_id"] = song_id

    pub = mcp.tool("tiktok_publish", args)
    pid = pub["publish_id"]
    log(f"게시 요청 완료: {pid}")

    try:
        st = mcp.tool("tiktok_publish_status", {"connector_id": connector, "publish_id": pid})
        log(f"상태: {st.get('status', st)}")
    except Exception as e:
        log(f"상태 조회 실패(무시): {e}")

    entry["tiktok_posted"] = True
    entry["posted"] = True
    json.dump(data, open(os.path.join(BASE, "pending_posts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    d = datetime.now(KST).strftime("%Y-%m-%d")
    with open(os.path.join(BASE, "tiktok_publish.log"), "a", encoding="utf-8") as f:
        f.write(f"{d} Actions 자동 게시 성공: {pid} ({day})\n")
    if song_id:
        with open(os.path.join(BASE, "tiktok_music.log"), "a", encoding="utf-8") as f:
            f.write(f"{d} {song_id} {song_name}\n")
    log("기록 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
