"""저장 파일 읽기/쓰기 (Qt 비의존).

- 위치: %APPDATA%\\DesktopPet\\save.json (경로는 호출하는 쪽이 정한다)
- 형식: {"version": 1, "next_id": n, "pets": [펫 기록...]}
- 쓰기: 임시 파일에 먼저 쓰고 fsync 한 뒤 교체한다. 이전 파일은 save.bak 로 남긴다.
- 읽기: save.json 이 깨졌으면 save.bak 로 복구한다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from core.records import PetRecord

SAVE_VERSION = 1


@dataclass
class SaveData:
    records: list[PetRecord] = field(default_factory=list)
    next_id: int = 1


def backup_path(path: Path) -> Path:
    return path.with_name(path.stem + ".bak")


def _parse(text: str) -> SaveData:
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("version") != SAVE_VERSION:
        raise ValueError("지원하지 않는 저장 파일 버전입니다.")
    pets = data.get("pets")
    if not isinstance(pets, list):
        raise ValueError("저장 파일 'pets' 가 목록이 아닙니다.")
    records = [PetRecord.from_dict(p) for p in pets]
    ids = [r.id for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("저장 파일에 같은 id 의 펫이 두 번 있습니다.")
    next_id = data.get("next_id")
    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
        raise ValueError("저장 파일 'next_id' 가 잘못되었습니다.")
    return SaveData(records=records, next_id=max(next_id, max(ids, default=0) + 1))


def load_save(path: Path) -> tuple[SaveData | None, list[str]]:
    """(데이터, 경고 목록). 둘 다 없거나 깨졌으면 데이터는 None."""
    warnings: list[str] = []
    for candidate in (path, backup_path(path)):
        if not candidate.exists():
            continue
        try:
            return _parse(candidate.read_text(encoding="utf-8")), warnings
        except (OSError, ValueError) as exc:  # json 오류도 ValueError 하위
            warnings.append(f"저장 파일을 읽지 못했습니다: {candidate} ({exc})")
    return None, warnings


def save_data(path: Path, data: SaveData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SAVE_VERSION,
        "next_id": data.next_id,
        "pets": [r.to_dict() for r in data.records],
    }
    tmp = path.with_name(path.stem + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    if path.exists():
        os.replace(path, backup_path(path))
    os.replace(tmp, path)
