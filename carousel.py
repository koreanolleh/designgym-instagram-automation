"""사장 계정(designgym.ceo) 캐러셀 슬라이드를 텍스트 조판으로 렌더한다.

AI 이미지 생성 없이 Pexels 배경 + 듀오톤 + Pretendard 조판만 쓴다(크레딧 0, 결정적 실행).
톤은 2026-08-19 사장 확정안 "B 중성그레이" 기준. 수치는 8/13 샘플에서 실측한 값.

사용:
    python3 carousel.py spec.json 출력폴더

spec.json 예시:
{
  "tone": "B",
  "bg_dir": "/Users/.../디자인짐_사장계정_배경/원본",
  "slides": [
    {"type": "cover",   "bg": "001_요가.jpg", "lines": ["요가 처음 할 때", "흔한 실수 5가지"]},
    {"type": "content", "bg": "002_요가.jpg", "badge": "호흡",
     "main": "당기는 느낌까지만", "sub": "찌르는 느낌이 오면 즉시 나오기"},
    {"type": "closing", "bg": "003_요가.jpg", "headline": "매트 위 시간이 편해지면 좋겠어요",
     "sub": "운동하는 사람의 기록"}
  ]
}
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350          # 4:5 (official 계정과 동일 규격)
INSET = 54                 # 프레임 여백 — 샘플 실측
AMBER = (218, 164, 66)     # 샘플 하단 바에서 추출
BAR_H = 23                 # 하단 앰버 바 두께
WHITE = (255, 255, 255)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "brand", "Pretendard-SemiBold.ttf")

# 듀오톤 3안. B가 확정안이고 나머지는 되돌릴 때를 위해 남겨둔다.
TONES = {
    "A": {"shadow": (34, 30, 24), "light": (214, 208, 198), "darken": 0.18},
    "B": {"shadow": (22, 22, 24), "light": (210, 210, 212), "darken": 0.22},
    "C": {"shadow": (14, 15, 19), "light": (176, 181, 190), "darken": 0.44},
}

HANDLE = "@designgym.ceo"
WATERMARK = "Design:Gym"
SAVE_HINT = "다시 꺼내볼 수 있게 저장해두세요"


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def crop_45(im):
    """중앙 기준 4:5 크롭 후 1080x1350."""
    w, h = im.size
    target = W / H
    if w / h > target:
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im.resize((W, H), Image.LANCZOS)


TARGET_MEAN = 104  # 2026-08-19 사장 피드백 "너무 어둡다" 반영해 상향(기존 78)


def duotone(im, tone, target_mean=TARGET_MEAN):
    """흑백 → shadow~light 선형 매핑 → darken → 밝기 정규화.

    사진마다 노출이 제각각이라 정규화가 없으면 그리드에서 톤이 튄다.
    """
    t = TONES[tone]
    gray = im.convert("L")
    keep = 1.0 - t["darken"]
    lut = []
    for ch in range(3):
        s, l = t["shadow"][ch], t["light"][ch]
        lut += [min(255, max(0, int(round((s + (l - s) * (v / 255.0)) * keep)))) for v in range(256)]
    out = gray.convert("RGB").point(lut)

    from PIL import ImageStat
    cur = sum(ImageStat.Stat(out).mean) / 3.0
    if cur > 1:
        k = max(0.30, min(1.25, target_mean / cur))
        out = out.point([min(255, int(round(v * k))) for v in range(256)] * 3)
    return out


def scrim(size=(W, H)):
    """하단으로 갈수록 어두워지는 그라데이션 — 밝은 사진에서도 흰 글씨가 읽히게."""
    w, h = size
    grad = Image.new("L", (1, h))
    for y in range(h):
        r = y / (h - 1)
        # 아래쪽: 표지·본문이 앉는 자리라 진하게
        a = 0 if r < 0.42 else int(round(((r - 0.42) / 0.58) ** 1.5 * 112))
        # 위쪽: top 레이아웃과 배지가 밝은 사진 위에 놓일 때를 대비해 옅게
        if r < 0.38:
            a = max(a, int(round(((0.38 - r) / 0.38) ** 1.3 * 96)))
        grad.putpixel((0, y), a)
    mask = grad.resize((w, h))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    layer.putalpha(mask)
    return layer


def text_w(draw, s, f):
    bb = draw.textbbox((0, 0), s, font=f)
    return bb[2] - bb[0]


def draw_chrome(draw):
    """모든 슬라이드 공통: 프레임 선 + 하단 앰버 바 + 워터마크."""
    draw.rectangle([INSET, INSET, W - INSET, H - INSET], outline=AMBER + (150,), width=2)
    draw.rectangle([INSET, H - INSET - BAR_H, W - INSET, H - INSET], fill=AMBER)
    f = font(30)
    draw.text(((W - text_w(draw, WATERMARK, f)) // 2, 1215),
              WATERMARK, font=f, fill=WHITE + (235,))


def draw_cover(draw, slide):
    # 8/13 샘플 실측: 글자높이 75px(=폰트 85), 줄 간격 109px, 첫 줄 글자 top 842
    lines = slide["lines"]
    f = font(85)
    y = 829
    for line in lines:
        draw.text((112, y), line, font=f, fill=WHITE)
        y += 109
    draw.rectangle([112, y + 24, 112 + 116, y + 29], fill=AMBER)


BODY_X = 140              # 본문 문단 좌측 기준선
BODY_MAX_W = W - BODY_X * 2
BODY_SIZE = 43
BODY_LEADING = 68
BODY_MAX_LINES = 5


def wrap(draw, text, f, max_w):
    """어절 단위로 접고, 한 어절이 너무 길면 글자 단위로 쪼갠다."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = f"{cur} {word}".strip()
        if text_w(draw, trial, f) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if text_w(draw, cur + ch, f) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


