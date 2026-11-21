"""첫 실행과 새 펫 입양: 동물 고르기(미리보기) → 이름 정하기."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.records import MAX_NAME_LEN


@dataclass(frozen=True)
class PetChoice:
    key: str        # 동물 폴더 이름
    name_ko: str    # 기본 이름
    preview: QImage  # 미리보기 그림 (이미 확대된 상태)


class AdoptDialog(QDialog):
    def __init__(self, choices: list[PetChoice], default_key: str, parent=None) -> None:
        super().__init__(parent)
        if not choices:
            raise ValueError("고를 수 있는 동물이 없습니다.")
        self.setWindowTitle("펫 고르기")
        self._choices = choices
        self.animal: str = ""
        self.name: str = ""

        # 1쪽: 동물 고르기
        self._list = QListWidget()
        for choice in choices:
            pixmap = QPixmap.fromImage(choice.preview)
            item = QListWidgetItem(QIcon(pixmap), choice.name_ko)
            self._list.addItem(item)
        self._list.setIconSize(QSize(choices[0].preview.width(), choices[0].preview.height()))
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(160, 160)
        keys = [c.key for c in choices]
        self._list.setCurrentRow(keys.index(default_key) if default_key in keys else 0)
        self._list.currentRowChanged.connect(self._show_preview)
        self._show_preview(self._list.currentRow())

        next_btn = QPushButton("다음")
        cancel_btn = QPushButton("취소")
        next_btn.clicked.connect(self._to_name_page)
        cancel_btn.clicked.connect(self.reject)
        page1 = QWidget()
        top = QHBoxLayout(page1)
        top.addWidget(self._list, 1)
        top.addWidget(self._preview, 1)
        bar1 = QHBoxLayout()
        bar1.addStretch(1)
        bar1.addWidget(cancel_btn)
        bar1.addWidget(next_btn)
        col1 = QVBoxLayout(page1)
        col1.addWidget(QLabel("함께 지낼 동물을 고르세요."))
        col1.addLayout(top)
        col1.addLayout(bar1)

        # 2쪽: 이름 정하기
        self._name = QLineEdit()
        self._name.setMaxLength(MAX_NAME_LEN)
        self._name.textChanged.connect(self._update_done)
        back_btn = QPushButton("이전")
        self._done_btn = QPushButton("완료")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        self._done_btn.clicked.connect(self._finish)
        page2 = QWidget()
        bar2 = QHBoxLayout()
        bar2.addWidget(back_btn)
        bar2.addStretch(1)
        bar2.addWidget(self._done_btn)
        col2 = QVBoxLayout(page2)
        col2.addWidget(QLabel(f"이름을 정해 주세요 (최대 {MAX_NAME_LEN}자)"))
        col2.addWidget(self._name)
        col2.addLayout(bar2)

        self._stack = QStackedWidget()
        self._stack.addWidget(page1)
        self._stack.addWidget(page2)
        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

    def _show_preview(self, row: int) -> None:
        if 0 <= row < len(self._choices):
            self._preview.setPixmap(QPixmap.fromImage(self._choices[row].preview))

    def _to_name_page(self) -> None:
        row = self._list.currentRow()
        if not 0 <= row < len(self._choices):
            return
        choice = self._choices[row]
        self.animal = choice.key
        self._name.setText(choice.name_ko)
        self._stack.setCurrentIndex(1)
        self._update_done()

    def _update_done(self) -> None:
        self._done_btn.setEnabled(bool(self._name.text().strip()))

    def _finish(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        self.name = name[:MAX_NAME_LEN]
        self.accept()
