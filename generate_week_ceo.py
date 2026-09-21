"""사장 계정 주간 원고(weeks/<주차>.json)를 만든다.

Claude 앱 예약 작업이 앱 로그인 토큰 만료로 두 주 연속 조용히 멈춰서
(2026-09-07·09-14, 401 OAuth access token has expired) 앱과 무관한
GitHub Actions에서 돌게 옮긴 것이다.

모델은 스레드 자동화(designgym-threads-automation/generate_weekly_ci.py)와 같은
구글 제미나이를 쓴다. 키도 같은 GEMINI_API_KEY라 새로 만들 필요가 없다.

두 단계로 부른다.
  1) 조사 — 구글 검색 그라운딩으로 주제 3개를 고르고 원 논문·한계를 확인
  2) 집필 — responseSchema로 weeks/<주차>.json 구조를 강제

제미나이는 Claude보다 규칙을 덜 지킬 수 있어서, 마지막에 로컬 검증을 돌린다.
하나라도 어기면 저장하지 않는다. 엉망인 원고가 발행 큐에 들어가는 것보다 비는 게 낫다.

사용:
    python generate_week_ceo.py             # 이번 주 월요일
    python generate_week_ceo.py 2026-09-28  # 주차 지정
    python generate_week_ceo.py --dry       # 호출 없이 입력만 점검
"""
import json
import os
import re
import sys
import time
from datetime import date, timedelta

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
# 스레드 자동화와 같은 목록. 앞에서부터 시도하고 실패하면 다음으로 넘어간다.
MODELS = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-flash-latest"]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

IMAGE_SET = ["01_cover.jpg"] + [f"0{i}_content.jpg" for i in range(2, 7)] + ["07_closing.jpg"]

# 제미나이 responseSchema는 OpenAPI 부분집합이라 additionalProperties를 받지 않는다.
SLIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": ["big", "stat", "bottom", "top", "classic"]},
        "badge": {"type": "string"},
        "main": {"type": "string"},
        "number": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["layout", "badge", "main", "number", "body"],
}

CAROUSEL_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string"},
        "bg_tag": {"type": "string", "enum": ["요가", "스트레칭", "홈트", "러닝", "필라테스"]},
        "cover": {"type": "array", "items": {"type": "string"}},
        "slides": {"type": "array", "items": SLIDE_SCHEMA},
        "closing": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "string"},
        "source": {"type": "string"},
        "blog_title": {"type": "string"},
        "blog": {"type": "string"},
        "blog_image_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "after": {"type": "string"},
                    "images": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["after", "images"],
            },
        },
    },
    "required": ["date", "bg_tag", "cover", "slides", "closing", "caption",
                 "hashtags", "source", "blog_title", "blog", "blog_image_plan"],
}

WEEK_SCHEMA = {
    "type": "object",
    "properties": {"carousels": {"type": "array", "items": CAROUSEL_SCHEMA}},
    "required": ["carousels"],
}


def read(path, limit=None):
    p = os.path.join(BASE_DIR, path)
    if not os.path.exists(p):
        return ""
    s = open(p, encoding="utf-8").read()
    return s[:limit] if limit else s


