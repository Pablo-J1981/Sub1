"""AI 생성 초록 배경 시트를 펫 에셋 PNG로 변환한다 (강아지 v2 시트).

입력:  assets/source/dog_v2/*.png  (4x4 격자, 초록(#00FF00) 배경, 칸 하나 = 256px)
출력:  assets/pets/dog/stage1/<동작>.png  (프레임을 가로로 이어 붙인 시트)
       assets/pets/dog/tomb.png
       assets/items/food_bowl.png

처리 순서
1. 초록 배경을 투명으로 바꾼다.
2. 칸을 FRAME 크기로 줄이고 알파를 이진화한다(도트 느낌 유지).
3. 시트마다 같은 이동량으로 발 위치(세로)와 가운데(가로)를 맞춘다.
   기준 칸(ref)의 발 위치 중앙값을 GROUND_Y에 맞추므로, 한 시트 안의 프레임끼리
   발이 튀지 않는다. 공중 동작도 같은 기준을 쓴다.

사용법: python tools/make_pet_sprites.py
"""

from __future__ import annotations

import statistics
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "source" / "dog"
PET_DIR = ROOT / "assets" / "pets" / "dog"
ITEMS_DIR = ROOT / "assets" / "items"

FRAME = 52          # 출력 프레임 한 변(원본 픽셀). 기존 64 대비 약 40% 크기 (pet_scale 2 와 곱해 104px)
GROUND_Y = 46       # 프레임 안에서 발이 닿는 선(행 번호 기준 바로 아래). pet.json 의 ground_y 와 같아야 한다
ALPHA_CUTOFF = 128  # 이 값 이상이면 불투명, 미만이면 투명
FOOD_WIDTH = 32     # 먹이 그릇 가로(원본 픽셀)

# 시트별 칸 배치. cells: 동작 -> 칸 번호 목록(왼쪽->오른쪽, 위->아래), ref: 정렬 기준 칸
DOG_SHEETS = [
    {
        "file": "dog_walk_idle.png",
        "cols": 4, "rows": 4,
        "cells": {
            "walk": [0, 1, 2, 3, 4, 5, 6, 7],
            "idle": [8, 9, 10, 11],
            "sit": [12, 13],
            "sleep": [14, 15],
        },
        "ref": [8, 9, 10, 11],
    },
    {
        "file": "dog_edge_fall.png",
        "cols": 4, "rows": 4,
        "cells": {
            "scared": [0, 1, 2, 3],
            "fall": [4, 5, 6, 7],
            "jump": [8, 9],
            "land": [10, 11],
            "held": [12, 13, 14, 15],
        },
        "ref": [10, 11],
    },
    {
        "file": "dog_mood_eat.png",
        "cols": 4, "rows": 4,
        "cells": {
            "happy": [0, 1, 2, 3],
            "eat": [4, 5, 6, 7],
            "sad": [8, 9],
            "hungry": [10, 11],
            "sick": [12, 13],
        },
        "ref": [8, 9],
        "food_cell": 15,
    },
    {
        "file": "dog_die.png",
        "cols": 4, "rows": 4,
        "cells": {"die": [0, 1]},
        "ref": [0, 1],
        "tomb_cell": 2,
    },
]


def is_green_screen(r: int, g: int, b: int) -> bool:
    """순수에 가까운 초록 배경 픽셀인지 판단한다. 몸 색이 잘못 지워지지 않게 기준을 엄격히 잡는다."""
    return g >= 200 and r <= 120 and b <= 120 and g - max(r, b) >= 90


def key_out_green(img: Image.Image) -> Image.Image:
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
    col = index % cols
    row = index // cols
    x0 = round(col * width / cols)
    x1 = round((col + 1) * width / cols)
    y0 = round(row * height / rows)
    y1 = round((row + 1) * height / rows)
    return x0, y0, x1, y1


def binarize_alpha(img: Image.Image) -> Image.Image:
    r, g, b, a = img.split()
    a = a.point(lambda v: 255 if v >= ALPHA_CUTOFF else 0)
    return Image.merge("RGBA", (r, g, b, a))


