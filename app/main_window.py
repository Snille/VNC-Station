"""Main application window: connection list, controls, chat, and coordination."""
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QEvent, QSettings, QSize, QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QCloseEvent, QFont, QIcon, QMovie, QPixmap
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .chat_window import ChatWindow
from .config import (
    config_path_for,
    load_default_mapping,
    load_default_settings,
    load_session_overrides,
    load_session_settings,
    position_by_name,
    resolve_ks_target,
    save_json,
    scan_connections,
    scan_positions,
    set_json_warning_reporter,
    update_session_overrides,
)
from .constants import (
    APP_VERSION,
    CANCEL_ICON_PATH,
    CHAT_ICON_PATH,
    CLEAR_ICON_PATH,
    CONTROL_ICON_PATH,
    DEFAULT_LOCAL_CONFIG_PATH,
    DELETE_ICON_PATH,
    EDIT_ICON_PATH,
    GEARS_ICON_PATH,
    HELLO_INTERVAL_MS,
    ICON_PATH,
    LINK_DARK_ICON_PATH,
    LINK_ICON_PATH,
    LINK_LIGHT_ICON_PATH,
    MODE_CONTROL,
    MODE_VIEW,
    MONITOR_ICON_PATH,
    NOTICE_SOUND_PATH,
    SAVE_ICON_PATH,
    SPREADSHEET_ICON_PATH,
    SESSION_BROADCAST_INTERVAL_MS,
    STATION_PRESENCE_CHECK_MS,
    UDP_PORT,
    USER_CONTROL_ICON_PATH,
    USER_DARK_ICON_PATH,
    USER_LIGHT_ICON_PATH,
    VNC_SETUPS_DIR,
    UNLOCK_ICON_PATH,
    UNTAG_ICON_PATH,
    VIEW_ICON_PATH,
)
from .logic import format_elapsed_duration, parse_chat_command
from .models import ConnectionEntry, SessionSettings
from .network import NetworkBus
from .settings_dialog import SettingsDialog
from .settings_window import SettingsWindow
from .theme import windows_prefers_dark
from .toast import ToastLabel
from .tools import (
    export_config_bundle,
    import_config_bundle,
    suggested_export_name,
    validate_runtime_configuration_details,
)
from .vnc import SessionManager
from .position_settings import PositionSettingsWindow
from .session_settings import SessionSettingsWindow

LOGGER = logging.getLogger(__name__)
ICON_TEXT_GAP_PREFIX = "\u2009"  # thin space: slightly tighter icon-to-text gap
BUTTON_ICON_PATH_PROPERTY = "button_icon_path"
BUTTON_ICON_BASE_SIZE_PROPERTY = "button_icon_base_size"
BUTTON_TEXT_RAW_PROPERTY = "button_text_raw"
BUTTON_CHROME = "font-weight:700; padding:2px 6px 4px 6px; border:none; border-radius:4px;"


def _icon_size_for_font_size(point_size: int) -> int:
    """Return a small icon size that tracks UI font size."""
    return max(13, min(30, int(point_size * 1.35)))


def _status_indicator_size_for_font_size(point_size: int) -> int:
    """Return a slightly larger status indicator size that scales with app font."""
    return max(18, min(34, int(point_size * 1.8)))


def _current_app_font_size() -> int:
    app = QApplication.instance()
    if app is None:
        return 10
    point_size = app.font().pointSize()
    return point_size if point_size > 0 else 10


def _apply_scaled_icon_size(button: QPushButton) -> None:
    """Update one button icon size from current application font."""
    if not bool(button.property("icon_scale_with_font")):
        return
    size_px = _icon_size_for_font_size(_current_app_font_size())
    button.setIconSize(QSize(size_px, size_px))


def _button_icons_enabled() -> bool:
    settings = QSettings("VNCStation", "Controller")
    value = settings.value("use_button_icons", "true")
    text = str(value).strip().lower()
    return text not in {"0", "false", "no", "off"}


def _button_text_without_prefix(text: str) -> str:
    return text.lstrip(f" {ICON_TEXT_GAP_PREFIX}")


def _set_button_text_for_icon_state(button: QPushButton, text: str) -> None:
    raw_text = _button_text_without_prefix(text)
    button.setProperty(BUTTON_TEXT_RAW_PROPERTY, raw_text)
    if _button_icons_enabled() and raw_text:
        button.setText(f"{ICON_TEXT_GAP_PREFIX}{raw_text}")
    else:
        button.setText(raw_text)


def _refresh_button_icon_state(button: QPushButton) -> None:
    raw_text = str(button.property(BUTTON_TEXT_RAW_PROPERTY) or _button_text_without_prefix(button.text()))
    button.setProperty(BUTTON_TEXT_RAW_PROPERTY, raw_text)
    if _button_icons_enabled():
        icon_path = str(button.property(BUTTON_ICON_PATH_PROPERTY) or "").strip()
        if icon_path and Path(icon_path).exists():
            button.setIcon(QIcon(icon_path))
            button.setProperty("icon_scale_with_font", True)
            _apply_scaled_icon_size(button)
        _set_button_text_for_icon_state(button, raw_text)
        return
    button.setIcon(QIcon())
    button.setProperty("icon_scale_with_font", False)
    button.setText(raw_text)


def _ensure_icon_text_spacing(button: QPushButton) -> None:
    """Add a small gap before button text when an icon is present."""
    text = button.text()
    if not text or text.startswith((" ", ICON_TEXT_GAP_PREFIX)):
        return
    button.setText(f"{ICON_TEXT_GAP_PREFIX}{text}")


def _set_button_icon(button: QPushButton, icon_path: Path, size_px: int = 16) -> None:
    """Apply a small icon when the asset exists (safe in source/frozen runs)."""
    button.setProperty(BUTTON_ICON_PATH_PROPERTY, str(icon_path))
    button.setProperty(BUTTON_TEXT_RAW_PROPERTY, _button_text_without_prefix(button.text()))
    if size_px > 0:
        button.setProperty(BUTTON_ICON_BASE_SIZE_PROPERTY, int(size_px))
        button.setProperty("icon_base_size", int(size_px))
    _refresh_button_icon_state(button)


def _make_icon_text_label(text: str, icon_path: Path, size_px: int = 14) -> QWidget:
    """Build a compact icon+text label widget."""
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


def _set_compact_button(button: QPushButton) -> None:
    """Prevent row layouts from stretching action buttons too wide."""
    button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    button.setMinimumHeight(24)


def _set_compact_combo(combo: QComboBox, min_width_px: int = 20) -> None:
    """Keep combo responsive with a very small pixel minimum width."""
    combo.setMinimumWidth(max(20, int(min_width_px)))
    combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)


def _match_button_widths(*buttons: QPushButton) -> None:
    """Give a button group the same width for visual consistency."""
    if not buttons:
        return
    width = max(button.sizeHint().width() for button in buttons)
    for button in buttons:
        button.setMinimumWidth(width)


