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

from publish_days import DAYS_EN as DAYS, KR, OFFSET, IMAGE_COUNT, CLOSER

DRY = os.environ.get("DRY_RUN") == "1"


def log(m):
    print(f"[{datetime.now(KST):%H:%M:%S}] {m}", flush=True)


def next_monday():
    """이번 주 월요일. 월요일 아침에 도는 워크플로이므로 '오늘이 속한 주'가 대상이다."""
    today = datetime.now(KST).date()
    return today - timedelta(days=today.weekday())


def model_for(lib, product_key):
    """등록 제품(Element)을 쓰는 컷은 nano_banana_pro로 만든다.

    Elements(<<<id>>>)는 marketing_studio_image가 지원하지 않는다. 매트는 무늬를 말로 설명하면
    계속 다른 매트가 나와서(2026-09-07 반복 반려) 등록 제품을 직접 참조해야 한다.
    """
    return "nano_banana_pro" if lib["products"][product_key].get("element") else "marketing_studio_image"


def build_snap_prompt(lib, product_key, setup_key, angle_key):
    """아이폰으로 방금 찍은 것처럼 보이는 한 컷. 하루치는 세트 하나 + 앵글 여러 개다.

    구성은 [스타일][카메라][장소·빛][제품 규격][금지사항] 순서다. 제품 규격은 종전과 같은
    실측 스펙을 쓰되, 매트는 무늬가 틀어지기 쉬워 프레이밍 조건을 함께 건다.
    """
    p = lib["products"][product_key]
    sh = lib["shared"]
    setup = lib["setups"][setup_key]
    angle = lib["angles"][angle_key]

    parts = [sh["iphone"], "", angle["prompt"], "", setup["prompt"], ""]

    if p.get("element"):
        parts += [f"THE PRODUCT IS <<<{p['element']}>>> - reproduce this exact registered product: its printed "
                  "artwork, colours, proportions and thickness must match the reference product photograph "
                  "precisely. Do not invent a different print or a different colourway."]
        if p["kind"] == "mat":
            parts += ["THE MAT: " + sh["mat_body"],
                      sh["mat_artwork_guard"],
                      "COLOUR CHECK - the printed artwork must read exactly as follows, with no shape or "
                      "colour substituted: " + p["spec"]]
    elif p["kind"] == "band":
        parts += ["THE BAND: " + p["spec"]]
    else:
        parts += ["THE PRODUCT - copy the reference exactly: " + p["spec"]]

    # 사람은 사진 찍는 본인의 발이나 손까지만. 모델컷은 이 체계에서 만들지 않는다.
    if angle_key in ("ang_topdown_feet", "ang_in_hand"):
        parts += ["", "The only body part anywhere in frame belongs to the person holding the phone, exactly "
                      "as the camera note says. No face, no second person, no model."]
    else:
        parts += ["", "No people at all."]

    if p["kind"] == "mat":
        parts += [sh["mat_logo_offframe"]]
    parts += ["", sh["iphone_negative"]]
    return "\n".join(x for x in parts if x)


def build_prompt(lib, product_key, scene_key):
    """구(舊) 월~금 체계용. 2026-09-16 화·목·일 개편 전에 만든 주차를 재현할 때만 쓴다."""
    p = lib["products"][product_key]
    s = lib["scenes"][scene_key]
    sh = lib["shared"]
    parts = [s["prompt"], ""]
    if p.get("element"):
        # 등록된 제품을 그대로 쓴다 — 무늬·비율·두께를 말로 설명하지 않는다
        parts += [f"THE PRODUCT IS <<<{p['element']}>>> - reproduce this exact registered product: its printed "
                  "artwork, colours, proportions and thickness must match the reference product photograph "
                  "precisely. Do not invent a different print or a different colourway.",
                  "THE MAT: " + sh["mat_body"] if p["kind"] == "mat" else ""]
        # 등록 제품이라도 색이 이웃 색조로 밀려 나오는 일이 있다(2026-09-14: 잿빛 보라 블롭이
        # 하늘색으로 나왔다). 무늬는 Element에 맡기고, 색만 한 줄로 다시 못박는다.
        if p["kind"] == "mat" and p.get("spec"):
            parts += ["COLOUR CHECK - the printed artwork must read exactly as follows, with no shape or "
                      "colour substituted: " + p["spec"]]
    elif p["kind"] == "mat":
        parts += ["THE MAT: " + sh["mat_body"], sh["mat_artwork_rule"],
                  "ARTWORK - copy the reference exactly. " + p["spec"]]
    elif p["kind"] == "band":
        parts += ["THE BAND: " + p["spec"]]
    else:
        parts += ["THE PRODUCT - copy the reference exactly: " + p["spec"]]
    if "person" in s["prompt"] or scene_key.startswith(("band_glute", "band_clam", "mat_bal", "mat_seated")):
        parts += ["", sh["person"]]
    # 밴드 착용컷·매트 인물컷은 매트가 함께 나오므로 매트 규격도 넣는다
    if scene_key in ("band_glute_bridge", "band_clamshell", "band_squat"):
        wm = lib["products"]["mat_warm_sunlight"]
        parts += ["", f"THE MAT UNDER HER IS <<<{wm['element']}>>> - reproduce that exact registered product. "
                  + sh["mat_body"],
                  sh["no_branding"]]
    if p["kind"] == "mat":
        # 실물 매트에는 워드마크가 인쇄돼 있지만, 생성 모델에 그리게 하면 우리 로고가 아닌
        # 엉뚱한 마크를 만들어 낸다(2026-09-14 실측). 로고는 아예 프레임 밖으로 빼고,
        # 화면 안에는 글자를 한 자도 두지 않는다.
        parts += ["", sh["no_branding"], sh["mat_logo_offframe"]]
    parts += ["", sh["quality"]]
    return "\n".join(x for x in parts if x is not None)