def call_gemini(prompt, *, schema=None, search=False, max_tokens=32000, label=""):
    """모델 목록을 순서대로 시도한다. 그라운딩이 거부되면 검색 없이 한 번 더."""
    cfg = {"maxOutputTokens": max_tokens, "temperature": 1.0}
    if schema:
        cfg["responseMimeType"] = "application/json"
        cfg["responseSchema"] = schema

    last = ""
    for model in MODELS:
        for use_search in ([True, False] if search else [False]):
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
            if use_search:
                body["tools"] = [{"google_search": {}}]
            for attempt in range(3):
                try:
                    r = requests.post(
                        ENDPOINT.format(m=model),
                        params={"key": GEMINI_KEY},
                        json=body,
                        timeout=600,
                    )
                except requests.RequestException as e:
                    last = f"{model}: 연결 실패 {e}"
                    time.sleep(3)
                    continue

                if r.status_code == 200:
                    data = r.json()
                    cands = data.get("candidates") or []
                    if not cands:
                        last = f"{model}: 후보 없음 {str(data)[:200]}"
                        break
                    c = cands[0]
                    if c.get("finishReason") not in (None, "STOP"):
                        last = f"{model}: 중단 사유 {c.get('finishReason')}"
                        break
                    parts = c.get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts)
                    if text.strip():
                        tag = f"{model}{' +검색' if use_search else ''}"
                        print(f"  [{label}] {tag} 응답 {len(text)}자", flush=True)
                        return text
                    last = f"{model}: 빈 응답"
                    break

                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                # 400은 요청 자체가 안 맞는 것 — 재시도해도 같다
                if r.status_code == 400:
                    break
                time.sleep(5)
    sys.exit(f"❌ 제미나이 호출 실패 — {last}")


def research(dates, rules, topics):
    prompt = f"""디자인짐 사장 계정(@designgym.ceo)의 이번 주 콘텐츠 주제 3개를 고르고, 근거를 확인해줘.

발행일: {dates[0]}(화), {dates[1]}(목), {dates[2]}(토)

# 주제 선정
- 사람들이 검색창에 **실제로 치는 질문** 형태여야 한다.
  좋은 예: 운동 며칠 쉬면 근력 빠지나 / 밤에 운동하면 잠 설치나 / 계단 오르기가 운동이 되나
  나쁜 예: 근육통이 젖산 때문인가 / 유연성은 왜 늘어나나 (알아도 내일 뭘 다르게 할지 없다)
- 아래 주제 대장의 "조사 완료, 미사용"이 1순위. 출처와 한계가 확인돼 있다.
- "완료" 목록 주제는 3개월 안에 재사용 금지. "다루지 말 것"은 피한다.
- 3건의 성격을 다르게 잡는다(러닝만 셋 금지).

# 근거
각 주제마다 **원 논문이나 공신력 있는 기관 자료**를 검색으로 확인해줘.
판매자 블로그·마케팅 글은 출처로 쓰지 않는다.
표본 크기, 대상 집단, 관찰연구 여부, 결론이 엇갈리는지 같은 한계도 적는다.
한계를 숨기지 않는 게 이 계정의 신뢰다.

# 주제 대장
{topics}

# 콘텐츠 기준 (발췌)
{rules[:2500]}

---
주제 3개에 대해 각각 정리해줘. 마크다운 평문.
- 주제(검색 질문 형태)
- 핵심 사실 3~5개 (숫자 포함, 비교 대상 명시)
- 출처 (저자, 저널, 연도)
- 한계
- 배치할 날짜와 bg_tag(요가/스트레칭/홈트/러닝/필라테스)
"""
    print("[1/2] 주제 조사", flush=True)
    return call_gemini(prompt, search=True, max_tokens=16000, label="조사")


