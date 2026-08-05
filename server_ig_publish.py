"""GitHub Actions에서 오늘자 인스타그램 게시물을 발행한다 (AI 판단 없는 결정적 실행).

- pending_posts.json에서 date==오늘(KST)인 항목을 찾아 발행
- 이미 ig_posted=True면 스킵 (중복 트리거에 안전 — cron·routine 어느 쪽이 먼저 와도 됨)
- 성공 시 posted/ig_posted 갱신 (커밋은 워크플로 스텝이 담당)
- DRY_RUN=1이면 발행 없이 대상 확인 + 토큰 유효성만 점검

시크릿: IG_ACCESS_TOKEN, IG_BUSINESS_ACCOUNT_ID (GitHub Secrets → env)
"""
import os
import json
import sys
from datetime import datetime, timezone, timedelta

import requests

from ig_post import post_images, GRAPH_HOST, GRAPH_VERSION

KST = timezone(timedelta(hours=9))
PENDING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_posts.json")


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    with open(PENDING, encoding="utf-8") as f:
        data = json.load(f)

    day_key, entry = None, None
    for k, p in data.get("posts", {}).items():
        if p.get("date") == today:
            day_key, entry = k, p
            break

    if not entry:
        print(f"[{today}] 오늘자 게시물 없음 — 종료")
        return

    if entry.get("ig_posted"):
        print(f"[{today}] {day_key} 이미 IG 게시됨 — 스킵")
        return

    urls = [im["image_url"] for im in entry.get("images", []) if im.get("image_url")]
    caption = entry.get("caption", "").strip() + "\n\n" + entry.get("hashtags", "").strip()
    if not urls:
        print(f"[{today}] 이미지 URL 없음 — 실패로 종료", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("DRY_RUN") == "1":
        token = os.environ["IG_ACCESS_TOKEN"]
        me = requests.get(
            f"{GRAPH_HOST}/{GRAPH_VERSION}/me",
            params={"fields": "id,username", "access_token": token},
            timeout=30,
        )
        print(f"[DRY_RUN] {day_key} {today} / 이미지 {len(urls)}장 / 토큰 점검: {me.status_code} {me.json()}")
        return

    media_id = post_images(urls, caption)
    print(f"[{today}] {day_key} IG 게시 완료: media {media_id}")

    entry["posted"] = True
    entry["ig_posted"] = True
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