def medias_for(lib, product_key, scene_key=None):
    if lib["products"][product_key].get("element"):
        return []          # 등록 제품은 프롬프트의 <<<element_id>>>가 이미지를 주입한다
    m = [{"value": lib["products"][product_key]["media"], "role": "image"}]
    if scene_key in ("band_glute_bridge", "band_clamshell"):
        m.append({"value": lib["products"]["mat_warm_sunlight"]["media"], "role": "image"})
    return m


def pool_key_for(lib, product_key):
    kind = lib["products"][product_key]["kind"]
    if kind in ("mat", "band"):
        return kind
    return "kettlebell" if "kettlebell" in product_key else "dumbbell"


def caption_for(lib, product_key, seen, is_closer, week_no=0, angle_keys=None, used=None):
    """seen: 이번 주에 그 제품군을 몇 번째로 쓰는지(0부터). week_no: ISO 주차.
    angle_keys: 그날 찍은 앵글들. used: 이번 주에 이미 쓴 문구 제목들(집합).
    is_closer: 한 주를 닫는 날이면 본문에 브랜드 서명을 붙인다.

    세 가지를 동시에 피해야 한다.
    (1) 한 주 안에서 겹침 — 같은 제품군이 두 번 나오는 주(매트 2일)에 같은 문구가 걸린다.
        2026-08-31에 화=1, 금=4 를 요일 인덱스로 골라 1%3==4%3 으로 동일 문구가 나갔다.
    (2) 주마다 겹침 — 순번이 매주 0부터 다시 시작하면 몇 주가 지나도 풀 앞쪽만 계속 쓴다.
        2026-09-14 '내용이 죄다 똑같다' 지적의 원인이 이것이다.
        그래서 주차를 오프셋으로 더해 풀 전체를 한 바퀴씩 돌린다.
    (3) 자세와 문구의 불일치 — 풀이 제품군으로만 묶여 있어서 글루트 브릿지 컷에
        스쿼트 문구가, 다운독 컷에 플랫레이 문구가 걸렸다(2026-09-14 반려).
        구도를 지목하는 문구에는 angles 허용목록이 달려 있으니, 그날 찍은 앵글 중
        하나라도 목록에 들어야 쓴다."""
    pool_key = pool_key_for(lib, product_key)
    pool = lib["captions"][pool_key]
    used = set() if used is None else used
    angles = set(angle_keys or [])

    fits = [c for c in pool
            if not angles or "angles" not in c or angles & set(c["angles"])]
    if not fits:                       # 허용목록을 너무 좁게 달면 고를 게 없어진다 — 그때는 풀 전체
        fits = pool

    # 주차만 오프셋으로 쓰면 배분안 주기(4주)와 맞물려 같은 장면에 같은 문구만 돈다:
    # 배분안이 week_no % 4 로 정해지므로 특정 장면이 도는 주는 week_no 가 항상 같은 나머지를
    # 갖고, week_no 의 어떤 1차식도 풀 길이 2·4 에 대해 상수가 된다(실측: band_flatlay 가
    # 20주 내내 같은 문구). 배분안이 몇 바퀴째인지(cycle)를 함께 더해 이 맞물림을 깬다.
    # 배분안이 몇 바퀴째인지(cycle)를 함께 더해 이 맞물림을 깬다. 배분안 주기가 4이므로
    # week_no = 4k + r 이고 오프셋은 (4+m)k + r 이 된다 — 풀 길이 L 로 나눈 나머지가 k 에
    # 따라 변하려면 (4+m) % L != 0 이어야 한다. m=3 이면 7 이라 L=2..6, 8, 9 에서 모두 안전하다.
    cycle = week_no // max(1, len(lib.get("week_plans") or [1]))
    start = (week_no + cycle * 3 + seen) % len(fits)
    order = fits[start:] + fits[:start]
    c = next((x for x in order if x["t"] not in used), order[0])
    used.add(c["t"])

    # 브랜드 서명은 한 주를 닫는 날에만, 본문이 이미 브랜드로 끝나지 않을 때만 붙인다.
    body = c["c"]
    if is_closer and "디자인짐" not in body:
        body += lib["brand_tail"]
    title = c["t"]
    tags = c["h"]
    tt = f"{title} {' '.join(tags.split()[:3])}"
    return body, tags, tt[:90]


