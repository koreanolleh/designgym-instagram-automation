"""월요일에 그 주 5장의 이미지+캡션 초안을 pending_posts.json과 옵시디언 노트로 저장한다.
이미지 생성 자체(힉스필드 호출)는 Claude가 매주 월요일에 직접 수행하고,
그 결과(이미지 파일 + 캡션 텍스트)를 이 스크립트의 save_week()에 넘겨 저장한다.
"""
import os
import json
import shutil
from datetime import date, timedelta

REPO_DIR = os.path.dirname(__file__)
PENDING_PATH = os.path.join(REPO_DIR, "pending_posts.json")
IMAGES_DIR = os.path.join(REPO_DIR, "images")

OBSIDIAN_BASE = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/메이크앤&옵시디언"
    "/03_프로젝트/디자인짐_콘텐츠_자동화/인스타_자동화/주간초안"
)

DAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일"]
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def week_label(monday: date) -> str:
    week_of_month = (monday.day - 1) // 7 + 1
    return f"{monday.year}-{monday.month:02d} {monday.month}월 {week_of_month}주차"


def save_week(day_plans: dict, monday: date = None):
    """day_plans: {"Monday": {"image_path": "<repo 내 images/... 절대/상대경로>",
                               "image_url": "<힉스필드 rawUrl, 발행 시 이걸 그대로 사용>",
                               "product": "매트|밴드", "hook": "Drop In", "caption": "...", "hashtags": "..."}, ...}
    """
    if monday is None:
        today = date.today()
        monday = today - timedelta(days=today.weekday())

    week_dir_name = monday.isoformat()
    repo_week_dir = os.path.join(IMAGES_DIR, week_dir_name)
    os.makedirs(repo_week_dir, exist_ok=True)

    label = week_label(monday)
    obsidian_week_dir = os.path.join(OBSIDIAN_BASE, label)
    os.makedirs(obsidian_week_dir, exist_ok=True)

    plan = {"week_of": monday.isoformat(), "posts": {}}
    lines = [f"# 디자인짐 인스타그램 — {monday.year}년 {monday.month}월 {week_label(monday).split(' ')[1]} {week_label(monday).split(' ')[-1]}\n"]
    lines.append("> 이미지를 보고 캡션/해시태그를 직접 수정하세요. 이미지 자체를 바꾸고 싶으면 채팅으로 요청하세요.")
    lines.append("> 각 날짜 저녁 7시반~8시 사이에 자동 게시됩니다.\n")

    for i, (day_en, day_kr) in enumerate(zip(DAYS_EN, DAYS_KR)):
        post_date = monday + timedelta(days=i)
        info = day_plans.get(day_en)
        if not info:
            continue

        src_image = info["image_path"]
        image_filename = os.path.basename(src_image)

        # 저장소(발행용 소스) 이미지 배치
        repo_image_path = os.path.join(repo_week_dir, image_filename)
        if os.path.abspath(src_image) != os.path.abspath(repo_image_path):
            shutil.copy2(src_image, repo_image_path)

        # 옵시디언 볼트(리뷰용) 이미지 배치 — Obsidian이 파일명으로 임베드를 찾음
        obsidian_image_path = os.path.join(obsidian_week_dir, image_filename)
        shutil.copy2(repo_image_path, obsidian_image_path)

        plan["posts"][day_en] = {
            "date": post_date.isoformat(),
            "product": info.get("product", ""),
            "hook": info.get("hook", ""),
            "image": f"images/{week_dir_name}/{image_filename}",
            "image_url": info.get("image_url", ""),
            "caption": info.get("caption", ""),
            "hashtags": info.get("hashtags", ""),
            "posted": False,
        }

        lines.append(f"## {day_kr} ({post_date.month}/{post_date.day}) — {info.get('product','')} / {info.get('hook','')}\n")
        lines.append(f"![[{image_filename}]]\n")
        lines.append("캡션:")
        lines.append(f"{info.get('caption','')}\n")
        lines.append("해시태그:")
        lines.append(f"{info.get('hashtags','')}\n")

    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    note_path = os.path.join(obsidian_week_dir, f"{label}.md")
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"pending_posts.json 저장 완료: {PENDING_PATH}")
    print(f"옵시디언 노트 저장 완료: {note_path}")
    return plan
