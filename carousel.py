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
        a = 0 if r < 0.42 else int(round(((r - 0.42) / 0.58) ** 1.5 * 112))
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
    draw.text(((W - text_w(draw, WATERMARK, f)) // 2, H - INSET - BAR_H - 60),
              WATERMARK, font=f, fill=WHITE + (190,))


def draw_cover(draw, slide):
    lines = slide["lines"]
    f = font(104)
    y = 843
    for line in lines:
        draw.text((112, y), line, font=f, fill=WHITE)
        y += 108
    draw.rectangle([112, y + 26, 112 + 116, y + 31], fill=AMBER)


def draw_content(draw, slide):
    # 좌상단 앰버 필 배지
    if slide.get("badge"):
        fb = font(34)
        tw = text_w(draw, slide["badge"], fb)
        pad_x, pad_y = 28, 16
        x0, y0 = 108, 150
        x1, y1 = x0 + tw + pad_x * 2, y0 + 34 + pad_y * 2
        draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=AMBER)
        draw.text((x0 + pad_x, y0 + pad_y - 4), slide["badge"], font=fb, fill=(30, 26, 18))

    fm = font(52)
    main = slide.get("main", "")
    draw.text(((W - text_w(draw, main, fm)) // 2, 600), main, font=fm, fill=WHITE)

    draw.rectangle([W // 2 - 58, 690, W // 2 + 58, 694], fill=AMBER)

    fs = font(44)
    sub = slide.get("sub", "")
    draw.text(((W - text_w(draw, sub, fs)) // 2, 748), sub, font=fs, fill=WHITE)


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
