"""사장 계정 주간 원고(weeks/<주차>.json)를 Claude API로 생성한다.

Claude 앱의 예약 작업이 앱 로그인 토큰 만료로 조용히 멈추는 일이 반복돼서
(2026-09-07·09-14 두 주 연속, 401 OAuth access token has expired),
앱과 무관한 GitHub Actions에서 돌 수 있게 옮긴 것이다.

두 번 호출한다.
  1) 조사 — 웹 검색으로 주제 3개를 고르고 원 논문과 한계를 확인해 브리프를 만든다
  2) 집필 — 브리프와 규칙 문서를 받아 weeks/<주차>.json 구조로 쓴다

집필 단계는 구조화 출력(output_config.format)으로 스키마를 강제한다.
웹 검색은 인용(citations)을 붙이는데 구조화 출력과 같이 못 쓰므로 단계를 나눴다.

사용:
    python generate_week_ceo.py            # 이번 주 월요일 기준
    python generate_week_ceo.py 2026-09-21 # 주차 지정
    python generate_week_ceo.py --dry      # 호출 없이 입력만 점검
"""
import json
import os
import sys
from datetime import date, timedelta

import anthropic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-opus-5"

# 캐러셀 한 건의 스키마. make_week_ceo.py가 읽는 필드와 정확히 같아야 한다.
CAROUSEL_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "bg_tag": {"type": "string", "enum": ["요가", "스트레칭", "홈트", "러닝", "필라테스"]},
        "cover": {
            "type": "array", "items": {"type": "string"},
            "minItems": 2, "maxItems": 2,
            "description": "표지 2줄. 각 줄 10자 안팎, 각 줄에 주어와 대상이 있어야 함",
        },
        "slides": {
            "type": "array", "minItems": 5, "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "layout": {"type": "string", "enum": ["big", "stat", "bottom", "top", "classic"]},
                    "badge": {"type": "string", "description": "4자 이내. big 레이아웃은 빈 문자열"},
                    "main": {"type": "string", "description": "18자 이내. stat 레이아웃은 빈 문자열"},
                    "number": {"type": "string", "description": "stat 레이아웃에만. 짧게(예: 4주, 30%)"},
                    "body": {"type": "string", "description": "5줄 이내. big 레이아웃은 빈 문자열"},
                },
                "required": ["layout", "badge", "main", "number", "body"],
                "additionalProperties": False,
            },
        },
        "closing": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "string"},
        "source": {"type": "string"},
        "blog_title": {"type": "string"},
        "blog": {"type": "string", "description": "1400~1800자. 소제목은 **소제목** 형식"},
        "blog_image_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "after": {"type": "string", "description": "top, end, 또는 본문 소제목과 정확히 같은 문자열"},
                    "images": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["after", "images"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["date", "bg_tag", "cover", "slides", "closing", "caption",
                 "hashtags", "source", "blog_title", "blog", "blog_image_plan"],
    "additionalProperties": False,
}

WEEK_SCHEMA = {
    "type": "object",
    "properties": {
        "week_of": {"type": "string"},
        "bg_dir": {"type": "string"},
        "carousels": {"type": "array", "minItems": 3, "maxItems": 3, "items": CAROUSEL_SCHEMA},
    },
    "required": ["week_of", "bg_dir", "carousels"],
    "additionalProperties": False,
}


def read(path, limit=None):
    p = os.path.join(BASE_DIR, path)
    if not os.path.exists(p):
        return ""
    s = open(p, encoding="utf-8").read()
    return s[:limit] if limit else s


def research(client, dates, rules, topics):
    """웹 검색으로 주제 3개를 고르고 근거를 확인한다."""
    prompt = f"""디자인짐 사장 계정(@designgym.ceo)의 이번 주 콘텐츠 주제 3개를 고르고, 각각의 근거를 확인해줘.

발행일: {dates[0]}(화), {dates[1]}(목), {dates[2]}(토)

# 주제 선정 기준
- 사람들이 검색창에 **실제로 치는 질문** 형태여야 한다. "내가 조사한 사실"이 아니라.
  좋은 예: 운동 며칠 쉬면 근력 빠지나 / 밤에 운동하면 잠 설치나 / 계단 오르기가 운동이 되나
  나쁜 예: 근육통이 젖산 때문인가 / 유연성은 왜 늘어나나 (알아도 내일 뭘 다르게 할지 없음)
- 아래 주제 대장의 "조사 완료, 미사용"에 있는 것이 1순위. 출처와 한계가 이미 확인돼 있다.
- 완료 목록의 주제는 3개월 안에 다시 쓰지 않는다.
- "다루지 말 것" 목록은 피한다.
- 3건의 성격을 다르게 잡는다(러닝만 셋 같은 구성 금지).

# 근거 확인
각 주제마다 **원 논문이나 공신력 있는 기관 자료**를 웹 검색으로 확인해줘.
판매자 블로그·마케팅 글은 출처로 쓰지 않는다.
연구의 한계(표본 크기, 대상 집단, 관찰연구 여부, 결론이 엇갈리는지)도 같이 적어줘.
한계가 있으면 숨기지 말고 그대로 쓴다. 이 계정의 신뢰는 거기서 나온다.

# 주제 대장
{topics}

# 콘텐츠 기준 (참고)
{rules[:3000]}

---
주제 3개에 대해 각각 아래를 정리해줘. 마크다운 평문으로.
- 주제(검색 질문 형태)
- 핵심 사실 3~5개 (숫자 포함, 비교 대상 명시)
- 출처 (저자, 저널, 연도)
- 한계
- 이 주제를 어느 날짜에 배치할지와 bg_tag(요가/스트레칭/홈트/러닝/필라테스)
"""
    print("[1/2] 주제 조사 중...", flush=True)
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 12}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        sys.exit(f"❌ 조사 단계가 거부됐습니다: {msg.stop_details}")
    brief = "\n".join(b.text for b in msg.content if b.type == "text")
    print(f"  브리프 {len(brief)}자 / 입력 {msg.usage.input_tokens} 출력 {msg.usage.output_tokens} 토큰", flush=True)
    return brief


