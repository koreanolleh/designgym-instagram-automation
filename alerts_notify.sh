#!/bin/bash
# 사람이 손대야 풀리는 고장을 맥 알림으로 띄운다.
#
# 왜 필요한가 (2026-11-23): 힉스필드 갱신토큰이 11/17 무렵 죽어 틱톡이 11/19·11/22
# 연속 실패했고, 그 플래그가 안 채워지자 주간 생성까지 멈췄다. 알림은 가고 있었다 —
# GitHub 이슈로. 사장님이 안 보는 곳이라 6일을 흘렀고, 결국 사장님이 먼저 발견했다.
# 자동화가 혼자 못 고치는 종류(토큰 만료·미발행)는 눈에 보이는 곳으로 와야 한다.
#
# 호출: vault_watchdog.sh 맨 앞에서 부른다(그 에이전트는 실제로 매일 돌고 있다).
# 같은 이슈로 하루 한 번만 알린다 — 매번 울리면 금방 무시하게 된다.

set -u
REPO="koreanolleh/designgym-instagram-automation"
STATE="$HOME/Library/Application Support/designgym-automation/alerts_seen.txt"
LOG="$HOME/Library/Logs/designgym-alerts.log"

# launchd 는 /opt/homebrew 를 PATH 에 안 넣는다 — gh 가 거기 있다(2026-11-23 실측).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"디자인짐 자동화\" subtitle \"$2\" sound name \"Basso\"" 2>/dev/null
  log "알림: $2 — $1"
}

command -v gh >/dev/null 2>&1 || { log "gh 없음 — 건너뜀"; exit 0; }
mkdir -p "$(dirname "$STATE")"; touch "$STATE"

# 사람 손이 필요한 이슈만 고른다. 🎨(컨펌 요청)는 고장이 아니므로 제외한다.
#
# 창(window)을 두는 이유: 첫 실행에서 안 닫힌 묵은 이슈 38건이 한꺼번에 울려 소음이 됐다
# (2026-11-23). 그날 전부 닫았고, 이제 '열려 있다 = 아직 손봐야 한다'가 성립한다.
# 그래서 3일 → 14일로 넓혔다. 3일이면 정말 안 고쳐진 고장이 나흘째부터 조용해지는데,
# 그게 바로 힉스필드 토큰 만료를 6일 동안 놓친 그 구멍이다. 해결하면 이슈를 닫을 것 —
# 닫지 않고 쌓으면 창을 아무리 잡아도 알림이 다시 죽는다.
FRESH_DAYS="${ALERT_FRESH_DAYS:-14}"
SINCE=$(date -v-${FRESH_DAYS}d +%Y-%m-%d 2>/dev/null || date -d "-${FRESH_DAYS} days" +%Y-%m-%d)
ROWS=$(gh issue list --repo "$REPO" --state open --limit 30 \
         --json number,title,createdAt \
         -q ".[] | select(.title | test(\"🔑|⚠️\")) | select(.createdAt >= \"$SINCE\") | \"\(.number)\t\(.title)\"" 2>/dev/null)
if [ -z "$ROWS" ]; then
  log "손댈 이슈 없음"
  exit 0
fi

TODAY=$(date +%F)
COUNT=0; NEWEST=""
while IFS=$'\t' read -r NUM TITLE; do
  [ -n "$NUM" ] || continue
  grep -qx "$TODAY $NUM" "$STATE" && continue      # 오늘 이미 알렸다
  echo "$TODAY $NUM" >> "$STATE"
  COUNT=$((COUNT+1)); [ -z "$NEWEST" ] && NEWEST="$TITLE"
done <<< "$ROWS"

if [ "$COUNT" -eq 0 ]; then
  log "새로 알릴 것 없음(오늘 이미 알림)"
  exit 0
fi

if [ "$COUNT" -eq 1 ]; then
  notify "$NEWEST" "조치가 필요합니다"
else
  notify "$NEWEST 외 $((COUNT-1))건" "조치가 필요합니다"
fi

# 상태 파일이 무한히 자라지 않게 최근 200줄만 남긴다.
tail -200 "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
exit 0
