"""Main application window: connection list, controls, chat, and coordination."""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QSettings, QSize, QTimer, Qt, QUrl
from PyQt5.QtGui import QCloseEvent, QIcon, QPixmap
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .chat_window import ChatWindow
from .config import (
    config_path_for,
    load_default_settings,
    load_session_overrides,
    load_session_settings,
    position_by_name,
    resolve_ks_target,
    save_json,
    scan_connections,
    scan_positions,
    update_session_overrides,
)
from .constants import (
    APPLYSETUP_ICON_PATH,
    CHAT_ICON_PATH,
    CONTROL_ICON_PATH,
    EDIT_ICON_PATH,
    EXPORT_ICON_PATH,
    HELLO_INTERVAL_MS,
    ICON_PATH,
    IMPORT_ICON_PATH,
    LINK_ICON_PATH,
    MODE_CONTROL,
    MODE_VIEW,
    MONITOR_ICON_PATH,
    NOTICE_SOUND_PATH,
    SAVE_ICON_PATH,
    SPREADSHEET_ICON_PATH,
    SESSION_BROADCAST_INTERVAL_MS,
    STATION_PRESENCE_CHECK_MS,
    UNLOCK_ICON_PATH,
    UNTAG_ICON_PATH,
    VALIDATE_ICON_PATH,
    VIEW_ICON_PATH,
)
from .logic import parse_chat_command
from .models import ConnectionEntry, SessionSettings
from .network import NetworkBus
from .settings_dialog import SettingsDialog
from .theme import windows_prefers_dark
from .toast import ToastLabel
from .tools import (
    export_config_bundle,
    import_config_bundle,
    suggested_export_name,
    validate_runtime_configuration,
)
from .vnc import SessionManager
from .layout_tool import LayoutToolWindow

LOGGER = logging.getLogger(__name__)


def _icon_size_for_font_size(point_size: int) -> int:
    """Return a small icon size that tracks UI font size."""
    return max(12, min(28, int(point_size * 1.25)))


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


