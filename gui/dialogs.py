"""Dialog windows: Pre-check file list dialog and Failed items dialog in Geek style."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScroller,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


class PreCheckDialog(QDialog):
    """File pre-check preview dialog with search and format filtering."""

    sig_start_requested = Signal()

    def __init__(self, files: list[Path], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("预检清单")
        self.resize(860, 540)
        self.setMinimumSize(640, 380)
        self.all_files = files
        self.current_filter = "all"
        self.search_text = ""

        self._init_ui()
        self._populate_table()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header bar
        header_layout = QHBoxLayout()
        title_label = QLabel(f"共扫描到 {len(self.all_files)} 个音频文件")
        title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #a5b4fc;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Search and Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件名或路径...")
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_input, stretch=2)

        # Count by extension
        ncm_count = sum(1 for f in self.all_files if f.suffix.lower() == ".ncm")
        flac_count = sum(1 for f in self.all_files if f.suffix.lower() == ".flac")
        mp3_count = sum(1 for f in self.all_files if f.suffix.lower() == ".mp3")

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for label_text, ext_key in [
            (f"全部 {len(self.all_files)}", "all"),
            (f"NCM {ncm_count}", ".ncm"),
            (f"FLAC {flac_count}", ".flac"),
            (f"MP3 {mp3_count}", ".mp3"),
        ]:
            btn = QPushButton(label_text)
            btn.setObjectName("filterPill")
            btn.setCheckable(True)
            if ext_key == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, k=ext_key: self._on_filter_changed(k))
            self.btn_group.addButton(btn)
            filter_layout.addWidget(btn)

        layout.addLayout(filter_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["序号", "格式", "文件名", "大小", "修改时间"])
        self.table.setShowGrid(True)
        self.table.setGridStyle(Qt.SolidLine)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        default_widths = [55, 80, 260, 85, 155]
        for col, width in enumerate(default_widths):
            self.table.setColumnWidth(col, width)

        for col in range(5):
            if col == 2:  # 文件名 默认拉伸
                header.setSectionResizeMode(col, QHeaderView.Stretch)
            elif col == 4:  # 修改时间 固定宽度吸附最右侧
                header.setSectionResizeMode(col, QHeaderView.Fixed)
            else:
                header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        QScroller.grabGesture(
            self.table.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )
        layout.addWidget(self.table)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #71717a; font-size: 11px;")
        bottom_layout.addWidget(self.stats_label)
        bottom_layout.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)

        self.btn_start = QPushButton("开始转换")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self._on_start_clicked)
        bottom_layout.addWidget(self.btn_start)

        layout.addLayout(bottom_layout)

    def _on_search_changed(self, text: str) -> None:
        self.search_text = text.strip().casefold()
        self._populate_table()

    def _on_filter_changed(self, ext_key: str) -> None:
        self.current_filter = ext_key
        self._populate_table()

    def _populate_table(self) -> None:
        filtered: list[Path] = []
        for f in self.all_files:
            ext = f.suffix.lower()
            if self.current_filter != "all" and ext != self.current_filter:
                continue
            if self.search_text:
                if (
                    self.search_text not in f.name.casefold()
                    and self.search_text not in str(f).casefold()
                ):
                    continue
            filtered.append(f)

        self.table.setRowCount(len(filtered))
        for row, f in enumerate(filtered):
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, idx_item)

            ext_str = f.suffix.lower().lstrip(".").upper()
            pill_label = QLabel(ext_str)
            if ext_str == "NCM":
                pill_label.setObjectName("pillNcm")
            elif ext_str == "FLAC":
                pill_label.setObjectName("pillFlac")
            else:
                pill_label.setObjectName("pillMp3")
            pill_label.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row, 1, pill_label)

            name_item = QTableWidgetItem(f.name)
            name_item.setToolTip(str(f.resolve()))
            self.table.setItem(row, 2, name_item)

            try:
                stat = f.stat()
                size_str = format_size(stat.st_size)
                mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                size_str = "-"
                mtime_str = "-"

            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, size_item)

            mtime_item = QTableWidgetItem(mtime_str)
            mtime_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, mtime_item)

        self.stats_label.setText(f"当前显示 {len(filtered)} / 总计 {len(self.all_files)}")

    def _on_start_clicked(self) -> None:
        self.sig_start_requested.emit()
        self.accept()


class FailedItemsDialog(QDialog):
    """Dialog for inspecting fail.json records and retrying."""

    sig_retry_requested = Signal()

    def __init__(self, fail_json_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("失败记录")
        self.resize(800, 460)
        self.fail_json_path = fail_json_path
        self.records: list[dict[str, Any]] = []

        self._init_ui()
        self._load_records()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        title_label = QLabel("转换失败列表")
        title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #f87171;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["时间", "文件名", "失败原因", "路径"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        QScroller.grabGesture(
            self.table.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )
        layout.addWidget(self.table)

        bottom_layout = QHBoxLayout()
        self.btn_retry = QPushButton("重试失败项")
        self.btn_retry.setObjectName("primaryButton")
        self.btn_retry.clicked.connect(self._on_retry)
        bottom_layout.addWidget(self.btn_retry)

        self.btn_clear = QPushButton("清空记录")
        self.btn_clear.setObjectName("dangerButton")
        self.btn_clear.clicked.connect(self._on_clear)
        bottom_layout.addWidget(self.btn_clear)

        bottom_layout.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)

        layout.addLayout(bottom_layout)

    def _load_records(self) -> None:
        if not self.fail_json_path.is_file():
            self.records = []
        else:
            try:
                data = json.loads(self.fail_json_path.read_text(encoding="utf-8"))
                self.records = data if isinstance(data, list) else []
            except Exception:
                self.records = []

        self.table.setRowCount(len(self.records))
        for row, item in enumerate(self.records):
            time_item = QTableWidgetItem(str(item.get("time") or ""))
            time_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, time_item)

            name_item = QTableWidgetItem(str(item.get("name") or ""))
            self.table.setItem(row, 1, name_item)

            reason_item = QTableWidgetItem(str(item.get("reason") or ""))
            reason_item.setForeground(Qt.red)
            self.table.setItem(row, 2, reason_item)

            path_item = QTableWidgetItem(str(item.get("path") or ""))
            self.table.setItem(row, 3, path_item)

        if not self.records:
            self.btn_retry.setEnabled(False)
            self.btn_clear.setEnabled(False)

    def _on_retry(self) -> None:
        self.sig_retry_requested.emit()
        self.accept()

    def _on_clear(self) -> None:
        if QMessageBox.question(
            self, "确认", "确定清空失败记录吗？", QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                if self.fail_json_path.is_file():
                    self.fail_json_path.unlink()
                self._load_records()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {e}")
