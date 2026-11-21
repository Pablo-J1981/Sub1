"""아이템 팩(먹이, 장난감)과 권한 확인 (Qt 비의존).

팩 형식: assets/items/<팩 이름>/item.json + 그림 파일
    {"id": "food_bone", "kind": "food", "name_ko": "뼈다귀", "image": "image.png"}
kind 는 "food" 또는 "toy". 새 아이템은 폴더를 추가하는 것으로 끝난다.
권한(EntitlementProvider)은 구매 연동을 위한 자리이며, 지금은 항상 허용한다.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

KINDS = ("food", "toy")


@dataclass(frozen=True)
class ItemPack:
    id: str
    kind: str
    name_ko: str
    image: Path
    sinks: bool = False  # True면 먹이가 천천히 가라앉는다 (물고기)


class EntitlementProvider(ABC):
    @abstractmethod
    def is_entitled(self, item_id: str) -> bool:
        """이 아이템을 쓸 수 있는지."""


class LocalAlwaysAllow(EntitlementProvider):
    """로컬 버전: 모든 아이템을 허용한다."""

    def is_entitled(self, item_id: str) -> bool:
        return True


def load_item_packs(items_root: Path) -> tuple[list[ItemPack], list[str]]:
    """(팩 목록, 오류 메시지 목록). 잘못된 팩은 건너뛴다."""
    packs: list[ItemPack] = []
    errors: list[str] = []
    if not items_root.is_dir():
        return packs, [f"아이템 폴더가 없습니다: {items_root}"]
    for folder in sorted(p for p in items_root.iterdir() if p.is_dir()):
        meta_path = folder / "item.json"
        if not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            item_id = data["id"]
            kind = data["kind"]
            name_ko = data["name_ko"]
            image = folder / data["image"]
            sinks = bool(data.get("sinks", False))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{meta_path}: 읽지 못했습니다 ({exc})")
            continue
        if kind not in KINDS or not isinstance(item_id, str) or not isinstance(name_ko, str):
            errors.append(f"{meta_path}: id/kind/name_ko 값이 잘못되었습니다.")
            continue
        if not image.is_file():
            errors.append(f"{meta_path}: 그림 파일이 없습니다 ({image.name}).")
            continue
        packs.append(ItemPack(item_id, kind, name_ko, image, sinks))
    return packs, errors


def entitled(packs: list[ItemPack], provider: EntitlementProvider, kind: str) -> list[ItemPack]:
    return [p for p in packs if p.kind == kind and provider.is_entitled(p.id)]
