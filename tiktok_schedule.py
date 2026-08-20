"""틱톡 스튜디오 웹에서 영상 예약 게시를 자동화한다 (Playwright + 실제 Chrome).

배경(2026-08-18): 틱톡은 내부용 앱에 API를 승인하지 않고(8/7 심사 반려),
힉스필드 API에는 예약 기능이 없다. 스튜디오 웹의 시간 픽커(TUX)는 합성 이벤트를
무시하지만, Playwright(CDP)의 클릭은 trusted라서 정상 동작한다 — 당일 실측 검증됨.
사용자 크롬과 완전히 분리된 전용 프로필을 쓰므로 마우스/키보드를 뺏지 않는다.

사용:
  python3 tiktok_schedule.py --login
      전용 프로필로 창을 열어준다. 틱톡 QR 로그인 1회 (세션은 프로필에 저장됨).
  python3 tiktok_schedule.py --video 경로.mp4 --caption "문구" --date 2026-08-19 --time 19:30
      영상 1건을 해당 일시로 예약. 성공 시 exit 0.

제약: 예약은 최소 15분 뒤 ~ 최대 30일 이내(틱톡 규칙). 영상만 가능(사진 불가).
"""
import argparse
import sys
import time as time_mod
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path.home() / ".designgym_tiktok_profile"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def launch(p, headed):
    return p.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        channel="chrome",          # 실제 설치된 Chrome 사용 (봇 감지 회피)
        headless=not headed,
        viewport={"width": 1280, "height": 900},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )


def do_login(p):
    ctx = launch(p, headed=True)
    page = ctx.new_page()
    page.goto(UPLOAD_URL)
    log("창이 열렸습니다. 틱톡 QR/문자 로그인을 완료해주세요 (완료 감지까지 최대 5분 대기)")
    try:
        page.wait_for_selector("input[type=file]", timeout=300_000)
        log("로그인 확인 — 세션이 프로필에 저장됐습니다")
    finally:
        ctx.close()


def ensure_logged_in(page):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("input[type=file]", timeout=20_000)
    except Exception:
        raise SystemExit("로그인 세션 없음/만료 — 먼저 --login 을 실행하세요")


def pick_time(page, hh, mm):
    """TUX 시간 픽커: 입력창 클릭 → 시/분 옵션 클릭. 분은 5분 단위만 존재."""
    inp = page.evaluate_handle(
        "() => [...document.querySelectorAll('input')].find(i => /^\\d{2}:\\d{2}$/.test(i.value))"
    )
    inp.as_element().click()
    page.wait_for_selector(".tiktok-timepicker-option-item", timeout=10_000)
    hour = page.locator(
        ".tiktok-timepicker-option-item", has=page.locator(".tiktok-timepicker-left")
    ).filter(has_text=hh).first
    hour.scroll_into_view_if_needed()
    hour.click()
    page.wait_for_timeout(400)
    minute = page.locator(
        ".tiktok-timepicker-option-item", has=page.locator(".tiktok-timepicker-right")
    ).filter(has_text=mm).first
    minute.scroll_into_view_if_needed()
    minute.click()
    page.wait_for_timeout(400)
    got = page.evaluate(
        "() => ([...document.querySelectorAll('input')].find(i => /^\\d{2}:\\d{2}$/.test(i.value))||{}).value"
    )
    if got != f"{hh}:{mm}":
        raise RuntimeError(f"시간 설정 실패: 기대 {hh}:{mm}, 실제 {got}")


