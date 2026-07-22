"""매일 저녁 7시반에 실행 — pending_posts.json에서 오늘 이미지를 꺼내 인스타에 게시한다."""
import os
import json
from datetime import date
from dotenv import load_dotenv

from ig_post import post_image

load_dotenv()

PENDING_PATH = os.path.join(os.path.dirname(__file__), "pending_posts.json")
PAGES_BASE = os.environ.get(
    "PAGES_BASE_URL", "https://koreanolleh.github.io/designgym-instagram-automation"
)

DAY_MAP = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}


def main():
    today = date.today()
    weekday = today.weekday()

    if weekday > 4:
        print("주말입니다. 게시하지 않습니다.")
        return

    if not os.path.exists(PENDING_PATH):
        print("pending_posts.json 없음.")
        return

    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        plan = json.load(f)

    day_key = DAY_MAP[weekday]
    post = plan.get("posts", {}).get(day_key)

    if not post:
        print(f"{day_key} 게시물이 없습니다.")
        return

    if post.get("posted"):
        print(f"{day_key} 게시물은 이미 게시됐습니다.")
        return

    image_url = f"{PAGES_BASE}/{post['image']}"
    caption = post["caption"]
    if post.get("hashtags"):
        caption = f"{caption}\n\n{post['hashtags']}"

    print(f"게시 중 [{day_key}]: {image_url}")
    post_id = post_image(image_url, caption)

    plan["posts"][day_key]["posted"] = True
    plan["posts"][day_key]["post_id"] = post_id
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"게시 완료: {post_id}")


if __name__ == "__main__":
    main()
