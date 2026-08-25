"""다음 주 인스타/틱톡 이미지 5장을 생성해 저장소에 반영한다 (GitHub Actions 전용).

배경(2026-08-24): 주간 생성은 claude.ai 클라우드 루틴이 맡고 있었는데, 그 세션은 저장소로
git push 하는 것이 플랫폼 차원에서 차단돼 있었다("add the repository to the session's sources").
8/3 이후 클라우드 push가 한 번도 성공한 적 없던 진짜 이유가 이것이다. 발행을 Actions로 옮긴 것과
같은 방식으로, 힉스필드 MCP를 갱신토큰으로 직접 호출해 생성까지 Actions에서 끝낸다.

프롬프트는 즉석에서 짓지 않는다. weekly_prompts.json에 실물 레퍼런스를 열어 확인한 제품 스펙이
들어 있고(덤벨=알약형, 케틀벨=초승달, 밴드=서로 다른 3종, 매트=폭을 꽉 채우는 넓은 타원),
여기서 조립만 한다. 제품 형태가 바뀌면 실물 사진을 먼저 보고 그 파일을 고칠 것.

매트에 로고를 얹는 합성(stamp_logo.py)은 매트 네 모서리 좌표가 매번 달라 자동화하지 않는다.
자동 생성분은 로고가 프레임에 안 나오는 구도만 쓰고, 로고 노출 컷이 필요하면 사람이 따로 만든다.

환경변수: HF_CLIENT_ID, HF_REFRESH_TOKEN (발행 워크플로와 동일), GH_TOKEN(시크릿 회전용)
옵션: WEEK_OF=YYYY-MM-DD 로 대상 주 강제, DRY_RUN=1 이면 생성 없이 계획만 출력
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from tt_publish import Mcp, access_token, KST, BASE

DRY = os.environ.get("DRY_RUN") == "1"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
KR = {"Monday": "월요일", "Tuesday": "화요일", "Wednesday": "수요일",
      "Thursday": "목요일", "Friday": "금요일"}


def log(m):
    print(f"[{datetime.now(KST):%H:%M:%S}] {m}", flush=True)


def next_monday():
    """이번 주 월요일. 월요일 아침에 도는 워크플로이므로 '오늘이 속한 주'가 대상이다."""
    today = datetime.now(KST).date()
    return today - timedelta(days=today.weekday())


def build_prompt(lib, product_key, scene_key):
    p = lib["products"][product_key]
    s = lib["scenes"][scene_key]
    sh = lib["shared"]
    parts = [s["prompt"], ""]
    if p["kind"] == "mat":
        parts += ["THE MAT: " + sh["mat_body"], sh["mat_artwork_rule"],
                  "ARTWORK - copy the reference exactly. " + p["spec"]]
    elif p["kind"] == "band":
        parts += ["THE BAND: " + p["spec"]]
    else:
        parts += ["THE PRODUCT - copy the reference exactly: " + p["spec"]]
    if "person" in s["prompt"] or scene_key.startswith(("band_glute", "band_clam", "mat_bal", "mat_seated")):
        parts += ["", sh["person"]]
    # 밴드 착용컷·매트 인물컷은 매트가 함께 나오므로 매트 규격도 넣는다
    if scene_key in ("band_glute_bridge", "band_clamshell"):
        parts += ["", "THE MAT UNDER HER: " + sh["mat_body"],
                  "Mat artwork: soft apricot-pink oval forms, a warm yellow ring and a slate-navy block on a cream ground.",
                  "NO text, NO lettering, NO logo and NO blurred smudge anywhere on the mat."]
    if p["kind"] == "mat":
        parts += ["", sh["no_branding"]]
    parts += ["", sh["quality"]]
    return "\n".join(x for x in parts if x is not None)


def medias_for(lib, product_key, scene_key):
    m = [{"value": lib["products"][product_key]["media"], "role": "image"}]
    if scene_key in ("band_glute_bridge", "band_clamshell"):
        m.append({"value": lib["products"]["mat_warm_sunlight"]["media"], "role": "image"})
    return m


def caption_for(lib, product_key, idx, is_friday):
    kind = lib["products"][product_key]["kind"]
    pool_key = {"mat": "mat", "band": "band"}.get(kind)
    if pool_key is None:
        pool_key = "kettlebell" if "kettlebell" in product_key else "dumbbell"
    pool = lib["captions"][pool_key]
    c = pool[idx % len(pool)]
    body = c["c"] + (lib["friday_tail"] if is_friday else "")
    title = c["t"]
    tags = c["h"]
    tt = f"{title} {' '.join(tags.split()[:3])}"
    return body, tags, tt[:90]


def main():
    lib = json.load(open(os.path.join(BASE, "weekly_prompts.json"), encoding="utf-8"))
    week_of = os.environ.get("WEEK_OF") or next_monday().strftime("%Y-%m-%d")
    monday = datetime.strptime(week_of, "%Y-%m-%d").date()

    pending_path = os.path.join(BASE, "pending_posts.json")
    existing = json.load(open(pending_path, encoding="utf-8"))
    if existing.get("week_of") == week_of:
        log(f"{week_of} 주차는 이미 만들어져 있음 — 종료 (덮어쓰지 않는다)")
        return 0

    # 지난주와 같은 배분안을 반복하지 않는다(주간 규칙: 같은 제품에 같은 구도 금지).
    # 훅 문구는 손으로 고쳐질 수 있어 비교 기준으로 못 쓴다 — 쓴 배분안 번호를 데이터에 남겨 비교한다.
    plans = lib["week_plans"]
    plan_idx = monday.isocalendar()[1] % len(plans)
    prev_idx = existing.get("plan_idx")
    if prev_idx is not None and plan_idx == prev_idx:
        plan_idx = (plan_idx + 1) % len(plans)
        log(f"배분안 #{prev_idx}는 지난주와 동일 — #{plan_idx}로 변경")
    plan = plans[plan_idx]
    log(f"대상 주 {week_of} / 배분안 #{plan_idx}")
    for day, (pk, sk) in zip(DAYS, plan):
        log(f"  {KR[day]}: {lib['products'][pk]['label']} / {lib['scenes'][sk]['hook']}")
    if DRY:
        log("[DRY_RUN] 생성 없이 계획만 출력하고 종료")
        return 0

    mcp = Mcp(access_token())
    reqs = [{"index": i, "params": {
        "model": "marketing_studio_image", "aspect_ratio": "4:5", "resolution": "2k",
        "medias": medias_for(lib, pk, sk), "prompt": build_prompt(lib, pk, sk)}}
        for i, (pk, sk) in enumerate(plan)]
    jobs = mcp.tool("generate_image_batch", {"requests": reqs})["jobs"]
    log(f"{len(jobs)}장 생성 요청 완료")

    pending = [{"index": j["index"], "job_id": j["job_id"]} for j in jobs]
    results = {}
    for _ in range(40):                      # 최대 약 10분
        if not pending:
            break
        r = mcp.tool("jobs_wait", {"jobs": pending, "timeout_seconds": 15})
        for j in r["jobs"]:
            if j["status"] == "completed" and j.get("result_url"):
                results[j["index"]] = j["result_url"]
            elif j["status"] in ("failed", "canceled"):
                results[j["index"]] = None
        pending = [p for p in pending if p["index"] not in results]
    log(f"생성 완료 {sum(1 for v in results.values() if v)}/{len(plan)}장")

    img_dir = os.path.join(BASE, "images", week_of)
    os.makedirs(img_dir, exist_ok=True)
    posts, missing = {}, []
    for i, (day, (pk, sk)) in enumerate(zip(DAYS, plan)):
        url = results.get(i)
        date = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
        if not url:
            missing.append(KR[day])
            continue
        fname = f"{day[:3].lower()}_1_{pk}.png"
        with urllib.request.urlopen(url, timeout=180) as resp, \
             open(os.path.join(img_dir, fname), "wb") as f:
            f.write(resp.read())
        cap, tags, tt = caption_for(lib, pk, i, day == "Friday")
        posts[day] = {
            "date": date, "product": lib["products"][pk]["label"],
            "hook": lib["scenes"][sk]["hook"],
            "images": [{"path": f"images/{week_of}/{fname}", "image_url": url}],
            "caption": cap, "hashtags": tags, "tiktok_title": tt + "\n\n---",
            "posted": False, "ig_posted": None, "tiktok_posted": None,
        }

    if not posts:
        log("한 장도 못 만들었다 — pending_posts.json 건드리지 않고 실패 처리")
        return 1

    json.dump({"week_of": week_of, "plan_idx": plan_idx, "posts": posts},
              open(pending_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"pending_posts.json 갱신 ({len(posts)}일)")
    if missing:
        log(f"경고: 생성 실패한 요일 있음 → {', '.join(missing)} (수동 보완 필요)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
