"""pending_posts.json에서 옵시디언 주간 노트를 생성한다 (노트가 없을 때만).

월요일 아침 클라우드 루틴이 JSON을 만들면, 맥이 켜졌을 때 launchd sync가
이 스크립트를 먼저 실행해 사용자가 검토·수정할 노트를 자동 생성한다.
"""
import os
import json
import urllib.request
from datetime import date

from prepare_week import OBSIDIAN_BASE, week_label

PENDING_PATH = os.path.join(os.path.dirname(__file__), "pending_posts.json")

DAYS = [
    ("Monday", "월요일"), ("Tuesday", "화요일"), ("Wednesday", "수요일"),
    ("Thursday", "목요일"), ("Friday", "금요일"),
]


def main():
    with open(PENDING_PATH, encoding="utf-8") as f:
        plan = json.load(f)

    week_of = plan.get("week_of", "")
    try:
        monday = date.fromisoformat(week_of)
    except ValueError:
        print("week_of 파싱 실패 — 스킵")
        return

    label = week_label(monday)
    week_dir = os.path.join(OBSIDIAN_BASE, label)
    note_path = os.path.join(week_dir, f"{label}.md")
    if os.path.exists(note_path):
        print("노트 이미 있음 — 스킵")
        return

    os.makedirs(week_dir, exist_ok=True)
    lines = [
        f"# 디자인짐 인스타그램 — {label}",
        "",
        "> 이미지를 보고 캡션/해시태그/틱톡제목을 직접 수정하세요. 수정하면 자동 반영됩니다(맥 켜져 있을 때).",
        "> 틱톡제목은 틱톡 화면에 보이는 유일한 글입니다 — 해시태그 포함 90자 이내로 유지하세요.",
        "> 이미지 자체를 바꾸고 싶으면 채팅으로 요청하세요. 매일 저녁 7시반 인스타+틱톡 자동 게시.",
        "",
    ]
    for day_en, day_kr in DAYS:
        post = plan["posts"].get(day_en)
        if not post:
            continue
        d = date.fromisoformat(post["date"])
        n_img = len(post.get("images", []))
        lines.append(
            f"## {day_kr} ({d.month}/{d.day}) — {post.get('product', '')} / {post.get('hook', '')} ({n_img}장)"
        )
        lines.append("")
        for i, img in enumerate(post.get("images", []), 1):
            fname = f"{day_en.lower()}_{i}.png"
            fpath = os.path.join(week_dir, fname)
            if not os.path.exists(fpath) and img.get("image_url"):
                try:
                    urllib.request.urlretrieve(img["image_url"], fpath)
                except Exception as e:
                    print(f"{fname} 다운로드 실패: {e}")
            lines.append(f"![[{fname}]]")
        lines += [
            "",
            "캡션:",
            post.get("caption", ""),
            "",
            "해시태그:",
            post.get("hashtags", ""),
            "",
            "틱톡제목:",
            post.get("tiktok_title", ""),
            "",
        ]
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"노트 생성 완료: {note_path}")


if __name__ == "__main__":
    main()
