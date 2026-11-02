"""사장님이 옵시디언에서 고친 문구를 캡션 풀(weekly_prompts.json)에 반영한다.

왜 필요한가 — 2026-11-02 사장님 지적:
  "내가 여태까지 수정하면 그냥 학습한다며 수정하는 내용으로, 근데 하나도 안하고 있지 지금?"

맞는 말이었다. sync_from_obsidian.py 는 수정본을 그 주의 pending_posts.json 에만
반영하고, 이력을 edit_history.json 에 쌓아왔다(50건). 그런데 그 파일을 읽는 코드가
한 줄도 없었다. 캡션 풀은 내가 처음 써둔 고정 문구 그대로였고, caption_for 는 매주
그 풀에서 순번으로 돌려 썼다. 그래서 사장님이 고친 문구가 다음에 또 원문으로 나왔다.
  실제 사고: 2026-10-12 일요일 밴드 캡션 "눈에 보이는 자리에 둡니다…" 를 사장님이
  "아무대나 툭 던져놔도 어울리는 힙업밴드…" 로 고쳤는데, 풀은 그대로여서 3주 뒤
  2026-11-05 목요일에 고치기 전 원문이 다시 걸렸다("목요일 캡션 예전에 썼던거 아냐?").

하는 일 — edit_history.json 을 시간순으로 훑어, 고치기 전 문구와 일치하는 풀 항목을
찾아 사장님이 쓰신 문장으로 덮는다. 즉 풀이 점점 사장님 문체로 바뀐다.
덮어쓴 항목에는 by/learned_at 을 남겨, 어느 문구가 사장님 것인지 보이게 한다.

쓰는 곳: weekly_generate 직전(워크플로)에서 먼저 돌린다. 단독 실행도 가능.
  python3 learn_captions.py          # 반영하고 저장
  DRY=1 python3 learn_captions.py    # 뭐가 바뀌는지만 보여주고 저장 안 함
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE, "weekly_prompts.json")
HISTORY_PATH = os.path.join(BASE, "edit_history.json")


def norm(s: str) -> str:
    """비교용 정규화 — 공백/빈 줄 차이로 못 알아보는 일을 막는다."""
    return re.sub(r"\s+", " ", (s or "")).strip()


def strip_tail(s: str, tail: str) -> str:
    """일요일(마감일)에만 붙는 브랜드 서명을 떼고 본문만 남긴다.

    풀에는 서명 없는 본문이 들어 있고, 노트에 찍히는 캡션에는 붙어 있다.
    떼지 않으면 일요일 수정은 영원히 풀과 안 맞는다.
    """
    s = (s or "").rstrip()
    t = (tail or "").strip()
    if t and s.endswith(t):
        s = s[: -len(t)].rstrip()
    return s


def title_of(tt: str) -> str:
    """틱톡 제목에서 해시태그와 구분선을 떼고 앞머리(=풀의 t)만 꺼낸다."""
    s = (tt or "").split("\n")[0]
    s = re.sub(r"#\S+", "", s)
    return s.strip(" ·-")


def main():
    lib = json.load(open(LIB_PATH, encoding="utf-8"))
    if not os.path.exists(HISTORY_PATH):
        print("수정 이력이 없다 — 반영할 것 없음")
        return 0
    history = json.load(open(HISTORY_PATH, encoding="utf-8"))
    tail = lib.get("brand_tail", "")

    # 본문 → (풀이름, 항목) 색인. 풀을 고치는 즉시 색인도 갱신해야
    # 같은 문구를 두 번 고친 이력(한 주에 두 번 저장)이 두 번째에서 길을 잃지 않는다.
    index = {}
    for pool_name, pool in lib["captions"].items():
        if not isinstance(pool, list):
            continue                      # _caption_note 같은 설명 키
        for item in pool:
            index[norm(item["c"])] = (pool_name, item)

    applied, skipped = [], 0
    for ev in sorted(history, key=lambda e: e.get("date", "")):
        field = ev.get("field")
        before = strip_tail(ev.get("original", ""), tail)
        after = strip_tail(ev.get("edited", ""), tail)

        if field == "caption":
            key = norm(before)
            if norm(after) == key:
                continue                  # 줄바꿈만 다른 저장 — 반영할 내용 없음
            hit = index.get(key)
            if not hit:
                skipped += 1              # 이미 한 번 반영됐거나, 그 뒤 내가 새로 쓴 문구
                continue
            pool_name, item = hit
            del index[key]
            item["c"] = after
            item["by"] = "ceo"
            item["learned_at"] = ev.get("date", "")[:10]
            index[norm(after)] = (pool_name, item)
            applied.append((ev.get("date", "")[:10], pool_name, "캡션", before, after))

        elif field == "tiktok_title":
            b, a = title_of(ev.get("original", "")), title_of(ev.get("edited", ""))
            if not b or b == a:
                continue                  # '---' 만 붙인 저장 — 제목은 그대로다
            for pool_name, pool in lib["captions"].items():
                if not isinstance(pool, list):
                    continue
                for item in pool:
                    if norm(item["t"]) == norm(b):
                        item["t"] = a
                        item["by"] = "ceo"
                        item["learned_at"] = ev.get("date", "")[:10]
                        applied.append((ev.get("date", "")[:10], pool_name, "틱톡제목", b, a))

    if not applied:
        print(f"새로 반영할 수정 없음 (이력 {len(history)}건, 짝 못 찾음 {skipped}건)")
        return 0

    print(f"사장님 수정 {len(applied)}건을 캡션 풀에 반영한다:\n")
    for when, pool_name, kind, before, after in applied:
        print(f"[{when}] {pool_name} / {kind}")
        print(f"  이전: {before[:70].replace(chr(10), ' / ')}")
        print(f"  이후: {after[:70].replace(chr(10), ' / ')}\n")

    if os.environ.get("DRY") == "1":
        print("DRY=1 — 저장하지 않았다")
        return 0

    json.dump(lib, open(LIB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"weekly_prompts.json 저장 완료 (짝 못 찾은 이력 {skipped}건은 건너뜀)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
