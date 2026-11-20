"""파일 로깅과 미처리 예외 기록 설정."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

# 로그 회전 크기는 운영 설정이 아니라 파일 관리용 상수이다.
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

LOGGER_NAME = "desktop_pet"


def setup_logging(log_file: Path) -> logging.Logger:
    """파일 로거를 만들고 반환한다. 여러 번 호출해도 핸들러가 중복되지 않는다."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return logger


def install_excepthook(logger: logging.Logger) -> None:
    """처리되지 않은 예외를 로그에 남긴다. 프로그램 종료는 막지 않는다."""

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        logger.error("처리되지 않은 예외", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook
