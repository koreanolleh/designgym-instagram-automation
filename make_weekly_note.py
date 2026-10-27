"""pending_posts.json에서 옵시디언 주간 노트를 생성한다 (노트가 없을 때만).

월요일 아침 주간 생성 워크플로가 JSON을 만들면, 맥이 켜졌을 때 launchd sync가
이 스크립트를 먼저 실행해 사용자가 검토·수정할 노트를 자동 생성한다.

노트 머리에 이번 생성에 크레딧을 얼마나 썼는지 적는다(2026-08-31 요청).
last_run_credits.json은 weekly_generate.py가 생성 전후 잔액을 재서 남긴다.
"""
import os
import json
import urllib.request
from datetime import date

from prepare_week import OBSIDIAN_BASE, week_label

PENDING_PATH = os.path.join(os.path.dirname(__file__), "pending_posts.json")

from publish_days import SCHEDULE

DAYS = [(en, kr) for en, kr, _off, _n in SCHEDULE]
CREDITS_PATH = os.path.join(os.path.dirname(__file__), "last_run_credits.json")


def credit_line(week_of: str) -> str:
    """이번 주 생성에 쓴 크레딧 한 줄. 기록이 없거나 다른 주면 빈 문자열."""
    if not os.path.exists(CREDITS_PATH):
        return ""
    try:
        c = json.load(open(CREDITS_PATH, encoding="utf-8"))
    except Exception:
        return ""
    if c.get("week_of") != week_of or c.get("credits_spent") is None:
        return ""
    n = c.get("images") or 0
    per = round(c["credits_spent"] / n, 2) if n else "-"
    line = (f"> 💳 **크레딧 {c['credits_spent']} 사용** — 이미지 {n}장 (장당 {per}) · "
            f"잔액 {c.get('balance_before')} → {c.get('balance_after')}")
    if c.get("note"):
        line += f" · {c['note']}"
    return line


def existing_texts(note_path: str) -> dict:
    """이미 있는 노트에서 요일별 캡션·해시태그·틱톡제목을 읽어 둔다.

    노트를 다시 찍을 때 이 글들을 그대로 되살려, 사장님이 옵시디언에서 고친
    문구가 큐 내용으로 덮어써지지 않게 한다. 덮어쓰면 git 이 같은 줄을 두 곳에서
    고친 것으로 보고 충돌 마커를 박는다 — 2026-10-27 에 그 충돌 때문에
    sync_from_obsidian 이 노트를 못 읽어 화요일이 옛 캡션으로 나갔다.

    원격 클론에서 돌 때는 사장님 로컬 수정본이 없으므로 sync_from_obsidian 을
    먼저 돌릴 수가 없다. 그래서 '덮어쓰지 않는' 쪽으로 막는다.
    """
    import re
    if not os.path.exists(note_path):
        return {}
    try:
        content = open(note_path, encoding="utf-8").read()
    except Exception:
        return {}
    if "<<<<<<<" in content:
        print("⚠️ 노트에 충돌 마커가 남아 있음 — 기존 문구를 믿을 수 없어 큐 내용을 쓴다")
        return {}
    out = {}
    days_kr = [kr for _en, kr in DAYS]
    pattern = r"## (" + "|".join(days_kr) + r")[^\n]*\n([\s\S]*?)(?=\n## |\Z)"
    for m in re.finditer(pattern, content):
        body = m.group(2)
        got = {}
        for key, rx in (("caption", r"캡션:\s*\n([\s\S]*?)\n(?:해시태그|틱톡제목):"),
                        ("hashtags", r"해시태그:\s*\n([\s\S]*?)(?=\n틱톡제목:|\Z)"),
                        ("tiktok_title", r"틱톡제목:\s*\n([\s\S]*?)\Z")):
            hit = re.search(rx, body)
            if hit and hit.group(1).strip():
                got[key] = hit.group(1).strip()
        if got:
            out[days_kr[days_kr.index(m.group(1))]] = got
    return out


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
    # 평소엔 덮어쓰지 않는다 — 노트는 사장님이 캡션을 고치는 원본이다.
    # 이미지나 캡션을 교체한 뒤 노트를 다시 찍어야 할 때만 FORCE_NOTE=1 로 부른다.
    # 그 전에 반드시 sync_from_obsidian.py 를 돌려 수정본을 큐로 끌어와야 한다.
    if os.path.exists(note_path) and os.environ.get("FORCE_NOTE") != "1":
        print("노트 이미 있음 — 스킵")
        return

    # 다시 찍는 경우, 노트에 이미 있는 문구를 살려 둔다(사장님이 고친 것일 수 있다).
    # KEEP_TEXT=0 으로 부르면 큐 내용으로 밀어버린다 — 내가 캡션을 새로 썼을 때만 쓴다.
    keep = {} if os.environ.get("KEEP_TEXT") == "0" else existing_texts(note_path)
    if keep:
        print(f"기존 노트의 문구 보존: {', '.join(keep)}")

    os.makedirs(week_dir, exist_ok=True)
    lines = [
        f"# 디자인짐 인스타그램 — {label}",
        "",
    ]
    cl = credit_line(week_of)
    if cl:
        lines += [cl, ""]
    lines += [
        "> 이미지를 보고 캡션/해시태그/틱톡제목을 직접 수정하세요. 수정하면 자동 반영됩니다(맥 켜져 있을 때).",
        "> 틱톡제목은 틱톡 화면에 보이는 유일한 글입니다 — 해시태그 포함 90자 이내로 유지하세요.",
        "> 이미지 자체를 바꾸고 싶으면 채팅으로 요청하세요. 화·목·일 저녁 인스타+틱톡 자동 게시.",
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
        # 2026-10-26: 사진을 볼트에 내려받지 않고 영구 URL 을 그대로 임베드한다.
        # 주간초안 PNG 103장이 볼트 git 의 92%(307MB)를 차지해, iCloud 에서 git 이
        # 느려지고 lock·교착 사고의 토대가 됐다. 옵시디언은 원격 이미지를 그대로
        # 렌더하므로 사장님 화면은 같고, 주차당 늘어나는 건 이 .md 파일 하나뿐이다.
        for img in post.get("images", []):
            url = img.get("image_url")
            if url:
                lines.append(f"![]({url})")
            else:
                lines.append(f"(이미지 URL 없음: {img.get('path', '')})")
        kept = keep.get(day_kr, {})
        lines += [
            "",
            "캡션:",
            kept.get("caption") or post.get("caption", ""),
            "",
            "해시태그:",
            kept.get("hashtags") or post.get("hashtags", ""),
            "",
            "틱톡제목:",
            kept.get("tiktok_title") or post.get("tiktok_title", ""),
            "",
        ]
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"노트 생성 완료: {note_path}")


if __name__ == "__main__":
    main()
