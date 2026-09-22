"""인스타그램 로그인 토큰을 만료 전에 갱신해 GitHub Secrets 에 되돌려 쓴다 (Actions 전용).

배경(2026-09-22): official 계정 토큰이 9/20 에 60일 만료로 조용히 죽었고, 화요일 발행 때
처음 드러났다. Instagram 로그인 API 토큰은 60일짜리이고 더 긴 종류는 없다 — 대신 만료 전에
갱신하면 그때마다 60일이 새로 붙어 사실상 무기한이다. 갱신 조건: 아직 유효할 것, 발급 24시간
경과. 이미 만료된 토큰은 갱신이 안 되고 콘솔에서 사람이 재발급해야 한다.

매주 돌면서 두 계정 토큰을 갱신한다. 하나가 실패해도 다른 하나는 계속 진행하고, 실패는
종료코드로 알려 워크플로가 이슈를 만들게 한다.

시크릿: IG_ACCESS_TOKEN(official) / IG_CEO_ACCESS_TOKEN(사장) / GH_PAT(시크릿 쓰기)
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

GRAPH = "https://graph.instagram.com"
ACCOUNTS = [("IG_ACCESS_TOKEN", "official"), ("IG_CEO_ACCESS_TOKEN", "designgym.ceo")]


def log(m):
    print(m, flush=True)


def refresh(token):
    url = f"{GRAPH}/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_refresh_token", "access_token": token})
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def whoami(token):
    url = f"{GRAPH}/v21.0/me?" + urllib.parse.urlencode({"fields": "username", "access_token": token})
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read()).get("username")


def save_secret(name, value):
    p = subprocess.run(["gh", "secret", "set", name], input=value, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"gh secret set {name} 실패: {p.stderr.strip()[:200]}")


def main():
    failed = []
    for secret, label in ACCOUNTS:
        tok = os.environ.get(secret, "").strip()
        if not tok:
            log(f"[{label}] 시크릿 {secret} 비어 있음 — 건너뜀")
            failed.append(label)
            continue
        try:
            d = refresh(tok)
            new, ttl = d["access_token"], int(d.get("expires_in", 0))
            user = whoami(new)                       # 새 토큰이 실제로 동작하는지 확인하고 나서 저장
            save_secret(secret, new)
            exp = datetime.now() + timedelta(seconds=ttl)
            log(f"[{label}] 갱신 완료 → @{user}, 새 만료 {exp:%Y-%m-%d} ({ttl // 86400}일)")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            log(f"[{label}] 갱신 실패 HTTP {e.code}: {body}")
            failed.append(label)
        except Exception as e:
            log(f"[{label}] 갱신 실패: {e}")
            failed.append(label)

    if failed:
        log(f"실패한 계정: {', '.join(failed)} — 만료됐다면 콘솔에서 재발급이 필요하다")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
