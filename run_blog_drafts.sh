#!/bin/zsh
# 이번 주 블로그 3편을 네이버 저장함에 초안으로 넣어둔다.
# ⚠️ 발행은 하지 않는다 — 사장님이 직접 누르는 것으로 남긴다.
# launchd(com.designgym.blogdrafts)가 화요일 오전에 호출한다.
#
# 수동 실행: ./run_blog_drafts.sh [주차날짜]
# 점검만: ./run_blog_drafts.sh --dry  (에디터는 건드리지 않고 준비 상태만 확인)

cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

DRY=0
[[ "$1" == "--dry" ]] && { DRY=1; shift; }

LOG=blog_drafts.log
say() { echo "$@" | tee -a "$LOG"; }
notify() { osascript -e "display notification \"$1\" with title \"디자인짐 블로그 초안\"" 2>/dev/null; }

echo "" >> "$LOG"
say "=== $(date '+%F %T') 블로그 초안 시작"

# 이번 주 월요일 (인자로 주면 그걸 쓴다)
WEEK=${1:-$(python3 -c "
from datetime import date, timedelta
t = date.today()
print(t - timedelta(days=t.weekday()))
")}
SPEC="weeks/${WEEK}.json"

# 월요일 Actions가 만든 원고·이미지를 받아온다
git -c rebase.autoStash=true pull --rebase --quiet origin main >> "$LOG" 2>&1

if [[ ! -f "$SPEC" ]]; then
  say "❌ 원고 없음: $SPEC — 월요일 생성이 안 돌았는지 확인 필요"
  notify "이번 주 원고($WEEK)가 없습니다"
  exit 1
fi

# 옵시디언에서 고친 블로그 원고를 먼저 반영한다
./venv/bin/python sync_blog_ceo.py "$SPEC" 2>&1 | tee -a "$LOG"

DATES=$(./venv/bin/python -c "
import json, sys
w = json.load(open('$SPEC'))
print(' '.join(c['date'] for c in w['carousels'] if c.get('blog')))
")

if [[ -z "$DATES" ]]; then
  say "❌ 블로그 원고가 있는 날짜가 없습니다"
  notify "블로그 원고가 비어 있습니다"
  exit 1
fi

if [[ $DRY -eq 1 ]]; then
  say "대상 날짜: ${DATES}"
  command -v node >/dev/null && say "node: $(node -v) ($(command -v node))" || say "❌ node 없음"
  ./venv/bin/python -c "import sys; print('python:', sys.version.split()[0])" | tee -a "$LOG"
  # 로그인 쿠키가 아직 살아 있는지만 확인한다 (글은 쓰지 않는다)
  (cd naver_automation && node check_login.js) 2>&1 | tee -a "$LOG"
  say "=== 점검 완료 (에디터는 건드리지 않음)"
  exit 0
fi

OK=0; FAIL=0
for D in ${=DATES}; do
  say "--- $D"
  OUT=$(cd naver_automation && node write_post.js "../$SPEC" "$D" 2>&1)
  CODE=$?
  echo "$OUT" >> "$LOG"

  if [[ $CODE -eq 2 ]]; then
    say "❌ 로그인 만료 — 나머지도 중단합니다"
    notify "네이버 로그인이 만료됐습니다. login.js 실행 필요"
    exit 2
  fi

  if echo "$OUT" | grep -q "임시저장 완료"; then
    say "  ✅ $(echo "$OUT" | grep '최종 상태')"
    ((OK++))
  else
    say "  ❌ 실패"
    ((FAIL++))
  fi
done

say "=== 완료: 성공 $OK / 실패 $FAIL"
if [[ $FAIL -gt 0 ]]; then
  notify "초안 $OK편 저장, $FAIL편 실패"
else
  notify "초안 $OK편을 저장함에 넣었습니다"
fi
