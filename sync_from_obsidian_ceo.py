"""사장 계정 옵시디언 노트에서 수정한 캡션/해시태그를 pending_posts_ceo.json에 반영한다.

official용 sync_from_obsidian.py와 같은 역할이지만 대상이 다르다.
- 노트: 사장계정_주간초안/<주차>/<주차>.md
- 요일: 화·목·토 (official은 월~금)
- 큐: pending_posts_ceo.json

주차는 pending_posts_ceo.json의 week_of로 정한다. 오늘 날짜 기준이 아니라서
다음 주 발행분을 미리 만들어둔 경우에도 맞는 노트를 찾는다.
"""
import json
import os
import re
import time
from datetime import date, datetime

from prepare_week import week_label

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_PATH = os.path.join(BASE_DIR, "pending_posts_ceo.json")
EDIT_HISTORY_PATH = os.path.join(BASE_DIR, "edit_history_ceo.json")

OBSIDIAN_CEO_BASE = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/메이크앤&옵시디언/"
    "03_프로젝트/디자인짐_콘텐츠_자동화/사장계정_주간초안"
)

DAYS_KR = ["화요일", "목요일", "토요일"]
DAYS_EN = ["Tuesday", "Thursday", "Saturday"]


def find_note(plan):
    week_of = plan.get("week_of")
    if not week_of:
        return None
    label = week_label(date.fromisoformat(week_of))
    path = os.path.join(OBSIDIAN_CEO_BASE, label, f"{label}.md")
    return path if os.path.exists(path) else None


def parse_note(content: str) -> dict:
    """요일 섹션에서 캡션·해시태그·출처를 뽑는다. 블로그 원고(###)는 건드리지 않는다."""
    result = {}
    for m in re.finditer(r"## (화요일|목요일|토요일)[^\n]*\n([\s\S]*?)(?=\n## |\Z)", content):
        day_kr, body = m.group(1), m.group(2)
        cap = re.search(r"캡션:\s*\n([\s\S]*?)\n해시태그:", body)
        tag = re.search(r"해시태그:\s*\n([\s\S]*?)\n출처:", body)
        src = re.search(r"출처:\s*\n([\s\S]*?)(?=\n###|\Z)", body)
        result[DAYS_EN[DAYS_KR.index(day_kr)]] = {
            "caption": cap.group(1).strip() if cap else "",
            "hashtags": tag.group(1).strip() if tag else "",
            "source": src.group(1).strip() if src else "",
        }
    return result


def save_edit(day_en, field, original, edited):
    history = []
    if os.path.exists(EDIT_HISTORY_PATH):
        with open(EDIT_HISTORY_PATH, encoding="utf-8") as f:
            history = json.load(f)
    history.append({"date": datetime.now().isoformat(), "day": day_en,
                    "field": field, "original": original, "edited": edited})
    with open(EDIT_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history[-50:], f, ensure_ascii=False, indent=2)


def main():
    if not os.path.exists(PENDING_PATH):
        print("pending_posts_ceo.json 없음 — 스킵")
        return False

    with open(PENDING_PATH, encoding="utf-8") as f:
        plan = json.load(f)

    note_path = find_note(plan)
    if not note_path:
        print("해당 주차 사장계정 노트 없음 — 스킵")
        return False

    content = None
    for attempt in range(5):  # iCloud 동기화 중이면 읽기 실패가 날 수 있어 재시도
        try:
            with open(note_path, encoding="utf-8") as f:
                content = f.read()
            break
        except OSError as e:
            print(f"노트 읽기 재시도 {attempt + 1}/5: {e}")
            time.sleep(3)
    if content is None:
        print("노트 읽기 최종 실패 — 스킵")
        return False

    parsed = parse_note(content)
    if not parsed:
        print("파싱 실패 — 요일 섹션을 찾지 못함")
        return False

    changed = False
    for day_en, fields in parsed.items():
        post = plan["posts"].get(day_en)
        if not post or post.get("posted"):
            continue

        # 캡션은 저장 시 출처를 덧붙인다(make_week_ceo.py와 동일 규칙)
        source = fields.get("source") or post.get("source", "")
        new_caption = fields["caption"].strip()
        if source:
            new_caption += f"\n\n📌 출처: {source}"

        for field, new_val in (("caption", new_caption),
                               ("hashtags", fields["hashtags"].strip()),
                               ("source", source)):
            if not new_val:
                continue
            if post.get(field, "").strip() != new_val.strip():
                print(f"✏️  {day_en} {field} 수정 반영")
                save_edit(day_en, field, post.get(field, ""), new_val)
                plan["posts"][day_en][field] = new_val
                changed = True

    if changed:
        with open(PENDING_PATH, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print("pending_posts_ceo.json 업데이트 완료")
    else:
        print("수정된 내용 없음")

    return changed


if __name__ == "__main__":
    main()
