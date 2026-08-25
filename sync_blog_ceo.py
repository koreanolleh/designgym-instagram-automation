"""옵시디언 노트의 블로그 원고 수정분을 weeks/<주차>.json에 되돌려 반영한다.

sync_from_obsidian_ceo.py는 인스타 캡션·해시태그만 다루고 블로그 원고(###)는 건드리지 않는다.
이 스크립트가 그 반대편을 맡는다: 노트의 `### 블로그 원고 — 제목` 블록을 읽어
carousels[].blog_title / blog 에 덮어쓴다.

blog_image_plan의 after 값은 본문 소제목 문자열을 가리키므로, 사장님이 소제목을 고치면
앵커가 깨진다. 그 경우 계획을 통째로 지워서 write_post.js의 자동 배치(소제목마다 1장)로
넘긴다 — 이미지 몇 장을 조용히 빠뜨리는 것보다 낫다.

사용: python sync_blog_ceo.py weeks/2026-08-24.json
"""
import json
import os
import re
import sys
from datetime import date

from prepare_week import week_label

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OBSIDIAN_CEO_BASE = os.environ.get("CEO_NOTE_BASE") or os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/메이크앤&옵시디언/"
    "03_프로젝트/디자인짐_콘텐츠_자동화/사장계정_주간초안"
)

DAY_KR = {1: "화요일", 3: "목요일", 5: "토요일"}


def parse_note(content: str) -> dict:
    """요일 → {title, body}. 블로그 원고 블록이 없는 요일은 빠진다."""
    out = {}
    for m in re.finditer(r"## (화요일|목요일|토요일)[^\n]*\n([\s\S]*?)(?=\n## |\Z)", content):
        day_kr, body = m.group(1), m.group(2)
        blog = re.search(r"### 블로그 원고 —\s*([^\n]*)\n([\s\S]*)", body)
        if not blog:
            continue
        # 다음 요일 섹션 앞의 `---` 구분선이 딸려 온다. 원고 자체가 `---`로 끝나면
        # 두 개가 연달아 붙으므로 뒤쪽 구분선을 전부 걷어낸다.
        text = re.sub(r"(?:\n\s*-{3,}\s*)+$", "", blog.group(2).strip()).strip()
        out[day_kr] = {"title": blog.group(1).strip(), "body": text}
    return out


def check_anchors(blog_md: str, plan: list) -> list:
    """계획의 after 값 중 본문에서 못 찾는 것들을 돌려준다."""
    lines = blog_md.split("\n")
    missing = []
    for step in plan or []:
        after = step.get("after")
        if after in ("top", "end"):
            continue
        if not any(after in l for l in lines):
            missing.append(after)
    return missing


def main():
    if len(sys.argv) < 2:
        sys.exit("사용: python sync_blog_ceo.py weeks/<주차>.json")
    spec_path = sys.argv[1]
    with open(spec_path, encoding="utf-8") as f:
        week = json.load(f)

    label = week_label(date.fromisoformat(week["week_of"]))
    note_path = os.path.join(OBSIDIAN_CEO_BASE, label, f"{label}.md")
    if not os.path.exists(note_path):
        print(f"노트 없음 — 원본 유지: {note_path}")
        return

    with open(note_path, encoding="utf-8") as f:
        edits = parse_note(f.read())

    changed = 0
    for car in week["carousels"]:
        d = date.fromisoformat(car["date"])
        day_kr = DAY_KR.get(d.weekday())
        edit = edits.get(day_kr)
        if not edit:
            continue

        if edit["title"] and edit["title"] != car.get("blog_title", ""):
            print(f"  {car['date']} 제목 수정 반영")
            car["blog_title"] = edit["title"]
            changed += 1

        if edit["body"] and edit["body"] != car.get("blog", "").strip():
            print(f"  {car['date']} 본문 수정 반영 ({len(edit['body'])}자)")
            car["blog"] = edit["body"]
            changed += 1

        missing = check_anchors(car.get("blog", ""), car.get("blog_image_plan"))
        if missing:
            print(f"  ⚠️ {car['date']} 이미지 배치 앵커 깨짐 {missing} — 자동 배치로 전환")
            car.pop("blog_image_plan", None)
            changed += 1

    if changed:
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(week, f, ensure_ascii=False, indent=2)
        print(f"업데이트 완료 — {changed}건")
    else:
        print("수정 없음")


if __name__ == "__main__":
    main()
