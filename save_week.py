"""주간 초안을 pending_posts.json에 저장하고 즉시 커밋·push한다.

클라우드 루틴이 JSON을 손으로 쓰거나 git 명령을 조합하지 않도록 하는 스크립트.
2단계로 나눠 부르는 것이 핵심 — 세션이 뒤에서 죽어도 이미지는 저장소에 남는다.

  1) 이미지 생성 직후 (캡션 없이도 즉시 저장)
     python3 save_week.py --images /tmp/images.json
  2) 캡션 작성 후
     python3 save_week.py --captions /tmp/captions.json

--images 입력 형식:
  {"week_of": "2026-08-17",
   "posts": {"Monday": {"product": "...", "hook": "...",
                        "image_urls": ["https://...png", ...]}, ...}}

--captions 입력 형식:
  {"posts": {"Monday": {"caption": "...", "hashtags": "...", "tiktok_title": "..."}, ...}}

두 경우 모두 저장 후 커밋·push까지 수행하며, push 충돌 시 pull --rebase 후 2회 재시도한다.
push에 쓰는 인증은 clone URL에 이미 들어 있으므로 이 스크립트는 토큰을 다루지 않는다.
"""
import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(BASE, "pending_posts.json")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def run(cmd, check=False):
    p = subprocess.run(cmd, cwd=BASE, shell=True, capture_output=True, text=True)
    if check and p.returncode != 0:
        print(f"[실패] {cmd}\n{p.stdout}{p.stderr}", file=sys.stderr)
    return p.returncode, (p.stdout + p.stderr).strip()


def monday_of_this_week() -> str:
    today = datetime.now(KST).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def load_pending() -> dict:
    if os.path.exists(PENDING):
        with open(PENDING, encoding="utf-8") as f:
            return json.load(f)
    return {"week_of": "", "posts": {}}


def save_pending(data: dict):
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def commit_push(message: str) -> bool:
    run("git config user.name claude-cloud-routine")
    run("git config user.email cloud@example.com")
    run("git add pending_posts.json")
    rc, _ = run("git diff --staged --quiet")
    if rc == 0:
        print("변경 없음 — 커밋 생략")
        return True
    run(f'git commit -m "{message}"', check=True)
    for attempt in range(1, 4):
        rc, out = run("git push")
        if rc == 0:
            print(f"push 성공 (시도 {attempt})")
            return True
        print(f"push 실패 (시도 {attempt}): {out[-300:]}", file=sys.stderr)
        run("git pull --rebase --autostash")
        time.sleep(3)
    print("push 최종 실패", file=sys.stderr)
    return False


def stage_images(payload: dict) -> bool:
    week_of = payload.get("week_of") or monday_of_this_week()
    monday = datetime.fromisoformat(week_of).date()

    data = load_pending()
    # 새 주차면 통째로 새로 시작한다(지난주 posted 플래그가 섞이지 않도록).
    if data.get("week_of") != week_of:
        data = {"week_of": week_of, "posts": {}}

    written = []
    for i, day in enumerate(DAYS):
        src = payload.get("posts", {}).get(day)
        if not src:
            continue
        urls = [u for u in src.get("image_urls", []) if u]
        if not urls:
            print(f"[경고] {day}: image_urls 비어 있음 — 건너뜀", file=sys.stderr)
            continue
        prev = data["posts"].get(day, {})
        data["posts"][day] = {
            "date": (monday + timedelta(days=i)).isoformat(),
            "product": src.get("product", prev.get("product", "")),
            "hook": src.get("hook", prev.get("hook", "")),
            "images": [{"path": "", "image_url": u} for u in urls],
            # 캡션은 2단계에서 채운다. 그 전에 발행되지 않도록 posted는 False 유지.
            "caption": prev.get("caption", ""),
            "hashtags": prev.get("hashtags", ""),
            "tiktok_title": prev.get("tiktok_title", ""),
            "posted": False,
            "ig_posted": None,
            "tiktok_posted": None,
        }
        written.append(f"{day}({len(urls)}장)")

    if not written:
        print("저장할 이미지가 없습니다 — 중단", file=sys.stderr)
        return False

    save_pending(data)
    print(f"[1단계] 이미지 저장: {week_of} / " + ", ".join(written))
    return commit_push(f"{week_of} 주차 이미지 생성 (1/2 이미지)")


def stage_captions(payload: dict) -> bool:
    data = load_pending()
    if not data.get("posts"):
        print("pending_posts.json이 비어 있습니다 — 1단계를 먼저 실행하세요", file=sys.stderr)
        return False

    filled = []
    for day in DAYS:
        src = payload.get("posts", {}).get(day)
        if not src or day not in data["posts"]:
            continue
        entry = data["posts"][day]
        for field in ("caption", "hashtags", "tiktok_title"):
            if src.get(field):
                entry[field] = src[field]
        tt = entry.get("tiktok_title", "")
        if len(tt) > 90:
            print(f"[경고] {day}: tiktok_title {len(tt)}자 (90자 초과)", file=sys.stderr)
        filled.append(day)

    missing = [d for d in DAYS if d in data["posts"] and not data["posts"][d].get("caption")]
    if missing:
        print(f"[경고] 캡션 비어 있는 요일: {', '.join(missing)}", file=sys.stderr)

    save_pending(data)
    print(f"[2단계] 캡션 저장: {', '.join(filled) if filled else '없음'}")
    return commit_push(f"{data.get('week_of','')} 주차 캡션 작성 (2/2 캡션)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", help="1단계 입력 JSON 경로")
    ap.add_argument("--captions", help="2단계 입력 JSON 경로")
    args = ap.parse_args()

    if not args.images and not args.captions:
        ap.error("--images 또는 --captions 중 하나가 필요합니다")

    path = args.images or args.captions
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    ok = stage_images(payload) if args.images else stage_captions(payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
