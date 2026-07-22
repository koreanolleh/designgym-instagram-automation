"""옵시디언 주간 노트에서 사용자가 수정한 캡션/해시태그를 읽어 pending_posts.json에 반영한다."""
import os
import re
import json
from datetime import date, timedelta, datetime

from prepare_week import OBSIDIAN_BASE, week_label

PENDING_PATH = os.path.join(os.path.dirname(__file__), "pending_posts.json")
EDIT_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "edit_history.json")

DAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일"]
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def find_obsidian_note():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    label = week_label(monday)
    path = os.path.join(OBSIDIAN_BASE, label, f"{label}.md")
    return path if os.path.exists(path) else None


def parse_obsidian(content: str) -> dict:
    result = {}
    pattern = r"## (월요일|화요일|수요일|목요일|금요일)[^\n]*\n([\s\S]*?)(?=\n## |\Z)"
    for match in re.finditer(pattern, content):
        day_kr = match.group(1)
        body = match.group(2)
        caption_match = re.search(r"캡션:\s*\n([\s\S]*?)\n해시태그:", body)
        hashtag_match = re.search(r"해시태그:\s*\n([\s\S]*?)\Z", body)
        if day_kr in DAYS_KR:
            idx = DAYS_KR.index(day_kr)
            result[DAYS_EN[idx]] = {
                "caption": caption_match.group(1).strip() if caption_match else "",
                "hashtags": hashtag_match.group(1).strip() if hashtag_match else "",
            }
    return result


def save_edit(day_en: str, field: str, original: str, edited: str):
    history = []
    if os.path.exists(EDIT_HISTORY_PATH):
        with open(EDIT_HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append({
        "date": datetime.now().isoformat(), "day": day_en, "field": field,
        "original": original, "edited": edited,
    })
    history = history[-50:]
    with open(EDIT_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    note_path = find_obsidian_note()
    if not note_path:
        print("이번 주 옵시디언 노트 없음 — 스킵")
        return False

    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()

    parsed = parse_obsidian(content)
    if not parsed:
        print("파싱 실패 — 텍스트 추출 못 함")
        return False

    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        plan = json.load(f)

    changed = False
    for day_en, fields in parsed.items():
        post = plan["posts"].get(day_en)
        if not post or post.get("posted"):
            continue
        for field in ("caption", "hashtags"):
            new_val = fields[field]
            if post.get(field, "").strip() != new_val.strip():
                print(f"✏️  {day_en} {field} 수정 반영")
                save_edit(day_en, field, post.get(field, ""), new_val)
                plan["posts"][day_en][field] = new_val
                changed = True

    if changed:
        with open(PENDING_PATH, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print("pending_posts.json 업데이트 완료")
    else:
        print("수정된 내용 없음")

    return changed


if __name__ == "__main__":
    main()
