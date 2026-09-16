"""발행 요일 한 곳 (2026-09-16부터 화·목·일).

요일이 여러 스크립트에 흩어져 있으면 한 군데만 고치고 나머지를 놓친다.
생성·노트·동기화·수동 저장이 전부 여기를 본다. 발행 스크립트는 요일이 아니라
pending_posts.json의 date를 보므로 손댈 필요가 없다.

바뀔 때 같이 고쳐야 하는 것: .github/workflows/ig_daily.yml, tiktok_daily.yml,
tiktok_watchdog.yml 의 cron 요일(UTC 기준 0=일 … 6=토). 지금은 '2,4,0'.
"""

# (영문 요일, 한글 요일, 월요일로부터의 일수, 그날 올릴 이미지 장수)
SCHEDULE = [
    ("Tuesday", "화요일", 1, 3),
    ("Thursday", "목요일", 3, 2),
    ("Sunday", "일요일", 6, 3),
]

DAYS_EN = [d[0] for d in SCHEDULE]
DAYS_KR = [d[1] for d in SCHEDULE]
OFFSET = {d[0]: d[2] for d in SCHEDULE}          # 월요일 기준 며칠 뒤인지
IMAGE_COUNT = {d[0]: d[3] for d in SCHEDULE}     # 그날 캐러셀 장수
KR = dict(zip(DAYS_EN, DAYS_KR))

# 한 주를 닫는 날 — 브랜드 서명을 붙인다
CLOSER = DAYS_EN[-1]

TOTAL_IMAGES = sum(IMAGE_COUNT.values())
