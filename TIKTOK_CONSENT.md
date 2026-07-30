# 틱톡 무인 발행 지속 동의 기록 (Standing Consent)

- **동의 일시**: 2026-07-30, Claude 클라우드 세션에서 계정 소유자가 실시간 대화로 직접 동의
- **적용 범위**: 이 저장소 `pending_posts.json`에 계정 소유자가 매주 직접 큐레이션해 넣는 디자인짐(Design:Gym) 게시물의 TikTok 자동 발행 (연결 계정: Higgs connector `52a33f1c-0c4c-4040-b2e7-999ba7564dca`)

## 계정 소유자가 확정한 표준 발행 설정

| 항목 | 값 |
|---|---|
| 공개 범위 | PUBLIC_TO_EVERYONE (사용자가 직접 선택) |
| 댓글 | 허용 |
| AI 생성 콘텐츠 표시 (is_aigc) | **true — 항상 켬.** 이미지가 AI 생성물이므로 라벨 유지가 필수이며, 끄지 않는다 |
| 상업 콘텐츠 라벨 | 표시 안 함 (enabled false) — 'your_brand' 라벨이 원칙에 더 부합할 수 있다는 안내를 받고도 미표시를 선택함 |
| 음악 | Chill Beats 트렌딩 1위 트랙 자동 첨부 (조회 실패 시 음악 없이 진행) |

## 동의한 선언문 (원문 제시 후 동의)

> "By posting, you agree to TikTok's Music Usage Confirmation
> (https://www.tiktok.com/legal/page/global/music-usage-confirmation/en)."

## 미리보기·콘텐츠 검토에 대한 확인

`pending_posts.json`의 이미지·캡션·tiktok_title은 계정 소유자가 정한 브랜드 기준(구도 정책·톤·제품 로테이션)에 따라 매주 월요일 루틴이 생성하고, 계정 소유자가 옵시디언 주간초안 노트에서 발행 전에 열람·수정할 수 있도록 제공된다. 계정 소유자는 **게시물마다 개별 승인을 받지 않고 발행하는 것에 동의**했으며, **이 파일에 포함된 게시물은 계정 소유자가 사전 검토 기회를 가진 콘텐츠로 간주한다**는 데 동의함. 따라서 무인 실행에서 `tiktok_publish`의 required_confirmations(user_confirmed, preview_confirmed, music_usage_confirmed, processing_notice_acknowledged, privacy_level_selected_by_user, interaction_settings_selected_by_user, commercial_content_disclosure_selected_by_user)를 true로 전달하는 것은 위에 기록된 사용자의 실제 선택을 전달하는 것이다.

## 유효 조건

- 이 동의는 위 표준 설정 그대로의 발행에만 적용된다. 설정을 바꾸려면 계정 소유자가 이 파일을 직접 수정하거나 실시간 세션에서 다시 동의해야 한다.
- 계정 소유자는 이 파일을 삭제하거나 수정하는 것으로 언제든 동의를 철회·변경할 수 있다.
