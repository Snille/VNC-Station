"""Visual layout tool for preparing per-connection VNC/label JSON settings."""

from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import (
    config_path_for,
    load_default_settings,
    load_session_settings,
    save_json,
    scan_connections,
    scan_positions,
)
from .constants import (
    CANCEL_ICON_PATH,
    CHAT_ICON_PATH,
    GEARS_ICON_PATH,
    ICON_PATH,
    MODE_CONTROL,
    MODE_VIEW,
    OPEN_ICON_PATH,
    VNC_POSITIONS_DIR,
)
from .constants import MONITOR_ICON_PATH
from .constants import SAVE_ICON_PATH
from .models import SessionSettings
from .theme import windows_prefers_dark

ICON_TEXT_GAP_PREFIX = "\u2009"  # thin space: slightly tighter icon-to-text gap


class FramelessPreviewWindow(QWidget):
    """Frameless top-level window with drag-inside and edge/corner resize."""

    changed = pyqtSignal()

    EDGE_NONE = 0
    EDGE_LEFT = 1
    EDGE_RIGHT = 2
    EDGE_TOP = 4
    EDGE_BOTTOM = 8

    def __init__(self, title: str, always_on_top: bool = False, parent=None) -> None:
        super().__init__(parent)
        flags = Qt.Window | Qt.FramelessWindowHint
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setMouseTracking(True)
        self.setMinimumSize(30, 20)

        self.title = QLabel(title, self)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-weight:700; background:transparent;")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._resize_margin = 8
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._start_geom = QRect()
        self._start_global = QPoint()
        self._resize_edges = self.EDGE_NONE

    def resizeEvent(self, event) -> None:
        self.title.setGeometry(0, 0, self.width(), 26)
        self.changed.emit()
        super().resizeEvent(event)

    def moveEvent(self, event) -> None:
        self.changed.emit()
        super().moveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self._resize_edges = self._detect_edges(event.pos())
        self._start_geom = self.geometry()
        self._start_global = event.globalPos()
        if self._resize_edges != self.EDGE_NONE:
            self._resizing = True
        else:
            self._dragging = True
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            self._perform_resize(event.globalPos())
            event.accept()
            return
        if self._dragging:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return

        self._update_cursor(self._detect_edges(event.pos()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        self._resizing = False
        self._resize_edges = self.EDGE_NONE
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _perform_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._start_global
        geom = QRect(self._start_geom)

        if self._resize_edges & self.EDGE_LEFT:
            geom.setLeft(geom.left() + delta.x())
        if self._resize_edges & self.EDGE_RIGHT:
            geom.setRight(geom.right() + delta.x())
        if self._resize_edges & self.EDGE_TOP:
            geom.setTop(geom.top() + delta.y())
        if self._resize_edges & self.EDGE_BOTTOM:
            geom.setBottom(geom.bottom() + delta.y())

        if geom.width() < self.minimumWidth():
            if self._resize_edges & self.EDGE_LEFT:
                geom.setLeft(geom.right() - self.minimumWidth() + 1)
            else:
                geom.setRight(geom.left() + self.minimumWidth() - 1)
        if geom.height() < self.minimumHeight():
            if self._resize_edges & self.EDGE_TOP:
                geom.setTop(geom.bottom() - self.minimumHeight() + 1)
            else:
                geom.setBottom(geom.top() + self.minimumHeight() - 1)

        self.setGeometry(geom)

    def _detect_edges(self, p: QPoint) -> int:
        edges = self.EDGE_NONE
        if p.x() <= self._resize_margin:
            edges |= self.EDGE_LEFT
        elif p.x() >= self.width() - self._resize_margin:
            edges |= self.EDGE_RIGHT
        if p.y() <= self._resize_margin:
            edges |= self.EDGE_TOP
        elif p.y() >= self.height() - self._resize_margin:
            edges |= self.EDGE_BOTTOM
        return edges

    def _update_cursor(self, edges: int) -> None:
        if edges in (self.EDGE_LEFT | self.EDGE_TOP, self.EDGE_RIGHT | self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in (self.EDGE_RIGHT | self.EDGE_TOP, self.EDGE_LEFT | self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edges in (self.EDGE_LEFT, self.EDGE_RIGHT):
            self.setCursor(Qt.SizeHorCursor)
        elif edges in (self.EDGE_TOP, self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)


def _set_button_icon(button: QPushButton, icon_path: Path, size_px: int = 16) -> None:
    if not icon_path.exists():
        return
    button.setIcon(QIcon(str(icon_path)))
    button.setIconSize(QSize(size_px, size_px))
    text = button.text()
    if text and not text.startswith((" ", ICON_TEXT_GAP_PREFIX)):
        button.setText(f"{ICON_TEXT_GAP_PREFIX}{text}")


def _make_icon_text_label(text: str, icon_path: Path, size_px: int = 14) -> QWidget:
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    if icon_path.exists():
        icon_label = QLabel()
        pixmap = QPixmap(str(icon_path)).scaled(
            size_px, size_px, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        icon_label.setPixmap(pixmap)
        row.addWidget(icon_label)
    row.addWidget(QLabel(text))
    return wrapper


class SaveTargetDialog(QDialog):
    """Select which existing .vnc target (view/control) receives saved JSON."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Layout To Connection")
        self.resize(420, 120)
        self._targets: List[Tuple[str, str]] = []

        body = QVBoxLayout(self)
        form = QFormLayout()
        body.addLayout(form)
        self.target_box = QComboBox()
        form.addRow("Connection:", self.target_box)
        self._populate()

        buttons = QHBoxLayout()
        body.addLayout(buttons)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        ok = QPushButton("Save")
        _set_button_icon(cancel, CANCEL_ICON_PATH)
        cancel.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        _set_button_icon(ok, SAVE_ICON_PATH)
        ok.setStyleSheet("background:#6741d9; color:white; font-weight:700; border-radius:4px;")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

    def _populate(self) -> None:
        for entry in scan_connections():
            if entry.view_vnc_path is not None:
                self._targets.append((entry.name, MODE_VIEW))
                self.target_box.addItem(f"{entry.name} [view]")
            if entry.control_vnc_path is not None:
                self._targets.append((entry.name, MODE_CONTROL))
                self.target_box.addItem(f"{entry.name} [control]")

    def selected(self) -> Optional[Tuple[str, str]]:
        idx = self.target_box.currentIndex()
        if idx < 0 or idx >= len(self._targets):
            return None
        return self._targets[idx]


class LayoutToolWindow(QMainWindow):
    """Control panel for frameless preview windows and JSON save."""

    window_closed = pyqtSignal()

    def __init__(self, theme_mode: str = "Auto") -> None:
        super().__init__()
        self.settings = load_default_settings()
        self.theme_mode = theme_mode
        self._syncing_form = False
        self._load_targets: List[Tuple[str, str]] = []
        self._position_paths_by_name: dict[str, Path] = {}
        self.setWindowTitle("VNC Layout Tool")
        if GEARS_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(GEARS_ICON_PATH)))
        self.resize(460, 520)

        self.vnc_preview = FramelessPreviewWindow("VNC Preview", always_on_top=False)
        self.label_preview = FramelessPreviewWindow("Label Preview", always_on_top=True)
        self.label_content = QLabel("", self.label_preview)
        self.label_content.setAlignment(Qt.AlignCenter)
        self.label_content.setWordWrap(True)
        self.label_content.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_content.setGeometry(0, 26, self.label_preview.width(), max(20, self.label_preview.height() - 26))
        if ICON_PATH.exists():
            self.vnc_preview.setWindowIcon(QIcon(str(ICON_PATH)))
        if CHAT_ICON_PATH.exists():
            self.label_preview.setWindowIcon(QIcon(str(CHAT_ICON_PATH)))

        self.vnc_preview.changed.connect(self._sync_from_preview_windows)
        self.label_preview.changed.connect(self._sync_from_preview_windows)

        self._build_ui()
        self._apply_settings_to_previews()
        self._apply_theme(self.theme_mode)
        self.vnc_preview.show()
        self._apply_editor_mode(self.mode_box.currentText())

    def _build_ui(self) -> None:
        root_widget = QWidget(self)
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)

        top = QVBoxLayout()
        root.addLayout(top)

        mode_row = QHBoxLayout()
        top.addLayout(mode_row)
        mode_row.addWidget(QLabel("Edit mode:"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["Position", "Session"])
        self.mode_box.currentTextChanged.connect(self._apply_editor_mode)
        mode_row.addWidget(self.mode_box)
        mode_row.addStretch(1)

        self.session_load_widget = QWidget()
        load_row = QHBoxLayout(self.session_load_widget)
        load_row.setContentsMargins(0, 0, 0, 0)
        load_row.addWidget(QLabel("Load settings:"))
        self.load_target_box = QComboBox()
        self._populate_load_targets()
        load_row.addWidget(self.load_target_box, 1)
        load_btn = QPushButton("Load")
        _set_button_icon(load_btn, OPEN_ICON_PATH)
        load_btn.setStyleSheet("background:#660063; color:white; font-weight:700; border-radius:4px;")
        load_btn.clicked.connect(self._load_selected_target_settings)
        load_row.addWidget(load_btn)
        save_current_btn = QPushButton("Save")
        _set_button_icon(save_current_btn, SAVE_ICON_PATH)
        save_current_btn.setStyleSheet("background:#6741d9; color:white; font-weight:700; border-radius:4px;")
        save_current_btn.clicked.connect(self._save_selected_target_settings)
        load_row.addWidget(save_current_btn)
        top.addWidget(self.session_load_widget)

        self.position_tools_widget = QWidget()
        position_row = QHBoxLayout(self.position_tools_widget)
        position_row.setContentsMargins(0, 0, 0, 0)
        position_row.addWidget(_make_icon_text_label("Positions:", MONITOR_ICON_PATH))
        self.position_box = QComboBox()
        self.position_box.setEditable(True)
        self._populate_position_targets()
        position_row.addWidget(self.position_box, 1)
        load_pos_btn = QPushButton("Load Pos")
        _set_button_icon(load_pos_btn, OPEN_ICON_PATH)
        load_pos_btn.setStyleSheet("background:#660063; color:white; font-weight:700; border-radius:4px;")
        load_pos_btn.clicked.connect(self._load_selected_position)
        save_pos_btn = QPushButton("Save Pos")
        _set_button_icon(save_pos_btn, SAVE_ICON_PATH)
        save_pos_btn.setStyleSheet("background:#6741d9; color:white; font-weight:700; border-radius:4px;")
        save_pos_btn.clicked.connect(self._save_selected_position)
        position_row.addWidget(load_pos_btn)
        position_row.addWidget(save_pos_btn)
        top.addWidget(self.position_tools_widget)

        self.info_label = QLabel(
            "Drag inside each preview to move.\n"
            "Resize from edges/corners.\n"
            "Windows are frameless and can be moved outside screen bounds."
        )
        self.info_label.setStyleSheet("color:#666;")
        root.addWidget(self.info_label)

        self.geometry_form_widget = QWidget()
        geometry_form = QFormLayout(self.geometry_form_widget)
        root.addWidget(self.geometry_form_widget)
        self.x_spin = self._spin(geometry_form, "VNC X", -10000, 10000, self.settings.x)
        self.y_spin = self._spin(geometry_form, "VNC Y", -10000, 10000, self.settings.y)
        self.w_spin = self._spin(geometry_form, "VNC Width", 100, 8000, self.settings.width)
        self.h_spin = self._spin(geometry_form, "VNC Height", 100, 8000, self.settings.height)

        self.label_form_widget = QWidget()
        label_form = QFormLayout(self.label_form_widget)
        root.addWidget(self.label_form_widget)
        self.label_text = QLineEdit(self.settings.label_text)
        label_form.addRow("Label Text", self.label_text)
        self.lx_spin = self._spin(label_form, "Label Offset X", -10000, 10000, self.settings.label_x)
        self.ly_spin = self._spin(label_form, "Label Offset Y", -10000, 10000, self.settings.label_y)
        self.lw_spin = self._spin(label_form, "Label Width", 30, 8000, self.settings.label_width)
        self.lh_spin = self._spin(label_form, "Label Height", 20, 4000, self.settings.label_height)
        self.font_spin = self._spin(label_form, "Label Font", 8, 200, self.settings.label_font)
        self.border_spin = self._spin(label_form, "Border Size", 0, 40, self.settings.label_border_size)
        self.bg_text = QLineEdit(self.settings.label_bg)
        self.fg_text = QLineEdit(self.settings.label_font_color)
        self.border_text = QLineEdit(self.settings.label_border_color)
        label_form.addRow("Label Background", self.bg_text)
        label_form.addRow("Label Font Color", self.fg_text)
        label_form.addRow("Label Border Color", self.border_text)

        for spin in [
            self.x_spin,
            self.y_spin,
            self.w_spin,
            self.h_spin,
            self.lx_spin,
            self.ly_spin,
            self.lw_spin,
            self.lh_spin,
            self.font_spin,
            self.border_spin,
        ]:
            spin.valueChanged.connect(self._sync_to_preview_windows)
        for line in [self.label_text, self.bg_text, self.fg_text, self.border_text]:
            line.textChanged.connect(self._sync_to_preview_windows)

        self.session_buttons_widget = QWidget()
        buttons = QHBoxLayout(self.session_buttons_widget)
        buttons.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.session_buttons_widget)
        reset_btn = QPushButton("Reset from default.json")
        save_btn = QPushButton("Save to connection JSON")
        _set_button_icon(save_btn, SAVE_ICON_PATH)
        save_btn.setStyleSheet("background:#6741d9; color:white; font-weight:700; border-radius:4px;")
        reset_btn.clicked.connect(self._reset_defaults)
        save_btn.clicked.connect(self._save_target_json)
        buttons.addWidget(reset_btn)
        buttons.addWidget(save_btn)

        close_row = QHBoxLayout()
        root.addLayout(close_row)
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        _set_button_icon(close_btn, CANCEL_ICON_PATH)
        close_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        close_row.addStretch(1)

        self.mode_box.setCurrentText("Position")
        self._apply_editor_mode(self.mode_box.currentText())

    def _spin(self, form: QFormLayout, label: str, low: int, high: int, value: int) -> QSpinBox:
        field = QSpinBox()
        field.setRange(low, high)
        field.setValue(value)
        form.addRow(label, field)
        return field

    def _apply_theme(self, mode: str) -> None:
        self.theme_mode = mode
        effective = "Dark" if mode == "Auto" and windows_prefers_dark() else ("Light" if mode == "Auto" else mode)
        base_button_style = "QPushButton{padding:1px 5px; border-radius:4px;}"
        if effective == "Dark":
            self.setStyleSheet(
                "QWidget{background:#1f2328;color:#e6edf3;} "
                "QLineEdit,QComboBox,QSpinBox{background:#0d1117;color:#e6edf3;border:1px solid #30363d;}"
                f"{base_button_style}"
            )
        else:
            self.setStyleSheet(base_button_style)
        self._apply_preview_styles()

    def set_theme_mode(self, mode: str) -> None:
        """Apply theme mode from main window selector."""
        self._apply_theme(mode)

    def _apply_editor_mode(self, mode: str) -> None:
        is_position_mode = mode.strip().lower() == "position"
        self.session_load_widget.setVisible(not is_position_mode)
        self.position_tools_widget.setVisible(is_position_mode)
        self.label_form_widget.setVisible(not is_position_mode)
        self.session_buttons_widget.setVisible(not is_position_mode)
        if is_position_mode:
            self.label_preview.hide()
        else:
            self.label_preview.show()
            self.label_preview.raise_()
        if is_position_mode:
            self.info_label.setText(
                "Position mode: editing VNC x/y/width/height only.\n"
                "Label fields are hidden and unchanged."
            )
        else:
            self.info_label.setText(
                "Session mode: edit full VNC + label settings and save to connection JSON."
            )

    def _apply_preview_styles(self) -> None:
        s = self._collect_settings()
        self.vnc_preview.setStyleSheet("background:#e3f2fd; border:2px solid #1971c2;")
        self.vnc_preview.title.setStyleSheet("font-weight:700; color:#111; background:transparent;")
        self.label_preview.setStyleSheet("background:transparent; border:2px dashed #333;")
        self.label_preview.title.setStyleSheet("font-weight:700; color:#111; background:transparent;")
        self.label_content.setText(s.label_text)
        self.label_content.setStyleSheet(
            (
                f"background:{s.label_bg};"
                f"color:{s.label_font_color};"
                f"font-size:{max(8, s.label_font)}px;"
                f"border:{max(0, s.label_border_size)}px solid {s.label_border_color};"
            )
        )
        self.label_content.setGeometry(0, 26, self.label_preview.width(), max(20, self.label_preview.height() - 26))

    def _collect_settings(self) -> SessionSettings:
        return SessionSettings(
            x=self.x_spin.value(),
            y=self.y_spin.value(),
            width=self.w_spin.value(),
            height=self.h_spin.value(),
            label_text=self.label_text.text().strip() or "Label",
            label_x=self.lx_spin.value(),
            label_y=self.ly_spin.value(),
            label_bg=self.bg_text.text().strip() or "white",
            label_width=self.lw_spin.value(),
            label_height=self.lh_spin.value(),
            label_font=self.font_spin.value(),
            label_font_color=self.fg_text.text().strip() or "black",
            label_border_size=self.border_spin.value(),
            label_border_color=self.border_text.text().strip() or "black",
            station_name=self.settings.station_name,
        )

    def _apply_settings_to_previews(self) -> None:
        s = self._collect_settings()
        self.vnc_preview.setGeometry(s.x, s.y, max(100, s.width), max(100, s.height))
        self.label_preview.setGeometry(
            s.x + s.label_x,
            s.y + s.label_y,
            max(30, s.label_width),
            max(20, s.label_height),
        )
        self.label_preview.raise_()
        self._apply_preview_styles()
        self.settings = s

    def _sync_to_preview_windows(self) -> None:
        if self._syncing_form:
            return
        self._apply_settings_to_previews()

    def _sync_from_preview_windows(self) -> None:
        self._syncing_form = True
        self.x_spin.setValue(self.vnc_preview.x())
        self.y_spin.setValue(self.vnc_preview.y())
        self.w_spin.setValue(self.vnc_preview.width())
        self.h_spin.setValue(self.vnc_preview.height())
        self.lx_spin.setValue(self.label_preview.x() - self.vnc_preview.x())
        self.ly_spin.setValue(self.label_preview.y() - self.vnc_preview.y())
        self.lw_spin.setValue(self.label_preview.width())
        self.lh_spin.setValue(self.label_preview.height())
        self._syncing_form = False
        self._apply_preview_styles()
        self.settings = self._collect_settings()

    def _reset_defaults(self) -> None:
        self.settings = load_default_settings()
        self._syncing_form = True
        self.x_spin.setValue(self.settings.x)
        self.y_spin.setValue(self.settings.y)
        self.w_spin.setValue(self.settings.width)
        self.h_spin.setValue(self.settings.height)
        self.label_text.setText(self.settings.label_text)
        self.lx_spin.setValue(self.settings.label_x)
        self.ly_spin.setValue(self.settings.label_y)
        self.lw_spin.setValue(self.settings.label_width)
        self.lh_spin.setValue(self.settings.label_height)
        self.font_spin.setValue(self.settings.label_font)
        self.border_spin.setValue(self.settings.label_border_size)
        self.bg_text.setText(self.settings.label_bg)
        self.fg_text.setText(self.settings.label_font_color)
        self.border_text.setText(self.settings.label_border_color)
        self._syncing_form = False
        self._apply_settings_to_previews()

    def _populate_load_targets(self) -> None:
        self._load_targets.clear()
        self.load_target_box.clear()
        for entry in scan_connections():
            if entry.view_vnc_path is not None:
                self._load_targets.append((entry.name, MODE_VIEW))
                self.load_target_box.addItem(f"{entry.name} [view]")
            if entry.control_vnc_path is not None:
                self._load_targets.append((entry.name, MODE_CONTROL))
                self.load_target_box.addItem(f"{entry.name} [control]")

    def _populate_position_targets(self) -> None:
        self._position_paths_by_name.clear()
        self.position_box.clear()
        self.position_box.addItem("")
        for preset in scan_positions():
            self._position_paths_by_name[preset.name] = preset.path
            self.position_box.addItem(preset.name)

    def _load_selected_position(self) -> None:
        name = self.position_box.currentText().strip()
        if not name:
            QMessageBox.information(self, "Layout Tool", "No position selected.")
            return
        path = self._position_paths_by_name.get(name)
        if path is None or not path.exists():
            QMessageBox.warning(self, "Layout Tool", f"Position file not found:\n{name}")
            self._populate_position_targets()
            return
        data = load_session_settings(path)
        self._syncing_form = True
        self.x_spin.setValue(data.x)
        self.y_spin.setValue(data.y)
        self.w_spin.setValue(data.width)
        self.h_spin.setValue(data.height)
        self._syncing_form = False
        self._apply_settings_to_previews()

    def _save_selected_position(self) -> None:
        name = self.position_box.currentText().strip()
        if not name:
            QMessageBox.information(self, "Layout Tool", "Select a position name first.")
            return
        path = self._position_paths_by_name.get(name, VNC_POSITIONS_DIR / f"{name}.json")
        VNC_POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "x": str(self.x_spin.value()),
            "y": str(self.y_spin.value()),
            "width": str(self.w_spin.value()),
            "height": str(self.h_spin.value()),
            "name": name,
        }
        save_json(path, payload)
        self._populate_position_targets()
        idx = self.position_box.findText(name)
        if idx >= 0:
            self.position_box.setCurrentIndex(idx)
        QMessageBox.information(self, "Layout Tool", f"Saved position:\n{path}")

    def _load_selected_target_settings(self) -> None:
        idx = self.load_target_box.currentIndex()
        if idx < 0 or idx >= len(self._load_targets):
            QMessageBox.information(self, "Layout Tool", "No connection selected.")
            return
        connection_name, mode = self._load_targets[idx]
        cfg = config_path_for(connection_name, mode)
        self.settings = load_session_settings(cfg)
        self._syncing_form = True
        self.x_spin.setValue(self.settings.x)
        self.y_spin.setValue(self.settings.y)
        self.w_spin.setValue(self.settings.width)
        self.h_spin.setValue(self.settings.height)
        self.label_text.setText(self.settings.label_text)
        self.lx_spin.setValue(self.settings.label_x)
        self.ly_spin.setValue(self.settings.label_y)
        self.lw_spin.setValue(self.settings.label_width)
        self.lh_spin.setValue(self.settings.label_height)
        self.font_spin.setValue(self.settings.label_font)
        self.border_spin.setValue(self.settings.label_border_size)
        self.bg_text.setText(self.settings.label_bg)
        self.fg_text.setText(self.settings.label_font_color)
        self.border_text.setText(self.settings.label_border_color)
        self._syncing_form = False
        self._apply_settings_to_previews()
        if self.settings.position_name:
            idx = self.position_box.findText(self.settings.position_name)
            if idx >= 0:
                self.position_box.setCurrentIndex(idx)

    def _save_selected_target_settings(self) -> None:
        idx = self.load_target_box.currentIndex()
        if idx < 0 or idx >= len(self._load_targets):
            QMessageBox.information(self, "Layout Tool", "No connection selected.")
            return
        connection_name, mode = self._load_targets[idx]
        self._sync_from_preview_windows()
        path = config_path_for(connection_name, mode)
        save_json(path, self._collect_settings_for_path(path))
        QMessageBox.information(self, "Layout Tool", f"Saved settings to:\n{path}")

    def _save_target_json(self) -> None:
        dialog = SaveTargetDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return
        selected = dialog.selected()
        if selected is None:
            QMessageBox.information(self, "Layout Tool", "No target selected.")
            return
        connection_name, mode = selected
        self._sync_from_preview_windows()
        path = config_path_for(connection_name, mode)
        save_json(path, self._collect_settings_for_path(path))
        QMessageBox.information(self, "Layout Tool", f"Saved settings to:\n{path}")

    def _collect_settings_for_path(self, path: Path) -> dict:
        merged = self._collect_settings()
        existing = load_session_settings(path)
        merged.position_name = existing.position_name
        merged.linked_session = existing.linked_session
        merged.ks = existing.ks
        return merged.to_json()

    def closeEvent(self, event) -> None:
        self.vnc_preview.close()
        self.label_preview.close()
        self.window_closed.emit()
        super().closeEvent(event)


def main() -> int:
    app = QApplication([])
    window = LayoutToolWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
