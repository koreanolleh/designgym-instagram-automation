"""이미 만든 주차에서 컷 한 장만 다시 뽑는다 (크레딧 2).

왜 필요한가 — 반려는 보통 한 장에서 난다("목요일에 발은 안보이게 해줘"). 그런데
weekly_generate 의 REGEN=1 은 그 주 8장을 통째로 다시 만들어 16크레딧을 쓴다.
멀쩡한 7장까지 버리는 셈이라, 한 장짜리 교체 경로를 따로 둔다.

하는 일: 지정한 요일·순번의 컷을 새 앵글로 다시 생성해서 같은 파일명에 덮고,
발행용 JPEG 을 올려 pending_posts.json 의 image_url 까지 바꾼다. 캡션은 건드리지 않는다.

사용:
  DAY=Thursday SLOT=1 ANGLE=ang_stretch_in_hand python3 regen_one.py
  DRY=1 ... 로 부르면 프롬프트만 찍고 크레딧을 쓰지 않는다.
옵션: SETUP=<setups 키> 로 방도 바꾼다(기본은 그 날 쓰던 방 그대로).
"""
import json
import os

from tt_publish import Mcp, access_token, BASE
from weekly_generate import (build_snap_prompt, medias_for, model_for,
                             to_web_jpeg, upload_bytes, log)

LIB_PATH = os.path.join(BASE, "weekly_prompts.json")
PENDING_PATH = os.path.join(BASE, "pending_posts.json")
DRY = os.environ.get("DRY") == "1"


def main():
    day = os.environ["DAY"]
    slot = int(os.environ.get("SLOT", "1"))          # 1부터 — 노트에 보이는 순서와 같다
    angle = os.environ["ANGLE"]

    lib = json.load(open(LIB_PATH, encoding="utf-8"))
    plan = json.load(open(PENDING_PATH, encoding="utf-8"))
    post = plan["posts"][day]

    # 이미 나간 날은 다시 만들지 않는다 — 올라간 사진과 저장소가 어긋나면 추적이 안 된다.
    if post.get("ig_posted") or post.get("tiktok_posted"):
        log(f"{day} 는 이미 발행됐다 — 교체하지 않는다")
        return 1

    images = post["images"]
    if not 1 <= slot <= len(images):
        log(f"{day} 는 {len(images)}장뿐이다 — SLOT={slot} 없음")
        return 1

    # 제품키는 파일명 뒤쪽에 들어 있다: thu_1_band.jpg → band
    fname = os.path.basename(images[slot - 1]["path"])
    pk = fname[:-4].split("_", 2)[2]
    if pk not in lib["products"]:
        log(f"파일명에서 제품을 못 읽었다: {fname}")
        return 1

    # 방·소품·그림자는 그 날 쓰던 것을 그대로 쓴다 — 한 장만 다른 방이면 캐러셀이 어긋난다.
    saved = {d["day"]: d for d in plan.get("day_plan", [])} if plan.get("day_plan") else {}
    rec = saved.get(day, {})
    setup = os.environ.get("SETUP") or rec.get("setup")
    props, shadow = rec.get("props"), rec.get("shadow")
    if not setup:
        # day_plan 이 없던 주차 — 훅 문구 앞머리가 방 이름이다.
        head = post.get("hook", "").split(" / ")[0].strip()
        setup = next((k for k, v in lib["setups"].items() if v["hook"] == head), None)
        if not setup:
            log(f"방을 못 찾았다. SETUP=<키> 로 지정하라. 훅: {post.get('hook')}")
            return 1
        log(f"day_plan 기록이 없어 훅에서 방을 찾았다: {setup}")

    prompt = build_snap_prompt(lib, pk, setup, angle, props, shadow)
    log(f"{day} {slot}번째 컷 교체 — 제품 {pk} / 방 {setup} / 앵글 {angle}")
    print("\n--- 프롬프트 ---\n" + prompt + "\n----------------\n", flush=True)
    if DRY:
        log("DRY=1 — 생성하지 않았다 (크레딧 0)")
        return 0

    mcp = Mcp(access_token())
    bal = mcp.tool("balance", {}).get("credits")
    log(f"생성 전 잔액 {bal}")
    if bal is not None and bal < 2:
        log("크레딧 부족 — 중단")
        return 1

    params = {"model": model_for(lib, pk), "aspect_ratio": "4:5", "resolution": "2k",
              "prompt": prompt}
    med = medias_for(lib, pk)
    if med:
        params["medias"] = med
    job = mcp.tool("generate_image_batch", {"requests": [{"index": 0, "params": params}]})["jobs"][0]

    url = None
    pending = [{"index": 0, "job_id": job["job_id"]}]
    for _ in range(40):                                  # 최대 약 10분
        r = mcp.tool("jobs_wait", {"jobs": pending, "timeout_seconds": 15})
        j = r["jobs"][0]
        if j["status"] == "completed" and j.get("result_url"):
            url = j["result_url"]
            break
        if j["status"] in ("failed", "canceled"):
            log(f"생성 실패: {j['status']}")
            return 1
    if not url:
        log("시간 초과 — 결과를 못 받았다")
        return 1

    # 인스타 8MB 한도 때문에 발행에 쓰는 URL 은 반드시 1080px JPEG 이다.
    jpeg = to_web_jpeg(url)
    out = os.path.join(BASE, "images", plan["week_of"], fname)
    with open(out, "wb") as f:
        f.write(jpeg)
    images[slot - 1]["image_url"] = upload_bytes(mcp, jpeg, fname)

    # 훅에도 바뀐 앵글을 반영한다 — 노트에서 어떤 구도인지 읽히는 유일한 줄이다.
    hooks = post.get("hook", "").split(" / ")
    if len(hooks) >= 4:
        shots = [h.strip() for h in hooks[3].split(",")]
        if slot <= len(shots):
            shots[slot - 1] = lib["angles"][angle]["hook"]
            post["hook"] = " / ".join(hooks[:3] + [", ".join(shots)])

    json.dump(plan, open(PENDING_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    after = mcp.tool("balance", {}).get("credits")
    log(f"교체 완료: {fname} (잔액 {bal} → {after})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
