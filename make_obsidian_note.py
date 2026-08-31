"""pending_posts.json → 옵시디언 주간초안 노트 + 이미지 사본.

사장님이 캡션·해시태그·틱톡제목을 옵시디언에서 고치면 sync_from_obsidian.py가 발행 큐에 반영한다.
노트 맨 위에 이번 생성에 크레딧을 얼마나 썼는지 적는다(요청: 2026-08-31).

사용:
  python3 make_obsidian_note.py <볼트 루트>
    예) python3 make_obsidian_note.py /tmp/vault
"""
import json
import os
import shutil
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
REL = "03_프로젝트/디자인짐_콘텐츠_자동화/인스타_자동화/주간초안"
KR = {"Monday": ("월요일", "monday_1"), "Tuesday": ("화요일", "tuesday_1"),
      "Wednesday": ("수요일", "wednesday_1"), "Thursday": ("목요일", "thursday_1"),
      "Friday": ("금요일", "friday_1")}


def week_label(week_of: str) -> str:
    """'2026-08-31' → '2026-08 8월 5주차' (그 달의 몇 번째 월요일인지로 센다)."""
    d = datetime.strptime(week_of, "%Y-%m-%d").date()
    nth = (d.day - 1) // 7 + 1
    return f"{d:%Y-%m} {d.month}월 {nth}주차"


def credit_block() -> str:
    p = os.path.join(BASE, "last_run_credits.json")
    if not os.path.exists(p):
        return ""
    c = json.load(open(p, encoding="utf-8"))
    spent = c.get("credits_spent")
    if spent is None:
        return "> 크레딧 사용량: 확인 실패\n\n"
    per = round(spent / c["images"], 2) if c.get("images") else "-"
    return (f"> **크레딧 {spent} 사용** — 이미지 {c.get('images')}장 (장당 {per}) · "
            f"잔액 {c.get('balance_before')} → {c.get('balance_after')} · "
            f"생성 {c.get('generated_at')}\n\n")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 make_obsidian_note.py <볼트 루트>", file=sys.stderr)
        return 1
    vault = sys.argv[1]
    data = json.load(open(os.path.join(BASE, "pending_posts.json"), encoding="utf-8"))
    week_of = data["week_of"]
    folder = os.path.join(vault, REL, week_label(week_of))
    os.makedirs(folder, exist_ok=True)

    out = [f"# {week_label(week_of)} 인스타/틱톡 초안", ""]
    out.append(credit_block().rstrip("\n"))
    out += ["", "> 캡션·해시태그·틱톡제목을 여기서 고치면 발행에 자동 반영됩니다.", ""]

    for day, (kd, stem) in KR.items():
        e = data["posts"].get(day)
        if not e:
            continue
        src = os.path.join(BASE, e["images"][0]["path"])
        ext = os.path.splitext(src)[1] or ".jpg"
        img = stem + ext
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(folder, img))
        d = datetime.strptime(e["date"], "%Y-%m-%d")
        out += [f"## {kd} ({d.month}/{d.day}) — {e['product']} / {e['hook']} (1장)", "",
                f"![[{img}]]", "",
                "캡션:", e["caption"], "",
                "해시태그:", e["hashtags"], "",
                "틱톡제목:", e["tiktok_title"].split("\n")[0], "", "---", ""]

    note = os.path.join(folder, f"{week_label(week_of)}.md")
    with open(note, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"옵시디언 노트 작성: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
