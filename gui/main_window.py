"""Main GUI window for NCM Tag Extractor in Geek Tool Style."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDateTime, QEvent, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QIntValidator,
    QKeyEvent,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScroller,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    DEFAULT_CONFIG,
    format_config_mtime,
    get_default_config_path,
    get_or_create_config,
    save_config,
)
from core.processor import iter_media_files
from gui.dialogs import FailedItemsDialog, PreCheckDialog
from gui.native_dialog import choose_directory, choose_files
from gui.styles import DARK_THEME_QSS
from gui.worker import ConvertWorker


class NumberBox(QLineEdit):
    """Clean manual number input with keyboard typing, wheel/arrow keys, and zero-padding."""

    valueChanged = Signal()

    def __init__(self, min_val: int, max_val: int, digits: int = 2, parent=None) -> None:
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.digits = digits
        self.setAlignment(Qt.AlignCenter)
        self.setMaxLength(max(digits, 4))
        self.setValidator(QIntValidator(0, 9999, self))
        self.setStyleSheet("padding: 2px 2px;")
        self.textChanged.connect(lambda: self.valueChanged.emit())
        self.editingFinished.connect(self._format_value)

    def _format_value(self) -> None:
        self.setValue(self.value())

    def value(self) -> int:
        txt = self.text().strip()
        if not txt:
            return self.min_val
        try:
            val = int(txt)
            return max(self.min_val, min(self.max_val, val))
        except ValueError:
            return self.min_val

    def setValue(self, val: int) -> None:
        clamped = max(self.min_val, min(self.max_val, val))
        formatted = f"{clamped:0{self.digits}d}"
        if self.text() != formatted:
            self.setText(formatted)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        # Select all on focus for effortless overwrite typing
        QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, event) -> None:
        self._format_value()
        super().focusOutEvent(event)

    def wheelEvent(self, event) -> None:
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.setValue(self.value() + delta)
        self.valueChanged.emit()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.clearFocus()
            return
        elif event.key() == Qt.Key_Up:
            self.setValue(self.value() + 1)
            self.valueChanged.emit()
            return
        elif event.key() == Qt.Key_Down:
            self.setValue(self.value() - 1)
            self.valueChanged.emit()
            return
        super().keyPressEvent(event)


class SplitDateTimeWidget(QWidget):
    """Separate manual input cells for Year, Month, Day, Hour, Minute, Second."""

    valueChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.spin_year = NumberBox(1990, 2099, 4)
        self.spin_year.setFixedWidth(44)
        self.spin_year.setToolTip("年 (YYYY)")

        self.spin_month = NumberBox(1, 12, 2)
        self.spin_month.setFixedWidth(26)
        self.spin_month.setToolTip("月 (01-12)")

        self.spin_day = NumberBox(1, 31, 2)
        self.spin_day.setFixedWidth(26)
        self.spin_day.setToolTip("日 (01-31)")

        self.spin_hour = NumberBox(0, 23, 2)
        self.spin_hour.setFixedWidth(26)
        self.spin_hour.setToolTip("时 (00-23)")

        self.spin_minute = NumberBox(0, 59, 2)
        self.spin_minute.setFixedWidth(26)
        self.spin_minute.setToolTip("分 (00-59)")

        self.spin_second = NumberBox(0, 59, 2)
        self.spin_second.setFixedWidth(26)
        self.spin_second.setToolTip("秒 (00-59)")

        def make_sep(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFixedWidth(5)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #71717a; font-weight: 500; font-size: 11px; padding: 0; margin: 0;")
            return lbl

        layout.addWidget(self.spin_year)
        layout.addWidget(make_sep("-"))
        layout.addWidget(self.spin_month)
        layout.addWidget(make_sep("-"))
        layout.addWidget(self.spin_day)
        layout.addSpacing(5)
        layout.addWidget(self.spin_hour)
        layout.addWidget(make_sep(":"))
        layout.addWidget(self.spin_minute)
        layout.addWidget(make_sep(":"))
        layout.addWidget(self.spin_second)

        for sb in [
            self.spin_year,
            self.spin_month,
            self.spin_day,
            self.spin_hour,
            self.spin_minute,
            self.spin_second,
        ]:
            sb.valueChanged.connect(lambda *_: self.valueChanged.emit(self.get_datetime_str()))

    def get_datetime_str(self) -> str:
        return (
            f"{self.spin_year.value():04d}-{self.spin_month.value():02d}-{self.spin_day.value():02d} "
            f"{self.spin_hour.value():02d}:{self.spin_minute.value():02d}:{self.spin_second.value():02d}"
        )

    def set_datetime_str(self, s: str) -> None:
        try:
            dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
            self.spin_year.setValue(dt.year)
            self.spin_month.setValue(dt.month)
            self.spin_day.setValue(dt.day)
            self.spin_hour.setValue(dt.hour)
            self.spin_minute.setValue(dt.minute)
            self.spin_second.setValue(dt.second)
        except Exception:
            pass

    def to_secs_since_epoch(self) -> int:
        try:
            dt = datetime.strptime(self.get_datetime_str(), "%Y-%m-%d %H:%M:%S")
            return int(dt.timestamp())
        except Exception:
            return 0


class MainWindow(QMainWindow):
    """Main window with sleek developer-tool interface."""

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("NCM Tag Extractor")
        self.resize(1020, 740)
        self.setMinimumSize(800, 560)
        self.setStyleSheet(DARK_THEME_QSS)
        self.setAcceptDrops(True)

        try:
            self.config, self.config_path = get_or_create_config(config_path)
            self._config_write_error = False
        except OSError as e:
            self.config = dict(DEFAULT_CONFIG)
            self.config_path = config_path or get_default_config_path()
            self._config_write_error = True
            QMessageBox.critical(
                self,
                "配置文件创建失败",
                f"检测到程序所在目录为只读或无写入权限，无法创建配置文件：\n\n{self.config_path}\n\n错误原因: {e}\n\n应用将以临时默认配置启动，但在只读环境下修改的设置将无法保存。",
            )

        self.worker: ConvertWorker | None = None
        self._is_saving_config = False

        self._init_ui()
        self._load_config_to_ui()
        self._update_fail_button_state()

        app_instance = QApplication.instance()
        if app_instance:
            app_instance.installEventFilter(self)

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit):
                try:
                    pos = event.globalPosition().toPoint()
                    clicked_widget = QApplication.widgetAt(pos)
                    if clicked_widget is not fw and not isinstance(clicked_widget, QLineEdit):
                        fw.clearFocus()
                except Exception:
                    pass
        return super().eventFilter(watched, event)

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # ================= 1. Path Card =================
        path_card = QFrame()
        path_card.setObjectName("cardFrame")
        grid_paths = QGridLayout(path_card)
        grid_paths.setContentsMargins(12, 10, 12, 10)
        grid_paths.setHorizontalSpacing(10)
        grid_paths.setVerticalSpacing(8)

        # Row 0: Input Row
        lbl_in = QLabel("输入")
        lbl_in.setStyleSheet("color: #8b8ea4; font-size: 12px; font-weight: 600;")
        lbl_in.setFixedWidth(32)
        lbl_in.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        grid_paths.addWidget(lbl_in, 0, 0, Qt.AlignTop)

        self.input_list = QListWidget()
        self.input_list.setObjectName("pathListCard")
        self.input_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.input_list.setMinimumHeight(66)
        self.input_list.setMaximumHeight(85)
        self.input_list.setToolTip("可直接将文件或文件夹拖拽进此窗口")
        self.input_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.input_list.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        QScroller.grabGesture(
            self.input_list.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )
        grid_paths.addWidget(self.input_list, 0, 1)

        # Input buttons (2x2 grid)
        in_btn_widget = QWidget()
        in_btn_grid = QGridLayout(in_btn_widget)
        in_btn_grid.setContentsMargins(0, 0, 0, 0)
        in_btn_grid.setHorizontalSpacing(6)
        in_btn_grid.setVerticalSpacing(6)

        self.btn_add_folder = QPushButton("选择文件夹")
        self.btn_add_folder.setFixedWidth(86)
        self.btn_add_folder.clicked.connect(self._on_add_folder_clicked)
        in_btn_grid.addWidget(self.btn_add_folder, 0, 0)

        self.btn_add_files = QPushButton("选择文件")
        self.btn_add_files.setFixedWidth(86)
        self.btn_add_files.clicked.connect(self._on_add_files_clicked)
        in_btn_grid.addWidget(self.btn_add_files, 0, 1)

        self.btn_remove_path = QPushButton("移除选中")
        self.btn_remove_path.setFixedWidth(86)
        self.btn_remove_path.clicked.connect(self._on_remove_path_clicked)
        in_btn_grid.addWidget(self.btn_remove_path, 1, 0)

        self.btn_clear_paths = QPushButton("清空输入")
        self.btn_clear_paths.setFixedWidth(86)
        self.btn_clear_paths.clicked.connect(self._on_clear_paths_clicked)
        in_btn_grid.addWidget(self.btn_clear_paths, 1, 1)

        grid_paths.addWidget(in_btn_widget, 0, 2, Qt.AlignTop)

        # Row 1: Output Row
        lbl_out = QLabel("输出")
        lbl_out.setStyleSheet("color: #8b8ea4; font-size: 12px; font-weight: 600;")
        lbl_out.setFixedWidth(32)
        lbl_out.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        grid_paths.addWidget(lbl_out, 1, 0)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("留空则保存到源文件所在目录")
        self.output_edit.textChanged.connect(self._on_config_changed)
        grid_paths.addWidget(self.output_edit, 1, 1)

        out_btn_widget = QWidget()
        out_btn_layout = QHBoxLayout(out_btn_widget)
        out_btn_layout.setContentsMargins(0, 0, 0, 0)
        out_btn_layout.setSpacing(6)

        self.btn_browse_output = QPushButton("选择文件夹")
        self.btn_browse_output.setFixedWidth(86)
        self.btn_browse_output.clicked.connect(self._on_browse_output_clicked)
        out_btn_layout.addWidget(self.btn_browse_output)

        self.btn_clear_output = QPushButton("清空输出")
        self.btn_clear_output.setFixedWidth(86)
        self.btn_clear_output.clicked.connect(self._on_clear_output_clicked)
        out_btn_layout.addWidget(self.btn_clear_output)

        grid_paths.addWidget(out_btn_widget, 1, 2)

        grid_paths.setColumnStretch(0, 0)
        grid_paths.setColumnStretch(1, 1)
        grid_paths.setColumnStretch(2, 0)

        main_layout.addWidget(path_card)

        # ================= 2. Settings Card =================
        opts_card = QFrame()
        opts_card.setObjectName("cardFrame")
        opts_layout = QVBoxLayout(opts_card)
        opts_layout.setContentsMargins(12, 10, 12, 10)
        opts_layout.setSpacing(8)

        opts_header = QHBoxLayout()
        title_opts = QLabel("转换选项")
        title_opts.setObjectName("sectionTitle")
        opts_header.addWidget(title_opts)
        opts_header.addStretch()
        opts_layout.addLayout(opts_header)

        # Row 1: Core Switches & Sort
        opts_row1 = QHBoxLayout()
        opts_row1.setSpacing(14)

        self.chk_recursive = QCheckBox("递归子目录")
        self.chk_recursive.toggled.connect(self._on_config_changed)
        opts_row1.addWidget(self.chk_recursive)

        self.chk_enrich = QCheckBox("联网补全网易云元数据")
        self.chk_enrich.toggled.connect(self._on_config_changed)
        opts_row1.addWidget(self.chk_enrich)

        self.chk_only_failed = QCheckBox("仅处理失败项")
        self.chk_only_failed.toggled.connect(self._on_only_failed_toggled)
        opts_row1.addWidget(self.chk_only_failed)

        opts_row1.addStretch()

        lbl_sort = QLabel("排序:")
        lbl_sort.setStyleSheet("color: #8b8ea4; font-size: 12px;")
        opts_row1.addWidget(lbl_sort)

        self.combo_sort = QComboBox()
        self.combo_sort.addItem("文件名升序", "name")
        self.combo_sort.addItem("时间新到旧排序", "mtime_desc")
        self.combo_sort.addItem("时间旧到新排序", "mtime")
        self.combo_sort.currentIndexChanged.connect(self._on_config_changed)
        opts_row1.addWidget(self.combo_sort)

        opts_layout.addLayout(opts_row1)

        # Row 2: Time Checkpoint
        opts_row2 = QHBoxLayout()
        opts_row2.setSpacing(6)

        self.chk_mtime_filter = QCheckBox("处理该时间以及该时间后的文件:")
        self.chk_mtime_filter.toggled.connect(self._on_mtime_filter_toggled)
        opts_row2.addWidget(self.chk_mtime_filter)

        self.time_picker = SplitDateTimeWidget()
        self.time_picker.valueChanged.connect(self._on_config_changed)
        opts_row2.addWidget(self.time_picker)

        self.btn_pick_file_mtime = QPushButton("从文件获取时间戳")
        self.btn_pick_file_mtime.clicked.connect(self._on_pick_file_mtime_clicked)
        opts_row2.addWidget(self.btn_pick_file_mtime)

        opts_row2.addSpacing(6)

        self.chk_auto_mtime = QCheckBox("处理后自动更新时间戳")
        self.chk_auto_mtime.toggled.connect(self._on_config_changed)
        opts_row2.addWidget(self.chk_auto_mtime)

        opts_row2.addStretch()

        opts_layout.addLayout(opts_row2)
        main_layout.addWidget(opts_card)

        # ================= 3. Action Toolbar & Progress =================
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #8b8ea4; font-size: 12px; font-weight: 500;")
        action_row.addWidget(self.lbl_status)

        self.lbl_counts = QLabel("总计 0 · 成功 0 · 失败 0")
        self.lbl_counts.setStyleSheet("color: #a5b4fc; font-size: 12px; font-weight: 600; margin-left: 8px;")
        action_row.addWidget(self.lbl_counts)

        action_row.addStretch()

        self.btn_toggle_log = QPushButton("日志 ▾")
        self.btn_toggle_log.clicked.connect(self._on_toggle_log_clicked)
        action_row.addWidget(self.btn_toggle_log)

        self.btn_precheck = QPushButton("预检")
        self.btn_precheck.clicked.connect(self._on_precheck_clicked)
        action_row.addWidget(self.btn_precheck)

        self.btn_failed_list = QPushButton("失败记录")
        self.btn_failed_list.setObjectName("warningButton")
        self.btn_failed_list.clicked.connect(self._on_show_failed_clicked)
        action_row.addWidget(self.btn_failed_list)

        self.btn_cancel = QPushButton("停止")
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        action_row.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("开始转换")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self._on_start_clicked)
        action_row.addWidget(self.btn_start)

        main_layout.addLayout(action_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # ================= 4. Task Table & Collapsible Logs =================
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(True)

        # Task Table
        self.task_table = QTableWidget()
        headers = [
            "序号",
            "状态",
            "格式",
            "文件名",
            "曲名",
            "艺术家",
            "专辑艺术家",
            "出版商",
            "音轨号",
            "音轨总数",
            "碟片号",
            "有歌词",
        ]
        self.task_table.setColumnCount(len(headers))
        self.task_table.setHorizontalHeaderLabels(headers)
        self.task_table.setShowGrid(True)
        self.task_table.setGridStyle(Qt.SolidLine)

        header = self.task_table.horizontalHeader()
        header.setStretchLastSection(False)

        default_widths = [50, 80, 60, 160, 140, 110, 100, 100, 60, 66, 60, 76]
        for col, width in enumerate(default_widths):
            self.task_table.setColumnWidth(col, width)

        for col in range(len(headers)):
            if col == 4:  # "曲名" stretches to fill extra window width
                header.setSectionResizeMode(col, QHeaderView.Stretch)
            elif col == 11:  # "有歌词" fixed to 76px and pinned to the right edge
                header.setSectionResizeMode(col, QHeaderView.Fixed)
            else:
                header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.task_table.setSelectionMode(QTableWidget.SingleSelection)
        self.task_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.task_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.task_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        QScroller.grabGesture(
            self.task_table.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )
        self.splitter.addWidget(self.task_table)

        # Log Console
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(140)
        self.log_console.setPlaceholderText("运行日志...")
        self.splitter.addWidget(self.log_console)

        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)

    # ================= Configuration Synchronization =================

    @staticmethod
    def _normalize_display_path(p: Path | str) -> str:
        """Format directories with a trailing slash to clearly distinguish from files."""
        try:
            path = Path(p).resolve()
            str_path = str(path)
            if path.is_dir() and not str_path.endswith("/"):
                return f"{str_path}/"
            return str_path
        except Exception:
            return str(p)

    def _load_config_to_ui(self) -> None:
        self._is_saving_config = True
        try:
            self.input_list.clear()
            for path in self.config.get("input_dirs", []):
                if path and str(path).strip():
                    self.input_list.addItem(self._normalize_display_path(str(path).strip()))

            out_dir = str(self.config.get("output_dir") or "").strip()
            if out_dir:
                self.output_edit.setText(self._normalize_display_path(out_dir))
            else:
                self.output_edit.clear()

            self.chk_recursive.setChecked(bool(self.config.get("recursive", True)))
            self.chk_enrich.setChecked(bool(self.config.get("enrich_netease", True)))
            self.chk_auto_mtime.setChecked(bool(self.config.get("auto_update_mtime", True)))
            self.chk_only_failed.setChecked(bool(self.config.get("only_process_failed", False)))

            sort_val = str(self.config.get("sort_by") or "name")
            idx = self.combo_sort.findData(sort_val)
            if idx >= 0:
                self.combo_sort.setCurrentIndex(idx)

            enable_mtime = bool(self.config.get("enable_mtime_filter", False))
            self.chk_mtime_filter.setChecked(enable_mtime)

            mtime_str = str(self.config.get("process_after_mtime") or "").strip()
            if mtime_str:
                self.time_picker.set_datetime_str(mtime_str)
            else:
                self.time_picker.set_datetime_str(datetime.now().strftime("%Y-%m-%d 00:00:00"))

        finally:
            self._is_saving_config = False

    def _save_ui_to_config(self) -> None:
        if self._is_saving_config:
            return

        input_dirs = [
            self.input_list.item(i).text() for i in range(self.input_list.count())
        ]
        output_dir = self.output_edit.text().strip()
        sort_by = self.combo_sort.currentData() or "name"
        mtime_str = self.time_picker.get_datetime_str()

        new_cfg = {
            "input_dirs": input_dirs,
            "output_dir": output_dir,
            "recursive": self.chk_recursive.isChecked(),
            "enrich_netease": self.chk_enrich.isChecked(),
            "sort_by": sort_by,
            "enable_mtime_filter": self.chk_mtime_filter.isChecked(),
            "process_after_mtime": mtime_str,
            "auto_update_mtime": self.chk_auto_mtime.isChecked(),
            "only_process_failed": self.chk_only_failed.isChecked(),
        }

        self.config = new_cfg
        try:
            save_config(self.config_path, new_cfg)
            self._config_write_error = False
        except OSError as e:
            if not getattr(self, "_config_write_error", False):
                self._config_write_error = True
                QMessageBox.critical(
                    self,
                    "配置文件保存失败",
                    f"无法将修改写入配置文件：\n\n{self.config_path}\n\n错误原因: {e}\n\n请检查程序所在目录是否具有写权限。",
                )

    def _on_config_changed(self) -> None:
        self._save_ui_to_config()

    def _on_mtime_filter_toggled(self, checked: bool) -> None:
        self._save_ui_to_config()

    def _on_only_failed_toggled(self, checked: bool) -> None:
        self._save_ui_to_config()

    def _on_toggle_log_clicked(self) -> None:
        is_visible = self.log_console.isVisible()
        self.log_console.setVisible(not is_visible)
        self.btn_toggle_log.setText("日志 ▸" if is_visible else "日志 ▾")

    def _update_fail_button_state(self) -> None:
        fail_file = self.config_path.parent / "fail.json"
        if fail_file.is_file():
            try:
                data = json.loads(fail_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    self.btn_failed_list.setText(f"失败记录 ({len(data)})")
                    self.btn_failed_list.setVisible(True)
                    return
            except Exception:
                pass
        self.btn_failed_list.setText("失败记录")
        self.btn_failed_list.setVisible(False)

    # ================= Drag & Drop =================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        added_count = 0
        for url in urls:
            path = Path(url.toLocalFile()).resolve()
            if path.exists():
                str_path = self._normalize_display_path(path)
                existing = [self.input_list.item(i).text() for i in range(self.input_list.count())]
                if str_path not in existing:
                    self.input_list.addItem(str_path)
                    added_count += 1

        if added_count > 0:
            self._save_ui_to_config()
            self._append_log(f"已添加 {added_count} 个路径", "info")
        event.acceptProposedAction()

    # ================= Path Actions =================

    def _on_add_folder_clicked(self) -> None:
        folder = choose_directory(self, "选择文件夹")
        if folder:
            str_path = self._normalize_display_path(folder)
            existing = [self.input_list.item(i).text() for i in range(self.input_list.count())]
            if str_path not in existing:
                self.input_list.addItem(str_path)
                self._save_ui_to_config()

    def _on_add_files_clicked(self) -> None:
        files = choose_files(
            self,
            "选择音频文件",
            file_filter="音频文件 (*.ncm *.flac *.mp3);;所有文件 (*.*)",
        )
        if files:
            existing = [self.input_list.item(i).text() for i in range(self.input_list.count())]
            added = 0
            for f in files:
                str_path = self._normalize_display_path(f)
                if str_path not in existing:
                    self.input_list.addItem(str_path)
                    existing.append(str_path)
                    added += 1
            if added:
                self._save_ui_to_config()

    def _on_remove_path_clicked(self) -> None:
        for item in self.input_list.selectedItems():
            self.input_list.takeItem(self.input_list.row(item))
        self._save_ui_to_config()

    def _on_clear_paths_clicked(self) -> None:
        if self.input_list.count() > 0:
            self.input_list.clear()
            self._save_ui_to_config()

    def _on_browse_output_clicked(self) -> None:
        folder = choose_directory(self, "选择输出目录")
        if folder:
            self.output_edit.setText(self._normalize_display_path(folder))
            self._save_ui_to_config()

    def _on_clear_output_clicked(self) -> None:
        if self.output_edit.text():
            self.output_edit.clear()
            self._save_ui_to_config()

    def _on_pick_file_mtime_clicked(self) -> None:
        files = choose_files(
            self,
            "选择文件以获取时间戳",
            file_filter="音频文件 (*.ncm *.flac *.mp3);;所有文件 (*.*)",
        )
        if files:
            target_path = Path(files[0])
            try:
                mtime = target_path.stat().st_mtime
                dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                self.time_picker.set_datetime_str(dt_str)
                self.chk_mtime_filter.setChecked(True)
                self._save_ui_to_config()
                self._append_log(f"已从文件获取时间戳: {target_path.name} -> {dt_str}", "info")
            except Exception as e:
                QMessageBox.warning(self, "读取失败", f"无法读取文件时间戳: {e}")

    # ================= Scanning Logic =================

    def _scan_files(self) -> list[Path]:
        if self.chk_only_failed.isChecked():
            fail_file = self.config_path.parent / "fail.json"
            if fail_file.is_file():
                try:
                    data = json.loads(fail_file.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        failed_paths = [
                            Path(item["path"]).resolve()
                            for item in data
                            if isinstance(item, dict) and "path" in item
                        ]
                        valid = [p for p in failed_paths if p.is_file()]
                        if valid:
                            sort_by = self.combo_sort.currentData() or "name"
                            if sort_by == "mtime":
                                valid.sort(key=lambda f: (f.stat().st_mtime, str(f).casefold()))
                            elif sort_by == "mtime_desc":
                                valid.sort(key=lambda f: (-f.stat().st_mtime, str(f).casefold()))
                            else:
                                valid.sort(key=lambda f: str(f).casefold())
                            return valid
                except Exception:
                    pass

        input_paths = [
            Path(self.input_list.item(i).text()).resolve()
            for i in range(self.input_list.count())
        ]
        if not input_paths:
            return []

        enrich = self.chk_enrich.isChecked()
        extensions = {".ncm", ".flac", ".mp3"} if enrich else {".ncm"}
        sort_by = self.combo_sort.currentData() or "name"
        recursive = self.chk_recursive.isChecked()

        found_files = iter_media_files(
            input_paths, recursive=recursive, extensions=extensions, sort_by=sort_by
        )

        if self.chk_mtime_filter.isChecked():
            cutoff = self.time_picker.to_secs_since_epoch()
            found_files = [f for f in found_files if f.stat().st_mtime >= cutoff]

        return found_files

    def _on_precheck_clicked(self) -> None:
        files = self._scan_files()
        if not files:
            QMessageBox.information(
                self, "预检提示", "未找到符合条件的待处理文件。\n请检查输入路径与过滤设置。"
            )
            return

        dialog = PreCheckDialog(files, self)
        dialog.sig_start_requested.connect(lambda: QTimer.singleShot(100, self._on_start_clicked))
        dialog.exec()

    def _on_show_failed_clicked(self) -> None:
        fail_file = self.config_path.parent / "fail.json"
        dialog = FailedItemsDialog(fail_file, self)
        dialog.sig_retry_requested.connect(self._retry_failed)
        dialog.exec()
        self._update_fail_button_state()

    def _retry_failed(self) -> None:
        self.chk_only_failed.setChecked(True)
        self._save_ui_to_config()
        self._on_start_clicked()

    # ================= Execution Engine =================

    def _on_start_clicked(self) -> None:
        files = self._scan_files()
        if not files:
            QMessageBox.warning(
                self, "提示", "未找到任何可处理的文件。\n请先添加文件夹或文件。"
            )
            return

        out_text = self.output_edit.text().strip()
        output_dir = Path(out_text).resolve() if out_text else None

        self.task_table.setRowCount(len(files))
        for row, f in enumerate(files):
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(row, 0, idx_item)

            badge_label = QLabel("● 待处理")
            badge_label.setObjectName("badgePending")
            badge_label.setAlignment(Qt.AlignCenter)
            self.task_table.setCellWidget(row, 1, badge_label)

            ext_str = f.suffix.lower().lstrip(".").upper()
            pill_label = QLabel(ext_str)
            if ext_str == "NCM":
                pill_label.setObjectName("pillNcm")
            elif ext_str == "FLAC":
                pill_label.setObjectName("pillFlac")
            else:
                pill_label.setObjectName("pillMp3")
            pill_label.setAlignment(Qt.AlignCenter)
            self.task_table.setCellWidget(row, 2, pill_label)

            # Col 3: Filename
            self.task_table.setItem(row, 3, QTableWidgetItem(f.name))

            # Col 4-11: Empty placeholders before conversion
            self.task_table.setItem(row, 4, QTableWidgetItem("-"))
            self.task_table.setItem(row, 5, QTableWidgetItem("-"))
            self.task_table.setItem(row, 6, QTableWidgetItem("-"))
            self.task_table.setItem(row, 7, QTableWidgetItem("-"))

            track_no_item = QTableWidgetItem("-")
            track_no_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(row, 8, track_no_item)

            track_tot_item = QTableWidgetItem("-")
            track_tot_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(row, 9, track_tot_item)

            disc_no_item = QTableWidgetItem("-")
            disc_no_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(row, 10, disc_no_item)

            lrc_item = QTableWidgetItem("-")
            lrc_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(row, 11, lrc_item)

        self.btn_start.setEnabled(False)
        self.btn_precheck.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("转换中...")
        self.lbl_counts.setText(f"总计 {len(files)} · 成功 0 · 失败 0")

        self.worker = ConvertWorker(
            files=files,
            output_dir=output_dir,
            enrich_netease=self.chk_enrich.isChecked(),
            auto_update_mtime=self.chk_auto_mtime.isChecked(),
            config_path=self.config_path,
        )
        self.worker.sig_batch_start.connect(self._on_worker_batch_start)
        self.worker.sig_item_update.connect(self._on_worker_item_update)
        self.worker.sig_log.connect(self._append_log)
        self.worker.sig_batch_finished.connect(self._on_worker_batch_finished)
        self.worker.start()

    def _on_cancel_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.lbl_status.setText("正在停止...")
            self.worker.cancel()

    def _on_worker_batch_start(self, total: int) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)

    def _on_worker_item_update(
        self, item_dict: dict, completed: int, total: int, log_msg: str
    ) -> None:
        idx = item_dict.get("idx", 1) - 1
        status = item_dict.get("status", "processing")

        if 0 <= idx < self.task_table.rowCount():
            badge_label = QLabel()
            badge_label.setAlignment(Qt.AlignCenter)
            if status == "success":
                badge_label.setText("● 成功")
                badge_label.setObjectName("badgeSuccess")
            elif status == "failed":
                badge_label.setText("● 失败")
                badge_label.setObjectName("badgeFailed")
            else:
                badge_label.setText("● 处理中")
                badge_label.setObjectName("badgePending")
            self.task_table.setCellWidget(idx, 1, badge_label)

            # Col 3: Filename
            self.task_table.setItem(idx, 3, QTableWidgetItem(item_dict.get("name", "")))

            # Metadata columns (blank / - if failed or not available)
            if status == "failed":
                title = "-"
                artist = "-"
                album_artist = "-"
                publisher = "-"
                track_no = "-"
                track_total = "-"
                disc_no = "-"
                has_lyrics = "-"
            else:
                title = item_dict.get("title") or "-"
                artist = item_dict.get("artist") or "-"
                album_artist = item_dict.get("album_artist") or "-"
                publisher = item_dict.get("publisher") or "-"
                track_no = str(item_dict.get("track_number") or "-")
                track_total = str(item_dict.get("track_total") or "-")
                disc_no = str(item_dict.get("disc_number") or "-")
                has_lyrics = item_dict.get("has_lyrics") or "-"

            self.task_table.setItem(idx, 4, QTableWidgetItem(title))
            self.task_table.setItem(idx, 5, QTableWidgetItem(artist))
            self.task_table.setItem(idx, 6, QTableWidgetItem(album_artist))
            self.task_table.setItem(idx, 7, QTableWidgetItem(publisher))

            t_no_item = QTableWidgetItem(track_no)
            t_no_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(idx, 8, t_no_item)

            t_tot_item = QTableWidgetItem(track_total)
            t_tot_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(idx, 9, t_tot_item)

            disc_item = QTableWidgetItem(disc_no)
            disc_item.setTextAlignment(Qt.AlignCenter)
            self.task_table.setItem(idx, 10, disc_item)

            lrc_item = QTableWidgetItem(has_lyrics)
            lrc_item.setTextAlignment(Qt.AlignCenter)
            if has_lyrics == "✓ 有":
                lrc_item.setForeground(QColor("#4ade80"))
            elif has_lyrics == "无":
                lrc_item.setForeground(QColor("#71717a"))
            self.task_table.setItem(idx, 11, lrc_item)

            self.task_table.scrollToItem(self.task_table.item(idx, 0))

        self.progress_bar.setValue(completed)
        fail_cnt = item_dict.get("idx", 1) - completed if status == "failed" else 0
        self.lbl_counts.setText(f"总计 {total} · 成功 {completed} · 失败 {fail_cnt}")

    def _on_worker_batch_finished(
        self, success: int, total: int, failed_items: list[dict[str, Any]]
    ) -> None:
        self.btn_start.setEnabled(True)
        self.btn_precheck.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(total)

        fail_count = len(failed_items)
        self.lbl_counts.setText(f"总计 {total} · 成功 {success} · 失败 {fail_count}")
        self.lbl_status.setText(f"完成 (成功 {success}，失败 {fail_count})")

        if self.chk_auto_mtime.isChecked():
            cfg, _ = get_or_create_config(self.config_path)
            new_mtime = str(cfg.get("process_after_mtime") or "")
            if new_mtime:
                self.time_picker.set_datetime_str(new_mtime)

        self._update_fail_button_state()

        if fail_count > 0:
            QMessageBox.warning(
                self,
                "提示",
                f"转换完成，共有 {fail_count} 个文件失败。\n点击 [失败记录] 可查看详情并重试。",
            )
        else:
            QMessageBox.information(
                self, "完成", f"全部 {total} 个音频文件转换完成。"
            )

    def _append_log(self, message: str, level: str = "info") -> None:
        time_str = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{time_str}] "
        if level == "error":
            color = "#f87171"
        elif level == "warning":
            color = "#fbbf24"
        elif level == "success":
            color = "#4ade80"
        else:
            color = "#8b8ea4"

        html_line = f'<span style="color: #4b5063;">{prefix}</span><span style="color: {color};">{message}</span>'
        self.log_console.appendHtml(html_line)
        self.log_console.moveCursor(QTextCursor.End)

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1500)
        event.accept()

