"""주간 원고(JSON) → 옵시디언 노트 + 이미지 사본.

make_week_ceo.py가 렌더를 끝낸 뒤에 실행한다. 사장이 검토·수정하는 화면을 만든다.
캡션·해시태그를 노트에서 고치면 sync_from_obsidian_ceo.py가 발행 큐에 반영한다.

사용:
    python3 make_obsidian_note_ceo.py weeks/2026-08-24.json
"""
import json
import os
import shutil
import sys
from datetime import date

from prepare_week import week_label

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_ROOT = os.path.join(BASE_DIR, "images", "ceo")
# GitHub Actions에서는 볼트 체크아웃 경로를 CEO_NOTE_BASE로 넘긴다
OBSIDIAN_CEO_BASE = os.environ.get("CEO_NOTE_BASE") or os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/메이크앤&옵시디언/"
    "03_프로젝트/디자인짐_콘텐츠_자동화/사장계정_주간초안"
)

DAY_KR = {1: ("화요일", "tue"), 3: ("목요일", "thu"), 5: ("토요일", "sat")}

HEADER = """# {label} 사장계정(@designgym.ceo) 초안

> ⚠️ **화·목·토 19:30에 자동 발행됩니다.** 캡션·해시태그를 여기서 고치면 30분 안에 발행에 반영됩니다.
> 이미지 안 문안 교체는 채팅으로 요청하세요.
> 블로그 원고는 **자동 발행되지 않습니다.** 손보신 뒤 직접 올리시면 됩니다.
"""


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 make_obsidian_note_ceo.py weeks/<week_of>.json")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        week = json.load(f)

    label = week_label(date.fromisoformat(week["week_of"]))
    outdir = os.path.join(OBSIDIAN_CEO_BASE, label)
    os.makedirs(outdir, exist_ok=True)

    parts = [HEADER.format(label=label)]

    for car in week["carousels"]:
        d = date.fromisoformat(car["date"])
        if d.weekday() not in DAY_KR:
            print(f"⚠️ {car['date']}는 화·목·토가 아닙니다 — 건너뜁니다")
            continue
        ko, pre = DAY_KR[d.weekday()]

        src_dir = os.path.join(IMAGES_ROOT, car["date"])
        files = sorted(f for f in os.listdir(src_dir) if f.endswith(".jpg"))
        for i, fn in enumerate(files, start=1):
            shutil.copy2(os.path.join(src_dir, fn), os.path.join(outdir, f"{pre}_{i}.jpg"))
        embeds = "\n".join(f"![[{pre}_{i}.jpg]]" for i in range(1, len(files) + 1))

        blog = car.get("blog", "").strip()
        blog_block = f"\n### 블로그 원고 — {car.get('blog_title', '')}\n\n{blog}\n" if blog else ""

        parts.append(f"""---

## {ko} ({d.month}/{d.day}) — {' '.join(car['cover'])}

{embeds}

캡션:
{car['caption'].rstrip()}

해시태그:
{car.get('hashtags', '')}

출처:
{car.get('source', '')}
{blog_block}""")

    note_path = os.path.join(outdir, f"{label}.md")
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"옵시디언 노트 작성: {note_path}")
    print(f"이미지 {len(week['carousels']) * 7}장 복사 완료")


if __name__ == "__main__":
    main()
