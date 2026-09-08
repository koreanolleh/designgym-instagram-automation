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


def pick_backgrounds(bg_dir, tag, count, seed, used=None):
    """태그로 후보를 좁히고 seed 기반으로 결정적으로 고른다(매번 같은 결과).

    used에 이미 쓴 파일명을 넘기면 그것들을 빼고 고른다. 같은 주 안에서 날짜별로
    배경이 통째로 겹치는 사고를 막기 위한 것 — 날짜 해시가 우연히 같은 시작점으로
    떨어지면 step이 고정이라 7장이 전부 같아진다(2026-09-08/10에서 실제로 발생).
    """
    used = used or set()
    pool = sorted(glob.glob(os.path.join(bg_dir, f"*{tag}*.jpg"))) if tag else []
    if not pool:
        pool = sorted(glob.glob(os.path.join(bg_dir, "*.jpg")))
    if not pool:
        raise SystemExit(f"배경 사진을 찾지 못했습니다: {bg_dir}")

    cands = [c for c in pool if os.path.basename(c) not in used]
    if len(cands) < count:
        # 태그 안에서 모자라면 전체 배경으로 넓힌다. 그래도 모자라면 재사용을 허용한다.
        wider = [c for c in sorted(glob.glob(os.path.join(bg_dir, "*.jpg")))
                 if os.path.basename(c) not in used]
        cands = wider if len(wider) >= count else pool
        print(f"  ⚠️ '{tag}' 배경이 모자라 후보를 넓혔습니다 ({len(cands)}장)")

    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    start = h % len(cands)
    # 한 캐러셀 안에서 같은 사진이 반복되지 않게 간격을 두고 뽑는다
    step = max(1, len(cands) // max(count, 1))
    picked, seen = [], set()
    i = 0
    while len(picked) < count and i < len(cands) * 2:
        name = os.path.basename(cands[(start + i * step) % len(cands)])
        if name not in seen:
            picked.append(name)
            seen.add(name)
        i += 1
    # step 배수가 한 바퀴를 못 돌면 남는 자리를 순서대로 채운다
    for c in cands:
        if len(picked) >= count:
            break
        name = os.path.basename(c)
        if name not in seen:
            picked.append(name)
            seen.add(name)
    return picked


def build_spec(car, bg_dir, used=None):
    n_slides = 1 + len(car["slides"]) + 1
    bgs = pick_backgrounds(bg_dir, car.get("bg_tag"), n_slides, car["date"], used)
    if used is not None:
        used.update(bgs)

    slides = [{"type": "cover", "bg": bgs[0], "lines": car["cover"]}]
    for i, s in enumerate(car["slides"], start=1):
        slides.append({
            "type": "content", "bg": bgs[i],
            "badge": s.get("badge", ""), "main": s.get("main", ""),
            "body": s.get("body", ""), "sub": s.get("sub", ""),
            "layout": s.get("layout", "classic"), "number": s.get("number", ""),
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
    # bg_dir가 없거나 존재하지 않으면 레포 안의 backgrounds/를 쓴다(클라우드 실행 대비)
    bg_dir = week.get("bg_dir") or ""
    if not os.path.isdir(bg_dir):
        bg_dir = os.path.join(BASE_DIR, "backgrounds")

    plan = {"week_of": week["week_of"], "account": "designgym.ceo",
            "note": "사장 계정 캐러셀 발행 대기열. 월요일 루틴이 주간 3건(화/목/토)을 채운다.",
            "posts": {}}

    # 기존 큐의 발행 기록을 읽어둔다. 같은 주를 다시 렌더할 때 이미 올라간 글을
    # 미발행으로 되돌리면 중복 게시가 난다.
    if os.path.exists(PENDING):
        try:
            with open(PENDING, encoding="utf-8") as f:
                plan["posts"] = json.load(f).get("posts", {})
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ 기존 큐를 읽지 못했습니다 ({e}) — 새로 만듭니다")

    used_bgs = set()   # 한 주 안에서 배경이 겹치지 않게 누적한다
    picked_by_date = {}

    for car in week["carousels"]:
        date = car["date"]
        weekday = DAY_KO[datetime.strptime(date, "%Y-%m-%d").weekday()]
        outdir = os.path.join(IMAGES_ROOT, date)

        spec = build_spec(car, bg_dir, used_bgs)
        picked_by_date[date] = [sl["bg"] for sl in spec["slides"]]
        if dry:
            print(f"[DRY] {date}({weekday}) 슬라이드 {len(spec['slides'])}장 / 표지: {' '.join(car['cover'])}")
            continue

        paths = render(spec, outdir)
        rel = [os.path.relpath(p, BASE_DIR) for p in paths]

        caption = car["caption"].rstrip()
        if car.get("source"):
            caption += f"\n\n📌 출처: {car['source']}"

        # 같은 날짜가 이미 게시됐다면 그 기록을 유지한다.
        # 렌더가 다시 돌 때 플래그를 False로 되돌리면 이미 올라간 글이 중복 게시된다.
        prev = plan["posts"].get(weekday) or {}
        keep = prev.get("date") == date and prev.get("ig_posted")
        if keep:
            print(f"  → {date}({weekday}) 이미 게시됨 — 발행 기록 유지")

        plan["posts"][weekday] = {
            "date": date,
            "cover": " ".join(car["cover"]),
            "images": [{"path": r, "image_url": f"{PAGES_BASE}/{r}"} for r in rel],
            "caption": caption,
            "hashtags": car.get("hashtags", ""),
            "source": car.get("source", ""),
            "posted": bool(keep),
            "ig_posted": bool(keep),
        }
        if keep and prev.get("post_id"):
            plan["posts"][weekday]["post_id"] = prev["post_id"]
        print(f"  → {date}({weekday}) {len(rel)}장 준비 완료")

    if dry:
        return

    # 날짜끼리 배경이 겹치면 멈춘다. 2026-09-08/10에서 7장이 통째로 같았던 적이 있다.
    dates = list(picked_by_date)
    for i in range(len(dates)):
        for j in range(i + 1, len(dates)):
            dup = set(picked_by_date[dates[i]]) & set(picked_by_date[dates[j]])
            if dup:
                sys.exit(f"❌ {dates[i]}와 {dates[j]}의 배경이 {len(dup)}장 겹칩니다: {sorted(dup)}")
    print("배경 중복 검사 통과 — 날짜 간 겹침 없음")

    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"\n{PENDING} 갱신 완료 ({len(plan['posts'])}건)")
    print("다음: git add images/ceo pending_posts_ceo.json && git commit && git push")
    print("⚠️ 이미지는 GitHub Pages로 서빙되므로 푸시 후에야 발행 가능합니다.")


if __name__ == "__main__":
    main()