def draw_badge(draw, text, y0=103):
    fb = font(34)
    tw = text_w(draw, text, fb)
    pad_x, pad_y = 28, 16
    x0 = 108
    x1, y1 = x0 + tw + pad_x * 2, y0 + 34 + pad_y * 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=AMBER)
    draw.text((x0 + pad_x, y0 + pad_y - 4), text, font=fb, fill=(30, 26, 18))


def draw_block(draw, lines, f, y, align, leading):
    """여러 줄을 정렬 방식에 맞춰 그린다."""
    for line in lines:
        x = BODY_X if align == "left" else (W - text_w(draw, line, f)) // 2
        draw.text((x, y), line, font=f, fill=WHITE)
        y += leading
    return y


def draw_content(draw, slide):
    """레이아웃 5종. 슬라이드마다 분량·배치를 바꿔 단조로움을 없앤다.

    classic : 소제목 가운데 + 구분선 + 본문 (기본, 중간 분량)
    bottom  : 아래쪽에 소제목·본문을 붙인 편집형 (긴 설명용)
    top     : 위쪽에 붙여 사진 아래를 비우는 배치
    big     : 문장 하나만 크게 (짧은 핵심용, 본문 없음)
    stat    : 숫자 하나를 크게 + 짧은 설명
    """
    layout = slide.get("layout", "classic")
    badge = slide.get("badge")
    main = slide.get("main", "")
    body = slide.get("body") or slide.get("sub", "")

    if layout == "big":
        if badge:
            draw_badge(draw, badge)
        f = font(66)
        lines = wrap(draw, main, f, W - 150 * 2)
        h = len(lines) * 84
        draw_block(draw, lines, f, (H - h) // 2 + 40, "center", 84)
        return

    if layout == "stat":
        if badge:
            draw_badge(draw, badge)
        fn = font(180)
        num = slide.get("number", main)
        draw.text(((W - text_w(draw, num, fn)) // 2, 520), num, font=fn, fill=WHITE)
        draw.rectangle([W // 2 - 58, 790, W // 2 + 58, 794], fill=AMBER)
        fb2 = font(44)
        lines = wrap(draw, body, fb2, W - 150 * 2)
        draw_block(draw, lines, fb2, 850, "center", 62)
        return

    fb2 = font(BODY_SIZE)
    lines = wrap(draw, body, fb2, BODY_MAX_W) if body else []
    if len(lines) > BODY_MAX_LINES:
        raise ValueError(f"본문이 {BODY_MAX_LINES}줄을 넘습니다({len(lines)}줄): {body[:30]}…")

    if layout == "bottom":
        if badge:
            draw_badge(draw, badge)
        fm = font(56)
        body_h = len(lines) * BODY_LEADING
        y_main = 1120 - body_h - 110
        draw.text((BODY_X, y_main), main, font=fm, fill=WHITE)
        draw.rectangle([BODY_X, y_main + 88, BODY_X + 116, y_main + 93], fill=AMBER)
        draw_block(draw, lines, fb2, y_main + 130, "left", BODY_LEADING)
        return

    if layout == "top":
        if badge:
            draw_badge(draw, badge)
        fm = font(56)
        draw.text((BODY_X, 250), main, font=fm, fill=WHITE)
        draw.rectangle([BODY_X, 338, BODY_X + 116, 343], fill=AMBER)
        draw_block(draw, lines, fb2, 386, "left", BODY_LEADING)
        return

    # classic
    if badge:
        draw_badge(draw, badge)
    fm = font(50)
    draw.text(((W - text_w(draw, main, fm)) // 2, 470), main, font=fm, fill=WHITE)
    draw.rectangle([W // 2 - 58, 596, W // 2 + 58, 600], fill=AMBER)
    draw_block(draw, lines, fb2, 660, "left", BODY_LEADING)


def draw_closing(draw, slide):
    fh = font(46)
    head = slide.get("headline", "")
    draw.text(((W - text_w(draw, head, fh)) // 2, 560), head, font=fh, fill=WHITE)

    # 흰 라운드 팔로우 카드
    fhd = font(36)
    hw = text_w(draw, HANDLE, fhd)
    card_w, card_h = 120 + hw + 190, 108
    cx = (W - card_w) // 2
    cy = 680
    draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=card_h // 2, fill=WHITE)

    # 아바타
    ax, ay, ar = cx + 22, cy + 18, 36
    draw.ellipse([ax, ay, ax + ar * 2, ay + ar * 2], fill=AMBER)
    fa = font(30)
    draw.text((ax + ar - text_w(draw, "DG", fa) // 2, ay + ar - 20), "DG", font=fa, fill=WHITE)

    draw.text((ax + ar * 2 + 22, cy + 34), HANDLE, font=fhd, fill=(28, 28, 30))

    # 팔로우 버튼
    fbn = font(30)
    bt = "팔로우"
    btw = text_w(draw, bt, fbn)
    bx1 = cx + card_w - 26
    bx0 = bx1 - (btw + 52)
    draw.rounded_rectangle([bx0, cy + 26, bx1, cy + card_h - 26], radius=(card_h - 52) // 2, fill=AMBER)
    draw.text((bx0 + 26, cy + 30), bt, font=fbn, fill=(30, 26, 18))

    fs = font(38)
    sub = slide.get("sub", "")
    draw.text(((W - text_w(draw, sub, fs)) // 2, cy + card_h + 46), sub, font=fs, fill=WHITE)

    fhint = font(30)
    draw.text(((W - text_w(draw, SAVE_HINT, fhint)) // 2, H - INSET - BAR_H - 120),
              SAVE_HINT, font=fhint, fill=WHITE + (210,))


RENDERERS = {"cover": draw_cover, "content": draw_content, "closing": draw_closing}


def render(spec, outdir):
    tone = spec.get("tone", "B")
    bg_dir = spec["bg_dir"]
    os.makedirs(outdir, exist_ok=True)
    paths = []

    for i, slide in enumerate(spec["slides"], start=1):
        bg = duotone(crop_45(Image.open(os.path.join(bg_dir, slide["bg"])).convert("RGB")), tone)
        bg = Image.alpha_composite(bg.convert("RGBA"), scrim())
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw_chrome(draw)
        RENDERERS[slide["type"]](draw, slide)
        out = Image.alpha_composite(bg.convert("RGBA"), layer).convert("RGB")

        path = os.path.join(outdir, f"{i:02d}_{slide['type']}.jpg")
        out.save(path, quality=92)
        paths.append(path)
        print(f"렌더: {path}")

    return paths


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python3 carousel.py spec.json 출력폴더")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        render(json.load(f), sys.argv[2])
