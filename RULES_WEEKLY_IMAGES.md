# 주간 이미지 생성 규칙 (클라우드 루틴이 매주 읽는 파일)

프롬프트를 짧게 유지하기 위해 상세 규칙은 전부 이 파일에 둔다. 루틴은 저장소를 clone한 뒤
이 파일을 읽고 그대로 따른다. 규칙이 바뀌면 프롬프트가 아니라 **이 파일만** 고친다.

## 1. 제품 레퍼런스 (media_input_id)

| 제품 | media_input_id | 특징 |
|---|---|---|
| 요가매트 Active steps | `ac1255f8-cd4f-4464-9618-944a4a36f140` | 연한 블루그레이 + 머스타드옐로 + 진한 틸그린 + 보라 워시 |
| 요가매트 Before sunrise | `40b1f8bd-b58b-41ce-8814-20414b3ad39f` | 네이비슬레이트 + 크림 + 살구핑크 오벌 |
| 요가매트 Warm sunlight | `df98632b-00e9-4b4d-8e4f-59ddbe7be358` | 살구핑크 오벌 + 노란 링 + 슬레이트네이비 블록 |
| 힙업밴드 3개입 | `86ffefa1-7898-4dee-8c72-bd4e683bc3ea` | 네이비틸 바탕 + 흰 야자잎 + 브라운 원 |
| 문 케틀벨 4.5kg 라이트그레이 | `1861e4e2-bd35-4470-9e91-a87e1a7e4ad0` | 링(도넛) 실루엣, 가운데 원형 구멍이 손잡이 |
| 문 케틀벨 4.5kg 라이트민트 | `5fda9835-12a7-49fa-9066-6066e2a0ae55` | 위와 동일 형태, 민트색 |
| 모던 덤벨 1kg 라이트블루 | `bfcfd08b-b8c0-451e-8529-4c7523b3551e` | 알약(캡슐) 실루엣, 소프트 실리콘 |
| 모던 덤벨 1kg 아이보리 | `860d359b-be34-48a7-8a2a-b06df2f1d400` | 위와 동일 형태, 아이보리 |

생성 파라미터: `model=marketing_studio_image`, `aspect_ratio=4:5`, `resolution=2k`,
`medias=[{value: <media_input_id>, role: image}]`.

## 2. 주간 배분

- 매트 2일(서로 다른 색, 연속 이틀 같은 색 금지) + 밴드 1일 + 케틀벨 1일 + 덤벨 1일
- 요일 순서는 매주 섞는다
- **지난주와 같은 제품에 같은 구도를 쓰지 않는다** — `pending_posts.json`의 지난주 `hook` 필드를 읽고 피할 것

## 3. 구도 정책 (사장 확정)

- 모델 얼굴이 나오는 컷은 주 5일 중 **최대 1일**. 나머지는 (a) 제품+공간 스타일링(사람 없음) 또는 (b) 얼굴 없는 사용 클로즈업(손/하체만, face completely OUT OF FRAME)
- **얼굴을 머리카락으로 가리지 말 것** — 귀신처럼 보인다는 지적(2026-08-03). 아기자세(balasana)·뒷모습·측면·엎드린 자세를 쓰고 머리는 낮은 번(low bun)으로 깔끔하게
- 같은 날 2장 이상이면 인물·의상·헤어까지 동일해야 한다. 첫 장의 job_id를 두 번째 요청의 medias에 넣고 `The SAME woman wearing the EXACT SAME OUTFIT as in the second reference image` + 구체적 의상 묘사를 명시
- 구도는 매주 돌려쓴다: 탑다운 플랫레이 / 로우앵글 / 선반 위 정물 / 창가 반쯤 말린 연출 / 벤치 옆 / 뒷모습 요가 등

## 4. 품질 규칙 (프롬프트에 반드시 문장으로 넣을 것)

1. **매트**: `LONG full-size rectangular yoga mat, roughly 3:1 length-to-width (180x61cm), printed artwork runs ALONG THE LENGTH, do NOT render as a small square rug`
2. **로고** — 가장 중요. 절대 "흐리게/소프트포커스로" 라고 쓰지 말 것(뭉개진 얼룩이 생긴다). 둘 중 하나만:
   - **(A) 노출** (제품이 주인공인 컷 — 이쪽을 우선): `the brand wordmark reads exactly "Design:Gym" - spelled D-e-s-i-g-n colon G-y-m, capital D and capital G, clean thin modern sans-serif, small, subtly embossed, crisp and perfectly legible, correctly spelled. Do NOT blur, smudge, warp or distort the lettering, do NOT invent any other words.`
   - **(B) 숨김** (사람이 제품을 잡거나 올라탄 컷): 프레임 밖으로 자르거나 신체로 완전히 가리고 `there must be NO text, NO lettering, NO logo and NO blurred smudge anywhere on the product surface`
3. **제품 형태**는 레퍼런스와 완전 동일 (케틀벨=링 실루엣, 덤벨=알약 실루엣)
4. **사람 컷**: 손가락/팔다리 개수 명시(`ONE hand five fingers`, `TWO legs` 등) + `natural realistic human proportions`
5. **밴드**는 허벅지(무릎 위)에 착용하고 **맨발**. 발목 착용·양말 금지. 텐션 차이를 색으로 표현 금지
6. **파스텔 색상은 말로도 명시**:
   - 아이보리 = `warm off-white IVORY, almost white, NOT beige, NOT tan, NOT cream-yellow`
   - 라이트블루 = `barely-blue cool white, extremely subtle pale blue tint`
   - 민트 = `soft pale MINT green, clearly visible gentle mint tint, not washed out to white`
   - 라이트그레이 = `soft light warm grey, gently desaturated, NOT white, NOT charcoal`
7. 우리 제품이 아닌 **요가매트·러그·코르크매트를 소품으로 넣지 말 것** (브랜드 혼동)
8. **NSFW 회피**: 서서 하는 전굴(uttanasana)처럼 엉덩이가 강조되는 각도는 반려된다. 앉거나 무릎 꿇거나 옆으로 누운 자세를 쓸 것

## 5. 캡션 / 해시태그 / 틱톡제목

- 요일당 캡션 1개: 한국어 구어체 3~6줄, 이모지 1개 내외
- 해시태그 5~8개, `#디자인짐` 포함
- **tiktok_title**: 틱톡 사진 게시물은 앱에서 이 문구만 보인다. 완결된 한 문장 + 핵심 해시태그 3~5개, 합쳐 **90자 이내**, 문장을 중간에서 자르지 말 것
- 제품별 톤:
  - 매트 = 인테리어 / 스웨이드 그립 반전정보
  - 밴드 = 흘러내림 반전정보(실리콘 라인)
  - 케틀벨 = 치울 필요 없는 오브제
  - 덤벨 = 1kg 부담 없음 / 침대 옆·선반 루틴
  - 금요일 = 주말 예열 + "나를 디자인하다, Design:Gym"
- 금지: 부정 프레임 / 클릭베이트 / 효과 단정
- `edit_history.json`이 있으면 사장의 수정 패턴(문장 길이, 이모지, 어미, 자주 지우는 표현)을 읽어 기본 톤보다 **우선** 적용한다