def opaque_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    return img.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUTOFF else 0).getbbox()


def shrink_cell(sheet: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """칸 하나를 정사각형 중앙 영역으로 잘라 FRAME 크기로 줄인다."""
    x0, y0, x1, y1 = box
    cell = sheet.crop(box)
    side = min(x1 - x0, y1 - y0)
    left = (x1 - x0 - side) // 2
    top = (y1 - y0 - side) // 2
    square = cell.crop((left, top, left + side, top + side))
    return binarize_alpha(square.resize((FRAME, FRAME), Image.Resampling.BOX))


def sheet_offset(refs: list[Image.Image]) -> tuple[int, int]:
    """기준 칸들의 발 위치와 가운데 위치 중앙값으로 이동량(dx, dy)을 구한다."""
    bottoms: list[int] = []
    centers: list[float] = []
    for img in refs:
        bb = opaque_bbox(img)
        if bb is None:
            continue
        bottoms.append(bb[3])
        centers.append((bb[0] + bb[2]) / 2)
    if not bottoms:
        raise ValueError("기준 칸에 그림이 없습니다.")
    dy = GROUND_Y - round(statistics.median(bottoms))
    dx = round(FRAME / 2 - statistics.median(centers))
    return dx, dy


def shift(img: Image.Image, dx: int, dy: int) -> Image.Image:
    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
    canvas.paste(img, (dx, dy))
    return canvas


def make_food(sheet: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """먹이 그릇: 칸 안의 그림만 잘라 가로 FOOD_WIDTH 로 줄인다."""
    cell = binarize_alpha(sheet.crop(box))
    cropped = cell.crop(cell.getchannel("A").getbbox())
    height = max(1, round(cropped.height * FOOD_WIDTH / cropped.width))
    return binarize_alpha(cropped.resize((FOOD_WIDTH, height), Image.Resampling.BOX))


def write_strip(path: Path, frames: list[Image.Image]) -> None:
    strip = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        strip.paste(frame, (i * FRAME, 0))
    strip.save(path)


def build_dog() -> tuple[dict[str, list[Image.Image]], Image.Image, Image.Image]:
    actions: dict[str, list[Image.Image]] = {}
    tomb: Image.Image | None = None
    food: Image.Image | None = None

    for spec in DOG_SHEETS:
        path = SOURCE_DIR / spec["file"]
        if not path.exists():
            raise FileNotFoundError(f"원본 시트가 없습니다: {path}")
        sheet = key_out_green(Image.open(path))
        width, height = sheet.size
        cols, rows = spec["cols"], spec["rows"]

        def box_of(index: int) -> tuple[int, int, int, int]:
            return cell_box(index, cols, rows, width, height)

        ref_imgs = [shrink_cell(sheet, box_of(i)) for i in spec["ref"]]
        dx, dy = sheet_offset(ref_imgs)
        for action, indices in spec["cells"].items():
            actions[action] = [shift(shrink_cell(sheet, box_of(i)), dx, dy) for i in indices]

        if "tomb_cell" in spec:
            tomb_small = shrink_cell(sheet, box_of(spec["tomb_cell"]))
            tdx, tdy = sheet_offset([tomb_small])
            tomb = shift(tomb_small, tdx, tdy)
        if "food_cell" in spec:
            food = make_food(sheet, box_of(spec["food_cell"]))

    if tomb is None or food is None:
        raise ValueError("무덤 또는 먹이 칸 설정이 없습니다.")
    return actions, tomb, food


def main() -> None:
    actions, tomb, food = build_dog()
    stage = PET_DIR / "stage1"
    stage.mkdir(parents=True, exist_ok=True)
    for name, frames in actions.items():
        write_strip(stage / f"{name}.png", frames)
        print(f"dog/{name}: {len(frames)} frames")
    tomb.save(PET_DIR / "tomb.png")
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    food.save(ITEMS_DIR / "food_bowl.png")
    print("tomb.png, items/food_bowl.png written")


if __name__ == "__main__":
    main()
