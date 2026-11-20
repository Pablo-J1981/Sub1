"""프로그램 경로 계산 (개발 실행과 exe 실행 모두 대응)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_FOLDER_NAME = "DesktopPet"


def app_root() -> Path:
    """설정(config)과 기본 에셋(assets)이 있는 루트 폴더.

    - 개발 실행: 저장소 루트 (src/platform_win/paths.py 기준 세 단계 위)
    - exe 실행(Nuitka/PyInstaller): exe 파일이 있는 폴더
    """
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """사용자 데이터 폴더: %APPDATA%\\DesktopPet"""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_FOLDER_NAME
