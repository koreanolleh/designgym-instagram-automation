"""생성된 매트 사진에 실제 Design:Gym 로고를 원근에 맞춰 합성한다.

AI 생성 모델은 이 브랜드의 추상 마크(덤벨 픽토그램)를 제대로 못 그린다 — 계속 뭉개진
덩어리나 엉뚱한 바벨이 나온다(2026-08-10). 그래서 매트는 로고 없이 깨끗하게 생성한 뒤
진짜 로고 파일을 여기서 얹는다.

사용:
  python3 stamp_logo.py --photo out.png --logo logo_white.png \
      --quad "x1,y1 x2,y2 x3,y3 x4,y4" \        # 매트 네 모서리 (원거리좌 원거리우 근거리우 근거리좌)
      --u 0.85 --v 0.5 --width 0.52 --opacity 0.92 --out final.png

  --u        매트 길이 방향 위치 (0=먼 끝, 1=가까운 끝)
  --v        매트 폭 방향 위치 (0=왼쪽 가장자리, 1=오른쪽 가장자리)
  --width    로고 가로폭을 매트 폭 대비 비율로
"""
import argparse

import numpy as np
from PIL import Image, ImageFilter

MAT_W = 1000  # 매트 평면 좌표계의 폭. 길이는 --plane-h 로 준다(quad가 매트 전체면 3000)


def parse_quad(s: str):
    pts = []
    for token in s.split():
        x, y = token.split(",")
        pts.append((float(x), float(y)))
    if len(pts) != 4:
        raise ValueError("quad는 점 4개여야 합니다")
    return pts


def perspective_coeffs(src, dst):
    """PIL PERSPECTIVE용 계수. 출력(dst) 좌표 → 입력(src) 좌표 매핑."""
    matrix = []
    for (sx, sy), (dx, dy) in zip(src, dst):
        matrix.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        matrix.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
    A = np.array(matrix, dtype=np.float64)
    B = np.array(src, dtype=np.float64).reshape(8)
    return np.linalg.solve(A, B)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True)
    ap.add_argument("--logo", required=True)
    ap.add_argument("--quad", help="매트 네 모서리: 먼좌 먼우 근우 근좌 (--u/--v/--width 와 함께)")
    ap.add_argument("--dstquad", help="로고가 놓일 네 꼭짓점을 직접 지정: 좌상 우상 우하 좌하. "
                                      "매트 아랫변과 평행하게 잡으면 면에 정확히 붙는다")
    ap.add_argument("--u", type=float, default=0.85)
    ap.add_argument("--v", type=float, default=0.5)
    ap.add_argument("--width", type=float, default=0.5, help="매트 폭 대비 로고 폭")
    ap.add_argument("--opacity", type=float, default=0.92)
    ap.add_argument("--blur", type=float, default=0.8)
    ap.add_argument("--plane-h", type=int, default=3000,
                    help="매트 평면 좌표계의 길이. quad가 매트 전체면 3000, 일부만이면 그 비율에 맞춰 줄인다")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    photo = Image.open(args.photo).convert("RGBA")
    logo = Image.open(args.logo).convert("RGBA")

    if args.dstquad:
        # 로고 이미지 자체를 네 꼭짓점으로 직접 매핑 (가장 정확한 제어)
        dst = parse_quad(args.dstquad)
        lw, lh = logo.size
        src = [(0, 0), (lw, 0), (lw, lh), (0, lh)]
        coeffs = perspective_coeffs(src, dst)
        warped = logo.transform(photo.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        if args.blur > 0:
            warped = warped.filter(ImageFilter.GaussianBlur(args.blur))
        if args.opacity < 1.0:
            ch = warped.getchannel("A").point(lambda q: int(q * args.opacity))
            warped.putalpha(ch)
        Image.alpha_composite(photo, warped).convert("RGB").save(args.out)
        print(f"합성 완료(직접지정) → {args.out}")
        return

    if not args.quad:
        raise SystemExit("--quad 또는 --dstquad 중 하나가 필요합니다")

    # 1) 매트 평면 캔버스에 로고를 정위치로 놓는다
    mat_h = args.plane_h
    plane = Image.new("RGBA", (MAT_W, mat_h), (0, 0, 0, 0))
    target_w = int(MAT_W * args.width)
    target_h = max(1, int(logo.height * target_w / logo.width))
    lg = logo.resize((target_w, target_h), Image.LANCZOS)
    cx, cy = int(MAT_W * args.v), int(mat_h * args.u)
    plane.alpha_composite(lg, (cx - target_w // 2, cy - target_h // 2))

    # 2) 매트 평면 → 사진 좌표로 원근 변환
    far_l, far_r, near_r, near_l = parse_quad(args.quad)
    src = [(0, 0), (MAT_W, 0), (MAT_W, mat_h), (0, mat_h)]
    dst = [far_l, far_r, near_r, near_l]
    coeffs = perspective_coeffs(src, dst)
    warped = plane.transform(photo.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)

    # 3) 인쇄물처럼 보이도록 아주 살짝 흐리고 투명도 적용
    if args.blur > 0:
        warped = warped.filter(ImageFilter.GaussianBlur(args.blur))
    if args.opacity < 1.0:
        a = warped.getchannel("A").point(lambda p: int(p * args.opacity))
        warped.putalpha(a)

    out = Image.alpha_composite(photo, warped)
    out.convert("RGB").save(args.out)
    print(f"합성 완료 → {args.out} (로고 폭 {target_w}px, u={args.u}, v={args.v})")


if __name__ == "__main__":
    main()