def write_spec(week_of, dates, rules, brief, sample):
    prompt = f"""아래 조사 브리프로 디자인짐 사장 계정 주간 원고 3건을 써줘.

날짜는 {dates[0]} / {dates[1]} / {dates[2]} 순서대로.

# 반드시 지킬 규칙
{rules}

# 특히 자주 틀리는 것
- 표지(cover) 두 줄 **각각**에 주어와 대상이 있어야 한다.
  ✗ "발 바꾸지 마세요" (무엇을 바꾸는지 없음)  ✓ "달릴 때 뒤꿈치부터 / 닿아도 괜찮아요"
  각 줄 12자 이내.
- 말투: `습니다`·`입니다`를 쓰지 않는다. `~요 / ~죠 / ~거든요 / ~잖아요 / ~더라고요`만.
  (표지 cover는 예외)
- slides는 정확히 5장. layout을 섞고 같은 것을 연속으로 쓰지 않는다.
  권장 순서: big → stat → classic → bottom → top
- `big`은 badge와 body를 빈 문자열("")로, main만 채운다.
- `stat`은 main을 빈 문자열로, number(예: "4주", "30%")와 body를 채운다.
- 나머지 layout은 number를 빈 문자열로 둔다.
- badge는 4자 이내, main은 18자 이내.
- closing은 "매트 위 시간이 편해지면 좋겠어요"로 고정.
- blog는 1300~2000자. 소제목은 `**소제목**` 한 줄로. `---`로 끝내지 않는다.
- blog_image_plan: 이미지 7장을 전부 쓴다.
  {", ".join(IMAGE_SET)}
  첫 항목은 after="top"에 01_cover.jpg, 마지막은 after="end"에 07_closing.jpg.
  나머지 5장은 본문 소제목들에 나눠 배치하고, `after`는 그 소제목과 **글자 하나까지 똑같이** 쓴다.
- 3건의 bg_tag를 서로 다르게.

# 조사 브리프
{brief}

# 지난주 원고 (형식 참고)
{sample[:5000]}
"""
    print("[2/2] 원고 작성", flush=True)
    text = call_gemini(prompt, schema=WEEK_SCHEMA, max_tokens=60000, label="집필")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"❌ JSON 파싱 실패: {e}\n앞부분: {text[:300]}")
    return {"week_of": week_of, "bg_dir": "", "carousels": data.get("carousels", [])}


def repair(week, problems, rules):
    """검증에 걸린 부분을 알려주고 한 번 고쳐 쓰게 한다.

    한 번에 완벽하길 기대하는 것보다, 뭘 어겼는지 구체적으로 돌려주는 쪽이 잘 먹힌다.
    """
    prompt = f"""아래 원고가 규칙을 어겼어. 지적한 부분만 고쳐서 같은 JSON 구조로 다시 줘.
내용과 주제는 그대로 두고 문장만 손봐. 안 걸린 부분은 건드리지 마.

# 어긴 것
""" + "\n".join(f"- {x}" for x in problems) + f"""

# 참고 규칙
{rules[:3000]}

# 고칠 원고
{json.dumps({"carousels": week["carousels"]}, ensure_ascii=False)}
"""
    print(f"  ↻ 위반 {len(problems)}건 — 고쳐쓰기 요청", flush=True)
    text = call_gemini(prompt, schema=WEEK_SCHEMA, max_tokens=60000, label="수정")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return week
    return {**week, "carousels": data.get("carousels", week["carousels"])}


