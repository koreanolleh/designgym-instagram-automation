"""지난 주차 노트에서 깨질 이미지 임베드 줄을 걷어낸다.

주간초안 PNG 103장(307MB)을 볼트에서 들어내면 `![[tuesday_1.png]]` 임베드가 전부
깨진다. 지난 주차는 이미지 URL 을 보관해두지 않아 URL 임베드로 되살릴 수 없으므로,
그 줄만 지우고 안내 한 줄을 남긴다. 이번 주 노트는 make_weekly_note 가 URL 임베드로
다시 찍으므로 여기서 손대지 않는다(이미 `![[...]]` 가 없다).

사용: OBSIDIAN_VAULT=/tmp/vault DIR=... python3 strip_vault_images.py
"""
import glob
import os
import re

VAULT = os.environ.get("OBSIDIAN_VAULT", "/tmp/vault")
DIR = os.environ.get("DIR", "03_프로젝트/디자인짐_콘텐츠_자동화/인스타_자동화/주간초안")
BANNER = ("> 🖼 이 주차의 이미지는 볼트 용량 문제로 제거됐습니다 (2026-10-26). "
          "원본은 자동화 저장소 `images/` 에 남아 있습니다.")

EMBED = re.compile(r"^!\[\[[^\]]+\.(?:png|jpg|jpeg)\]\]\s*$", re.I | re.M)


def main():
    base = os.path.join(VAULT, DIR)
    if not os.path.isdir(base):
        print(f"주간초안 폴더 없음: {base}")
        return
    touched = 0
    for note in sorted(glob.glob(os.path.join(base, "*", "*.md"))):
        with open(note, encoding="utf-8") as f:
            s = f.read()
        if not EMBED.search(s):
            continue
        s = EMBED.sub("", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        if BANNER not in s:
            lines = s.split("\n")
            for i, ln in enumerate(lines):
                if ln.startswith("# "):
                    lines.insert(i + 1, "\n" + BANNER)
                    break
            s = "\n".join(lines)
        with open(note, "w", encoding="utf-8") as f:
            f.write(s)
        touched += 1
        print("정리:", os.path.basename(os.path.dirname(note)))
    print(f"노트 {touched}개 정리 완료")


if __name__ == "__main__":
    main()