def write_spec(client, week_of, dates, rules, brief, sample):
    """브리프를 받아 weeks/<주차>.json 구조로 쓴다."""
    prompt = f"""아래 조사 브리프를 바탕으로 디자인짐 사장 계정 주간 원고 3건을 써줘.

week_of는 "{week_of}", bg_dir는 빈 문자열, 날짜는 {dates[0]} / {dates[1]} / {dates[2]}.

# 반드시 지킬 규칙
{rules}

# 특히 자주 틀리는 것
- 표지 두 줄 **각각**에 주어와 대상이 있어야 한다. "발 바꾸지 마세요"처럼 무엇을 바꾸는지 없으면 안 된다.
- 말투: `습니다`·`입니다`를 쓰지 않는다. `~요 / ~죠 / ~거든요 / ~잖아요 / ~더라고요`만. (표지는 예외)
- 슬라이드 5장의 layout을 섞고 같은 것을 연속으로 쓰지 않는다. 순서 예: big, stat, classic, bottom, top
- `big` 레이아웃은 badge와 body를 빈 문자열로, `stat`은 main을 빈 문자열로 두고 number를 채운다.
- 그 외 레이아웃은 number를 빈 문자열로 둔다.
- blog_image_plan의 `after`는 본문에 있는 소제목과 **정확히 같은 문자열**이어야 한다.
  이미지 파일명은 01_cover.jpg, 02_content.jpg ~ 06_content.jpg, 07_closing.jpg 7장을 전부 써야 한다.
  top에 01_cover.jpg, end에 07_closing.jpg, 나머지 5장을 소제목들에 나눠 배치한다.
- closing은 "매트 위 시간이 편해지면 좋겠어요"로 고정.
- blog 본문은 1400~1800자. `---`로 끝내지 않는다.
- 3건의 bg_tag를 서로 다르게 잡는다.

# 조사 브리프
{brief}

# 지난주 원고 (형식 참고)
{sample[:6000]}
"""
    print("[2/2] 원고 작성 중...", flush=True)
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": WEEK_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        sys.exit(f"❌ 집필 단계가 거부됐습니다: {msg.stop_details}")
    if msg.stop_reason == "max_tokens":
        sys.exit("❌ 출력이 max_tokens에 걸려 잘렸습니다. 다시 실행하세요.")
    text = next(b.text for b in msg.content if b.type == "text")
    print(f"  입력 {msg.usage.input_tokens} 출력 {msg.usage.output_tokens} 토큰", flush=True)
    return json.loads(text)


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
        for i, line in enumerate(cover, 1):
            if len(line) > 12:
                problems.append(f"{d}: 표지 {i}행이 {len(line)}자")

        lays = [s.get("layout") for s in c.get("slides", [])]
        for i in range(len(lays) - 1):
            if lays[i] == lays[i + 1]:
                problems.append(f"{d}: layout {lays[i]}가 연속")
        for s in c.get("slides", []):
            if len(s.get("badge", "")) > 4:
                problems.append(f"{d}: badge '{s['badge']}'가 4자 초과")

        # 말투 (따옴표 안 인용과 출처 줄은 제외)
        import re
        blog = re.sub(r"출처:.*", "", re.sub(r'"[^"]*"', "", c.get("blog", "")))
        cap = re.sub(r'"[^"]*"', "", c.get("caption", ""))
        slide_txt = " ".join(s.get("body", "") + s.get("main", "") for s in c.get("slides", []))
        for name, t in [("블로그", blog), ("캡션", cap), ("슬라이드", slide_txt)]:
            hit = [x for x in stiff if x in t]
            if hit:
                problems.append(f"{d}: {name}에 문어체 {hit}")

        # 이미지 배치
        lines = c.get("blog", "").split("\n")
        plan = c.get("blog_image_plan", [])
        imgs = [i for p in plan for i in p.get("images", [])]
        if sorted(imgs) != sorted(["01_cover.jpg", "07_closing.jpg"] + [f"0{i}_content.jpg" for i in range(2, 7)]):
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

    if args:
        monday = date.fromisoformat(args[0])
    else:
        t = date.today()
        monday = t - timedelta(days=t.weekday())
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

    client = anthropic.Anthropic()
    brief = research(client, dates, rules, topics)
    week = write_spec(client, week_of, dates, rules, brief, sample)
    week["week_of"] = week_of
    week["bg_dir"] = ""

    problems = validate(week, dates)
    if problems:
        print("\n❌ 규칙 위반으로 저장하지 않습니다:")
        for p in problems:
            print("  -", p)
        # 브리프는 남겨둔다. 사람이 이어서 쓰거나 원인을 볼 수 있게.
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
