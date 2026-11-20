"""펫 스프라이트 시트 로딩.

시트는 가로로 프레임을 이어 붙인 PNG이다. 파일이 없거나 크기가 맞지 않으면
동작 이름이 적힌 색 네모로 대체하고, 어떤 동작이 대체되었는지 missing에 남긴다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage

from core.pet_spec import PetSpec
from ui.placeholder import make_placeholder_image


class SpriteBank:
    def __init__(self, spec: PetSpec) -> None:
        self._spec = spec
        self._frames: dict[str, list[QImage]] = {}
        self._tomb: QImage | None = None
        self.missing: list[str] = []

    def load(self) -> None:
        fw, fh = self._spec.frame_size
        for name, action in self._spec.actions.items():
            path = self._spec.root / action.file
            self._frames[name] = self._load_sheet(path, action.frames, name, fw, fh)
        self._tomb = self._load_single(self._spec.root / self._spec.tomb, "tomb", fw, fh)

    def frame(self, action: str, index: int) -> QImage:
        frames = self._frames[action]
        return frames[index % len(frames)]

    def tomb(self) -> QImage:
        if self._tomb is None:
            raise RuntimeError("SpriteBank.load() 를 먼저 호출하세요.")
        return self._tomb

    def _load_sheet(
        self, path: Path, frames: int, name: str, fw: int, fh: int
    ) -> list[QImage]:
        sheet = QImage(str(path))
        if sheet.isNull() or sheet.width() < fw * frames or sheet.height() < fh:
            self.missing.append(name)
            return [make_placeholder_image(name, (fw, fh)) for _ in range(frames)]
        return [sheet.copy(i * fw, 0, fw, fh) for i in range(frames)]

    def _load_single(self, path: Path, name: str, fw: int, fh: int) -> QImage:
        image = QImage(str(path))
        if image.isNull():
            self.missing.append(name)
            return make_placeholder_image(name, (fw, fh))
        return image