def pick_date(page, target: datetime):
    cur = page.evaluate(
        "() => ([...document.querySelectorAll('input')].find(i => /^\\d{4}-\\d{2}-\\d{2}$/.test(i.value))||{}).value"
    )
    want = target.strftime("%Y-%m-%d")
    if cur == want:
        return
    inp = page.evaluate_handle(
        "() => [...document.querySelectorAll('input')].find(i => /^\\d{4}-\\d{2}-\\d{2}$/.test(i.value))"
    )
    inp.as_element().click()
    page.wait_for_timeout(600)
    # 달력에서 날짜 셀 클릭 (이번 달 범위 내 사용 전제. 셀 클래스는 calendar-wrapper 하위 span)
    day = str(target.day)
    cell = page.locator(".calendar-wrapper span, [class*=calendar] span").filter(
        has_text=day
    ).filter(has_not_text="월").first
    try:
        cell.click(timeout=5_000)
    except Exception:
        page.get_by_text(day, exact=True).last.click(timeout=5_000)
    page.wait_for_timeout(500)
    got = page.evaluate(
        "() => ([...document.querySelectorAll('input')].find(i => /^\\d{4}-\\d{2}-\\d{2}$/.test(i.value))||{}).value"
    )
    if got != want:
        raise RuntimeError(f"날짜 설정 실패: 기대 {want}, 실제 {got}")


def schedule(p, video, caption, date_s, time_s, headed):
    target = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
    hh, mm = time_s.split(":")
    if int(mm) % 5 != 0:
        raise SystemExit("분은 5분 단위여야 합니다 (틱톡 픽커 제약)")

    ctx = launch(p, headed=headed)
    page = ctx.new_page()
    try:
        ensure_logged_in(page)

        page.set_input_files("input[type=file]", video)
        log("영상 업로드 중...")
        page.wait_for_selector("div[contenteditable=true]", timeout=60_000)
        # 처리 완료 대기: '교체' 버튼 등장
        page.get_by_role("button", name="교체").wait_for(timeout=120_000)
        log("업로드 완료")

        editor = page.locator("div[contenteditable=true]").first
        editor.click()
        page.keyboard.press("Meta+A")
        page.keyboard.press("Delete")
        editor.type(caption, delay=15)
        page.wait_for_timeout(300)
        got = editor.inner_text()
        if caption[:10] not in got:
            raise RuntimeError(f"캡션 입력 실패: {got[:50]!r}")
        log("캡션 입력 완료")

        # 예약 라디오 (두 번째 postSchedule)
        page.evaluate(
            """() => {
              const r = [...document.querySelectorAll('input[name=postSchedule]')][1];
              const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'checked').set;
              set.call(r, true);
              r.dispatchEvent(new Event('click',{bubbles:true}));
              r.dispatchEvent(new Event('change',{bubbles:true}));
            }"""
        )
        page.wait_for_timeout(800)
        checked = page.evaluate(
            "() => [...document.querySelectorAll('input[name=postSchedule]')][1].checked"
        )
        if not checked:
            page.get_by_text("예약", exact=True).first.click()
            page.wait_for_timeout(800)

        pick_date(page, target)
        pick_time(page, hh, mm)
        log(f"일시 설정 완료: {date_s} {time_s}")

        page.get_by_role("button", name="예약", exact=True).click()
        page.wait_for_url("**/tiktokstudio/content**", timeout=30_000)
        log("예약 제출 완료 — 콘텐츠 목록으로 이동함")

        # 목록에서 검증
        page.wait_for_timeout(2_000)
        body = page.inner_text("body")
        head = caption[:15]
        if head in body:
            log(f"검증 OK: 목록에 '{head}...' 확인")
        else:
            log("경고: 목록에서 캡션을 못 찾음 — 수동 확인 필요")
        return True
    finally:
        ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--video")
    ap.add_argument("--caption")
    ap.add_argument("--date")
    ap.add_argument("--time", default="19:30")
    ap.add_argument("--headed", action="store_true", help="창 보이게 실행(디버그)")
    args = ap.parse_args()

    with sync_playwright() as p:
        if args.login:
            do_login(p)
            return
        if not (args.video and args.caption and args.date):
            ap.error("--video --caption --date 필요")
        ok = schedule(p, args.video, args.caption, args.date, args.time, args.headed)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
