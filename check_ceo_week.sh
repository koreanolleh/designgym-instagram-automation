#!/bin/zsh
# 사장계정 이번 주 원고가 준비됐는지 확인하고, 없으면 알림을 띄운다.
# 월요일 원고 생성 작업이 조용히 건너뛰어도 화요일 발행 전에 사람이 알 수 있게 하는 안전망.
# launchd(com.designgym.ceoweekcheck)가 월 18:00 / 화 08:00에 호출한다.
#
# 수동: ./check_ceo_week.sh [주차날짜]

cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

LOG=ceo_week_check.log
say() { echo "$@" | tee -a "$LOG"; }
notify() {  # $1=제목 $2=본문
  osascript -e "display notification \"$2\" with title \"$1\" sound name \"Basso\"" 2>/dev/null
}

WEEK=${1:-$(python3 -c "
from datetime import date, timedelta
t = date.today()
print(t - timedelta(days=t.weekday()))
")}

echo "" >> "$LOG"
say "=== $(date '+%F %T') 사장계정 원고 점검 (주차 $WEEK)"

git -c rebase.autoStash=true pull --rebase --quiet origin main >> "$LOG" 2>&1

STATUS=$(./venv/bin/python - "$WEEK" <<'PY'
import json, os, sys
week = sys.argv[1]
spec = f"weeks/{week}.json"
problems = []

if not os.path.exists(spec):
    print(f"MISSING|원고 파일이 없습니다 ({spec})")
    sys.exit(0)

try:
    w = json.load(open(spec, encoding="utf-8"))
except Exception as e:
    print(f"BROKEN|원고 파일을 읽을 수 없습니다 ({e})")
    sys.exit(0)

cars = w.get("carousels", [])
if len(cars) != 3:
    problems.append(f"캐러셀이 {len(cars)}건")
for c in cars:
    if not c.get("blog"):
        problems.append(f"{c.get('date')} 블로그 원고 없음")
    d = os.path.join("images", "ceo", c.get("date", ""))
    n = len([f for f in os.listdir(d) if f.endswith(".jpg")]) if os.path.isdir(d) else 0
    if n != 7:
        problems.append(f"{c.get('date')} 이미지 {n}장")

# 발행 큐가 이번 주를 가리키는지
try:
    q = json.load(open("pending_posts_ceo.json", encoding="utf-8"))
    if q.get("week_of") != week:
        problems.append(f"발행 큐가 {q.get('week_of')} 주차를 보고 있음")
except Exception as e:
    problems.append(f"발행 큐를 읽을 수 없음 ({e})")

print(("INCOMPLETE|" + " / ".join(problems)) if problems else "OK|3건 준비 완료")
PY
)

CODE=${STATUS%%|*}
MSG=${STATUS#*|}
say "$CODE — $MSG"

case "$CODE" in
  OK)
    exit 0 ;;
  MISSING)
    notify "⚠️ 사장계정 원고 없음" "이번 주($WEEK) 원고가 없어요. 월요일 생성이 안 돈 것 같습니다."
    exit 1 ;;
  *)
    notify "⚠️ 사장계정 원고 미완성" "$MSG"
    exit 1 ;;
esac