def validate(week, dates):
    """규칙 위반을 잡는다. 여기서 걸리면 렌더까지 가지 않는다."""
    problems = []
    stiff = ["습니다", "입니다", "한 경우", "로 봅니다"]
    cars = week.get("carousels", [])
    if len(cars) != 3:
        problems.append(f"carousels가 {len(cars)}건")

    tags = set()
    for c in cars:
        d = c.get("date", "?")
        if d not in dates:
            problems.append(f"{d}: 예정 날짜({', '.join(dates)})가 아님")
        tags.add(c.get("bg_tag"))

        cover = c.get("cover", [])
        if len(cover) != 2:
            problems.append(f"{d}: 표지가 {len(cover)}줄")
        for i, line in enumerate(cover, 1):
            if len(line) > 12:
                problems.append(f"{d}: 표지 {i}행이 {len(line)}자")

        slides = c.get("slides", [])
        if len(slides) != 5:
            problems.append(f"{d}: 슬라이드가 {len(slides)}장")
        lays = [s.get("layout") for s in slides]
        for i in range(len(lays) - 1):
            if lays[i] == lays[i + 1]:
                problems.append(f"{d}: layout {lays[i]}가 연속")
        for s in slides:
            if len(s.get("badge", "")) > 4:
                problems.append(f"{d}: badge '{s['badge']}'가 4자 초과")
            if len(s.get("main", "")) > 18:
                problems.append(f"{d}: main이 {len(s['main'])}자 ('{s['main']}')")

        if c.get("closing") != "매트 위 시간이 편해지면 좋겠어요":
            problems.append(f"{d}: closing이 고정 문구가 아님")

        blog = re.sub(r"출처:.*", "", re.sub(r'"[^"]*"', "", c.get("blog", "")))
        cap = re.sub(r'"[^"]*"', "", c.get("caption", ""))
        slide_txt = " ".join(s.get("body", "") + s.get("main", "") for s in slides)
        for name, t in [("블로그", blog), ("캡션", cap), ("슬라이드", slide_txt)]:
            hit = [x for x in stiff if x in t]
            if hit:
                problems.append(f"{d}: {name}에 문어체 {hit}")

        lines = c.get("blog", "").split("\n")
        plan = c.get("blog_image_plan", [])
        imgs = [i for p in plan for i in p.get("images", [])]
        if sorted(imgs) != sorted(IMAGE_SET):
            problems.append(f"{d}: 이미지 목록이 7장 세트와 다름 ({len(imgs)}장)")
        for p in plan:
            a = p.get("after")
            if a in ("top", "end"):
                continue
            if not any(a in l for l in lines):
                problems.append(f"{d}: 이미지 앵커 '{a}'를 본문에서 못 찾음")

        n = len(c.get("blog", ""))
        if not (1200 <= n <= 2200):
            problems.append(f"{d}: 블로그 {n}자 (1200~2200 벗어남)")

    if len(tags) < 3:
        problems.append(f"bg_tag가 겹침: {tags}")
    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv

    monday = date.fromisoformat(args[0]) if args else (
        date.today() - timedelta(days=date.today().weekday()))
    week_of = monday.isoformat()
    dates = [(monday + timedelta(days=d)).isoformat() for d in (1, 3, 5)]

    out = os.path.join(BASE_DIR, "weeks", f"{week_of}.json")
    if os.path.exists(out):
        print(f"이미 있습니다: weeks/{week_of}.json — 생성하지 않고 종료")
        return

    rules = read("RULES_CEO_CAROUSEL.md")
    topics = read("weeks/topics_used.md")
    prev = sorted(f for f in os.listdir(os.path.join(BASE_DIR, "weeks"))
                  if f.endswith(".json") and f[0].isdigit())
    sample = read(f"weeks/{prev[-1]}") if prev else ""

    print(f"주차 {week_of} / 발행 {', '.join(dates)}")
    print(f"규칙 {len(rules)}자 / 주제대장 {len(topics)}자 / 참고원고 {len(sample)}자")
    if not rules or not topics:
        sys.exit("❌ RULES_CEO_CAROUSEL.md 또는 weeks/topics_used.md를 못 읽었습니다")
    if dry:
        print("[DRY] 입력 점검만 하고 종료")
        return
    if not GEMINI_KEY:
        sys.exit("❌ GEMINI_API_KEY가 없습니다 (저장소 시크릿에 등록하세요)")

    brief = research(dates, rules, topics)
    week = write_spec(week_of, dates, rules, brief, sample)

    problems = validate(week, dates)
    if problems:
        week = repair(week, problems, rules)
        problems = validate(week, dates)
    if problems:
        print("\n❌ 규칙 위반으로 저장하지 않습니다:")
        for p in problems:
            print("  -", p)
        bp = os.path.join(BASE_DIR, f"brief_{week_of}.md")
        open(bp, "w", encoding="utf-8").write(brief)
        print(f"\n조사 브리프는 {bp}에 남겨뒀습니다.")
        sys.exit(1)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(week, f, ensure_ascii=False, indent=2)
    print(f"\n✅ weeks/{week_of}.json 생성")
    for c in week["carousels"]:
        print(f"  {c['date']} [{c['bg_tag']}] {' / '.join(c['cover'])}")
        print(f"     블로그: {c['blog_title']} ({len(c['blog'])}자)")


if __name__ == "__main__":
    main()