def to_web_jpeg(url, width=1080, quality=92):
    """생성 원본(PNG)을 발행용 JPEG으로. 인스타 8MB 한도와 틱톡 JPEG 요구를 한 번에 만족시킨다."""
    import io
    from PIL import Image
    with urllib.request.urlopen(url, timeout=180) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    w, h = im.size
    im = im.resize((width, round(h * width / w)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def upload_bytes(mcp, data, filename):
    """힉스필드에 올려 영구 URL을 받는다. 생성 결과 URL 대신 이걸 발행에 쓴다."""
    up = mcp.tool("media_upload", {"filename": filename, "content_type": "image/jpeg"})["uploads"][0]
    req = urllib.request.Request(up["upload_url"], data=data,
                                 headers={"Content-Type": "image/jpeg"}, method="PUT")
    with urllib.request.urlopen(req, timeout=180) as r:
        if r.status != 200:
            raise RuntimeError(f"업로드 실패 {r.status}")
    mcp.tool("media_confirm", {"type": "image", "media_id": up["media_id"]})
    return up["url"]


def main():
    lib = json.load(open(os.path.join(BASE, "weekly_prompts.json"), encoding="utf-8"))
    week_of = os.environ.get("WEEK_OF") or next_monday().strftime("%Y-%m-%d")
    monday = datetime.strptime(week_of, "%Y-%m-%d").date()

    pending_path = os.path.join(BASE, "pending_posts.json")
    existing = json.load(open(pending_path, encoding="utf-8"))
    if existing.get("week_of") == week_of:
        log(f"{week_of} 주차는 이미 만들어져 있음 — 종료 (덮어쓰지 않는다)")
        return 0

    # 일요일이 발행일이 되면서 '전 주 일요일 발행'과 '이번 주 생성'이 같은 밤에 붙었다.
    # 생성이 먼저 돌면 아직 안 나간 게시물이 파일째 사라진다. 아직 때가 안 지난 미발행분이
    # 남아 있으면 덮어쓰지 않고 다음 크론에 넘긴다(크론은 하루에 여러 번 돈다).
    today = datetime.now(KST).date().isoformat()
    stuck = [f"{e.get('date')}({d})" for d, e in existing.get("posts", {}).items()
             if e.get("date") and e["date"] <= today
             and not (e.get("ig_posted") and e.get("tiktok_posted"))]
    if stuck and not DRY:
        log(f"지난 주차에 아직 안 나간 게시물이 있음 — 덮어쓰지 않고 종료: {', '.join(sorted(stuck))}")
        return 0
    if stuck:
        log(f"[DRY_RUN] 실제 실행이면 여기서 멈춘다(미발행분: {', '.join(sorted(stuck))})")

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
    for day, (pk, setup, angles) in zip(DAYS, plan):
        log(f"  {KR[day]} ({IMAGE_COUNT[day]}장): {lib['products'][pk]['label']} / "
            f"{lib['setups'][setup]['hook']} / " + ", ".join(lib['angles'][a]['hook'] for a in angles))
    if DRY:
        log("[DRY_RUN] 생성 없이 계획만 출력하고 종료")
        return 0

    mcp = Mcp(access_token())
    try:
        bal_before = mcp.tool("balance", {}).get("credits")
    except Exception as e:
        bal_before = None
        log(f"잔액 조회 실패(무시): {e}")
    # 컷 단위로 펼친다 — (요일, 그 요일 안의 순번, 제품, 세트, 앵글)
    shots = []
    for day, (pk, setup, angles) in zip(DAYS, plan):
        for n, angle in enumerate(angles):
            shots.append((day, n, pk, setup, angle))

    if bal_before is not None:
        log(f"생성 전 잔액 {bal_before}")
        if bal_before < len(shots) * 2:
            raise SystemExit(
                f"크레딧 부족: 잔액 {bal_before}, 필요 약 {len(shots)*2} "
                "(장당 2크레딧). 충전 후 다시 실행하세요.")

    reqs = []
    for i, (day, n, pk, setup, angle) in enumerate(shots):
        params = {"model": model_for(lib, pk), "aspect_ratio": "4:5", "resolution": "2k",
                  "prompt": build_snap_prompt(lib, pk, setup, angle)}
        med = medias_for(lib, pk)
        if med:
            params["medias"] = med
        reqs.append({"index": i, "params": params})
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
    log(f"생성 완료 {sum(1 for v in results.values() if v)}/{len(shots)}장")

    # 컷을 요일별로 다시 묶는다. 한 장이라도 실패하면 그날은 남은 장수로 올린다 —
    # 캐러셀은 장수가 줄어도 게시가 되므로, 하루를 통째로 버리지 않는다.
    img_dir = os.path.join(BASE, "images", week_of)
    os.makedirs(img_dir, exist_ok=True)
    by_day = {}
    for i, (day, n, pk, setup, angle) in enumerate(shots):
        url = results.get(i)
        if not url:
            log(f"  {KR[day]} {n+1}번째 컷 실패 — 건너뜀")
            continue
        # 인스타는 이미지 8MB를 넘으면 400으로 거부한다(2026-08-27 금요일분 10.46MB로 실패).
        # 생성 원본은 PNG 10MB대까지 나오므로, 발행에 쓸 URL은 1080px JPEG으로 만들어 올린다.
        fname = f"{day[:3].lower()}_{n+1}_{pk}.jpg"
        jpeg = to_web_jpeg(url)
        with open(os.path.join(img_dir, fname), "wb") as f:
            f.write(jpeg)
        by_day.setdefault(day, []).append(
            {"path": f"images/{week_of}/{fname}", "image_url": upload_bytes(mcp, jpeg, fname)})

    posts, missing, used = {}, [], {}
    used_titles = set()            # 한 주 안에서 같은 문구가 두 번 걸리지 않게 제목을 모아둔다
    for day, (pk, setup, angles) in zip(DAYS, plan):
        images = by_day.get(day)
        date = (monday + timedelta(days=OFFSET[day])).strftime("%Y-%m-%d")
        if not images:
            missing.append(KR[day])
            continue
        seen = used.get(pool_key_for(lib, pk), 0)
        used[pool_key_for(lib, pk)] = seen + 1
        cap, tags, tt = caption_for(lib, pk, seen, day == CLOSER, monday.isocalendar()[1],
                                    angle_keys=angles, used=used_titles)
        hook = (f"{lib['setups'][setup]['hook']} / "
                + ", ".join(lib['angles'][a]['hook'] for a in angles))
        posts[day] = {
            "date": date, "product": lib["products"][pk]["label"], "hook": hook,
            "images": images,
            "caption": cap, "hashtags": tags, "tiktok_title": tt + "\n\n---",
            "posted": False, "ig_posted": None, "tiktok_posted": None,
        }

    if not posts:
        log("한 장도 못 만들었다 — pending_posts.json 건드리지 않고 실패 처리")
        return 1

    try:
        bal_after = mcp.tool("balance", {}).get("credits")
    except Exception:
        bal_after = None
    spent = round(bal_before - bal_after, 2) if (bal_before is not None and bal_after is not None) else None
    made = sum(len(p["images"]) for p in posts.values())    # 요일 수가 아니라 실제 장수
    if spent is not None:
        log(f"크레딧 사용 {spent} (생성 {made}장 / {len(posts)}일, 잔액 {bal_before} → {bal_after})")
    json.dump({"week_of": week_of, "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
               "images": made, "credits_spent": spent,
               "balance_before": bal_before, "balance_after": bal_after},
              open(os.path.join(BASE, "last_run_credits.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    json.dump({"week_of": week_of, "plan_idx": plan_idx, "posts": posts},
              open(pending_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"pending_posts.json 갱신 ({len(posts)}일)")
    if missing:
        log(f"경고: 생성 실패한 요일 있음 → {', '.join(missing)} (수동 보완 필요)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
