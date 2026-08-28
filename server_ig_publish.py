"""GitHub Actions에서 오늘자 인스타그램 게시물을 발행한다 (AI 판단 없는 결정적 실행).

- pending_posts.json에서 예정일이 지났는데 아직 안 올라간 항목 중 가장 이른 것을 발행
  (GitHub 예약 실행이 몇 시간씩 밀려 날짜가 넘어가도 다음 실행 때 복구된다)
- 한 번에 한 건만 올린다. 밀린 게 여럿이면 다음 실행에서 이어서 처리
- IG_MAX_LATE_DAYS(기본 3)일보다 오래 밀린 건은 건너뛴다 — 철 지난 글을 뒤늦게 올리지 않기 위해
- 이미 ig_posted=True면 스킵 (중복 트리거에 안전 — cron·routine 어느 쪽이 먼저 와도 됨)
- 성공 시 posted/ig_posted 갱신 (커밋은 워크플로 스텝이 담당)
- DRY_RUN=1이면 발행 없이 대상 확인 + 토큰 유효성만 점검

시크릿: IG_ACCESS_TOKEN, IG_BUSINESS_ACCOUNT_ID (GitHub Secrets → env)

계정 전환: IG_PENDING_FILE로 발행 대상 파일을 바꾼다.
  - official  : 기본값 pending_posts.json
  - 사장(ceo) : IG_PENDING_FILE=pending_posts_ceo.json + 해당 계정 토큰/ID
"""
import os
import json
import sys
from datetime import datetime, timezone, timedelta

import requests

from ig_post import post_images, GRAPH_HOST, GRAPH_VERSION

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(BASE_DIR, os.environ.get("IG_PENDING_FILE", "pending_posts.json"))
ACCOUNT_LABEL = os.environ.get("IG_ACCOUNT_LABEL", "official")
MAX_LATE_DAYS = int(os.environ.get("IG_MAX_LATE_DAYS", "3"))


def due_posts(posts: dict, today: str):
    """예정일이 지났고 아직 안 올라간 항목을 이른 날짜순으로. [(day_key, entry, 밀린 일수)]"""
    out = []
    for k, p in posts.items():
        d = p.get("date")
        if not d or d > today or p.get("ig_posted"):
            continue
        late = (
            datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")
        ).days
        out.append((k, p, late))
    return sorted(out, key=lambda t: t[1]["date"])


def pick(posts: dict, today: str):
    """올릴 것 하나를 고른다.

    가장 최근 예정분부터 본다. 오래된 것부터 올리면 하루씩 밀린 상태가 계속 이어져
    영영 제 날짜를 못 따라잡는다. 오늘 것이 있으면 오늘 것이 먼저다.
    지나간 건 MAX_LATE_DAYS 안쪽이면 올리고, 그보다 오래됐으면 건너뛴다.

    반환: (day_key, entry, 밀린 일수, 안 올리고 넘긴 목록)
    """
    passed = []
    chosen = None
    for k, p, late in reversed(due_posts(posts, today)):
        if chosen is None and late <= MAX_LATE_DAYS:
            chosen = (k, p, late)
        else:
            passed.append((k, p["date"], late))
    if chosen is None:
        return None, None, 0, passed
    return (*chosen, passed)


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    with open(PENDING, encoding="utf-8") as f:
        data = json.load(f)

    posts = data.get("posts", {})
    day_key, entry, late, passed = pick(posts, today)

    for k, d, n in passed:
        why = f"{n}일 밀려 한도({MAX_LATE_DAYS}일) 초과" if n > MAX_LATE_DAYS else "더 최근 게시물이 있어 후순위"
        print(f"[{today}][{ACCOUNT_LABEL}] ⏭️ {k}({d}) 건너뜀 — {why}")

    if not entry:
        print(f"[{today}][{ACCOUNT_LABEL}] 올릴 게시물 없음 — 종료")
        return

    if late:
        print(f"[{today}][{ACCOUNT_LABEL}] ⏰ {entry['date']} 예정분이 {late}일 밀렸습니다 — 지금 올립니다")

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
        print(f"[DRY_RUN][{ACCOUNT_LABEL}] {day_key} {today} / 이미지 {len(urls)}장 / 토큰 점검: {me.status_code} {me.json()}")
        return

    media_id = post_images(urls, caption)
    print(f"[{today}][{ACCOUNT_LABEL}] {day_key} IG 게시 완료: media {media_id}")

    entry["posted"] = True
    entry["ig_posted"] = True
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
