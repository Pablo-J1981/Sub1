"""AI 생성 초록 배경 액션 시트를 펫 에셋 PNG로 변환한다.

입력:  assets/source/<animal>_sheet.png  (격자 시트, 초록(#00FF00) 배경)
출력:  assets/pets/<animal>/stage1/<동작>.png  (프레임 크기 FRAME x FRAME, 투명 배경)
       assets/pets/<animal>/tomb.png

사용법: python tools/make_pet_sprites.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "source"
PETS_DIR = ROOT / "assets" / "pets"

FRAME = 64          # 출력 프레임 한 변(픽셀). 셀 256px -> 64px 로 정확히 1/4 축소
ALPHA_CUTOFF = 128  # 이 값 이상이면 불투명, 미만이면 투명 (도트 느낌 유지를 위해 이진화)

# 시트의 칸 순서(왼쪽->오른쪽, 위->아래)와 동작 이름의 대응
SHEETS = {
    "dog": {
        "file": "dog_sheet.png",
        "cols": 4,
        "rows": 4,
        "cells": {
            "idle": 0, "walk": 1, "sit": 2, "sleep": 3,
            "fall": 4, "land": 5, "scared": 6, "jump": 7,
            "eat": 8, "held": 9, "happy": 10, "sad": 11,
            "hungry": 12, "sick": 13, "die": 14,
        },
        "tomb_cell": 15,
    },
    "shark": {
        "file": "shark_sheet.png",
        "cols": 4,
        "rows": 3,
        "cells": {
            "idle": 0, "swim": 1, "startled": 2, "eat": 3,
            "held": 4, "happy": 5, "sad": 6, "hungry": 7,
            "sick": 8, "die": 9,
        },
        "tomb_cell": 10,
    },
}


def is_green_screen(r: int, g: int, b: int) -> bool:
    """순수에 가까운 초록 배경 픽셀인지 판단한다.

    연두색 같은 몸 색이 잘못 지워지지 않도록 기준을 엄격하게 잡는다.
    """
    return g >= 200 and r <= 120 and b <= 120 and g - max(r, b) >= 90


def key_out_green(img: Image.Image) -> Image.Image:
    """초록 배경 픽셀을 완전 투명으로 바꾼 RGBA 이미지를 반환한다."""
    rgba = img.convert("RGBA")
    px = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            r, g, b, _ = px[x, y]
            if is_green_screen(r, g, b):
                px[x, y] = (0, 0, 0, 0)
    return rgba


def cell_box(index: int, cols: int, rows: int, width: int, height: int) -> tuple[int, int, int, int]:
    """칸 인덱스의 영역 (좌, 상, 우, 하). 칸 경계는 반올림해서 누적 오차를 막는다."""
    col = index % cols
    row = index // cols
    x0 = round(col * width / cols)
    x1 = round((col + 1) * width / cols)
    y0 = round(row * height / rows)
    y1 = round((row + 1) * height / rows)
    return x0, y0, x1, y1


def make_frame(sheet: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """칸 하나를 정사각형 중앙 영역으로 잘라 FRAME 크기로 축소하고 알파를 이진화한다.

    모든 칸을 같은 방식으로 자르므로 캐릭터의 기준선과 크기가 칸끼리 일정하다.
    """
    x0, y0, x1, y1 = box
    cell_w, cell_h = x1 - x0, y1 - y0
    side = min(cell_w, cell_h)
    sx = x0 + (cell_w - side) // 2
    sy = y0 + (cell_h - side) // 2
    square = sheet.crop((sx, sy, sx + side, sy + side))

    small = square.resize((FRAME, FRAME), Image.Resampling.BOX)
    px = small.load()
    for y in range(FRAME):
        for x in range(FRAME):
            r, g, b, a = px[x, y]
            if a >= ALPHA_CUTOFF:
                px[x, y] = (r, g, b, 255)
            else:
                px[x, y] = (0, 0, 0, 0)
    return small


def build_pet(animal: str, spec: dict) -> list[Path]:
    source = SOURCE_DIR / spec["file"]
    if not source.exists():
        raise FileNotFoundError(f"원본 시트가 없습니다: {source}")

    sheet = key_out_green(Image.open(source))
    width, height = sheet.size
    cols, rows = spec["cols"], spec["rows"]

    stage_dir = PETS_DIR / animal / "stage1"
    stage_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for action, index in spec["cells"].items():
        frame = make_frame(sheet, cell_box(index, cols, rows, width, height))
        out = stage_dir / f"{action}.png"
        frame.save(out)
        written.append(out)

    tomb = make_frame(sheet, cell_box(spec["tomb_cell"], cols, rows, width, height))
    tomb_out = PETS_DIR / animal / "tomb.png"
    tomb.save(tomb_out)
    written.append(tomb_out)
    return written


def main() -> None:
    for animal, spec in SHEETS.items():
        files = build_pet(animal, spec)
        print(f"{animal}: {len(files)} files")


if __name__ == "__main__":
    main()
