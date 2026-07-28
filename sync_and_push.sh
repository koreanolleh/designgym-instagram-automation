#!/bin/zsh
# 옵시디언 주간 노트 변경 감지 시 실행: 캡션/해시태그를 pending_posts.json에 반영하고 GitHub에 push한다.
# launchd(com.designgym.obsidian-sync)가 노트 폴더 WatchPaths로 호출한다.
cd "$(dirname "$0")"

LOG=sync.log
echo "--- $(date '+%F %T') sync 시작" >> "$LOG"

# 발행 루틴의 posted 커밋을 먼저 받아와야 충돌이 없다
git -c rebase.autoStash=true pull --rebase --quiet origin main >> "$LOG" 2>&1

OUT=$(./venv/bin/python sync_from_obsidian.py 2>> "$LOG")
echo "$OUT" >> "$LOG"

if [[ "$OUT" == *"업데이트 완료"* ]]; then
  git add pending_posts.json edit_history.json 2>> "$LOG"
  git commit -q -m "✏️ 옵시디언 수정 반영 $(date '+%m/%d %H:%M')" >> "$LOG" 2>&1
  git push --quiet origin main >> "$LOG" 2>&1 && echo "push 완료" >> "$LOG" || echo "push 실패" >> "$LOG"
fi
