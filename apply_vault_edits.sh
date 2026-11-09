#!/bin/bash
# 사장님이 옵시디언 노트에서 고친 캡션/해시태그/틱톡제목을 저장소에 반영한다.
#
# 왜 Actions 에서 도는가 (2026-11-09): 원래는 맥의 launchd(com.designgym.obsidian-sync)가
# 로컬 iCloud 볼트를 읽어 반영했다. 그런데 그 에이전트가 launchd 에서 disabled 상태였고,
# 아무도 몰랐다 — edit_history 마지막 기록이 10/27 에서 멈춰 있었다. 노트 머리에는
# "수정하면 자동 반영됩니다(맥 켜져 있을 때)" 라고 적혀 있었지만 사실이 아니었다.
#
# 사장님 옵시디언 Git 플러그인이 10분마다 볼트를 push 하므로, **원격 볼트**를 읽으면
# 맥이 꺼져 있든 옵시디언이 닫혀 있든 같은 내용을 볼 수 있다. 그래서 반영 주체를
# 맥에서 Actions 로 옮긴다. 로컬 볼트는 건드리지 않는다(사장님 옵시디언 전용).
#
# 커밋은 하지 않는다 — 부르는 쪽에서 push_flags.py 로 묶어 올린다.
# 필요: VAULT_TOKEN (GH_PAT — 읽기 전용 토큰으로는 볼트 clone 이 안 된다)

set -u
cd "$(dirname "$0")"

if [ -z "${VAULT_TOKEN:-}" ]; then
  echo "::warning::VAULT_TOKEN 이 없어 볼트 수정 반영을 건너뜁니다"
  exit 0
fi

DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT

NOTES="03_프로젝트/디자인짐_콘텐츠_자동화/인스타_자동화/주간초안"
CEO_NOTES="03_프로젝트/디자인짐_콘텐츠_자동화/사장계정_주간초안"

# 볼트는 400MB가 넘는다. 주간초안 두 폴더만 받아온다(sparse + blob 지연 전송).
if ! git clone --depth 1 --filter=blob:none --sparse --quiet \
     "https://x-access-token:${VAULT_TOKEN}@github.com/koreanolleh/obsidian-vault.git" "$DIR" \
   || ! git -C "$DIR" sparse-checkout set --no-cone "$NOTES" "$CEO_NOTES" >/dev/null 2>&1; then
  echo "::warning::볼트 clone 실패 — 수정 반영을 건너뜁니다"
  exit 0
fi

# 노트에 git 충돌 마커가 남아 있으면 sync 쪽이 스스로 거부한다(조용히 옛 캡션으로
# 발행된 2026-10-27 사고 이후 넣은 안전장치). 여기서는 그 출력을 그대로 보여준다.
export OBSIDIAN_VAULT="$DIR"
export CEO_NOTE_BASE="$DIR/$CEO_NOTES"

echo "— official 계정"
python3 sync_from_obsidian.py || echo "::warning::official 수정 반영 실패(무시하고 계속)"
echo "— 사장 계정"
python3 sync_from_obsidian_ceo.py || echo "::warning::사장계정 수정 반영 실패(무시하고 계속)"