class ConnectionRow:
    """UI bundle for one connection entry and its row-level buttons."""

    def __init__(
        self,
        entry: ConnectionEntry,
        callbacks: Dict[str, object],
        position_names: List[str],
        link_options: List[Tuple[str, str]],
    ) -> None:
        """Build one connection row and wire mode-specific controls."""
        self.entry = entry
        self._callbacks = callbacks
        self._position_names = list(position_names)
        self._link_options = list(link_options)
        self._syncing = False
        self._status_indicators: List[Tuple[str, str]] = []
        self._status_indicator_movies: List[QMovie] = []
        self._status_indicator_icon_px = _status_indicator_size_for_font_size(_current_app_font_size())
        self._mode_highlight: Dict[str, str] = {MODE_VIEW: "", MODE_CONTROL: ""}
        self._indicators_bg_color = ""
        self._mode_open_state: Dict[str, bool] = {MODE_VIEW: False, MODE_CONTROL: False}
        self._owner_header_in_use = False
        self._owner_header_mode = ""
        self._owner_header_theme = "Light"
        self._minimized = False
        self.widget = QFrame()
        self.widget.setObjectName("connectionRowCard")
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(8, 5, 8, 5)
        outer.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        outer.addLayout(header_row)

        self.tag = QCheckBox()
        self.name_btn = QPushButton(entry.name)
        self.name_btn.setStyleSheet(f"{BUTTON_CHROME} text-align:left;")
        self.name_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.name_btn.clicked.connect(lambda: self.tag.setChecked(not self.tag.isChecked()))
        header_row.addWidget(self.tag)
        header_row.addWidget(self.name_btn)
        self.link_header_icon = QLabel()
        self.link_header_icon.setVisible(False)
        header_row.addWidget(self.link_header_icon)
        self.minimized_ks_btn = QPushButton("KS")
        self.minimized_ksv_btn = QPushButton("KSV")
        self.minimized_ksc_btn = QPushButton("KSC")
        _set_button_icon(self.minimized_ks_btn, SPREADSHEET_ICON_PATH)
        _set_button_icon(self.minimized_ksv_btn, SPREADSHEET_ICON_PATH)
        _set_button_icon(self.minimized_ksc_btn, SPREADSHEET_ICON_PATH)
        _set_compact_button(self.minimized_ks_btn)
        _set_compact_button(self.minimized_ksv_btn)
        _set_compact_button(self.minimized_ksc_btn)
        self.minimized_ks_btn.clicked.connect(lambda: callbacks["open_ks"](entry.name, "shared"))
        self.minimized_ksv_btn.clicked.connect(lambda: callbacks["open_ks"](entry.name, MODE_VIEW))
        self.minimized_ksc_btn.clicked.connect(lambda: callbacks["open_ks"](entry.name, MODE_CONTROL))
        self.minimized_ks_btn.setVisible(False)
        self.minimized_ksv_btn.setVisible(False)
        self.minimized_ksc_btn.setVisible(False)
        header_row.addWidget(self.minimized_ks_btn)
        header_row.addWidget(self.minimized_ksv_btn)
        header_row.addWidget(self.minimized_ksc_btn)
        self.minimized_view_btn = QPushButton("View")
        _set_button_icon(self.minimized_view_btn, VIEW_ICON_PATH)
        _set_compact_button(self.minimized_view_btn)
        self.minimized_view_btn.clicked.connect(lambda: callbacks["toggle_open"](entry.name, MODE_VIEW))
        self.minimized_view_btn.setVisible(False)
        header_row.addWidget(self.minimized_view_btn)
        self.minimized_control_btn = QPushButton("Control")
        _set_button_icon(self.minimized_control_btn, CONTROL_ICON_PATH)
        _set_compact_button(self.minimized_control_btn)
        self.minimized_control_btn.clicked.connect(lambda: callbacks["toggle_open"](entry.name, MODE_CONTROL))
        self.minimized_control_btn.setVisible(False)
        header_row.addWidget(self.minimized_control_btn)
        self.indicators_widget = QWidget()
        self.indicators_widget.setObjectName("sensorIndicators")
        self.indicators_layout = QHBoxLayout(self.indicators_widget)
        self.indicators_layout.setContentsMargins(0, 0, 0, 0)
        self.indicators_layout.setSpacing(2)
        header_row.addStretch(1)
        header_row.addWidget(self.indicators_widget)
        self.owner_header_icon = QLabel()
        self.owner_header_icon.setVisible(False)
        header_row.addWidget(self.owner_header_icon)
        self.minimize_btn = QPushButton("-")
        _set_compact_button(self.minimize_btn)
        self.minimize_btn.setToolTip("Minimize this session card")
        self.minimize_btn.clicked.connect(self.toggle_minimized)
        header_row.addWidget(self.minimize_btn)

        self.body_widget = QWidget()
        body_row = QHBoxLayout(self.body_widget)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(6)
        outer.addWidget(self.body_widget)

        self.child_container = QWidget()
        self.child_layout = QVBoxLayout(self.child_container)
        self.child_layout.setContentsMargins(22, 2, 0, 0)
        self.child_layout.setSpacing(6)
        outer.addWidget(self.child_container)
        self.child_container.setVisible(False)

        self.details_widget = QWidget()
        left_col = QVBoxLayout(self.details_widget)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(3)
        body_row.addWidget(self.details_widget, 1)

        self.actions_widget = QWidget()
        right_col = QVBoxLayout(self.actions_widget)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(3)
        right_col.setAlignment(Qt.AlignTop | Qt.AlignRight)
        body_row.addWidget(self.actions_widget)

        self.owner_label = QLabel("Owner: available")
        self.owner_label.setObjectName("ownerLabel")
        left_col.addWidget(self.owner_label)

        self.position_view = QComboBox()
        self.position_control = QComboBox()
        _set_compact_combo(self.position_view)
        _set_compact_combo(self.position_control)
        self._fill_position_combo(self.position_view)
        self._fill_position_combo(self.position_control)
        self.position_view.currentTextChanged.connect(
            lambda _text: self._on_position_combo_changed(MODE_VIEW)
        )
        self.position_control.currentTextChanged.connect(
            lambda _text: self._on_position_combo_changed(MODE_CONTROL)
        )
        pos_header = QHBoxLayout()
        pos_header.addWidget(_make_icon_text_label("Position", MONITOR_ICON_PATH))
        pos_header.addStretch(1)
        left_col.addLayout(pos_header)
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("V"))
        pos_row.addWidget(self.position_view, 1)
        pos_row.addWidget(QLabel("C"))
        pos_row.addWidget(self.position_control, 1)
        left_col.addLayout(pos_row)

        self.link_view = QComboBox()
        self.link_control = QComboBox()
        _set_compact_combo(self.link_view)
        _set_compact_combo(self.link_control)
        self._fill_link_combo(self.link_view, MODE_VIEW)
        self._fill_link_combo(self.link_control, MODE_CONTROL)
        self.link_view.currentTextChanged.connect(lambda _text: self._on_link_combo_changed(MODE_VIEW))
        self.link_control.currentTextChanged.connect(
            lambda _text: self._on_link_combo_changed(MODE_CONTROL)
        )
        link_header = QHBoxLayout()
        link_header.addWidget(_make_icon_text_label("Link", LINK_ICON_PATH))
        link_header.addStretch(1)
        left_col.addLayout(link_header)
        link_row = QHBoxLayout()
        link_row.addWidget(QLabel("V"))
        link_row.addWidget(self.link_view, 1)
        link_row.addWidget(QLabel("C"))
        link_row.addWidget(self.link_control, 1)
        left_col.addLayout(link_row)

        self.ks_btn = QPushButton("KS")
        self.ksv_btn = QPushButton("KSV")
        self.ksc_btn = QPushButton("KSC")
        _set_button_icon(self.ks_btn, SPREADSHEET_ICON_PATH)
        _set_button_icon(self.ksv_btn, SPREADSHEET_ICON_PATH)
        _set_button_icon(self.ksc_btn, SPREADSHEET_ICON_PATH)
        _set_compact_button(self.ks_btn)
        _set_compact_button(self.ksv_btn)
        _set_compact_button(self.ksc_btn)
        self.ks_btn.clicked.connect(lambda: callbacks["open_ks"](entry.name, "shared"))
        self.ksv_btn.clicked.connect(lambda: callbacks["open_ks"](entry.name, MODE_VIEW))
        self.ksc_btn.clicked.connect(lambda: callbacks["open_ks"](entry.name, MODE_CONTROL))
        ks_row = QVBoxLayout()
        ks_row.setContentsMargins(0, 0, 0, 0)
        ks_row.setSpacing(3)
        ks_row.setAlignment(Qt.AlignRight)
        ks_row.addWidget(self.ks_btn, 0, Qt.AlignRight)
        ks_row.addWidget(self.ksv_btn, 0, Qt.AlignRight)
        ks_row.addWidget(self.ksc_btn, 0, Qt.AlignRight)
        right_col.addLayout(ks_row)

        self.view_btn = QPushButton("View")
        _set_button_icon(self.view_btn, VIEW_ICON_PATH)
        _set_compact_button(self.view_btn)
        self.view_btn.clicked.connect(lambda: callbacks["toggle_open"](entry.name, MODE_VIEW))
        self.control_btn = QPushButton("Control")
        _set_button_icon(self.control_btn, CONTROL_ICON_PATH)
        _set_compact_button(self.control_btn)
        self.control_btn.clicked.connect(lambda: callbacks["toggle_open"](entry.name, MODE_CONTROL))
        open_row = QVBoxLayout()
        open_row.setContentsMargins(0, 0, 0, 0)
        open_row.setSpacing(3)
        open_row.setAlignment(Qt.AlignRight)
        open_row.addWidget(self.view_btn, 0, Qt.AlignRight)
        open_row.addWidget(self.control_btn, 0, Qt.AlignRight)
        right_col.addLayout(open_row)

        self._match_action_button_widths()
        self.update_action_button_font(_current_app_font_size())

        view_available = entry.view_vnc_path is not None
        control_available = entry.control_vnc_path is not None

        self._apply_mode_button_style(self.view_btn, view_available, "#2f9e44")
        self._apply_mode_button_style(self.control_btn, control_available, "#b87400")
        self._apply_mode_button_style(self.minimized_view_btn, view_available, "#2f9e44")
        self._apply_mode_button_style(self.minimized_control_btn, control_available, "#b87400")
        self._apply_mode_button_style(self.minimized_ksv_btn, view_available, "#666666")
        self._apply_mode_button_style(self.minimized_ksc_btn, control_available, "#666666")
        self._apply_mode_button_style(self.ksv_btn, view_available, "#666666")
        self._apply_mode_button_style(self.ksc_btn, control_available, "#666666")
        self._apply_minimize_button_style()
        self._refresh_ks_buttons("", "", "", "")
        self._update_minimized_action_buttons()
        self._update_link_header_icon()

    def set_mode_open_state(self, mode: str, is_open: bool, available: bool) -> None:
        """Toggle row action text between open/close while keeping icon."""
        self._mode_open_state[mode] = bool(is_open)
        if mode == MODE_VIEW:
            view_label = "Close" if is_open else self._view_button_label()
            _set_button_text_for_icon_state(self.view_btn, view_label)
            self._apply_mode_button_style(
                self.view_btn,
                available,
                "#2f9e44",
                self._mode_highlight.get(MODE_VIEW, ""),
            )
            _set_button_text_for_icon_state(self.minimized_view_btn, view_label)
            self._apply_mode_button_style(
                self.minimized_view_btn,
                available,
                "#2f9e44",
                self._mode_highlight.get(MODE_VIEW, ""),
            )
            return
        _set_button_text_for_icon_state(self.control_btn, "Close" if is_open else "Control")
        self._apply_mode_button_style(
            self.control_btn,
            available,
            "#b87400",
            self._mode_highlight.get(MODE_CONTROL, ""),
        )
        _set_button_text_for_icon_state(self.minimized_control_btn, "Close" if is_open else "Control")
        self._apply_mode_button_style(
            self.minimized_control_btn,
            available,
            "#b87400",
            self._mode_highlight.get(MODE_CONTROL, ""),
        )

    def _notify_position_change(self, mode: str) -> None:
        if self._syncing:
            return
        self._callbacks["position_changed"](self.entry.name, mode)

    def _on_position_combo_changed(self, mode: str) -> None:
        self._refresh_mode_button_labels(mode)
        self._update_minimized_action_buttons()
        self._notify_position_change(mode)

    def _notify_link_change(self, mode: str) -> None:
        if self._syncing:
            return
        self._callbacks["link_changed"](self.entry.name, mode)

    def _on_link_combo_changed(self, mode: str) -> None:
        self._update_link_header_icon()
        self._notify_link_change(mode)

    def _fill_position_combo(self, combo: QComboBox) -> None:
        combo.clear()
        combo.addItem("")
        combo.addItems(self._position_names)

    def _fill_link_combo(self, combo: QComboBox, mode: str) -> None:
        combo.clear()
        combo.addItem("")
        for token, label in self._link_options:
            if token == self._make_session_token(self.entry.name, mode):
                continue
            combo.addItem(label, token)

    def refresh_option_sets(self, position_names: List[str], link_options: List[Tuple[str, str]]) -> None:
        """Refresh position/link dropdown choices while preserving current values."""
        self._position_names = list(position_names)
        self._link_options = list(link_options)
        current_pos_view = self.selected_position(MODE_VIEW)
        current_pos_control = self.selected_position(MODE_CONTROL)
        current_link_view = self.selected_link(MODE_VIEW)
        current_link_control = self.selected_link(MODE_CONTROL)
        self._syncing = True
        self._fill_position_combo(self.position_view)
        self._fill_position_combo(self.position_control)
        self._fill_link_combo(self.link_view, MODE_VIEW)
        self._fill_link_combo(self.link_control, MODE_CONTROL)
        self._set_combo_text(self.position_view, current_pos_view)
        self._set_combo_text(self.position_control, current_pos_control)
        self._set_combo_data(self.link_view, current_link_view)
        self._set_combo_data(self.link_control, current_link_control)
        self._syncing = False

    def is_minimized(self) -> bool:
        return self._minimized

    def set_minimized(self, minimized: bool) -> None:
        self._minimized = bool(minimized)
        self.body_widget.setVisible(not self._minimized)
        self._refresh_child_visibility()
        self._update_minimized_action_buttons()
        self._update_owner_header_icon()
        self.minimize_btn.setText("+" if self._minimized else "-")
        self.minimize_btn.setToolTip(
            "Restore this session card" if self._minimized else "Minimize this session card"
        )

    def toggle_minimized(self) -> None:
        self.set_minimized(not self._minimized)
        minimized_changed = self._callbacks.get("minimized_changed")
        if callable(minimized_changed):
            minimized_changed()

    @staticmethod
    def _make_session_token(connection_name: str, mode: str) -> str:
        return f"{connection_name}|{mode}"

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def selected_position(self, mode: str) -> str:
        combo = self.position_view if mode == MODE_VIEW else self.position_control
        return combo.currentText().strip()

    def set_selected_position(self, mode: str, name: str) -> None:
        combo = self.position_view if mode == MODE_VIEW else self.position_control
        self._syncing = True
        self._set_combo_text(combo, name.strip())
        self._syncing = False
        self._refresh_mode_button_labels(mode)
        self._update_minimized_action_buttons()

    def selected_link(self, mode: str) -> str:
        combo = self.link_view if mode == MODE_VIEW else self.link_control
        data = combo.currentData()
        if not data:
            return ""
        return str(data)

    def set_selected_link(self, mode: str, token: str) -> None:
        combo = self.link_view if mode == MODE_VIEW else self.link_control
        self._syncing = True
        self._set_combo_data(combo, token.strip())
        self._syncing = False
        self._update_link_header_icon()

    def clear_child_rows(self) -> None:
        while self.child_layout.count():
            item = self.child_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._refresh_child_visibility()

    def add_child_row(self, child_row: "ConnectionRow") -> None:
        self.child_layout.addWidget(child_row.widget)
        self._refresh_child_visibility()

    def _refresh_child_visibility(self) -> None:
        self.child_container.setVisible(not self._minimized and self.child_layout.count() > 0)

    def _refresh_ks_buttons(
        self, view_ks: str, control_ks: str, view_label: str, control_label: str
    ) -> None:
        view_label = view_label.strip()
        control_label = control_label.strip()
        same = bool(
            view_ks
            and control_ks
            and view_ks == control_ks
            and view_label == control_label
        )
        view_only = bool(view_ks) and not bool(control_ks)
        control_only = bool(control_ks) and not bool(view_ks)
        both_different = bool(view_ks) and bool(control_ks) and not same

        self.ks_btn.setVisible(same)
        self.ksv_btn.setVisible(view_only or both_different)
        self.ksc_btn.setVisible(control_only or both_different)
        self.minimized_ks_btn.setVisible(self._minimized and same)
        self.minimized_ksv_btn.setVisible(self._minimized and (view_only or both_different))
        self.minimized_ksc_btn.setVisible(self._minimized and (control_only or both_different))
        self.ks_btn.setEnabled(same)
        self.minimized_ks_btn.setEnabled(same)
        _set_button_text_for_icon_state(self.ksv_btn, view_label or ("KS" if view_only else "KSV"))
        _set_button_text_for_icon_state(self.ksc_btn, control_label or ("KS" if control_only else "KSC"))
        _set_button_text_for_icon_state(
            self.minimized_ksv_btn, view_label or ("KS" if view_only else "KSV")
        )
        _set_button_text_for_icon_state(
            self.minimized_ksc_btn, control_label or ("KS" if control_only else "KSC")
        )
        if same:
            _set_button_text_for_icon_state(self.ks_btn, view_label or control_label or "KS")
            _set_button_text_for_icon_state(
                self.minimized_ks_btn, view_label or control_label or "KS"
            )
            self.ks_btn.setStyleSheet(
                "background:#666666; color:white; font-weight:700; "
                "padding:2px 6px 4px 6px; border:none; border-radius:4px;"
            )
            self.minimized_ks_btn.setStyleSheet(
                "background:#666666; color:white; font-weight:700; "
                "padding:2px 6px 4px 6px; border:none; border-radius:4px;"
            )
        self._match_action_button_widths()

    def set_ks_paths(
        self, view_ks: str, control_ks: str, view_label: str = "", control_label: str = ""
    ) -> None:
        self._refresh_ks_buttons(
            view_ks.strip(),
            control_ks.strip(),
            view_label.strip(),
            control_label.strip(),
        )

    def _match_action_button_widths(self) -> None:
        """Keep session action buttons at one shared width when visible."""
        buttons = [self.ks_btn, self.ksv_btn, self.ksc_btn, self.view_btn, self.control_btn]
        probe_texts = {
            self.ks_btn: "KS",
            self.ksv_btn: "KSV",
            self.ksc_btn: "KSC",
            self.view_btn: "View",
            self.control_btn: "Control",
        }
        width = 0
        for button in buttons:
            original_text = button.text()
            original_raw = str(
                button.property(BUTTON_TEXT_RAW_PROPERTY) or _button_text_without_prefix(button.text())
            )
            raw_text = original_raw
            text_candidates = [raw_text, probe_texts.get(button, "")]
            if button in (self.view_btn, self.control_btn):
                text_candidates.append("Close")
            for candidate in text_candidates:
                if not candidate:
                    continue
                _set_button_text_for_icon_state(button, candidate)
                width = max(width, button.sizeHint().width())
            button.setProperty(BUTTON_TEXT_RAW_PROPERTY, original_raw)
            button.setText(original_text)
        if width <= 0:
            return
        for button in buttons:
            button.setMinimumWidth(width)
            button.setMaximumWidth(width)

    def _view_button_label(self) -> str:
        selected_view = self.selected_position(MODE_VIEW)
        return selected_view or "View"

    def _refresh_mode_button_labels(self, mode: str) -> None:
        if mode != MODE_VIEW:
            return
        available = self.entry.view_vnc_path is not None
        is_open = self._mode_open_state.get(MODE_VIEW, False)
        self.set_mode_open_state(MODE_VIEW, is_open, available)
        self._match_action_button_widths()

    @staticmethod
    def _apply_mode_button_style(button: QPushButton, available: bool, active_bg: str, highlight_bg: str = "") -> None:
        """Set clear visual state for available/unavailable mode buttons."""
        button.setEnabled(available)
        if available:
            chosen_bg = highlight_bg.strip() or active_bg
            button.setStyleSheet(
                f"background:{chosen_bg}; color:white; {BUTTON_CHROME}"
            )
            button.setToolTip("")
            return
        button.setStyleSheet(
            f"background:#edf0f3; color:#6b7280; {BUTTON_CHROME}"
        )
        button.setToolTip("No .vnc file available for this mode")

    def _apply_minimize_button_style(self) -> None:
        self.minimize_btn.setStyleSheet(
            f"background:#5f6b7a; color:white; {BUTTON_CHROME}"
        )

    def set_mode_background_color(self, mode: str, color_text: str) -> None:
        self._mode_highlight[mode] = color_text.strip()
        if mode == MODE_VIEW:
            available = self.entry.view_vnc_path is not None
            is_open = self._mode_open_state.get(MODE_VIEW, False)
            self.set_mode_open_state(MODE_VIEW, is_open, available)
            return
        available = self.entry.control_vnc_path is not None
        is_open = self._mode_open_state.get(MODE_CONTROL, False)
        self.set_mode_open_state(MODE_CONTROL, is_open, available)

    def set_indicators_background_color(self, color_text: str) -> None:
        self._indicators_bg_color = color_text.strip()
        if self._indicators_bg_color:
            self.indicators_widget.setStyleSheet(
                "QWidget#sensorIndicators {"
                f"background:{self._indicators_bg_color};"
                " border-radius:4px; padding:1px 3px;}"
                "QWidget#sensorIndicators QLabel {"
                " background:transparent;}"
            )
        else:
            self.indicators_widget.setStyleSheet("")
        self.indicators_widget.setVisible(bool(self._status_indicators) or bool(self._indicators_bg_color))

    def set_status_indicators(self, indicators: List[Tuple[str, str]]) -> None:
        """Show multiple custom status icons in row header."""
        self._status_indicators = []
        for icon_path, tooltip in indicators:
            path_text = str(icon_path).strip()
            tip_text = str(tooltip).strip()
            if path_text:
                self._status_indicators.append((path_text, tip_text))
        self._render_status_indicator()

    def update_status_indicator_size(self, point_size: int) -> None:
        """Scale status indicator icon based on current app font size."""
        self._status_indicator_icon_px = _status_indicator_size_for_font_size(point_size)
        self._render_status_indicator()
        self._update_link_header_icon()
        self._update_owner_header_icon()

    def update_action_button_font(self, point_size: int) -> None:
        button_font = QFont(QApplication.instance().font() if QApplication.instance() is not None else QFont())
        base_size = point_size if point_size > 0 else button_font.pointSize()
        if base_size <= 0:
            base_size = 10
        button_font.setPointSize(base_size)
        self.ks_btn.setFont(button_font)
        self.ksv_btn.setFont(button_font)
        self.ksc_btn.setFont(button_font)
        self.view_btn.setFont(button_font)
        self.control_btn.setFont(button_font)
        self.minimized_ks_btn.setFont(button_font)
        self.minimized_ksv_btn.setFont(button_font)
        self.minimized_ksc_btn.setFont(button_font)
        self.minimized_view_btn.setFont(button_font)
        self.minimized_control_btn.setFont(button_font)

    def _render_status_indicator(self) -> None:
        for movie in self._status_indicator_movies:
            movie.stop()
        self._status_indicator_movies.clear()
        while self.indicators_layout.count():
            item = self.indicators_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        visible_count = 0
        for icon_path_text, tooltip in self._status_indicators:
            icon_path = Path(icon_path_text)
            if not icon_path.exists():
                continue
            pixmap = QPixmap(str(icon_path)).scaled(
                self._status_indicator_icon_px,
                self._status_indicator_icon_px,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            label = QLabel()
            label.setFixedSize(self._status_indicator_icon_px + 2, self._status_indicator_icon_px + 2)
            if icon_path.suffix.lower() == ".gif":
                movie = QMovie(str(icon_path))
                movie.setScaledSize(QSize(self._status_indicator_icon_px, self._status_indicator_icon_px))
                label.setMovie(movie)
                movie.start()
                self._status_indicator_movies.append(movie)
            else:
                label.setPixmap(pixmap)
            label.setToolTip(tooltip)
            self.indicators_layout.addWidget(label)
            visible_count += 1
        self.indicators_widget.setVisible(visible_count > 0 or bool(self._indicators_bg_color))

    def set_owner_in_use(self, in_use: bool, mode: str = "") -> None:
        self._owner_header_in_use = bool(in_use)
        self._owner_header_mode = mode.strip().lower() if self._owner_header_in_use else ""
        self._update_owner_header_icon()

    def set_effective_theme(self, theme: str) -> None:
        self._owner_header_theme = "Dark" if str(theme).strip().lower() == "dark" else "Light"
        self._update_link_header_icon()
        self._update_owner_header_icon()

    def _set_header_icon(self, label: QLabel, icon_path: Path, tooltip: str, visible: bool) -> None:
        label.setVisible(visible)
        if not visible:
            label.clear()
            return
        pixmap = QPixmap(str(icon_path)).scaled(
            self._status_indicator_icon_px,
            self._status_indicator_icon_px,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        label.setPixmap(pixmap)
        label.setFixedSize(self._status_indicator_icon_px + 2, self._status_indicator_icon_px + 2)
        label.setToolTip(tooltip)

    def _update_owner_header_icon(self) -> None:
        visible = self._minimized and self._owner_header_in_use
        if self._owner_header_mode == MODE_CONTROL:
            icon_path = USER_CONTROL_ICON_PATH
        else:
            icon_path = USER_DARK_ICON_PATH if self._owner_header_theme == "Dark" else USER_LIGHT_ICON_PATH
        self._set_header_icon(self.owner_header_icon, icon_path, "Session currently in use", visible)

    def _update_link_header_icon(self) -> None:
        has_link = bool(self.selected_link(MODE_VIEW) or self.selected_link(MODE_CONTROL))
        icon_path = LINK_DARK_ICON_PATH if self._owner_header_theme == "Dark" else LINK_LIGHT_ICON_PATH
        self._set_header_icon(self.link_header_icon, icon_path, "Session link configured", has_link)

    def _update_minimized_action_buttons(self) -> None:
        self.minimized_view_btn.setVisible(self._minimized and bool(self.selected_position(MODE_VIEW)))
        self.minimized_control_btn.setVisible(self._minimized and bool(self.selected_position(MODE_CONTROL)))
        self.minimized_ks_btn.setVisible(self._minimized and not self.ks_btn.isHidden())
        self.minimized_ksv_btn.setVisible(self._minimized and not self.ksv_btn.isHidden())
        self.minimized_ksc_btn.setVisible(self._minimized and not self.ksc_btn.isHidden())

class MainWindow(QMainWindow):
    """Primary controller window that coordinates all app subsystems."""
    binary_sensor_states_received = pyqtSignal(object)
    json_warning_received = pyqtSignal(str)

    def __init__(self) -> None:
        """Initialize state, services, and build the full UI."""
        super().__init__()
        self._pending_json_warnings: List[str] = []
        self.json_warning_received.connect(self._display_json_warning)
        set_json_warning_reporter(self._queue_json_warning)
        self.settings_store = QSettings("VNCStation", "Controller")
        self.default_settings = load_default_settings()
        self.station_name = self.default_settings.station_name
        self.topic = "#General"
        self.away_message = ""
        self.theme_mode = str(self.settings_store.value("theme_mode", "Auto"))
        self.font_size = self._load_font_size_setting()
        self._apply_global_font_size(self.font_size, persist=False)
        self.effective_theme = "Dark" if windows_prefers_dark() else "Light"
        self.reconnect_on_drop = str(self.settings_store.value("reconnect_on_drop", "false")).lower() == "true"
        self.udp_port = self._load_udp_port_setting()
        self.follow_links_on_tagged = self._load_follow_links_on_tagged_setting()
        self.connections = scan_connections()
        self.position_names: List[str] = [p.name for p in scan_positions()]
        self.session_link_options: List[Tuple[str, str]] = self._build_session_link_options()
        self.rows: Dict[str, ConnectionRow] = {}
        self._suspend_tag_auto_assign = False
        # Tracks latest remote holder per (connection, mode) by station id.
        self._remote_mode_holders: Dict[Tuple[str, str], str] = {}
        # Station id -> latest seen station display name.
        self._station_names_by_id: Dict[str, str] = {}
        self._online_snapshot: set[str] = set()
        self._startup_sync_pending = True
        self._startup_sync_attempts = 0
        self._positions_tool_window: Optional[PositionSettingsWindow] = None
        self._sessions_tool_window: Optional[SessionSettingsWindow] = None
        self._settings_window: Optional[SettingsWindow] = None
        self._binary_sensor_by_connection: Dict[str, List[Dict[str, str]]] = {}
        self._binary_sensor_by_connection_mode: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        self._binary_sensor_targets_dirty = True
        self._live_mode_label_bg: Dict[Tuple[str, str], str] = {}
        self._ha_binary_sensor_refresh_inflight = False
        self._last_ha_binary_sensor_error = ""

        self.session_manager = SessionManager(
            self._on_session_closed,
            self._show_info,
            on_unexpected_exit=self._on_session_unexpected_exit,
        )
        self.network = NetworkBus(self.station_name, udp_port=self.udp_port)
        self._bind_network_signals()

        self.sound = QSoundEffect()
        if NOTICE_SOUND_PATH.exists():
            self.sound.setSource(QUrl.fromLocalFile(str(NOTICE_SOUND_PATH)))
            self.sound.setVolume(0.4)

        self.chat_window = ChatWindow(
            station_name=self.station_name,
            send_message=self._send_chat,
            refresh_stations=self._refresh_stations,
            clear_away=self._clear_away_if_needed,
        )
        self.chat_window.resize(
            int(self.settings_store.value("chat_width", 680)),
            int(self.settings_store.value("chat_height", 500)),
        )
        saved_chat_geometry = self.settings_store.value("chat_geometry")
        if saved_chat_geometry:
            self.chat_window.restoreGeometry(saved_chat_geometry)
        self.toast = ToastLabel(self)
        self.chat_window.set_topic(self.topic)

        self._build_ui()
        self._flush_pending_json_warnings()
        saved_main_geometry = self.settings_store.value("main_geometry")
        if saved_main_geometry:
            self.restoreGeometry(saved_main_geometry)
        self.binary_sensor_states_received.connect(self._apply_binary_sensor_states)
        self._set_open_controls_enabled(False)
        self._refresh_station_targets()
        # Announce this station immediately on startup.
        self.network.send_hello()
        self.network.send_session_sync_request()

        self.hello_timer = QTimer(self)
        self.hello_timer.timeout.connect(self._send_hello)
        self.hello_timer.start(HELLO_INTERVAL_MS)

        self.rebroadcast_timer = QTimer(self)
        self.rebroadcast_timer.timeout.connect(self._rebroadcast_sessions)
        self.rebroadcast_timer.start(SESSION_BROADCAST_INTERVAL_MS)

        self.presence_timer = QTimer(self)
        self.presence_timer.timeout.connect(self._check_station_presence_changes)
        self.presence_timer.start(STATION_PRESENCE_CHECK_MS)

        self.startup_sync_timer = QTimer(self)
        self.startup_sync_timer.timeout.connect(self._process_startup_sync)
        self.startup_sync_timer.start(700)
        self.ha_binary_sensor_timer = QTimer(self)
        self.ha_binary_sensor_timer.timeout.connect(self._refresh_binary_sensor_indicators)
        self.ha_binary_sensor_timer.start(7000)
        QTimer.singleShot(600, self._refresh_binary_sensor_indicators)

    def _build_ui(self) -> None:
        """Create widgets, connection list, and fixed bottom action rows."""
        self._refresh_window_title()
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(
            int(self.settings_store.value("main_width", 250)),
            int(self.settings_store.value("main_height", 830)),
        )

        outer = QWidget(self)
        self.setCentralWidget(outer)
        root = QVBoxLayout(outer)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        content = QWidget()
        self.rows_layout = QVBoxLayout(content)
        self.rows_layout.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(content)
        self._rebuild_connection_rows()

        lower_panel = QHBoxLayout()
        root.addLayout(lower_panel)
        setup_list_panel = QVBoxLayout()
        lower_panel.addLayout(setup_list_panel, 1)
        setup_list_label = QLabel("Select setup")
        setup_list_label.setStyleSheet("font-weight:600; padding:1px 3px;")
        setup_list_panel.addWidget(setup_list_label)
        self.setup_select = QListWidget()
        self.setup_select.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setup_select.setDragDropMode(QAbstractItemView.InternalMove)
        self.setup_select.setDefaultDropAction(Qt.MoveAction)
        self.setup_select.setDragEnabled(True)
        self.setup_select.setAcceptDrops(True)
        self.setup_select.setDropIndicatorShown(True)
        self.setup_select.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setup_select.currentItemChanged.connect(self._on_setup_selection_changed)
        self.setup_select.itemClicked.connect(self._on_setup_item_clicked)
        self.setup_select.model().rowsMoved.connect(self._on_setup_order_changed)
        self._apply_setup_list_minimum_height()
        setup_list_panel.addWidget(self.setup_select, 1)

        controls_panel = QVBoxLayout()
        lower_panel.addLayout(controls_panel)
        controls_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        setup_actions_row = QHBoxLayout()
        setup_actions_row.setAlignment(Qt.AlignLeft)
        controls_panel.addLayout(setup_actions_row)
        untag_all = QPushButton("Untag all")
        _set_button_icon(untag_all, UNTAG_ICON_PATH)
        _set_compact_button(untag_all)
        untag_all.setStyleSheet("background:#666666; color:white; font-weight:700; border-radius:4px;")
        untag_all.clicked.connect(self._untag_all)
        self.view_all_btn = QPushButton("View tagged")
        _set_button_icon(self.view_all_btn, VIEW_ICON_PATH)
        _set_compact_button(self.view_all_btn)
        self.view_all_btn.setStyleSheet("background:#2f9e44; color:white; font-weight:700; border-radius:4px;")
        self.view_all_btn.clicked.connect(lambda: self._toggle_tagged_mode(MODE_VIEW))
        self.control_all_btn = QPushButton("Control tagged")
        _set_button_icon(self.control_all_btn, CONTROL_ICON_PATH)
        _set_compact_button(self.control_all_btn)
        self.control_all_btn.setStyleSheet("background:#b87400; color:white; font-weight:700; border-radius:4px;")
        self.control_all_btn.clicked.connect(lambda: self._toggle_tagged_mode(MODE_CONTROL))
        _match_button_widths(self.view_all_btn, self.control_all_btn)
        setup_actions_row.addWidget(self.view_all_btn)
        setup_actions_row.addWidget(self.control_all_btn)
        setup_actions_row.addStretch(1)
        self.minimize_all_btn = QPushButton("-")
        _set_compact_button(self.minimize_all_btn)
        self.minimize_all_btn.setToolTip("Minimize all session cards")
        self.minimize_all_btn.setStyleSheet(f"background:#5f6b7a; color:white; {BUTTON_CHROME}")
        self.minimize_all_btn.clicked.connect(self._toggle_all_rows_minimized)
        setup_actions_row.addWidget(self.minimize_all_btn)
        self._refresh_minimize_all_button()
        self._refresh_tagged_mode_buttons()
        self._refresh_setup_targets()

        actions_row_close_all = QHBoxLayout()
        actions_row_close_all.setAlignment(Qt.AlignLeft)
        controls_panel.addLayout(actions_row_close_all)
        close_all_open_btn = QPushButton("Close all sessions")
        _set_button_icon(close_all_open_btn, CANCEL_ICON_PATH)
        _set_compact_button(close_all_open_btn)
        close_all_open_btn.setStyleSheet(
            "background:#666666; color:white; font-weight:700; border-radius:4px;"
        )
        close_all_open_btn.clicked.connect(self._close_all_sessions)
        actions_row_close_all.addWidget(close_all_open_btn)
        actions_row_close_all.addWidget(untag_all)

        self.setup_name_input = QLineEdit()
        self.setup_name_input.setPlaceholderText("Setup name")
        self.setup_name_input.setFocusPolicy(Qt.ClickFocus)
        controls_panel.addWidget(self.setup_name_input)

        setup_manage_row = QHBoxLayout()
        setup_manage_row.setAlignment(Qt.AlignLeft)
        controls_panel.addLayout(setup_manage_row)
        self.setup_save_btn = QPushButton("Save")
        _set_button_icon(self.setup_save_btn, SAVE_ICON_PATH)
        _set_compact_button(self.setup_save_btn)
        self.setup_save_btn.setStyleSheet("background:#666666; color:white; font-weight:700; border-radius:4px;")
        self.setup_save_btn.clicked.connect(self._save_current_setup)
        setup_manage_row.addWidget(self.setup_save_btn)
        self.setup_clear_btn = QPushButton("Clear")
        _set_button_icon(self.setup_clear_btn, CLEAR_ICON_PATH)
        _set_compact_button(self.setup_clear_btn)
        self.setup_clear_btn.setStyleSheet("background:#666666; color:white; font-weight:700; border-radius:4px;")
        self.setup_clear_btn.clicked.connect(self._clear_setup_state)
        setup_manage_row.addWidget(self.setup_clear_btn)
        self.setup_delete_btn = QPushButton("Delete")
        _set_button_icon(self.setup_delete_btn, DELETE_ICON_PATH)
        _set_compact_button(self.setup_delete_btn)
        self.setup_delete_btn.setStyleSheet("background:#bd001b; color:white; font-weight:700; border-radius:4px;")
        self.setup_delete_btn.clicked.connect(self._delete_current_setup)
        setup_manage_row.addWidget(self.setup_delete_btn)

        shared_sessions_row = QHBoxLayout()
        shared_sessions_row.setAlignment(Qt.AlignLeft)
        controls_panel.addLayout(shared_sessions_row)
        self.takeover_checkbox = QCheckBox("Allow shared sessions")
        shared_sessions_row.addWidget(self.takeover_checkbox)
        shared_sessions_row.addStretch(1)
        self._apply_setup_manage_row_font()

        self.chat_btn = QPushButton("Chat")
        _set_button_icon(self.chat_btn, CHAT_ICON_PATH)
        _set_compact_button(self.chat_btn)
        self.chat_btn.setStyleSheet("background:#666666; color:white; font-weight:700; border-radius:4px;")
        self.chat_btn.clicked.connect(self._open_chat)
        controls_panel.addStretch(1)

        actions_row5 = QHBoxLayout()
        root.addLayout(actions_row5)
        positions_tool_btn = QPushButton("Positions")
        _set_button_icon(positions_tool_btn, EDIT_ICON_PATH)
        _set_compact_button(positions_tool_btn)
        positions_tool_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        positions_tool_btn.clicked.connect(self._open_positions_tool)
        sessions_tool_btn = QPushButton("Sessions")
        _set_button_icon(sessions_tool_btn, EDIT_ICON_PATH)
        _set_compact_button(sessions_tool_btn)
        sessions_tool_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        sessions_tool_btn.clicked.connect(self._open_sessions_tool)
        settings_btn = QPushButton("Settings")
        _set_button_icon(settings_btn, GEARS_ICON_PATH)
        _set_compact_button(settings_btn)
        settings_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        settings_btn.clicked.connect(self._open_settings_window)
        _match_button_widths(positions_tool_btn, sessions_tool_btn, settings_btn)
        actions_row5.addWidget(self.chat_btn)
        actions_row5.addWidget(positions_tool_btn)
        actions_row5.addWidget(sessions_tool_btn)
        actions_row5.addWidget(settings_btn)
        actions_row5.addStretch(1)

        self._apply_theme(self.theme_mode)

    @staticmethod
    def _default_app_font_size() -> int:
        app = QApplication.instance()
        if app is None:
            return 10
        point_size = app.font().pointSize()
        return point_size if point_size > 0 else 10

    def _refresh_window_title(self) -> None:
        self.setWindowTitle(f"{self.station_name} v{APP_VERSION}")

    def _load_font_size_setting(self) -> int:
        default_size = self._default_app_font_size()
        raw_value = self.settings_store.value("font_size", default_size)
        try:
            value = int(str(raw_value))
        except (TypeError, ValueError):
            value = default_size
        return max(8, min(32, value))

    def _apply_global_font_size(self, size: int, persist: bool = True) -> None:
        app = QApplication.instance()
        if app is None:
            return
        clamped = max(8, min(32, int(size)))
        font = app.font()
        if font.pointSize() != clamped:
            font.setPointSize(clamped)
            app.setFont(font)
            # Force-refresh existing widgets that may not fully inherit app font live.
            for top_level in app.topLevelWidgets():
                top_level.setFont(font)
                for child in top_level.findChildren(QWidget):
                    child.setFont(font)
                    if isinstance(child, QPushButton):
                        _apply_scaled_icon_size(child)
                        _refresh_button_icon_state(child)
                if isinstance(top_level, QPushButton):
                    _apply_scaled_icon_size(top_level)
                    _refresh_button_icon_state(top_level)
        self.font_size = clamped
        self._apply_setup_manage_row_font()
        self._refresh_status_indicator_sizes()
        if hasattr(self, "rows"):
            for row in self.rows.values():
                row.update_action_button_font(self.font_size)
        if persist:
            self.settings_store.setValue("font_size", clamped)

    def _set_use_button_icons(self, enabled: bool, persist: bool = True) -> None:
        """Persist and apply the global button-icon preference across open windows."""
        if persist:
            self.settings_store.setValue("use_button_icons", "true" if enabled else "false")
        app = QApplication.instance()
        if app is None:
            return
        top_levels = list(app.topLevelWidgets())
        for top_level in top_levels:
            if isinstance(top_level, QPushButton):
                _refresh_button_icon_state(top_level)
            for child in top_level.findChildren(QPushButton):
                _refresh_button_icon_state(child)

    def _apply_setup_manage_row_font(self) -> None:
        """Keep setup widgets aligned with the global app font."""
        if not hasattr(self, "setup_select"):
            return
        app = QApplication.instance()
        if app is None:
            return
        base_size = app.font().pointSize()
        if base_size <= 0:
            return
        aligned_font = QFont(app.font())
        aligned_font.setPointSize(base_size)
        self.setup_select.setFont(aligned_font)
        self._apply_setup_list_minimum_height()
        if hasattr(self, "setup_name_input"):
            self.setup_name_input.setFont(aligned_font)
        if hasattr(self, "setup_save_btn"):
            self.setup_save_btn.setFont(aligned_font)
        if hasattr(self, "setup_clear_btn"):
            self.setup_clear_btn.setFont(aligned_font)
        if hasattr(self, "setup_delete_btn"):
            self.setup_delete_btn.setFont(aligned_font)

    def _current_setup_name(self) -> str:
        if hasattr(self, "setup_name_input"):
            typed_name = self.setup_name_input.text().strip()
            if typed_name:
                return typed_name
        if not hasattr(self, "setup_select"):
            return ""
        item = self.setup_select.currentItem()
        if item is None:
            return ""
        return item.text().strip()

    def _set_selected_setup_name(self, name: str, *, trigger: bool = False) -> None:
        if not hasattr(self, "setup_select"):
            return
        target = name.strip()
        should_block = not trigger
        if should_block:
            self.setup_select.blockSignals(True)
        if hasattr(self, "setup_name_input"):
            self.setup_name_input.setText(target)
        try:
            if not target:
                self.setup_select.clearSelection()
                self.setup_select.setCurrentItem(None)
                return
            matches = self.setup_select.findItems(target, Qt.MatchExactly)
            if matches:
                self.setup_select.setCurrentItem(matches[0])
            else:
                self.setup_select.clearSelection()
                self.setup_select.setCurrentItem(None)
        finally:
            if should_block:
                self.setup_select.blockSignals(False)

    def _setup_names_in_ui_order(self) -> List[str]:
        if not hasattr(self, "setup_select"):
            return []
        names: List[str] = []
        for index in range(self.setup_select.count()):
            item = self.setup_select.item(index)
            if item is None:
                continue
            name = item.text().strip()
            if name:
                names.append(name)
        return names

    def _save_setup_order(self) -> None:
        self.settings_store.setValue("setup_order", json.dumps(self._setup_names_in_ui_order()))

    def _load_setup_order(self) -> List[str]:
        raw_value = self.settings_store.value("setup_order", "")
        if not raw_value:
            return []
        try:
            data = json.loads(str(raw_value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        ordered: List[str] = []
        seen: Set[str] = set()
        for value in data:
            name = str(value).strip()
            lowered = name.lower()
            if not name or lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(name)
        return ordered

    def _on_setup_order_changed(self, *_args) -> None:
        self._save_setup_order()

    def _apply_setup_list_minimum_height(self) -> None:
        if not hasattr(self, "setup_select"):
            return
        row_height = self.setup_select.sizeHintForRow(0)
        if row_height <= 0:
            row_height = max(20, self.setup_select.fontMetrics().height() + 8)
        frame = self.setup_select.frameWidth() * 2
        target_height = (row_height * 8) + frame
        self.setup_select.setMinimumHeight(target_height)
        self.setup_select.setMaximumHeight(target_height)

    def _refresh_status_indicator_sizes(self) -> None:
        """Recompute status indicator icon size for all rows using current font size."""
        if not hasattr(self, "rows"):
            return
        for row in self.rows.values():
            row.update_status_indicator_size(self.font_size)

    def _apply_theme(self, mode: str) -> None:
        """Apply selected theme to both main window and chat window."""
        self.theme_mode = mode
        self.settings_store.setValue("theme_mode", mode)
        if mode == "Auto":
            self.effective_theme = "Dark" if windows_prefers_dark() else "Light"
        effective = self.effective_theme if mode == "Auto" else mode
        base_button_style = f"QPushButton{{{BUTTON_CHROME}}}"
        light_row_style = (
            "QFrame#connectionRowCard{background:#fbfcfd; border:1px solid #e5e7eb; border-radius:6px;}"
            "QLabel#ownerLabel{color:#6b7280;}"
        )
        stylesheet = f"{base_button_style}{light_row_style}"
        if effective == "Dark":
            stylesheet = (
                "QWidget{background:#1f2328;color:#e6edf3;}"
                "QLineEdit,QTextEdit,QComboBox,QSpinBox{background:#0d1117;color:#e6edf3;border:1px solid #30363d;}"
                "QFrame#connectionRowCard{background:#262c34; border:1px solid #3b4350; border-radius:6px;}"
                "QLabel#ownerLabel{color:#9aa4b2;}"
                f"{base_button_style}"
            )

        self.setStyleSheet(stylesheet)
        self.chat_window.setStyleSheet(stylesheet)
        if hasattr(self, "rows"):
            for row in self.rows.values():
                row.set_effective_theme(effective)
        if self._positions_tool_window is not None:
            self._positions_tool_window.set_theme_mode(mode)
        if self._sessions_tool_window is not None:
            self._sessions_tool_window.set_theme_mode(mode)
        # Toast uses opposite contrast of the selected/effective app theme.
        if effective == "Dark":
            self.toast.set_theme("light")
        else:
            self.toast.set_theme("dark")

    def _set_reconnect_on_drop(self, enabled: bool) -> None:
        """Persist reconnect-on-drop operator preference."""
        self.reconnect_on_drop = bool(enabled)
        self.settings_store.setValue("reconnect_on_drop", "true" if enabled else "false")

    @staticmethod
    def _parse_udp_port(value: object, fallback: int = UDP_PORT) -> int:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError, AttributeError):
            return fallback
        return max(1, min(65535, parsed))

    def _load_udp_port_setting(self) -> int:
        data = load_default_mapping()
        return self._parse_udp_port(data.get("udp_port"), UDP_PORT)

    def _load_follow_links_on_tagged_setting(self) -> bool:
        data = load_default_mapping()
        value = data.get("follow_links_on_tagged", "false")
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _bind_network_signals(self) -> None:
        self.network.station_seen.connect(self._on_station_seen)
        self.network.session_state.connect(self._on_remote_session_state)
        self.network.chat_received.connect(self._on_chat_received)
        self.network.takeover_notice.connect(self._on_takeover_notice)
        self.network.topic_changed.connect(self._on_topic_changed)
        self.network.away_changed.connect(self._on_away_changed)
        self.network.nick_changed.connect(self._on_nick_changed)
        self.network.session_sync_requested.connect(self._on_session_sync_requested)

    def _queue_json_warning(self, message: str) -> None:
        """Receive config warnings from any thread and route them to the UI."""
        self.json_warning_received.emit(str(message).strip())

    def _display_json_warning(self, message: str) -> None:
        """Show one queued config warning once the toast UI is available."""
        if not message:
            return
        if not hasattr(self, "toast"):
            self._pending_json_warnings.append(message)
            return
        self._show_info(message)

    def _flush_pending_json_warnings(self) -> None:
        """Drain any warnings emitted before the main UI was fully built."""
        if not hasattr(self, "toast"):
            return
        pending = list(self._pending_json_warnings)
        self._pending_json_warnings.clear()
        for message in pending:
            self._show_info(message)

    def _send_hello(self) -> None:
        """Send station discovery using the currently active network bus."""
        self.network.send_hello()

    def _recreate_network_bus(self, udp_port: int) -> None:
        self.network.close()
        self.network = NetworkBus(self.station_name, udp_port=udp_port)
        self._bind_network_signals()
        self.udp_port = udp_port
        self._remote_mode_holders.clear()
        self._station_names_by_id.clear()
        self._online_snapshot.clear()
        self._refresh_station_targets()
        self.network.send_hello()
        self.network.send_session_sync_request()
        self._rebroadcast_sessions()

    def _load_default_json_mapping(self) -> Dict[str, object]:
        """Read default settings merged with optional local overrides."""
        data: Dict[str, object] = dict(load_default_mapping())

        defaults = self.default_settings.to_json()
        defaults["station_name"] = self.default_settings.station_name
        for key, value in defaults.items():
            data.setdefault(key, value)
        data.setdefault("ha_url", "")
        data.setdefault("ha_api_key", "")
        data.setdefault("udp_port", str(self.udp_port))
        data.setdefault("allow_multiple_instances", "false")
        data.setdefault("reconnect_on_drop", "true" if self.reconnect_on_drop else "false")
        data.setdefault(
            "follow_links_on_tagged", "true" if self.follow_links_on_tagged else "false"
        )
        return data

    @staticmethod
    def _state_to_bool(value: str) -> Optional[bool]:
        text = value.strip().lower()
        if text in {"on", "open", "true", "1"}:
            return True
        if text in {"off", "closed", "false", "0"}:
            return False
        return None

    @staticmethod
    def _format_tooltip(template: str, state_text: str, entity_id: str, sensor_name: str) -> str:
        cleaned = template.strip()
        if not cleaned:
            return ""
        try:
            return (
                cleaned.replace("{state}", state_text)
                .replace("{entity_id}", entity_id)
                .replace("{name}", sensor_name)
            )
        except Exception:
            return cleaned

    def _refresh_binary_sensor_targets(self) -> None:
        """Map each connection row to saved HA sensor/icon configurations."""
        if not self._binary_sensor_targets_dirty:
            return
        mappings_by_connection: Dict[str, List[Dict[str, str]]] = {}
        mode_mappings_by_connection: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        for connection_name in self.rows.keys():
            merged_mappings: List[Dict[str, str]] = []
            per_mode: Dict[str, List[Dict[str, str]]] = {MODE_VIEW: [], MODE_CONTROL: []}
            for mode in (MODE_VIEW, MODE_CONTROL):
                settings = load_session_settings(config_path_for(connection_name, mode))
                for mapping in settings.ha_sensor_icons:
                    if not isinstance(mapping, dict):
                        continue
                    entity_id = str(mapping.get("entity_id", "")).strip()
                    if not entity_id:
                        continue
                    parsed = {
                        "entity_id": entity_id,
                        "icon": str(mapping.get("icon", "")).strip(),
                        "icon_on": str(mapping.get("icon_on", "")).strip(),
                        "icon_off": str(mapping.get("icon_off", "")).strip(),
                        "tooltip": str(mapping.get("tooltip", "")).strip(),
                        "bg_state": str(mapping.get("bg_state", "")).strip().lower(),
                        "bg_color": str(mapping.get("bg_color", "")).strip(),
                    }
                    merged_mappings.append(parsed)
                    per_mode[mode].append(parsed)
                if not settings.ha_sensor_icons:
                    for sensor in settings.ha_sensors:
                        entity_id = str(sensor).strip()
                        if entity_id:
                            parsed = {
                                "entity_id": entity_id,
                                "icon": "",
                                "icon_on": "",
                                "icon_off": "",
                                "tooltip": "",
                                "bg_state": "",
                                "bg_color": "",
                            }
                            merged_mappings.append(parsed)
                            per_mode[mode].append(parsed)
            if merged_mappings:
                deduped: List[Dict[str, str]] = []
                by_entity: Dict[str, Dict[str, str]] = {}
                for mapping in merged_mappings:
                    key = mapping["entity_id"].lower()
                    existing = by_entity.get(key)
                    if existing is None:
                        by_entity[key] = dict(mapping)
                        continue
                    # Same sensor in both view/control: keep one mapping and fill missing icons.
                    if not existing.get("icon") and mapping.get("icon"):
                        existing["icon"] = mapping.get("icon", "")
                    if not existing.get("icon_on") and mapping.get("icon_on"):
                        existing["icon_on"] = mapping.get("icon_on", "")
                    if not existing.get("icon_off") and mapping.get("icon_off"):
                        existing["icon_off"] = mapping.get("icon_off", "")
                    if not existing.get("tooltip") and mapping.get("tooltip"):
                        existing["tooltip"] = mapping.get("tooltip", "")
                    if not existing.get("bg_state") and mapping.get("bg_state"):
                        existing["bg_state"] = mapping.get("bg_state", "")
                    if not existing.get("bg_color") and mapping.get("bg_color"):
                        existing["bg_color"] = mapping.get("bg_color", "")
                deduped.extend(by_entity.values())
                mappings_by_connection[connection_name] = deduped
                mode_mappings_by_connection[connection_name] = per_mode
        self._binary_sensor_by_connection = mappings_by_connection
        self._binary_sensor_by_connection_mode = mode_mappings_by_connection
        self._binary_sensor_targets_dirty = False
        for connection_name, row in self.rows.items():
            if connection_name not in self._binary_sensor_by_connection:
                row.set_status_indicators([])
                row.set_indicators_background_color("")

    def _refresh_binary_sensor_indicators(self) -> None:
        """Poll HA for sensor states and update row indicator icons."""
        if self._ha_binary_sensor_refresh_inflight:
            return
        self._refresh_binary_sensor_targets()
        if not self._binary_sensor_by_connection:
            return
        defaults = self._load_default_json_mapping()
        ha_url = str(defaults.get("ha_url", "")).strip()
        ha_api_key = str(defaults.get("ha_api_key", "")).strip()
        if not ha_url or not ha_api_key:
            return

        self._ha_binary_sensor_refresh_inflight = True
        mappings_snapshot = dict(self._binary_sensor_by_connection)
        mode_snapshot = dict(self._binary_sensor_by_connection_mode)
        thread = threading.Thread(
            target=self._fetch_binary_sensor_states_thread,
            args=(ha_url, ha_api_key, mappings_snapshot, mode_snapshot),
            daemon=True,
        )
        thread.start()

    def _fetch_binary_sensor_states_thread(
        self,
        ha_url: str,
        ha_api_key: str,
        mappings_by_connection: Dict[str, List[Dict[str, str]]],
        mode_mappings_by_connection: Dict[str, Dict[str, List[Dict[str, str]]]],
    ) -> None:
        indicators_by_connection: Dict[str, Dict[str, object]] = {}
        try:
            url = ha_url.rstrip("/") + "/api/states"
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {ha_api_key}",
                    "Content-Type": "application/json",
                },
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=7) as response:
                body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            if not isinstance(payload, list):
                self._ha_binary_sensor_refresh_inflight = False
                return
            by_entity: Dict[str, str] = {}
            by_entity_name: Dict[str, str] = {}
            for item in payload:
                if not isinstance(item, dict):
                    continue
                entity_id = str(item.get("entity_id", "")).strip().lower()
                state = str(item.get("state", "")).strip()
                attributes = item.get("attributes", {})
                sensor_name = ""
                if isinstance(attributes, dict):
                    sensor_name = str(attributes.get("friendly_name", "")).strip()
                if entity_id:
                    by_entity[entity_id] = state
                    by_entity_name[entity_id] = sensor_name or entity_id
            for connection_name, mappings in mappings_by_connection.items():
                connection_indicators: List[Dict[str, str]] = []
                for mapping in mappings:
                    entity_id = str(mapping.get("entity_id", "")).strip().lower()
                    if not entity_id:
                        continue
                    chosen_tip = ""
                    state_text = str(by_entity.get(entity_id, "")).strip()
                    if not state_text:
                        continue
                    tooltip_template = str(mapping.get("tooltip", "")).strip()
                    sensor_name = str(by_entity_name.get(entity_id, entity_id)).strip() or entity_id
                    templated_tip = self._format_tooltip(tooltip_template, state_text, entity_id, sensor_name)
                    bool_state = self._state_to_bool(state_text)
                    is_binary = entity_id.startswith("binary_sensor.") or entity_id.startswith("input_boolean.")
                    icon_path = ""
                    if is_binary:
                        if bool_state is True:
                            icon_path = str(mapping.get("icon_on", "")).strip()
                            chosen_tip = templated_tip or ("Door open" if "door" in entity_id else "On")
                        elif bool_state is False:
                            icon_path = str(mapping.get("icon_off", "")).strip()
                            chosen_tip = templated_tip or ("Door closed" if "door" in entity_id else "Off")
                    if not icon_path:
                        icon_path = str(mapping.get("icon", "")).strip()
                        if icon_path:
                            chosen_tip = templated_tip or state_text
                    if not icon_path:
                        continue
                    if not chosen_tip:
                        chosen_tip = templated_tip or state_text
                    connection_indicators.append({"icon": icon_path, "tip": chosen_tip})
                mode_colors: Dict[str, str] = {MODE_VIEW: "", MODE_CONTROL: ""}
                mode_mappings = mode_mappings_by_connection.get(connection_name, {})
                for mode in (MODE_VIEW, MODE_CONTROL):
                    for mapping in mode_mappings.get(mode, []):
                        entity_id = str(mapping.get("entity_id", "")).strip().lower()
                        state_text = str(by_entity.get(entity_id, "")).strip()
                        desired_state = str(mapping.get("bg_state", "")).strip().lower()
                        desired_color = str(mapping.get("bg_color", "")).strip()
                        if not entity_id or not state_text or not desired_state or not desired_color:
                            continue
                        bool_state = self._state_to_bool(state_text)
                        if desired_state == "on" and bool_state is True:
                            mode_colors[mode] = desired_color
                            break
                        if desired_state == "off" and bool_state is False:
                            mode_colors[mode] = desired_color
                            break

                area_color = mode_colors.get(MODE_VIEW, "") or mode_colors.get(MODE_CONTROL, "")
                if connection_indicators or area_color or mode_colors.get(MODE_VIEW) or mode_colors.get(MODE_CONTROL):
                    indicators_by_connection[connection_name] = {
                        "indicators": connection_indicators,
                        "mode_colors": mode_colors,
                        "area_color": area_color,
                    }
            self.binary_sensor_states_received.emit(indicators_by_connection)
            self._last_ha_binary_sensor_error = ""
        except Exception as exc:
            error_text = str(exc)
            if error_text and error_text != self._last_ha_binary_sensor_error:
                LOGGER.warning("Binary sensor indicator HA refresh failed: %s", error_text)
                self._last_ha_binary_sensor_error = error_text
        finally:
            self._ha_binary_sensor_refresh_inflight = False

    def _apply_binary_sensor_states(self, states_obj: object) -> None:
        """Apply parsed status-icon mappings to row labels in the UI thread."""
        if not isinstance(states_obj, dict):
            return
        seen_connections = set()
        for connection_name, payload in states_obj.items():
            row = self.rows.get(str(connection_name))
            if row is None:
                continue
            seen_connections.add(str(connection_name))
            indicators: List[Tuple[str, str]] = []
            mode_colors: Dict[str, str] = {MODE_VIEW: "", MODE_CONTROL: ""}
            area_color = ""
            if isinstance(payload, dict):
                raw_indicators = payload.get("indicators", [])
                if isinstance(raw_indicators, list):
                    for item in raw_indicators:
                        if not isinstance(item, dict):
                            continue
                        icon_path = str(item.get("icon", "")).strip()
                        tooltip = str(item.get("tip", "")).strip()
                        if icon_path:
                            indicators.append((icon_path, tooltip))
                raw_mode_colors = payload.get("mode_colors", {})
                if isinstance(raw_mode_colors, dict):
                    mode_colors[MODE_VIEW] = str(raw_mode_colors.get(MODE_VIEW, "")).strip()
                    mode_colors[MODE_CONTROL] = str(raw_mode_colors.get(MODE_CONTROL, "")).strip()
                area_color = str(payload.get("area_color", "")).strip()
            row.set_status_indicators(indicators)
            row.set_indicators_background_color(area_color)
            self._live_mode_label_bg[(str(connection_name), MODE_VIEW)] = mode_colors.get(MODE_VIEW, "")
            self._live_mode_label_bg[(str(connection_name), MODE_CONTROL)] = mode_colors.get(MODE_CONTROL, "")
            self._apply_overlay_label_background(str(connection_name), MODE_VIEW, mode_colors.get(MODE_VIEW, ""))
            self._apply_overlay_label_background(str(connection_name), MODE_CONTROL, mode_colors.get(MODE_CONTROL, ""))
        for connection_name, row in self.rows.items():
            if connection_name in seen_connections:
                continue
            if connection_name not in self._binary_sensor_by_connection:
                continue
            row.set_status_indicators([])
            row.set_indicators_background_color("")
            self._live_mode_label_bg[(connection_name, MODE_VIEW)] = ""
            self._live_mode_label_bg[(connection_name, MODE_CONTROL)] = ""
            self._apply_overlay_label_background(connection_name, MODE_VIEW, "")
            self._apply_overlay_label_background(connection_name, MODE_CONTROL, "")

    def _apply_overlay_label_background(self, connection_name: str, mode: str, color_text: str) -> None:
        """Apply runtime label background color to an open overlay session."""
        self.session_manager.set_overlay_label_background((connection_name, mode), color_text)

    def _save_default_json_mapping(self, updates: Dict[str, str]) -> str:
        """Persist app-level defaults to local override file and refresh runtime state."""
        reconnect_value = str(updates.pop("reconnect_on_drop", "true" if self.reconnect_on_drop else "false"))
        self._set_reconnect_on_drop(reconnect_value.strip().lower() in {"1", "true", "yes", "on"})
        follow_links_value = str(
            updates.pop(
                "follow_links_on_tagged",
                "true" if self.follow_links_on_tagged else "false",
            )
        )
        self.follow_links_on_tagged = follow_links_value.strip().lower() in {"1", "true", "yes", "on"}
        existing: Dict[str, object] = {}
        if DEFAULT_LOCAL_CONFIG_PATH.exists():
            try:
                with DEFAULT_LOCAL_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                if isinstance(raw, dict):
                    existing = dict(raw)
            except (OSError, json.JSONDecodeError):
                existing = {}
        existing.update({k: str(v) for k, v in updates.items()})
        save_json(DEFAULT_LOCAL_CONFIG_PATH, existing)
        self.default_settings = load_default_settings()
        new_udp_port = self._parse_udp_port(existing.get("udp_port"), self.udp_port)
        udp_port_changed = new_udp_port != self.udp_port
        if udp_port_changed:
            self._recreate_network_bus(new_udp_port)

        new_station_name = self.default_settings.station_name.strip() or self.station_name
        if new_station_name != self.station_name:
            self.station_name = new_station_name
            self._refresh_window_title()
            self.network.set_station_name(self.station_name)
            self.chat_window.set_station_title(self.station_name)
            self.chat_window.add_notice(f"Station name updated to {self.station_name}")
        if udp_port_changed:
            return f"Settings saved. UDP port changed to {new_udp_port}."
        return "Settings saved."

    def _reload_runtime_defaults_from_disk(self) -> None:
        """Refresh runtime state from imported default/default.local config files."""
        self.default_settings = load_default_settings()
        self.follow_links_on_tagged = self._load_follow_links_on_tagged_setting()
        new_udp_port = self._load_udp_port_setting()
        if new_udp_port != self.udp_port:
            self._recreate_network_bus(new_udp_port)

        new_station_name = self.default_settings.station_name.strip() or self.station_name
        if new_station_name != self.station_name:
            self.station_name = new_station_name
            self._refresh_window_title()
            self.network.set_station_name(self.station_name)
            self.chat_window.set_station_title(self.station_name)
            self.chat_window.add_notice(f"Station name updated to {self.station_name}")

        if self._settings_window is not None and self._settings_window.isVisible():
            self._settings_window.reload_defaults(self._load_default_json_mapping())

    def _open_settings_window(self) -> None:
        """Open or focus the global settings window."""
        if self._settings_window is None or not self._settings_window.isVisible():
            self._settings_window = SettingsWindow(
                theme_mode=self.theme_mode,
                font_size=self.font_size,
                use_button_icons=_button_icons_enabled(),
                apply_button_icons=self._set_use_button_icons,
                defaults=self._load_default_json_mapping(),
                apply_theme=self._apply_theme,
                apply_font_size=self._apply_global_font_size,
                save_defaults=self._save_default_json_mapping,
                show_toast=self._show_info,
                run_validation=self._run_validation,
                import_config=self._import_config_bundle,
                export_config=self._export_config_bundle,
                parent=self,
            )
            self._settings_window.setAttribute(Qt.WA_DeleteOnClose, True)
            self._settings_window.destroyed.connect(self._on_settings_window_closed)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_window_closed(self, _obj=None) -> None:
        self._settings_window = None

    def _open_chat(self) -> None:
        """Show and focus the chat window."""
        self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()

    def _entry_for(self, name: str) -> Optional[ConnectionEntry]:
        """Return connection entry by name, or None if unknown."""
        for entry in self.connections:
            if entry.name == name:
                return entry
        return None

    @staticmethod
    def _sanitize_setup_name(name: str) -> str:
        cleaned = name.strip()
        cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1F]", "_", cleaned)
        cleaned = cleaned.strip(" .")
        return cleaned

    def _setup_path_for_name(self, name: str) -> Optional[Path]:
        safe_name = self._sanitize_setup_name(name)
        if not safe_name:
            return None
        return VNC_SETUPS_DIR / f"{safe_name}.json"

    def _refresh_setup_targets(self) -> None:
        VNC_SETUPS_DIR.mkdir(parents=True, exist_ok=True)
        current_text = self._current_setup_name() if hasattr(self, "setup_select") else ""
        if not current_text:
            current_text = str(self.settings_store.value("last_setup_name", "")).strip()
        names = sorted((p.stem for p in VNC_SETUPS_DIR.glob("*.json")), key=str.lower)
        stored_order = self._load_setup_order()
        known_names = {name.lower(): name for name in names}
        ordered_names: List[str] = []
        seen: Set[str] = set()
        for saved_name in stored_order:
            actual_name = known_names.get(saved_name.lower())
            if actual_name is None:
                continue
            lowered = actual_name.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered_names.append(actual_name)
        for name in names:
            lowered = name.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered_names.append(name)
        self.setup_select.blockSignals(True)
        self.setup_select.clear()
        for name in ordered_names:
            QListWidgetItem(name, self.setup_select)
        self.setup_select.blockSignals(False)
        self._apply_setup_list_minimum_height()
        self._save_setup_order()
        if current_text:
            self._set_selected_setup_name(current_text, trigger=False)
        elif hasattr(self, "setup_name_input"):
            self.setup_name_input.clear()

    def _save_current_setup(self) -> None:
        raw_name = self._current_setup_name()
        path = self._setup_path_for_name(raw_name)
        if path is None:
            self._show_info("Enter a setup name before saving.")
            return
        payload: Dict[str, object] = {
            "name": path.stem,
            "connections": {},
        }
        connections: Dict[str, object] = {}
        for connection_name, row in self.rows.items():
            connections[connection_name] = {
                "tagged": bool(row.tag.isChecked()),
                "minimized": bool(row.is_minimized()),
                "position_view": row.selected_position(MODE_VIEW),
                "position_control": row.selected_position(MODE_CONTROL),
                "link_view": row.selected_link(MODE_VIEW),
                "link_control": row.selected_link(MODE_CONTROL),
            }
        payload["connections"] = connections
        save_json(path, payload)
        self._refresh_setup_targets()
        self._set_selected_setup_name(path.stem, trigger=False)
        self.settings_store.setValue("last_setup_name", path.stem)
        self._show_info(f"Saved setup: {path.stem}")

    def _delete_current_setup(self) -> None:
        raw_name = self._current_setup_name()
        path = self._setup_path_for_name(raw_name)
        if path is None or not raw_name:
            self._show_info("Select a setup name to delete.")
            return
        if not path.exists():
            self._show_info(f"Setup not found: {raw_name}")
            return
        try:
            path.unlink()
        except OSError as exc:
            self._show_info(f"Failed to delete setup '{raw_name}': {exc}")
            return
        self._refresh_setup_targets()
        self._set_selected_setup_name("", trigger=False)
        if str(self.settings_store.value("last_setup_name", "")).strip().lower() == raw_name.lower():
            self.settings_store.setValue("last_setup_name", "")
        self._show_info(f"Deleted setup: {raw_name}")

    def _on_setup_selection_changed(
        self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]
    ) -> None:
        if current is None:
            return
        selected_name = current.text().strip()
        self._apply_setup_by_name(selected_name)

    def _on_setup_item_clicked(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        self._apply_setup_by_name(item.text().strip())

    def _apply_setup_by_name(self, selected_name: str) -> None:
        if hasattr(self, "setup_name_input"):
            self.setup_name_input.setText(selected_name)
        self.settings_store.setValue("last_setup_name", selected_name)
        if not selected_name:
            return
        path = self._setup_path_for_name(selected_name)
        if path is None or not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._show_info(f"Failed to load setup '{selected_name}': {exc}")
            return
        if not isinstance(data, dict):
            self._show_info(f"Invalid setup format in '{selected_name}'.")
            return
        connections = data.get("connections", {})
        if not isinstance(connections, dict):
            self._show_info(f"Invalid setup connections in '{selected_name}'.")
            return
        # Reset all rows first so missing keys/rows in the setup become defaults.
        self._suspend_tag_auto_assign = True
        try:
            for connection_name, row in self.rows.items():
                row.tag.setChecked(False)
                row.set_minimized(False)
                row.set_selected_position(MODE_VIEW, "")
                row.set_selected_position(MODE_CONTROL, "")
                row.set_selected_link(MODE_VIEW, "")
                row.set_selected_link(MODE_CONTROL, "")

            for connection_name, config in connections.items():
                row = self.rows.get(str(connection_name))
                if row is None or not isinstance(config, dict):
                    continue
                row.tag.setChecked(bool(config.get("tagged", row.tag.isChecked())))
                row.set_minimized(bool(config.get("minimized", False)))
                pos_v = str(config.get("position_view", "")).strip()
                pos_c = str(config.get("position_control", "")).strip()
                link_v = str(config.get("link_view", "")).strip()
                link_c = str(config.get("link_control", "")).strip()
                row.set_selected_position(MODE_VIEW, pos_v)
                row.set_selected_position(MODE_CONTROL, pos_c)
                row.set_selected_link(MODE_VIEW, link_v)
                row.set_selected_link(MODE_CONTROL, link_c)
        finally:
            self._suspend_tag_auto_assign = False

        self._clear_duplicate_positions_after_load()
        self._rebuild_row_hierarchy()
        self._refresh_minimize_all_button()
        self._show_info(f"Applied setup: {selected_name}")

    def _clear_setup_state(self) -> None:
        """Clear setup-only UI state, then reload persisted per-session settings."""
        self._suspend_tag_auto_assign = True
        try:
            for connection_name, row in self.rows.items():
                row.tag.setChecked(False)
                row.set_minimized(True)
                row.set_selected_position(MODE_VIEW, "")
                row.set_selected_position(MODE_CONTROL, "")
                row.set_selected_link(MODE_VIEW, "")
                row.set_selected_link(MODE_CONTROL, "")
                self._populate_row_from_saved_settings(row)
                view_overrides = load_session_overrides(config_path_for(connection_name, MODE_VIEW))
                if not str(view_overrides.get("position_name", "")).strip():
                    row.set_selected_position(MODE_VIEW, "")
                row.set_minimized(True)
        finally:
            self._suspend_tag_auto_assign = False
        self._refresh_minimize_all_button()
        self._rebuild_row_hierarchy()
        if hasattr(self, "setup_select"):
            self._set_selected_setup_name("", trigger=False)
        self._show_info("Setup cleared.")

    def _build_session_link_options(self) -> List[Tuple[str, str]]:
        """Build selectable link targets from all available view/control sessions."""
        options: List[Tuple[str, str]] = []
        for entry in self.connections:
            if entry.view_vnc_path is not None:
                options.append((self._session_token(entry.name, MODE_VIEW), f"{entry.name} [view]"))
            if entry.control_vnc_path is not None:
                options.append((self._session_token(entry.name, MODE_CONTROL), f"{entry.name} [control]"))
        return options

    @staticmethod
    def _session_token(connection_name: str, mode: str) -> str:
        return f"{connection_name}|{mode}"

    @staticmethod
    def _parse_session_token(token: str) -> Optional[Tuple[str, str]]:
        parts = token.split("|", 1)
        if len(parts) != 2:
            return None
        connection_name, mode = parts
        mode = mode.strip().lower()
        if not connection_name.strip() or mode not in (MODE_VIEW, MODE_CONTROL):
            return None
        return connection_name.strip(), mode

    def _vnc_path(self, connection_name: str, mode: str) -> Optional[Path]:
        """Resolve concrete .vnc path for the requested connection+mode."""
        entry = self._entry_for(connection_name)
        if entry is None:
            return None
        return entry.view_vnc_path if mode == MODE_VIEW else entry.control_vnc_path

    def _selected_position_name(self, connection_name: str, mode: str) -> str:
        row = self.rows.get(connection_name)
        if row is None:
            return ""
        return row.selected_position(mode)

    def _selected_link_token(self, connection_name: str, mode: str) -> str:
        row = self.rows.get(connection_name)
        if row is None:
            return ""
        return row.selected_link(mode)

    def _persist_ui_selections(self, connection_name: str, mode: str) -> None:
        config_path = config_path_for(connection_name, mode)
        update_session_overrides(
            config_path,
            {
                "linked_session": self._selected_link_token(connection_name, mode),
            },
        )

    def _apply_position_override(self, connection_name: str, mode: str, settings: SessionSettings) -> None:
        selected_name = self._selected_position_name(connection_name, mode) or settings.position_name
        if not selected_name:
            return
        preset = position_by_name(selected_name)
        if preset is None:
            self._show_info(f"Position '{selected_name}' not found for {connection_name} [{mode}]")
            return
        settings.position_name = preset.name
        settings.x = preset.x
        settings.y = preset.y
        settings.width = preset.width
        settings.height = preset.height
        settings.label_x = preset.label_x
        settings.label_y = preset.label_y
        settings.label_bg = preset.label_bg
        settings.label_width = preset.label_width
        settings.label_height = preset.label_height
        settings.label_font = preset.label_font
        settings.label_font_color = preset.label_font_color
        settings.label_border_size = preset.label_border_size
        settings.label_border_color = preset.label_border_color

    def _open_session(self, connection_name: str, mode: str) -> None:
        """Open one session and any configured linked session."""
        if self._startup_sync_pending:
            self._show_info("Please wait: synchronizing session ownership...")
            return
        self._open_session_with_link(connection_name, mode, visited=set())

    def _open_session_with_link(
        self, connection_name: str, mode: str, visited: Set[Tuple[str, str]]
    ) -> None:
        key = (connection_name, mode)
        if key in visited:
            return
        visited.add(key)
        if not self._open_single_session(connection_name, mode):
            return
        link_token = self._selected_link_token(connection_name, mode)
        parsed = self._parse_session_token(link_token)
        if parsed is None:
            return
        linked_connection, linked_mode = parsed
        self._open_session_with_link(linked_connection, linked_mode, visited)

    def _try_open_single_session(self, connection_name: str, mode: str) -> Tuple[bool, str]:
        """Open one session after missing-file and remote-lock checks."""
        vnc_path = self._vnc_path(connection_name, mode)
        if not vnc_path or not vnc_path.exists():
            return False, f"Missing .vnc file for {connection_name} [{mode}]"
        # Station lock is per connection (not per mode), based on station ID.
        remote_holder_id = None
        for (remote_connection, _remote_mode), holder_id in self.network.remote_session_holders.items():
            if remote_connection == connection_name and holder_id != self.network.station_id:
                remote_holder_id = holder_id
                break
        remote_holder = self.network.station_name_for_id(remote_holder_id) if remote_holder_id else None
        if remote_holder_id and not self.takeover_checkbox.isChecked():
            # Soft-lock behavior: prevent duplicates unless user explicitly overrides.
            return (
                False,
                f"{connection_name} is currently open on station '{remote_holder}'. "
                "Enable 'Allow shared sessions' to open it anyway.",
            )

        takeover_used = bool(remote_holder_id and self.takeover_checkbox.isChecked())
        config_path = config_path_for(connection_name, mode)
        settings = load_session_settings(config_path)
        self._apply_position_override(connection_name, mode, settings)
        self._persist_ui_selections(connection_name, mode)
        if self.session_manager.launch((connection_name, mode), vnc_path, settings):
            self._apply_overlay_label_background(
                connection_name,
                mode,
                self._live_mode_label_bg.get((connection_name, mode), ""),
            )
            LOGGER.info("Session opened: %s [%s]", connection_name, mode)
            # Notify peers this station now holds the session.
            self.network.send_session(connection_name, mode, True)
            if takeover_used and remote_holder:
                # Local notice (own broadcast packets are ignored by design).
                self.chat_window.add_notice(
                    f"{self.station_name} took over session {connection_name} from {remote_holder}"
                )
                # Broadcast takeover notice so all other stations log it as well.
                self.network.send_takeover(connection_name, remote_holder)
            self._refresh_owner_labels()
            self._refresh_setup_mode_buttons()
            self._refresh_tagged_mode_buttons()
            return True, ""
        return False, f"Failed to start session {connection_name} [{mode}]"

    def _open_single_session(self, connection_name: str, mode: str) -> bool:
        """Open one session and show any failure reason as a toast."""
        opened, reason = self._try_open_single_session(connection_name, mode)
        if not opened and reason:
            self._show_info(reason)
        return opened

    def _close_session(self, connection_name: str, mode: str) -> None:
        """Close one specific session and any configured linked session chain."""
        self._close_session_with_link(connection_name, mode, visited=set())

    def _close_session_with_link(
        self, connection_name: str, mode: str, visited: Set[Tuple[str, str]]
    ) -> None:
        key = (connection_name, mode)
        if key in visited:
            return
        visited.add(key)
        self.session_manager.close_session(key)
        link_token = self._selected_link_token(connection_name, mode)
        parsed = self._parse_session_token(link_token)
        if parsed is None:
            return
        linked_connection, linked_mode = parsed
        self._close_session_with_link(linked_connection, linked_mode, visited)

    def _close_all_sessions(self) -> None:
        """Close all currently running sessions."""
        self.session_manager.close_all()

    def _toggle_all_rows_minimized(self) -> None:
        """Minimize all rows, or restore only configured/tagged rows when all are collapsed."""
        if self._all_rows_minimized():
            rows_to_expand = []
            for row in self.rows.values():
                should_expand = (
                    row.tag.isChecked()
                    or bool(row.selected_position(MODE_VIEW))
                    or bool(row.selected_position(MODE_CONTROL))
                    or bool(row.selected_link(MODE_VIEW))
                    or bool(row.selected_link(MODE_CONTROL))
                )
                if should_expand:
                    rows_to_expand.append(row)
            if not rows_to_expand:
                rows_to_expand = list(self.rows.values())
            for row in self.rows.values():
                row.set_minimized(row not in rows_to_expand)
            self._refresh_minimize_all_button()
            return
        for row in self.rows.values():
            row.set_minimized(True)
        self._refresh_minimize_all_button()

    def _all_rows_minimized(self) -> bool:
        return bool(self.rows) and all(row.is_minimized() for row in self.rows.values())

    def _refresh_minimize_all_button(self) -> None:
        if not hasattr(self, "minimize_all_btn"):
            return
        all_minimized = self._all_rows_minimized()
        self.minimize_all_btn.setText("+" if all_minimized else "-")
        self.minimize_all_btn.setToolTip(
            "Expand configured/tagged session cards" if all_minimized else "Minimize all session cards"
        )

    def _close_tagged_sessions(self) -> None:
        """Close both modes for all currently tagged connection rows."""
        any_tagged = False
        for row in self.rows.values():
            if row.tag.isChecked():
                any_tagged = True
                self._close_session(row.entry.name, MODE_VIEW)
                self._close_session(row.entry.name, MODE_CONTROL)
        if not any_tagged:
            self._show_info("No tagged connections.")
        self._refresh_tagged_mode_buttons()

    def _open_tagged(self, mode: str) -> None:
        """Open selected mode for every currently tagged connection row."""
        if self._startup_sync_pending:
            self._show_info("Please wait: synchronizing session ownership...")
            return
        any_tagged = False
        for row in self.rows.values():
            if row.tag.isChecked():
                any_tagged = True
                self._open_session_with_link(row.entry.name, mode, visited=set())
        if not any_tagged:
            self._show_info("No tagged connections.")

    def _close_tagged_mode(self, mode: str) -> None:
        """Close one mode for all currently tagged connection rows."""
        any_tagged = False
        for row in self.rows.values():
            if not row.tag.isChecked():
                continue
            any_tagged = True
            self._close_session(row.entry.name, mode)
        if not any_tagged:
            self._show_info("No tagged connections.")

    def _has_open_tagged_mode(self, mode: str) -> bool:
        """Return True when any tagged row currently has this local mode open."""
        for row in self.rows.values():
            if not row.tag.isChecked():
                continue
            if (row.entry.name, mode) in self.session_manager.sessions:
                return True
        return False

    def _toggle_tagged_mode(self, mode: str) -> None:
        """Toggle tagged open/close action for a specific mode."""
        if self._has_open_tagged_mode(mode):
            self._close_tagged_mode(mode)
        else:
            self._open_tagged(mode)
        self._refresh_tagged_mode_buttons()

    def _refresh_tagged_mode_buttons(self) -> None:
        if hasattr(self, "view_all_btn"):
            view_label = "Close tagged" if self._has_open_tagged_mode(MODE_VIEW) else "View tagged"
            _set_button_text_for_icon_state(self.view_all_btn, view_label)
        if hasattr(self, "control_all_btn"):
            control_label = "Close tagged" if self._has_open_tagged_mode(MODE_CONTROL) else "Control tagged"
            _set_button_text_for_icon_state(self.control_all_btn, control_label)

    def _next_available_view_position_name(self, current_connection_name: str = "") -> str:
        used_positions: Set[str] = set()
        for connection_name, row in self.rows.items():
            if current_connection_name and connection_name == current_connection_name:
                continue
            selected = row.selected_position(MODE_VIEW)
            if selected:
                used_positions.add(selected)
        for position_name in self.position_names:
            if position_name not in used_positions:
                return position_name
        return ""

    def _on_row_tag_toggled(self, row: ConnectionRow, checked: bool) -> None:
        if checked and not self._suspend_tag_auto_assign and not row.selected_position(MODE_VIEW):
            next_position = self._next_available_view_position_name(row.entry.name)
            if next_position:
                row.set_selected_position(MODE_VIEW, next_position)
        elif not checked and not self._suspend_tag_auto_assign and row.selected_position(MODE_VIEW):
            row.set_selected_position(MODE_VIEW, "")
        self._refresh_tagged_mode_buttons()

    def _toggle_session(self, connection_name: str, mode: str) -> None:
        """Toggle one row mode: open when closed, close when open."""
        key = (connection_name, mode)
        if key in self.session_manager.sessions:
            self._close_session(connection_name, mode)
            return
        self._open_session(connection_name, mode)

    def _toggle_setup_mode(self, mode: str) -> None:
        """Toggle setup mode action for one mode: open all or close all local sessions."""
        if self._has_local_sessions_for_mode(mode):
            self._close_setup_mode_sessions(mode)
            return
        self._open_setup_mode_sessions(mode)

    def _open_setup_mode_sessions(self, mode: str) -> None:
        """Open all available sessions for one mode without linked-session chaining."""
        if self._startup_sync_pending:
            self._show_info("Please wait: synchronizing session ownership...")
            return
        if mode == MODE_VIEW and not self._validate_unique_position_assignments():
            return
        opened_any = False
        selected_any = False
        blocked_reasons: List[str] = []
        for row in self.rows.values():
            if not row.selected_position(mode):
                continue
            selected_any = True
            has_vnc = row.entry.view_vnc_path is not None if mode == MODE_VIEW else row.entry.control_vnc_path is not None
            if not has_vnc:
                continue
            self._persist_ui_selections(row.entry.name, mode)
            opened, reason = self._try_open_single_session(row.entry.name, mode)
            opened_any = opened or opened_any
            if not opened and reason:
                blocked_reasons.append(reason)
        if not selected_any:
            self._show_info(f"No {mode} positions selected.")
            return
        if not opened_any:
            if blocked_reasons:
                preview = " | ".join(blocked_reasons[:3])
                suffix = ""
                if len(blocked_reasons) > 3:
                    suffix = f" | ...and {len(blocked_reasons) - 3} more."
                self._show_info(f"No {mode} sessions were opened. {preview}{suffix}")
            else:
                self._show_info(f"No {mode} sessions were opened.")
        self._refresh_setup_mode_buttons()

    def _close_setup_mode_sessions(self, mode: str) -> None:
        """Close only local sessions for one mode (no linked-session close propagation)."""
        keys_to_close = [key for key in self.session_manager.sessions.keys() if key[1] == mode]
        if not keys_to_close:
            self._show_info(f"No open {mode} sessions.")
            self._refresh_setup_mode_buttons()
            return
        for key in keys_to_close:
            self.session_manager.close_session(key)
        self._refresh_owner_labels()
        self._refresh_setup_mode_buttons()

    def _has_local_sessions_for_mode(self, mode: str) -> bool:
        return any(open_mode == mode for _connection_name, open_mode in self.session_manager.sessions.keys())

    def _refresh_setup_mode_buttons(self) -> None:
        if hasattr(self, "setup_view_btn"):
            view_label = "Close View" if self._has_local_sessions_for_mode(MODE_VIEW) else "Setup View"
            _set_button_text_for_icon_state(self.setup_view_btn, view_label)
        if hasattr(self, "setup_control_btn"):
            control_label = "Close Control" if self._has_local_sessions_for_mode(MODE_CONTROL) else "Setup Control"
            _set_button_text_for_icon_state(self.setup_control_btn, control_label)

    def _on_position_selection_changed(self, connection_name: str, mode: str) -> None:
        row = self.rows.get(connection_name)
        if row is None:
            return
        if mode == MODE_CONTROL:
            # Control positions are allowed to overlap other assignments.
            return
        selected = row.selected_position(mode)
        if not selected:
            return
        for other_name, other_row in self.rows.items():
            for other_mode in (MODE_VIEW, MODE_CONTROL):
                if other_name == connection_name and other_mode == mode:
                    continue
                if other_row.selected_position(other_mode) != selected:
                    continue
                row.set_selected_position(mode, "")
                self._show_info(
                    f"Position '{selected}' is already selected by {other_name} [{other_mode}]."
                )
                return

    def _on_link_selection_changed(self, _connection_name: str, _mode: str) -> None:
        """Persist row link selections and refresh linked-row nesting."""
        self._persist_ui_selections(_connection_name, _mode)
        self._rebuild_row_hierarchy()

    def _validate_unique_position_assignments(self, show_message: bool = True) -> bool:
        assignments: Dict[str, Tuple[str, str]] = {}
        for connection_name, row in self.rows.items():
            for mode in (MODE_VIEW, MODE_CONTROL):
                if mode == MODE_CONTROL:
                    continue
                selected = row.selected_position(mode)
                if not selected:
                    continue
                existing = assignments.get(selected)
                if existing is not None:
                    other_connection, other_mode = existing
                    if show_message:
                        self._show_info(
                            f"Position '{selected}' is used by both "
                            f"{other_connection} [{other_mode}] and {connection_name} [{mode}]."
                        )
                    return False
                assignments[selected] = (connection_name, mode)
        return True

    def _open_ks_file(self, connection_name: str, mode_or_shared: str) -> None:
        view_settings = load_session_settings(config_path_for(connection_name, MODE_VIEW))
        control_settings = load_session_settings(config_path_for(connection_name, MODE_CONTROL))
        configured = ""
        if mode_or_shared == "shared":
            configured = view_settings.ks or control_settings.ks
        elif mode_or_shared == MODE_VIEW:
            configured = view_settings.ks
        else:
            configured = control_settings.ks

        configured = configured.strip()
        if not configured:
            self._show_info(f"No Active Folder configured for {connection_name}.")
            return

        target, error = resolve_ks_target(configured)
        if target is None:
            self._show_info(error)
            return

        try:
            os.startfile(str(target))
            self._show_info(f"Opened active file: {target}")
        except OSError as exc:
            self._show_info(f"Failed to open active file: {exc}")

    def _untag_all(self) -> None:
        """Clear all row selection checkboxes."""
        for row in self.rows.values():
            row.tag.setChecked(False)
        self._refresh_tagged_mode_buttons()

    def _edit_session(self, connection_name: str, mode: str) -> None:
        """Open settings editor for one connection/mode and save if accepted."""
        vnc_path = self._vnc_path(connection_name, mode)
        if not vnc_path or not vnc_path.exists():
            self._show_info(f"Cannot edit: missing .vnc file for {connection_name} [{mode}]")
            return
        config_path = config_path_for(connection_name, mode)
        settings = load_session_settings(config_path)
        available_link_options = [
            (token, label)
            for token, label in self.session_link_options
            if token != self._session_token(connection_name, mode)
        ]
        dialog = SettingsDialog(
            f"Edit {mode.title()} - {connection_name}",
            settings,
            self,
            link_options=available_link_options,
            position_names=self.position_names,
            selected_position=self._selected_position_name(connection_name, mode),
        )
        if dialog.exec_() == dialog.Accepted:
            updated_settings = dialog.values()
            save_json(config_path, updated_settings.to_session_json())
            row = self.rows.get(connection_name)
            if row is not None:
                row.set_selected_position(mode, updated_settings.position_name)
                row.set_selected_link(mode, updated_settings.linked_session)
            self._persist_ui_selections(connection_name, mode)
            self._rebuild_row_hierarchy()
            self._refresh_row_ks_buttons(connection_name)
            self._binary_sensor_targets_dirty = True
            self._refresh_binary_sensor_indicators()

    def _on_session_closed(self, key: Tuple[str, str]) -> None:
        """Broadcast session close event when local process exits/closes."""
        connection_name, mode = key
        LOGGER.info("Session closed: %s [%s]", connection_name, mode)
        self.network.send_session(connection_name, mode, False)
        self._refresh_owner_labels()
        self._refresh_setup_mode_buttons()
        self._refresh_tagged_mode_buttons()

    def _on_session_unexpected_exit(self, key: Tuple[str, str]) -> None:
        """Handle dropped VNC process and optionally auto-reconnect."""
        connection_name, mode = key
        LOGGER.warning("Session dropped unexpectedly: %s [%s]", connection_name, mode)
        self._show_info(f"Session dropped: {connection_name} [{mode}]")
        if self.reconnect_on_drop:
            QTimer.singleShot(900, lambda: self._open_session(connection_name, mode))

    def _on_station_seen(self, station_name: str, _ip: str) -> None:
        """Refresh chat target list when peer discovery updates."""
        self._refresh_station_targets()
        self._refresh_owner_labels()

    def _on_remote_session_state(
        self, connection: str, mode: str, station: str, opened: bool, station_id: str
    ) -> None:
        """Only display takeover notices for peer session events."""
        self._finish_startup_sync()
        self._station_names_by_id[station_id] = station
        key = (connection, mode)
        if opened:
            # If another station already held this connection (in any mode),
            # this open implies a takeover event.
            previous_holder_ids = {
                holder_id
                for (conn_name, _conn_mode), holder_id in self._remote_mode_holders.items()
                if conn_name == connection and holder_id != station_id
            }
            if previous_holder_ids:
                previous_id = sorted(previous_holder_ids, key=str.lower)[0]
                previous = self._station_names_by_id.get(previous_id, "Unknown station")
                self.chat_window.add_notice(
                    f"{station} took over session {connection} from {previous}"
                )
            self._remote_mode_holders[key] = station_id
            self._refresh_owner_labels()
            return

        self._remote_mode_holders.pop(key, None)
        self._refresh_owner_labels()

    def _send_chat(self, text: str, target_label: str) -> None:
        """Handle outgoing chat, including slash commands."""
        target = None if target_label == "All stations" else target_label
        command, payload = parse_chat_command(text)
        if command == "/help":
            self.chat_window.add_notice("Available commands:")
            self.chat_window.add_notice("/help - Show this help text")
            self.chat_window.add_notice("/nick NewName - Change your station name")
            self.chat_window.add_notice("/topic #Topic - Set chat topic (global)")
            self.chat_window.add_notice("/me Action text - Send action-style message")
            self.chat_window.add_notice("/away [Message] - Set away status until chat input is used")
            self.chat_window.add_notice("/notify [Message] - Send notification (plays sound on receivers)")
            return
        if command == "/nick":
            # /nick updates runtime identity and persists to default.local.json.
            new_name = payload
            if new_name:
                self.station_name = new_name
                self.network.set_station_name(new_name)
                self.chat_window.set_station_title(new_name)
                self._refresh_window_title()
                self.default_settings.station_name = new_name
                local_data: Dict[str, object] = {}
                if DEFAULT_LOCAL_CONFIG_PATH.exists():
                    try:
                        with DEFAULT_LOCAL_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                            raw_local = json.load(handle)
                        if isinstance(raw_local, dict):
                            local_data = dict(raw_local)
                    except (OSError, json.JSONDecodeError):
                        local_data = {}
                local_data["station_name"] = new_name
                save_json(DEFAULT_LOCAL_CONFIG_PATH, local_data)
                self.chat_window.add_notice(f"Nickname changed to {new_name}")
                LOGGER.info("Nick changed to: %s", new_name)
            return
        if command == "/topic":
            # /topic is global for all online stations.
            self.topic = payload or "#General"
            self.chat_window.set_topic(self.topic)
            self.chat_window.add_notice(f"Topic changed to {self.topic}")
            self.network.send_topic(self.topic)
            LOGGER.info("Topic changed to: %s", self.topic)
            return
        if command == "/away":
            # /away marks station name and is auto-cleared on next local chat input.
            msg = payload or "Away"
            self.away_message = msg
            if "(Away)" not in self.station_name:
                self.station_name = f"{self.station_name} (Away)"
                self.network.set_station_name(self.station_name)
                self._refresh_window_title()
                self.chat_window.set_station_title(self.station_name)
            self.network.send_away(True, msg)
            self.chat_window.add_notice(f"Away: {msg}")
            return
        if command == "/me":
            # /me sends action-style chat messages.
            action_text = payload
            if action_text:
                self.network.send_chat(action_text, target, is_action=True)
                self.chat_window.add_message(self.station_name, action_text, action=True)
            return
        if command == "/notify":
            notify_text = payload
            if not notify_text:
                notify_text = "Notification"
            self.network.send_chat(notify_text, target, is_action=False, is_notify=True)
            if target:
                self.chat_window.add_message(f"{self.station_name} -> {target}", f"[NOTIFY] {notify_text}", action=False)
            else:
                self.chat_window.add_message(self.station_name, f"[NOTIFY] {notify_text}", action=False)
            return

        self.network.send_chat(text, target, is_action=False)
        if target:
            self.chat_window.add_message(f"{self.station_name} -> {target}", text, action=False)
        else:
            self.chat_window.add_message(self.station_name, text, action=False)

    def _clear_away_if_needed(self) -> None:
        """Remove away marker when user interacts with chat input again."""
        if "(Away)" in self.station_name:
            self.station_name = self.station_name.replace(" (Away)", "").strip()
            self.network.set_station_name(self.station_name)
            self.chat_window.set_station_title(self.station_name)
            self._refresh_window_title()
            if self.away_message:
                self.chat_window.add_notice("Away status cleared.")
            self.network.send_away(False, "")
            self.away_message = ""

    def _on_chat_received(self, station: str, text: str, _target: str, is_action: bool, is_notify: bool) -> None:
        """Handle incoming chat: append, focus chat window, and play notice sound."""
        shown_text = f"[NOTIFY] {text}" if is_notify else text
        self.chat_window.add_message(station, shown_text, action=is_action)
        self._refresh_station_targets()
        index = self.chat_window.target_box.findText(station)
        if index >= 0:
            self.chat_window.target_box.setCurrentIndex(index)
        if not self.chat_window.isVisible():
            self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()
        if is_notify and self.sound.source().isValid():
            self.sound.play()

    def _on_takeover_notice(self, station: str, connection: str, previous_holder: str) -> None:
        """Append takeover notices broadcast by other stations."""
        self.chat_window.add_notice(
            f"{station} took over session {connection} from {previous_holder}"
        )

    def _on_topic_changed(self, station: str, topic: str) -> None:
        """Apply incoming global topic updates from remote stations."""
        self.topic = topic
        self.chat_window.set_topic(topic)
        self.chat_window.add_notice(f"{station} changed topic to {topic}")

    def _on_away_changed(self, station: str, is_away: bool, message: str) -> None:
        """Display remote away/back status updates in chat notices."""
        if is_away:
            if message:
                self.chat_window.add_notice(f"{station} is away: {message}")
            else:
                self.chat_window.add_notice(f"{station} is away")
        else:
            self.chat_window.add_notice(f"{station} is back")

    def _on_nick_changed(self, old_name: str, new_name: str) -> None:
        """Display remote station nickname changes in chat."""
        self.chat_window.add_notice(f"{old_name} is now known as {new_name}")

    def _refresh_station_targets(self) -> None:
        """Rebuild chat dropdown options from known active stations."""
        self.chat_window.set_targets(list(self.network.stations.keys()))

    def _refresh_stations(self) -> None:
        """Trigger manual discovery broadcast and note it in chat."""
        self.network.send_hello()
        self.network.send_session_sync_request()
        self._refresh_station_targets()
        self.chat_window.add_notice("Station refresh sent.")
        self._refresh_owner_labels()

    def _rebroadcast_sessions(self) -> None:
        """Periodically re-announce open local sessions for late joiners."""
        for connection_name, mode in self.session_manager.sessions.keys():
            self.network.send_session(connection_name, mode, True)
        self._refresh_owner_labels()

    def _refresh_owner_labels(self) -> None:
        """Refresh owner/age metadata for each connection row."""
        remote_info = self.network.remote_sessions_info
        for name, row in self.rows.items():
            local_modes = [m for (conn, m) in self.session_manager.sessions.keys() if conn == name]
            if local_modes:
                row.owner_label.setText(f"Owner: {self.station_name} ({'/'.join(sorted(local_modes))})")
                owner_mode = MODE_CONTROL if MODE_CONTROL in local_modes else (local_modes[0] if local_modes else "")
                row.set_owner_in_use(True, owner_mode)
            else:
                matches = []
                for (conn, mode), (holder, age_seconds) in remote_info.items():
                    if conn == name:
                        matches.append((holder, mode, int(age_seconds)))
                if matches:
                    holder, mode, age_seconds = sorted(matches, key=lambda x: x[2])[0]
                    row.owner_label.setText(
                        f"Owner: {holder} [{mode}] {format_elapsed_duration(age_seconds)}"
                    )
                    row.set_owner_in_use(True, mode)
                else:
                    row.owner_label.setText("Owner: available")
                    row.set_owner_in_use(False, "")
            row.set_mode_open_state(
                MODE_VIEW, MODE_VIEW in local_modes, row.entry.view_vnc_path is not None
            )
            row.set_mode_open_state(
                MODE_CONTROL, MODE_CONTROL in local_modes, row.entry.control_vnc_path is not None
            )

    def _check_station_presence_changes(self) -> None:
        """Emit online/offline notices based on station set deltas."""
        current = set(self.network.stations.keys())
        joined = sorted(current - self._online_snapshot, key=str.lower)
        left = sorted(self._online_snapshot - current, key=str.lower)
        for station in joined:
            self.chat_window.add_notice(f"{station} is online")
        for station in left:
            self.chat_window.add_notice(f"{station} is offline")
        self._online_snapshot = current
        self._refresh_owner_labels()

    def _run_validation(self) -> None:
        """Run config/runtime validation and show concise summary."""
        findings, checked_files = validate_runtime_configuration_details()
        if not findings:
            self._show_info(f"Validation passed with no findings. Checked {checked_files} file(s).")
            LOGGER.info("Validation passed. Checked %d file(s).", checked_files)
            return
        preview_count = min(3, len(findings))
        preview = "\n".join(f"- {item}" for item in findings[:preview_count])
        suffix = ""
        if len(findings) > preview_count:
            suffix = f"\n...and {len(findings) - preview_count} more (see logs/app.log)."
        self._show_info(
            f"Validation found {len(findings)} issue(s) across {checked_files} checked file(s):\n"
            f"{preview}{suffix}"
        )
        for item in findings:
            LOGGER.warning("Validation: %s", item)

    def _export_config_bundle(self) -> None:
        """Export JSON config bundle to user-selected zip path."""
        suggested = suggested_export_name()
        out_path, _ = QFileDialog.getSaveFileName(self, "Export config bundle", suggested, "Zip Files (*.zip)")
        if not out_path:
            return
        final = export_config_bundle(Path(out_path))
        self._show_info(f"Exported config bundle: {final}")
        LOGGER.info("Config bundle exported: %s", final)

    def _import_config_bundle(self) -> None:
        """Import JSON config bundle from zip."""
        in_path, _ = QFileDialog.getOpenFileName(self, "Import config bundle", "", "Zip Files (*.zip)")
        if not in_path:
            return
        try:
            applied = import_config_bundle(Path(in_path))
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self._show_info(f"Import failed: {exc}")
            LOGGER.warning("Config bundle import failed: %s", exc)
            return
        self._reload_runtime_defaults_from_disk()
        self.connections = scan_connections()
        self._binary_sensor_targets_dirty = True
        self._rebuild_connection_rows()
        self._show_info(f"Imported {len(applied)} config file(s).")
        LOGGER.info("Config bundle imported: %s (%d files)", in_path, len(applied))

    def _rebuild_connection_rows(self) -> None:
        """Recreate the scroll-area row widgets from current connection list."""
        self.position_names = [p.name for p in scan_positions()]
        self.session_link_options = self._build_session_link_options()
        self._binary_sensor_targets_dirty = True
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.rows.clear()
        if not self.connections:
            self.rows_layout.addWidget(QLabel("No .vnc files found in vnc-control/ or vnc-view/"))
        for entry in self.connections:
            row = ConnectionRow(
                entry,
                {
                    "open": self._open_session,
                    "toggle_open": self._toggle_session,
                    "close": self._close_session,
                    "edit": self._edit_session,
                    "open_ks": self._open_ks_file,
                    "minimized_changed": self._refresh_minimize_all_button,
                    "position_changed": self._on_position_selection_changed,
                    "link_changed": self._on_link_selection_changed,
                },
                self.position_names,
                self.session_link_options,
            )
            row.set_effective_theme(self.effective_theme)
            self._populate_row_from_saved_settings(row)
            row.tag.toggled.connect(
                lambda checked, row=row, self=self: self._on_row_tag_toggled(row, checked)
            )
            self.rows[entry.name] = row
        self._rebuild_row_hierarchy()
        self._clear_duplicate_positions_after_load()
        self._restore_local_ui_state()
        self._rebuild_row_hierarchy()
        self._refresh_minimize_all_button()
        self._refresh_owner_labels()
        self._refresh_binary_sensor_indicators()
        if hasattr(self, "setup_select"):
            self._refresh_setup_targets()

    def _linked_row_structure(self) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
        parent_to_children: Dict[str, List[str]] = {}
        child_to_parent: Dict[str, str] = {}
        for connection_name in [entry.name for entry in self.connections]:
            row = self.rows.get(connection_name)
            if row is None:
                continue
            seen_children: Set[str] = set()
            for mode in (MODE_VIEW, MODE_CONTROL):
                parsed = self._parse_session_token(row.selected_link(mode))
                if parsed is None:
                    continue
                child_name, _child_mode = parsed
                if child_name == connection_name or child_name in seen_children or child_name not in self.rows:
                    continue
                if child_name in child_to_parent:
                    continue
                if self._would_create_link_cycle(connection_name, child_name, child_to_parent):
                    continue
                parent_to_children.setdefault(connection_name, []).append(child_name)
                child_to_parent[child_name] = connection_name
                seen_children.add(child_name)
        return parent_to_children, child_to_parent

    @staticmethod
    def _would_create_link_cycle(parent_name: str, child_name: str, child_to_parent: Dict[str, str]) -> bool:
        current = parent_name
        while current in child_to_parent:
            current = child_to_parent[current]
            if current == child_name:
                return True
        return False

    def _rebuild_row_hierarchy(self) -> None:
        if not hasattr(self, "rows_layout"):
            return
        for row in self.rows.values():
            row.clear_child_rows()
            row.widget.setParent(None)
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        if not self.rows:
            self.rows_layout.addWidget(QLabel("No .vnc files found in vnc-control/ or vnc-view/"))
            self.rows_layout.addStretch(1)
            return
        parent_to_children, child_to_parent = self._linked_row_structure()

        def attach_children(parent_name: str) -> None:
            parent_row = self.rows.get(parent_name)
            if parent_row is None:
                return
            for child_name in parent_to_children.get(parent_name, []):
                child_row = self.rows.get(child_name)
                if child_row is None:
                    continue
                parent_row.add_child_row(child_row)
                attach_children(child_name)

        for entry in self.connections:
            if entry.name in child_to_parent:
                continue
            row = self.rows.get(entry.name)
            if row is None:
                continue
            self.rows_layout.addWidget(row.widget)
            attach_children(entry.name)
        self.rows_layout.addStretch(1)

    def _collect_local_ui_state(self) -> Dict[str, object]:
        connections: Dict[str, object] = {}
        for connection_name, row in self.rows.items():
            connections[connection_name] = {
                "tagged": bool(row.tag.isChecked()),
                "minimized": bool(row.is_minimized()),
                "position_view": row.selected_position(MODE_VIEW),
                "position_control": row.selected_position(MODE_CONTROL),
                "link_view": row.selected_link(MODE_VIEW),
                "link_control": row.selected_link(MODE_CONTROL),
            }
        current_setup = self._current_setup_name() if hasattr(self, "setup_select") else ""
        return {
            "setup_name": current_setup,
            "connections": connections,
        }

    def _restore_local_ui_state(self) -> None:
        raw_state = self.settings_store.value("local_ui_state", "")
        if not raw_state:
            return
        try:
            data = json.loads(str(raw_state))
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        setup_name = str(data.get("setup_name", "")).strip()
        if setup_name and hasattr(self, "setup_select"):
            self._set_selected_setup_name(setup_name, trigger=False)
            self.settings_store.setValue("last_setup_name", setup_name)
        connections = data.get("connections", {})
        if not isinstance(connections, dict):
            return
        self._suspend_tag_auto_assign = True
        try:
            for connection_name, config in connections.items():
                row = self.rows.get(str(connection_name))
                if row is None or not isinstance(config, dict):
                    continue
                row.tag.setChecked(bool(config.get("tagged", row.tag.isChecked())))
                row.set_minimized(bool(config.get("minimized", row.is_minimized())))
                row.set_selected_position(MODE_VIEW, str(config.get("position_view", "")).strip())
                row.set_selected_position(MODE_CONTROL, str(config.get("position_control", "")).strip())
                stored_link_view = str(config.get("link_view", "")).strip()
                stored_link_control = str(config.get("link_control", "")).strip()
                if stored_link_view:
                    row.set_selected_link(MODE_VIEW, stored_link_view)
                if stored_link_control:
                    row.set_selected_link(MODE_CONTROL, stored_link_control)
        finally:
            self._suspend_tag_auto_assign = False
        self._clear_duplicate_positions_after_load()
        self._refresh_minimize_all_button()

    def _populate_row_from_saved_settings(self, row: ConnectionRow) -> None:
        view_settings = load_session_settings(config_path_for(row.entry.name, MODE_VIEW))
        control_settings = load_session_settings(config_path_for(row.entry.name, MODE_CONTROL))
        row.set_selected_position(MODE_VIEW, view_settings.position_name)
        row.set_selected_position(MODE_CONTROL, control_settings.position_name)
        row.set_selected_link(MODE_VIEW, view_settings.linked_session)
        row.set_selected_link(MODE_CONTROL, control_settings.linked_session)
        row.set_ks_paths(
            view_settings.ks,
            control_settings.ks,
            view_settings.ks_button_text,
            control_settings.ks_button_text,
        )

    def _refresh_row_ks_buttons(self, connection_name: str) -> None:
        row = self.rows.get(connection_name)
        if row is None:
            return
        view_settings = load_session_settings(config_path_for(connection_name, MODE_VIEW))
        control_settings = load_session_settings(config_path_for(connection_name, MODE_CONTROL))
        row.set_ks_paths(
            view_settings.ks,
            control_settings.ks,
            view_settings.ks_button_text,
            control_settings.ks_button_text,
        )

    def _clear_duplicate_positions_after_load(self) -> None:
        """Keep first assignment per position and clear later duplicates."""
        assigned: Dict[str, Tuple[str, str]] = {}
        for connection_name, row in self.rows.items():
            for mode in (MODE_VIEW, MODE_CONTROL):
                if mode == MODE_CONTROL:
                    continue
                selected = row.selected_position(mode)
                if not selected:
                    continue
                if selected in assigned:
                    row.set_selected_position(mode, "")
                    continue
                assigned[selected] = (connection_name, mode)

    def _show_info(self, text: str) -> None:
        """Show non-blocking informational feedback."""
        self.toast.show_message(text)
        LOGGER.info("Info: %s", text)

    def _open_positions_tool(self) -> None:
        """Open or focus the dedicated positions tool window."""
        if self._positions_tool_window is None or not self._positions_tool_window.isVisible():
            self._positions_tool_window = PositionSettingsWindow(theme_mode=self.theme_mode)
            self._positions_tool_window.window_closed.connect(self._on_positions_tool_closed)
        self._positions_tool_window.show()
        self._positions_tool_window.raise_()
        self._positions_tool_window.activateWindow()

    def _open_sessions_tool(self) -> None:
        """Open or focus the dedicated sessions tool window."""
        if self._sessions_tool_window is None or not self._sessions_tool_window.isVisible():
            self._sessions_tool_window = SessionSettingsWindow(theme_mode=self.theme_mode)
            self._sessions_tool_window.window_closed.connect(self._on_sessions_tool_closed)
        self._sessions_tool_window.show()
        self._sessions_tool_window.raise_()
        self._sessions_tool_window.activateWindow()

    def _on_positions_tool_closed(self) -> None:
        self._positions_tool_window = None
        self._on_settings_tool_closed()

    def _on_sessions_tool_closed(self) -> None:
        self._sessions_tool_window = None
        self._on_settings_tool_closed()

    def _on_settings_tool_closed(self) -> None:
        """Refresh UI state after closing the position/session settings tool."""
        self.position_names = [p.name for p in scan_positions()]
        for row in self.rows.values():
            row.refresh_option_sets(self.position_names, self.session_link_options)
            self._populate_row_from_saved_settings(row)
        for connection_name in self.rows.keys():
            self._refresh_row_ks_buttons(connection_name)
        self._clear_duplicate_positions_after_load()
        self._rebuild_row_hierarchy()
        self._binary_sensor_targets_dirty = True
        self._refresh_binary_sensor_indicators()

    def _set_open_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable all actions that can open new sessions."""
        self.view_all_btn.setEnabled(enabled)
        self.control_all_btn.setEnabled(enabled)
        for row in self.rows.values():
            row.view_btn.setEnabled(enabled and row.entry.view_vnc_path is not None)
            row.control_btn.setEnabled(enabled and row.entry.control_vnc_path is not None)

    def _process_startup_sync(self) -> None:
        """Poll startup sync and unlock open actions after short handshake window."""
        if not self._startup_sync_pending:
            return
        self._startup_sync_attempts += 1
        if self._startup_sync_attempts <= 3:
            self.network.send_session_sync_request()
            return
        self._finish_startup_sync()

    def _finish_startup_sync(self) -> None:
        """Mark startup sync complete and re-enable open controls."""
        if not self._startup_sync_pending:
            return
        self._startup_sync_pending = False
        self._set_open_controls_enabled(True)
        if self.startup_sync_timer.isActive():
            self.startup_sync_timer.stop()
        self._refresh_owner_labels()

    def _on_session_sync_requested(self, _station_name: str) -> None:
        """Respond to peer sync request by rebroadcasting local open sessions."""
        self._rebroadcast_sessions()

    def changeEvent(self, event) -> None:
        """Keep the setup-name placeholder visible when the main window regains focus."""
        if (
            event.type() == QEvent.ActivationChange
            and self.isActiveWindow()
            and hasattr(self, "setup_name_input")
            and self.setup_name_input.text().strip() == ""
            and self.focusWidget() is self.setup_name_input
        ):
            self.setup_name_input.clearFocus()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure sessions/network/chat are closed cleanly with the main window."""
        self.settings_store.setValue("main_geometry", self.saveGeometry())
        self.settings_store.setValue("chat_geometry", self.chat_window.saveGeometry())
        self.settings_store.setValue("main_width", self.width())
        self.settings_store.setValue("main_height", self.height())
        self.settings_store.setValue("chat_width", self.chat_window.width())
        self.settings_store.setValue("chat_height", self.chat_window.height())
        if hasattr(self, "setup_select"):
            self.settings_store.setValue("last_setup_name", self._current_setup_name())
        self.settings_store.setValue("local_ui_state", json.dumps(self._collect_local_ui_state()))
        if hasattr(self, "ha_binary_sensor_timer") and self.ha_binary_sensor_timer.isActive():
            self.ha_binary_sensor_timer.stop()
        set_json_warning_reporter(None)
        self.session_manager.close_all()
        self.network.close()
        if self._positions_tool_window is not None:
            self._positions_tool_window.close()
        if self._sessions_tool_window is not None:
            self._sessions_tool_window.close()
        if self._settings_window is not None:
            self._settings_window.close()
        self.chat_window.close()
        super().closeEvent(event)