def _set_button_icon(button: QPushButton, icon_path: Path, size_px: int = 14) -> None:
    """Apply a small icon when the asset exists (safe in source/frozen runs)."""
    if not icon_path.exists():
        return
    button.setIcon(QIcon(str(icon_path)))
    button.setProperty("icon_scale_with_font", True)
    if size_px > 0:
        button.setProperty("icon_base_size", int(size_px))
    _apply_scaled_icon_size(button)


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
        self.widget = QFrame()
        self.widget.setObjectName("connectionRowCard")
        outer = QHBoxLayout(self.widget)
        outer.setContentsMargins(8, 5, 8, 5)
        outer.setSpacing(6)

        left_col = QVBoxLayout()
        left_col.setSpacing(3)
        outer.addLayout(left_col, 1)
        right_col = QVBoxLayout()
        right_col.setSpacing(3)
        outer.addLayout(right_col)

        self.tag = QCheckBox()
        self.name_btn = QPushButton(entry.name)
        self.name_btn.setStyleSheet("font-weight:600; text-align:left; padding:1px 4px;")
        self.name_btn.clicked.connect(lambda: self.tag.setChecked(not self.tag.isChecked()))
        header_row = QHBoxLayout()
        header_row.addWidget(self.tag)
        header_row.addWidget(self.name_btn, 1)
        left_col.addLayout(header_row)

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
            lambda _text: self._notify_position_change(MODE_VIEW)
        )
        self.position_control.currentTextChanged.connect(
            lambda _text: self._notify_position_change(MODE_CONTROL)
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
        self.link_view.currentTextChanged.connect(lambda _text: self._notify_link_change(MODE_VIEW))
        self.link_control.currentTextChanged.connect(
            lambda _text: self._notify_link_change(MODE_CONTROL)
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
        _match_button_widths(self.ks_btn, self.ksv_btn, self.ksc_btn)
        ks_row = QHBoxLayout()
        ks_row.addWidget(self.ks_btn)
        ks_row.addWidget(self.ksv_btn)
        ks_row.addWidget(self.ksc_btn)
        right_col.addLayout(ks_row)

        self.view_btn = QPushButton("View")
        _set_button_icon(self.view_btn, VIEW_ICON_PATH)
        _set_compact_button(self.view_btn)
        self.view_btn.clicked.connect(lambda: callbacks["open"](entry.name, MODE_VIEW))
        self.control_btn = QPushButton("Control")
        _set_button_icon(self.control_btn, CONTROL_ICON_PATH)
        _set_compact_button(self.control_btn)
        self.control_btn.clicked.connect(lambda: callbacks["open"](entry.name, MODE_CONTROL))
        open_row = QHBoxLayout()
        open_row.addWidget(self.view_btn)
        open_row.addWidget(self.control_btn)
        right_col.addLayout(open_row)

        self.edit_view_btn = QPushButton("Edit View")
        _set_button_icon(self.edit_view_btn, EDIT_ICON_PATH)
        _set_compact_button(self.edit_view_btn)
        self.edit_view_btn.clicked.connect(lambda: callbacks["edit"](entry.name, MODE_VIEW))
        self.edit_control_btn = QPushButton("Edit Control")
        _set_button_icon(self.edit_control_btn, EDIT_ICON_PATH)
        _set_compact_button(self.edit_control_btn)
        self.edit_control_btn.clicked.connect(lambda: callbacks["edit"](entry.name, MODE_CONTROL))
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.edit_view_btn)
        edit_row.addWidget(self.edit_control_btn)
        right_col.addLayout(edit_row)

        self.close_view_btn = QPushButton("Close view")
        _set_button_icon(self.close_view_btn, UNLOCK_ICON_PATH)
        _set_compact_button(self.close_view_btn)
        self.close_view_btn.clicked.connect(lambda: callbacks["close"](entry.name, MODE_VIEW))
        self.close_control_btn = QPushButton("Close control")
        _set_button_icon(self.close_control_btn, UNLOCK_ICON_PATH)
        _set_compact_button(self.close_control_btn)
        self.close_control_btn.clicked.connect(lambda: callbacks["close"](entry.name, MODE_CONTROL))
        close_row = QHBoxLayout()
        close_row.addWidget(self.close_view_btn)
        close_row.addWidget(self.close_control_btn)
        right_col.addLayout(close_row)

        _match_button_widths(
            self.view_btn,
            self.control_btn,
            self.edit_view_btn,
            self.edit_control_btn,
            self.close_view_btn,
            self.close_control_btn,
        )

        view_available = entry.view_vnc_path is not None
        control_available = entry.control_vnc_path is not None

        self._apply_mode_button_style(self.view_btn, view_available, "#2f9e44")
        self._apply_mode_button_style(self.control_btn, control_available, "#c92a2a")
        self._apply_secondary_mode_button_style(self.close_view_btn, view_available, "#8f7500", "white")
        self._apply_secondary_mode_button_style(self.close_control_btn, control_available, "#8f7500", "white")
        self._apply_mode_button_style(self.edit_view_btn, view_available, "#1971c2")
        self._apply_mode_button_style(self.edit_control_btn, control_available, "#1971c2")
        self._apply_mode_button_style(self.ksv_btn, view_available, "#6741d9")
        self._apply_mode_button_style(self.ksc_btn, control_available, "#6741d9")
        self._refresh_ks_buttons("", "")

    def _notify_position_change(self, mode: str) -> None:
        if self._syncing:
            return
        self._callbacks["position_changed"](self.entry.name, mode)

    def _notify_link_change(self, mode: str) -> None:
        if self._syncing:
            return
        self._callbacks["link_changed"](self.entry.name, mode)

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

    def _refresh_ks_buttons(self, view_ks: str, control_ks: str) -> None:
        same = bool(view_ks and control_ks and view_ks == control_ks)
        view_only = bool(view_ks) and not bool(control_ks)
        control_only = bool(control_ks) and not bool(view_ks)
        both_different = bool(view_ks) and bool(control_ks) and not same

        self.ks_btn.setVisible(same)
        self.ksv_btn.setVisible(view_only or both_different)
        self.ksc_btn.setVisible(control_only or both_different)
        self.ks_btn.setEnabled(same)
        self.ksv_btn.setText("KS" if view_only else "KSV")
        self.ksc_btn.setText("KS" if control_only else "KSC")
        if same:
            self.ks_btn.setStyleSheet("background:#6741d9; color:white; font-weight:700;")

    def set_ks_paths(self, view_ks: str, control_ks: str) -> None:
        self._refresh_ks_buttons(view_ks.strip(), control_ks.strip())

    @staticmethod
    def _apply_mode_button_style(button: QPushButton, available: bool, active_bg: str) -> None:
        """Set clear visual state for available/unavailable mode buttons."""
        button.setEnabled(available)
        if available:
            button.setStyleSheet(
                f"background:{active_bg}; color:white; font-weight:600; padding:1px 6px; border:none;"
            )
            button.setToolTip("")
            return
        button.setStyleSheet(
            "background:#edf0f3; color:#6b7280; font-weight:500; padding:1px 6px; border:none;"
        )
        button.setToolTip("No .vnc file available for this mode")

    @staticmethod
    def _apply_secondary_mode_button_style(
        button: QPushButton, available: bool, active_bg: str, active_fg: str
    ) -> None:
        """Set visual state for secondary mode buttons (close/edit style variants)."""
        button.setEnabled(available)
        if available:
            button.setStyleSheet(
                f"background:{active_bg}; color:{active_fg}; font-weight:600; padding:1px 6px; border:none;"
            )
            button.setToolTip("")
            return
        button.setStyleSheet(
            "background:#edf0f3; color:#6b7280; font-weight:500; padding:1px 6px; border:none;"
        )
        button.setToolTip("No .vnc file available for this mode")


class MainWindow(QMainWindow):
    """Primary controller window that coordinates all app subsystems."""

    def __init__(self) -> None:
        """Initialize state, services, and build the full UI."""
        super().__init__()
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
        self.connections = scan_connections()
        self.position_names: List[str] = [p.name for p in scan_positions()]
        self.session_link_options: List[Tuple[str, str]] = self._build_session_link_options()
        self.rows: Dict[str, ConnectionRow] = {}
        # Tracks latest remote holder per (connection, mode) by station id.
        self._remote_mode_holders: Dict[Tuple[str, str], str] = {}
        # Station id -> latest seen station display name.
        self._station_names_by_id: Dict[str, str] = {}
        self._online_snapshot: set[str] = set()
        self._startup_sync_pending = True
        self._startup_sync_attempts = 0
        self._layout_tool_window: Optional[LayoutToolWindow] = None

        self.session_manager = SessionManager(
            self._on_session_closed,
            self._show_info,
            on_unexpected_exit=self._on_session_unexpected_exit,
        )
        self.network = NetworkBus(self.station_name)
        self.network.station_seen.connect(self._on_station_seen)
        self.network.session_state.connect(self._on_remote_session_state)
        self.network.chat_received.connect(self._on_chat_received)
        self.network.takeover_notice.connect(self._on_takeover_notice)
        self.network.topic_changed.connect(self._on_topic_changed)
        self.network.away_changed.connect(self._on_away_changed)
        self.network.nick_changed.connect(self._on_nick_changed)
        self.network.session_sync_requested.connect(self._on_session_sync_requested)

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
        self.toast = ToastLabel(self)
        self.chat_window.set_topic(self.topic)

        self._build_ui()
        self._set_open_controls_enabled(False)
        self._refresh_station_targets()
        # Announce this station immediately on startup.
        self.network.send_hello()
        self.network.send_session_sync_request()

        self.hello_timer = QTimer(self)
        self.hello_timer.timeout.connect(self.network.send_hello)
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

    def _build_ui(self) -> None:
        """Create widgets, connection list, and fixed bottom action rows."""
        self.setWindowTitle(self.station_name)
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

        setup_row = QHBoxLayout()
        root.addLayout(setup_row)
        setup_row.addStretch(1)
        self.setup_positions_btn = QPushButton("Setup Positions")
        _set_button_icon(self.setup_positions_btn, APPLYSETUP_ICON_PATH)
        _set_compact_button(self.setup_positions_btn)
        self.setup_positions_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700;")
        self.setup_positions_btn.clicked.connect(self._setup_positions)
        setup_row.addWidget(self.setup_positions_btn)
        setup_row.addStretch(1)

        actions_row1 = QHBoxLayout()
        root.addLayout(actions_row1)
        self.view_all_btn = QPushButton("View all tagged")
        _set_button_icon(self.view_all_btn, VIEW_ICON_PATH)
        _set_compact_button(self.view_all_btn)
        self.view_all_btn.setStyleSheet("background:#2f9e44; color:white; font-weight:700;")
        self.view_all_btn.clicked.connect(lambda: self._open_tagged(MODE_VIEW))
        self.control_all_btn = QPushButton("Control all tagged")
        _set_button_icon(self.control_all_btn, CONTROL_ICON_PATH)
        _set_compact_button(self.control_all_btn)
        self.control_all_btn.setStyleSheet("background:#c92a2a; color:white; font-weight:700;")
        self.control_all_btn.clicked.connect(lambda: self._open_tagged(MODE_CONTROL))
        _match_button_widths(self.view_all_btn, self.control_all_btn)
        actions_row1.addWidget(self.view_all_btn)
        actions_row1.addWidget(self.control_all_btn)

        actions_row2 = QHBoxLayout()
        root.addLayout(actions_row2)
        close_tagged = QPushButton("Close all tagged")
        _set_button_icon(close_tagged, UNLOCK_ICON_PATH)
        _set_compact_button(close_tagged)
        close_tagged.clicked.connect(self._close_tagged_sessions)
        close_tagged.setStyleSheet("background:#8f7500; color:white; font-weight:700;")
        close_all = QPushButton("Close all sessions")
        _set_button_icon(close_all, UNLOCK_ICON_PATH)
        _set_compact_button(close_all)
        close_all.clicked.connect(self._close_all_sessions)
        close_all.setStyleSheet("background:#8f7500; color:white; font-weight:700;")
        _match_button_widths(close_tagged, close_all)
        actions_row2.addWidget(close_tagged)
        actions_row2.addWidget(close_all)

        actions_row3 = QHBoxLayout()
        root.addLayout(actions_row3)
        untag_all = QPushButton("Untag all")
        _set_button_icon(untag_all, UNTAG_ICON_PATH)
        _set_compact_button(untag_all)
        untag_all.clicked.connect(self._untag_all)
        self.chat_btn = QPushButton("Chat")
        _set_button_icon(self.chat_btn, CHAT_ICON_PATH)
        _set_compact_button(self.chat_btn)
        self.chat_btn.clicked.connect(self._open_chat)
        _match_button_widths(untag_all, self.chat_btn)
        actions_row3.addWidget(untag_all)
        actions_row3.addWidget(self.chat_btn)

        actions_row4 = QHBoxLayout()
        root.addLayout(actions_row4)
        actions_row4.addStretch(1)
        tools_stack = QVBoxLayout()
        tools_top_row = QHBoxLayout()
        sizes_btn = QPushButton("Sizes")
        _set_button_icon(sizes_btn, EDIT_ICON_PATH)
        _set_compact_button(sizes_btn)
        sizes_btn.clicked.connect(self._open_layout_tool)
        validate_btn = QPushButton("Validate config")
        _set_button_icon(validate_btn, VALIDATE_ICON_PATH)
        _set_compact_button(validate_btn)
        validate_btn.clicked.connect(self._run_validation)
        _match_button_widths(sizes_btn, validate_btn)
        tools_top_row.addWidget(sizes_btn)
        tools_top_row.addWidget(validate_btn)
        tools_stack.addLayout(tools_top_row)

        take_row = QHBoxLayout()
        self.takeover_checkbox = QCheckBox("Take over session")
        import_btn = QPushButton("Import config")
        _set_button_icon(import_btn, IMPORT_ICON_PATH)
        _set_compact_button(import_btn)
        import_btn.clicked.connect(self._import_config_bundle)
        take_row.addWidget(self.takeover_checkbox)
        take_row.addWidget(import_btn)
        tools_stack.addLayout(take_row)

        reconnect_row = QHBoxLayout()
        self.reconnect_checkbox = QCheckBox("Reconnect on drop")
        self.reconnect_checkbox.setChecked(self.reconnect_on_drop)
        self.reconnect_checkbox.toggled.connect(self._set_reconnect_on_drop)
        export_btn = QPushButton("Export config")
        _set_button_icon(export_btn, EXPORT_ICON_PATH)
        _set_compact_button(export_btn)
        export_btn.clicked.connect(self._export_config_bundle)
        _match_button_widths(import_btn, export_btn)
        reconnect_row.addWidget(self.reconnect_checkbox)
        reconnect_row.addWidget(export_btn)
        tools_stack.addLayout(reconnect_row)

        actions_row4.addLayout(tools_stack)
        actions_row4.addStretch(1)

        actions_row5 = QHBoxLayout()
        root.addLayout(actions_row5)
        actions_row5.addStretch(1)
        theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Auto", "Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        font_label = QLabel("Font Size:")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 32)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setValue(self.font_size)
        apply_font_btn = QPushButton("Apply")
        _set_button_icon(apply_font_btn, SAVE_ICON_PATH)
        _set_compact_button(apply_font_btn)
        apply_font_btn.clicked.connect(self._apply_font_size_from_ui)
        _match_button_widths(apply_font_btn)
        actions_row5.addWidget(theme_label)
        actions_row5.addWidget(self.theme_combo)
        actions_row5.addWidget(font_label)
        actions_row5.addWidget(self.font_size_spin)
        actions_row5.addWidget(apply_font_btn)
        actions_row5.addStretch(1)

        theme_idx = self.theme_combo.findText(self.theme_mode)
        self.theme_combo.setCurrentIndex(max(0, theme_idx))
        self._apply_theme(self.theme_mode)

    @staticmethod
    def _default_app_font_size() -> int:
        app = QApplication.instance()
        if app is None:
            return 10
        point_size = app.font().pointSize()
        return point_size if point_size > 0 else 10

    def _load_font_size_setting(self) -> int:
        default_size = self._default_app_font_size()
        raw_value = self.settings_store.value("font_size", default_size)
        try:
            value = int(str(raw_value))
        except (TypeError, ValueError):
            value = default_size
        return max(8, min(32, value))

    def _apply_font_size_from_ui(self) -> None:
        self._apply_global_font_size(self.font_size_spin.value(), persist=True)
        self._show_info(f"Font size applied: {self.font_size} pt")

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
                if isinstance(top_level, QPushButton):
                    _apply_scaled_icon_size(top_level)
        self.font_size = clamped
        if persist:
            self.settings_store.setValue("font_size", clamped)

    def _apply_theme(self, mode: str) -> None:
        """Apply selected theme to both main window and chat window."""
        self.theme_mode = mode
        self.settings_store.setValue("theme_mode", mode)
        if mode == "Auto":
            self.effective_theme = "Dark" if windows_prefers_dark() else "Light"
        effective = self.effective_theme if mode == "Auto" else mode
        base_button_style = "QPushButton{padding:2px 6px;}"
        light_row_style = (
            "QFrame#connectionRowCard{background:#fbfcfd; border:1px solid #e5e7eb; border-radius:6px;}"
            "QLabel#ownerLabel{color:#6b7280; font-size:11px;}"
        )
        stylesheet = f"{base_button_style}{light_row_style}"
        if effective == "Dark":
            stylesheet = (
                "QWidget{background:#1f2328;color:#e6edf3;}"
                "QLineEdit,QTextEdit,QComboBox,QSpinBox{background:#0d1117;color:#e6edf3;border:1px solid #30363d;}"
                "QFrame#connectionRowCard{background:#262c34; border:1px solid #3b4350; border-radius:6px;}"
                "QLabel#ownerLabel{color:#9aa4b2; font-size:11px;}"
                f"{base_button_style}"
            )

        self.setStyleSheet(stylesheet)
        self.chat_window.setStyleSheet(stylesheet)
        # Toast uses opposite contrast of the selected/effective app theme.
        if effective == "Dark":
            self.toast.set_theme("light")
        else:
            self.toast.set_theme("dark")

    def _set_reconnect_on_drop(self, enabled: bool) -> None:
        """Persist reconnect-on-drop operator preference."""
        self.reconnect_on_drop = bool(enabled)
        self.settings_store.setValue("reconnect_on_drop", "true" if enabled else "false")

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
                "position_name": self._selected_position_name(connection_name, mode),
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

    def _open_single_session(self, connection_name: str, mode: str) -> bool:
        """Open one session after missing-file and remote-lock checks."""
        vnc_path = self._vnc_path(connection_name, mode)
        if not vnc_path or not vnc_path.exists():
            self._show_info(f"Missing .vnc file for {connection_name} [{mode}]")
            return False
        # Station lock is per connection (not per mode), based on station ID.
        remote_holder_id = None
        for (remote_connection, _remote_mode), holder_id in self.network.remote_session_holders.items():
            if remote_connection == connection_name and holder_id != self.network.station_id:
                remote_holder_id = holder_id
                break
        remote_holder = self.network.station_name_for_id(remote_holder_id) if remote_holder_id else None
        if remote_holder_id and not self.takeover_checkbox.isChecked():
            # Soft-lock behavior: prevent duplicates unless user explicitly overrides.
            self._show_info(
                f"Session {connection_name} is currently open on station '{remote_holder}'. "
                "Enable 'Take over session' to force open."
            )
            return False

        takeover_used = bool(remote_holder_id and self.takeover_checkbox.isChecked())
        config_path = config_path_for(connection_name, mode)
        settings = load_session_settings(config_path)
        self._apply_position_override(connection_name, mode, settings)
        self._persist_ui_selections(connection_name, mode)
        if self.session_manager.launch((connection_name, mode), vnc_path, settings):
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
            return True
        return False

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

    def _open_tagged(self, mode: str) -> None:
        """Open selected mode for every currently tagged connection row."""
        any_tagged = False
        for row in self.rows.values():
            if row.tag.isChecked():
                any_tagged = True
                self._open_session(row.entry.name, mode)
        if not any_tagged:
            self._show_info("No tagged connections.")

    def _setup_positions(self) -> None:
        """Open all sessions that have a selected position and persist position refs."""
        if self._startup_sync_pending:
            self._show_info("Please wait: synchronizing session ownership...")
            return
        if not self._validate_unique_position_assignments():
            return
        selected_targets: List[Tuple[str, str]] = []
        for row in self.rows.values():
            for mode in (MODE_VIEW, MODE_CONTROL):
                if row.selected_position(mode):
                    selected_targets.append((row.entry.name, mode))
        if not selected_targets:
            self._show_info("No positions selected.")
            return
        for connection_name, mode in selected_targets:
            self._persist_ui_selections(connection_name, mode)
            self._open_session_with_link(connection_name, mode, visited=set())

    def _on_position_selection_changed(self, connection_name: str, mode: str) -> None:
        row = self.rows.get(connection_name)
        if row is None:
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
        """Reserved for future link validation hooks."""
        return

    def _validate_unique_position_assignments(self, show_message: bool = True) -> bool:
        assignments: Dict[str, Tuple[str, str]] = {}
        for connection_name, row in self.rows.items():
            for mode in (MODE_VIEW, MODE_CONTROL):
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
            self._show_info(f"No KS folder configured for {connection_name}.")
            return

        target, error = resolve_ks_target(configured)
        if target is None:
            self._show_info(error)
            return

        try:
            os.startfile(str(target))
        except OSError as exc:
            self._show_info(f"Failed to open KS file: {exc}")

    def _untag_all(self) -> None:
        """Clear all row selection checkboxes."""
        for row in self.rows.values():
            row.tag.setChecked(False)

    def _edit_session(self, connection_name: str, mode: str) -> None:
        """Open settings editor for one connection/mode and save if accepted."""
        vnc_path = self._vnc_path(connection_name, mode)
        if not vnc_path or not vnc_path.exists():
            self._show_info(f"Cannot edit: missing .vnc file for {connection_name} [{mode}]")
            return
        config_path = config_path_for(connection_name, mode)
        settings = load_session_settings(config_path)
        dialog = SettingsDialog(f"Edit {mode.title()} - {connection_name}", settings, self)
        if dialog.exec_() == dialog.Accepted:
            data = dialog.values().to_json()
            overrides = load_session_overrides(config_path)
            data["position_name"] = self._selected_position_name(connection_name, mode) or str(
                overrides.get("position_name", "")
            )
            data["linked_session"] = self._selected_link_token(connection_name, mode) or str(
                overrides.get("linked_session", "")
            )
            save_json(config_path, data)
            self._refresh_row_ks_buttons(connection_name)

    def _on_session_closed(self, key: Tuple[str, str]) -> None:
        """Broadcast session close event when local process exits/closes."""
        connection_name, mode = key
        LOGGER.info("Session closed: %s [%s]", connection_name, mode)
        self.network.send_session(connection_name, mode, False)
        self._refresh_owner_labels()

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
            # /nick updates runtime identity and persists to default.json.
            new_name = payload
            if new_name:
                self.station_name = new_name
                self.network.set_station_name(new_name)
                self.chat_window.set_station_title(new_name)
                self.setWindowTitle(new_name)
                self.default_settings.station_name = new_name
                path = Path(__file__).resolve().parent.parent / "default.json"
                merged = self.default_settings.to_json()
                merged["station_name"] = new_name
                save_json(path, merged)
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
                self.setWindowTitle(self.station_name)
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
            self.setWindowTitle(self.station_name)
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
                continue
            matches = []
            for (conn, mode), (holder, age_seconds) in remote_info.items():
                if conn == name:
                    matches.append((holder, mode, int(age_seconds)))
            if matches:
                holder, mode, age_seconds = sorted(matches, key=lambda x: x[2])[0]
                row.owner_label.setText(f"Owner: {holder} [{mode}] {age_seconds}s")
            else:
                row.owner_label.setText("Owner: available")

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
        findings = validate_runtime_configuration()
        if not findings:
            self._show_info("Validation passed with no findings.")
            LOGGER.info("Validation passed")
            return
        self._show_info(f"Validation found {len(findings)} item(s). See logs/app.log.")
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
        applied = import_config_bundle(Path(in_path))
        self.connections = scan_connections()
        self._rebuild_connection_rows()
        self._show_info(f"Imported {len(applied)} config file(s).")
        LOGGER.info("Config bundle imported: %s (%d files)", in_path, len(applied))

    def _rebuild_connection_rows(self) -> None:
        """Recreate the scroll-area row widgets from current connection list."""
        self.position_names = [p.name for p in scan_positions()]
        self.session_link_options = self._build_session_link_options()
        self.rows.clear()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.connections:
            self.rows_layout.addWidget(QLabel("No .vnc files found in vnc-control/ or vnc-view/"))
        for entry in self.connections:
            row = ConnectionRow(
                entry,
                {
                    "open": self._open_session,
                    "close": self._close_session,
                    "edit": self._edit_session,
                    "open_ks": self._open_ks_file,
                    "position_changed": self._on_position_selection_changed,
                    "link_changed": self._on_link_selection_changed,
                },
                self.position_names,
                self.session_link_options,
            )
            self._populate_row_from_saved_settings(row)
            self.rows[entry.name] = row
            self.rows_layout.addWidget(row.widget)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            self.rows_layout.addWidget(line)
        self.rows_layout.addStretch(1)
        self._clear_duplicate_positions_after_load()
        self._refresh_owner_labels()

    def _populate_row_from_saved_settings(self, row: ConnectionRow) -> None:
        view_settings = load_session_settings(config_path_for(row.entry.name, MODE_VIEW))
        control_settings = load_session_settings(config_path_for(row.entry.name, MODE_CONTROL))
        row.set_selected_position(MODE_VIEW, view_settings.position_name)
        row.set_selected_position(MODE_CONTROL, control_settings.position_name)
        row.set_selected_link(MODE_VIEW, view_settings.linked_session)
        row.set_selected_link(MODE_CONTROL, control_settings.linked_session)
        row.set_ks_paths(view_settings.ks, control_settings.ks)

    def _refresh_row_ks_buttons(self, connection_name: str) -> None:
        row = self.rows.get(connection_name)
        if row is None:
            return
        view_settings = load_session_settings(config_path_for(connection_name, MODE_VIEW))
        control_settings = load_session_settings(config_path_for(connection_name, MODE_CONTROL))
        row.set_ks_paths(view_settings.ks, control_settings.ks)

    def _clear_duplicate_positions_after_load(self) -> None:
        """Keep first assignment per position and clear later duplicates."""
        assigned: Dict[str, Tuple[str, str]] = {}
        for connection_name, row in self.rows.items():
            for mode in (MODE_VIEW, MODE_CONTROL):
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

    def _open_layout_tool(self) -> None:
        """Open or focus the visual layout tool window."""
        if self._layout_tool_window is None or not self._layout_tool_window.isVisible():
            self._layout_tool_window = LayoutToolWindow()
            self._layout_tool_window.window_closed.connect(self._on_layout_tool_closed)
        self._layout_tool_window.show()
        self._layout_tool_window.raise_()
        self._layout_tool_window.activateWindow()

    def _on_layout_tool_closed(self) -> None:
        """Refresh row position selectors after editing position presets."""
        self.position_names = [p.name for p in scan_positions()]
        for row in self.rows.values():
            row.refresh_option_sets(self.position_names, self.session_link_options)
        self._clear_duplicate_positions_after_load()

    def _set_open_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable all actions that can open new sessions."""
        self.view_all_btn.setEnabled(enabled)
        self.control_all_btn.setEnabled(enabled)
        self.setup_positions_btn.setEnabled(enabled)
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

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure sessions/network/chat are closed cleanly with the main window."""
        self.settings_store.setValue("main_width", self.width())
        self.settings_store.setValue("main_height", self.height())
        self.settings_store.setValue("chat_width", self.chat_window.width())
        self.settings_store.setValue("chat_height", self.chat_window.height())
        self.session_manager.close_all()
        self.network.close()
        self.chat_window.close()
        super().closeEvent(event)
