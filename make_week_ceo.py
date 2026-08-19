"""주간 캐러셀 원고(JSON) → 슬라이드 렌더 + pending_posts_ceo.json 갱신.

월요일 밤에 돌린다. 옵시디언에서 사장이 문안을 고친 뒤 실행하면
이미지를 레포에 커밋할 수 있는 상태로 만들고 발행 큐를 채운다.
발행 자체는 ig_ceo.yml(화·목·토 19:30)이 담당.

사용:
    python3 make_week_ceo.py week_spec.json [--dry]

week_spec.json:
{
  "week_of": "2026-08-24",
  "bg_dir": "/Users/.../디자인짐_사장계정_배경/원본",
  "carousels": [
    {
      "date": "2026-08-25",
      "cover": ["운동 전 스트레칭", "사실 힘이 빠집니다"],
      "slides": [
        {"badge": "통설", "main": "...", "sub": "..."},
        ...
      ],
      "closing": "매트 위 시간이 편해지면 좋겠어요",
      "caption": "...",
      "hashtags": "#디자인짐 #스트레칭",
      "source": "Journal of Strength and Conditioning Research, 2012",
      "bg_tag": "스트레칭"
    }
  ]
}
"""
import glob
import hashlib
import json
import os
import sys
from datetime import datetime

from carousel import render

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(BASE_DIR, "pending_posts_ceo.json")
IMAGES_ROOT = os.path.join(BASE_DIR, "images", "ceo")
PAGES_BASE = "https://koreanolleh.github.io/designgym-instagram-automation"

DAY_KO = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def pick_backgrounds(bg_dir, tag, count, seed):
    """태그로 후보를 좁히고 seed 기반으로 결정적으로 고른다(매번 같은 결과)."""
    cands = sorted(glob.glob(os.path.join(bg_dir, f"*{tag}*.jpg"))) if tag else []
    if not cands:
        cands = sorted(glob.glob(os.path.join(bg_dir, "*.jpg")))
    if not cands:
        raise SystemExit(f"배경 사진을 찾지 못했습니다: {bg_dir}")

    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    start = h % len(cands)
    # 한 캐러셀 안에서 같은 사진이 반복되지 않게 간격을 두고 뽑는다
    step = max(1, len(cands) // max(count, 1))
    return [os.path.basename(cands[(start + i * step) % len(cands)]) for i in range(count)]


def build_spec(car, bg_dir):
    n_slides = 1 + len(car["slides"]) + 1
    bgs = pick_backgrounds(bg_dir, car.get("bg_tag"), n_slides, car["date"])

    slides = [{"type": "cover", "bg": bgs[0], "lines": car["cover"]}]
    for i, s in enumerate(car["slides"], start=1):
        slides.append({
            "type": "content", "bg": bgs[i],
            "badge": s.get("badge", ""), "main": s.get("main", ""), "sub": s.get("sub", ""),
        })
    slides.append({
        "type": "closing", "bg": bgs[-1],
        "headline": car.get("closing", "매트 위 시간이 편해지면 좋겠어요"),
        "sub": "운동하는 사람의 기록",
    })
    return {"tone": car.get("tone", "B"), "bg_dir": bg_dir, "slides": slides}


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 make_week_ceo.py week_spec.json [--dry]")
        sys.exit(1)
    dry = "--dry" in sys.argv

    with open(sys.argv[1], encoding="utf-8") as f:
        week = json.load(f)
    bg_dir = week["bg_dir"]

    plan = {"week_of": week["week_of"], "account": "designgym.ceo",
            "note": "사장 계정 캐러셀 발행 대기열. 월요일 루틴이 주간 3건(화/목/토)을 채운다.",
            "posts": {}}

    for car in week["carousels"]:
        date = car["date"]
        weekday = DAY_KO[datetime.strptime(date, "%Y-%m-%d").weekday()]
        outdir = os.path.join(IMAGES_ROOT, date)

        spec = build_spec(car, bg_dir)
        if dry:
            print(f"[DRY] {date}({weekday}) 슬라이드 {len(spec['slides'])}장 / 표지: {' '.join(car['cover'])}")
            continue

        paths = render(spec, outdir)
        rel = [os.path.relpath(p, BASE_DIR) for p in paths]

        caption = car["caption"].rstrip()
        if car.get("source"):
            caption += f"\n\n📌 출처: {car['source']}"

        plan["posts"][weekday] = {
            "date": date,
            "cover": " ".join(car["cover"]),
            "images": [{"path": r, "image_url": f"{PAGES_BASE}/{r}"} for r in rel],
            "caption": caption,
            "hashtags": car.get("hashtags", ""),
            "source": car.get("source", ""),
            "posted": False,
            "ig_posted": False,
        }
        print(f"  → {date}({weekday}) {len(rel)}장 준비 완료")

    if dry:
        return

    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"\n{PENDING} 갱신 완료 ({len(plan['posts'])}건)")
    print("다음: git add images/ceo pending_posts_ceo.json && git commit && git push")
    print("⚠️ 이미지는 GitHub Pages로 서빙되므로 푸시 후에야 발행 가능합니다.")


if __name__ == "__main__":
    main()
