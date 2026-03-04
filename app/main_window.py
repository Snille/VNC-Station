"""Main application window: connection list, controls, chat, and coordination."""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QSettings, QTimer, Qt, QUrl
from PyQt5.QtGui import QCloseEvent, QIcon
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .chat_window import ChatWindow
from .config import config_path_for, load_default_settings, load_session_settings, save_json, scan_connections
from .constants import (
    HELLO_INTERVAL_MS,
    ICON_PATH,
    MODE_CONTROL,
    MODE_VIEW,
    NOTICE_SOUND_PATH,
    SESSION_BROADCAST_INTERVAL_MS,
    STATION_PRESENCE_CHECK_MS,
)
from .logic import parse_chat_command
from .models import ConnectionEntry
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


class ConnectionRow:
    """UI bundle for one connection entry and its row-level buttons."""

    def __init__(self, entry: ConnectionEntry, callbacks: Dict[str, object]) -> None:
        """Build the 4-row connection layout and wire callback actions."""
        self.entry = entry
        self.widget = QWidget()
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)

        self.tag = QCheckBox()

        self.name_btn = QPushButton(entry.name)
        self.name_btn.setStyleSheet("font-weight:700;")
        self.name_btn.clicked.connect(lambda: self.tag.setChecked(not self.tag.isChecked()))
        name_row = QHBoxLayout()
        name_row.addWidget(self.tag)
        name_row.addWidget(self.name_btn, 1)
        outer.addLayout(name_row)

        self.view_btn = QPushButton("View")
        self.view_btn.setStyleSheet("background:#2f9e44; color:white; font-weight:700;")
        self.view_btn.clicked.connect(lambda: callbacks["open"](entry.name, MODE_VIEW))

        self.control_btn = QPushButton("Control")
        self.control_btn.setStyleSheet("background:#c92a2a; color:white; font-weight:700;")
        self.control_btn.clicked.connect(lambda: callbacks["open"](entry.name, MODE_CONTROL))
        action_row = QHBoxLayout()
        action_row.addWidget(self.view_btn)
        action_row.addWidget(self.control_btn)
        outer.addLayout(action_row)

        self.close_view_btn = QPushButton("Close view")
        self.close_view_btn.clicked.connect(lambda: callbacks["close"](entry.name, MODE_VIEW))

        self.close_control_btn = QPushButton("Close control")
        self.close_control_btn.clicked.connect(lambda: callbacks["close"](entry.name, MODE_CONTROL))
        close_row = QHBoxLayout()
        close_row.addWidget(self.close_view_btn)
        close_row.addWidget(self.close_control_btn)
        outer.addLayout(close_row)

        self.edit_view_btn = QPushButton("Edit View")
        self.edit_view_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700;")
        self.edit_view_btn.clicked.connect(lambda: callbacks["edit"](entry.name, MODE_VIEW))
        self.edit_view_btn.setEnabled(entry.view_vnc_path is not None)

        self.edit_control_btn = QPushButton("Edit Control")
        self.edit_control_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700;")
        self.edit_control_btn.clicked.connect(lambda: callbacks["edit"](entry.name, MODE_CONTROL))
        self.edit_control_btn.setEnabled(entry.control_vnc_path is not None)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.edit_view_btn)
        edit_row.addWidget(self.edit_control_btn)
        outer.addLayout(edit_row)

        self.owner_label = QLabel("Owner: available")
        self.owner_label.setStyleSheet("font-size:11px; color:#666;")
        outer.addWidget(self.owner_label)

        self.view_btn.setEnabled(entry.view_vnc_path is not None)
        self.control_btn.setEnabled(entry.control_vnc_path is not None)


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
        self.effective_theme = "Dark" if windows_prefers_dark() else "Light"
        self.reconnect_on_drop = str(self.settings_store.value("reconnect_on_drop", "false")).lower() == "true"
        self.connections = scan_connections()
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

        actions_row1 = QHBoxLayout()
        root.addLayout(actions_row1)
        self.view_all_btn = QPushButton("View all tagged")
        self.view_all_btn.setStyleSheet("background:#2f9e44; color:white; font-weight:700;")
        self.view_all_btn.clicked.connect(lambda: self._open_tagged(MODE_VIEW))
        self.control_all_btn = QPushButton("Control all tagged")
        self.control_all_btn.setStyleSheet("background:#c92a2a; color:white; font-weight:700;")
        self.control_all_btn.clicked.connect(lambda: self._open_tagged(MODE_CONTROL))
        actions_row1.addWidget(self.view_all_btn)
        actions_row1.addWidget(self.control_all_btn)

        actions_row2 = QHBoxLayout()
        root.addLayout(actions_row2)
        close_tagged = QPushButton("Close all tagged")
        close_tagged.clicked.connect(self._close_tagged_sessions)
        close_all = QPushButton("Close all sessions")
        close_all.clicked.connect(self._close_all_sessions)
        actions_row2.addWidget(close_tagged)
        actions_row2.addWidget(close_all)

        actions_row3 = QHBoxLayout()
        root.addLayout(actions_row3)
        untag_all = QPushButton("Untag all")
        untag_all.clicked.connect(self._untag_all)
        self.chat_btn = QPushButton("Chat")
        self.chat_btn.clicked.connect(self._open_chat)
        actions_row3.addWidget(untag_all)
        actions_row3.addWidget(self.chat_btn)

        actions_row4 = QHBoxLayout()
        root.addLayout(actions_row4)
        actions_row4.addStretch(1)
        tools_stack = QVBoxLayout()
        take_row = QHBoxLayout()
        self.takeover_checkbox = QCheckBox("Take over session")
        import_btn = QPushButton("Import config")
        import_btn.clicked.connect(self._import_config_bundle)
        take_row.addWidget(self.takeover_checkbox)
        take_row.addWidget(import_btn)
        tools_stack.addLayout(take_row)

        reconnect_row = QHBoxLayout()
        self.reconnect_checkbox = QCheckBox("Reconnect on drop")
        self.reconnect_checkbox.setChecked(self.reconnect_on_drop)
        self.reconnect_checkbox.toggled.connect(self._set_reconnect_on_drop)
        export_btn = QPushButton("Export config")
        export_btn.clicked.connect(self._export_config_bundle)
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
        sizes_btn = QPushButton("Sizes")
        sizes_btn.clicked.connect(self._open_layout_tool)
        validate_btn = QPushButton("Validate config")
        validate_btn.clicked.connect(self._run_validation)
        actions_row5.addWidget(theme_label)
        actions_row5.addWidget(self.theme_combo)
        actions_row5.addWidget(sizes_btn)
        actions_row5.addWidget(validate_btn)
        actions_row5.addStretch(1)

        theme_idx = self.theme_combo.findText(self.theme_mode)
        self.theme_combo.setCurrentIndex(max(0, theme_idx))
        self._apply_theme(self.theme_mode)

    def _apply_theme(self, mode: str) -> None:
        """Apply selected theme to both main window and chat window."""
        self.theme_mode = mode
        self.settings_store.setValue("theme_mode", mode)
        if mode == "Auto":
            self.effective_theme = "Dark" if windows_prefers_dark() else "Light"
        effective = self.effective_theme if mode == "Auto" else mode
        stylesheet = ""
        if effective == "Dark":
            stylesheet = (
                "QWidget{background:#1f2328;color:#e6edf3;}"
                "QLineEdit,QTextEdit,QComboBox,QSpinBox{background:#0d1117;color:#e6edf3;border:1px solid #30363d;}"
            )
        elif effective == "Light":
            stylesheet = ""
        else:
            stylesheet = ""

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

    def _vnc_path(self, connection_name: str, mode: str) -> Optional[Path]:
        """Resolve concrete .vnc path for the requested connection+mode."""
        entry = self._entry_for(connection_name)
        if entry is None:
            return None
        return entry.view_vnc_path if mode == MODE_VIEW else entry.control_vnc_path

    def _open_session(self, connection_name: str, mode: str) -> None:
        """Open one session after missing-file and remote-lock checks."""
        if self._startup_sync_pending:
            self._show_info("Please wait: synchronizing session ownership...")
            return
        vnc_path = self._vnc_path(connection_name, mode)
        if not vnc_path or not vnc_path.exists():
            self._show_info(f"Missing .vnc file for {connection_name} [{mode}]")
            return
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
            return

        takeover_used = bool(remote_holder_id and self.takeover_checkbox.isChecked())
        settings = load_session_settings(config_path_for(connection_name, mode))
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

    def _close_session(self, connection_name: str, mode: str) -> None:
        """Close one specific session."""
        self.session_manager.close_session((connection_name, mode))

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
            save_json(config_path, dialog.values().to_json())

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
                {"open": self._open_session, "close": self._close_session, "edit": self._edit_session},
            )
            self.rows[entry.name] = row
            self.rows_layout.addWidget(row.widget)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            self.rows_layout.addWidget(line)
        self.rows_layout.addStretch(1)
        self._refresh_owner_labels()

    def _show_info(self, text: str) -> None:
        """Show non-blocking informational feedback."""
        self.toast.show_message(text)
        LOGGER.info("Info: %s", text)

    def _open_layout_tool(self) -> None:
        """Open or focus the visual layout tool window."""
        if self._layout_tool_window is None or not self._layout_tool_window.isVisible():
            self._layout_tool_window = LayoutToolWindow()
        self._layout_tool_window.show()
        self._layout_tool_window.raise_()
        self._layout_tool_window.activateWindow()

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
