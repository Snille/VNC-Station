"""Session editor for per-connection settings and per-mode position/link selection."""

from pathlib import Path
from typing import List, Tuple

from PyQt5.QtCore import QSettings, QSize, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .config import config_path_for, load_session_settings, save_json, scan_connections, scan_positions, update_session_overrides
from .constants import CANCEL_ICON_PATH, GEARS_ICON_PATH, MODE_CONTROL, MODE_VIEW, OPEN_ICON_PATH, SAVE_ICON_PATH
from .models import SessionSettings
from .settings_dialog import SensorMappingsEditor
from .theme import windows_prefers_dark

ICON_TEXT_GAP_PREFIX = "\u2009"
BUTTON_ICON_PATH_PROPERTY = "button_icon_path"
BUTTON_ICON_BASE_SIZE_PROPERTY = "button_icon_base_size"
BUTTON_TEXT_RAW_PROPERTY = "button_text_raw"
BUTTON_CHROME = "color:white; font-weight:700; padding:2px 6px 4px 6px; border:none; border-radius:4px;"
DEFAULT_BUTTON_STYLE = f"background:#666666; {BUTTON_CHROME}"
LOAD_BUTTON_STYLE = f"background:#666666; {BUTTON_CHROME}"
SAVE_BUTTON_STYLE = f"background:#666666; {BUTTON_CHROME}"


def _button_icons_enabled() -> bool:
    settings = QSettings("VNCStation", "Controller")
    value = settings.value("use_button_icons", "true")
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _button_text_without_prefix(text: str) -> str:
    return text.lstrip(f" {ICON_TEXT_GAP_PREFIX}")


def _apply_button_icon_preference(button: QPushButton) -> None:
    raw_text = str(button.property(BUTTON_TEXT_RAW_PROPERTY) or _button_text_without_prefix(button.text()))
    button.setProperty(BUTTON_TEXT_RAW_PROPERTY, raw_text)
    if _button_icons_enabled():
        icon_path = str(button.property(BUTTON_ICON_PATH_PROPERTY) or "").strip()
        if icon_path and Path(icon_path).exists():
            button.setIcon(QIcon(icon_path))
            size_px = int(button.property(BUTTON_ICON_BASE_SIZE_PROPERTY) or 16)
            button.setIconSize(QSize(size_px, size_px))
        button.setText(f"{ICON_TEXT_GAP_PREFIX}{raw_text}" if raw_text else "")
        return
    button.setIcon(QIcon())
    button.setText(raw_text)


def _set_button_icon(button: QPushButton, icon_path: Path, size_px: int = 16) -> None:
    button.setProperty(BUTTON_ICON_PATH_PROPERTY, str(icon_path))
    button.setProperty(BUTTON_ICON_BASE_SIZE_PROPERTY, int(size_px))
    button.setProperty(BUTTON_TEXT_RAW_PROPERTY, _button_text_without_prefix(button.text()))
    _apply_button_icon_preference(button)


class SessionSettingsWindow(QMainWindow):
    """Editor for per-session JSON values and per-mode position/link assignments."""

    window_closed = pyqtSignal()

    def __init__(self, theme_mode: str = "Auto") -> None:
        super().__init__()
        self._geometry_store = QSettings("VNCStation", "Controller")
        self.theme_mode = theme_mode
        self._load_targets: List[Tuple[str, str]] = []
        self._current_connection_name = ""
        self.settings = SessionSettings()
        self.setWindowTitle("Sessions")
        if GEARS_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(GEARS_ICON_PATH)))
        self.resize(620, 860)
        self._build_ui()
        saved_geometry = self._geometry_store.value("session_settings_window_geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        self._apply_theme(self.theme_mode)
        if self.load_target_box.count() > 0:
            self.load_target_box.setCurrentIndex(0)
            self._load_selected_target_settings()

    def _build_ui(self) -> None:
        root_widget = QWidget(self)
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        self._root_layout = root
        top_row = QHBoxLayout()
        root.addLayout(top_row)
        top_row.addWidget(QLabel("Load settings:"))
        self.load_target_box = QComboBox()
        self._populate_load_targets()
        top_row.addWidget(self.load_target_box, 1)
        load_btn = QPushButton("Load")
        _set_button_icon(load_btn, OPEN_ICON_PATH)
        load_btn.setStyleSheet(LOAD_BUTTON_STYLE)
        load_btn.clicked.connect(self._load_selected_target_settings)
        save_btn = QPushButton("Save")
        _set_button_icon(save_btn, SAVE_ICON_PATH)
        save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        save_btn.clicked.connect(self._save_selected_target_settings)
        top_row.addWidget(load_btn)
        top_row.addWidget(save_btn)
        form = QFormLayout()
        root.addLayout(form)
        self.label_text = QLineEdit(self.settings.label_text)
        form.addRow("Label text", self.label_text)
        self.position_view_box = QComboBox()
        self.position_control_box = QComboBox()
        form.addRow("Position V", self.position_view_box)
        form.addRow("Position C", self.position_control_box)
        self.link_view_box = QComboBox()
        self.link_control_box = QComboBox()
        form.addRow("Link V", self.link_view_box)
        form.addRow("Link C", self.link_control_box)
        self._add_active_path_picker(form, self.settings.ks)
        self.ks_button_text = QLineEdit()
        form.addRow("Active Button Text", self.ks_button_text)
        self.sensor_editor = SensorMappingsEditor(self.settings, self)
        root.addWidget(self.sensor_editor)
        close_row = QHBoxLayout()
        root.addLayout(close_row)
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        _set_button_icon(close_btn, CANCEL_ICON_PATH)
        close_btn.setStyleSheet(DEFAULT_BUTTON_STYLE)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        close_row.addStretch(1)
        self._populate_position_boxes()

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

    def _populate_position_boxes(self) -> None:
        names = [preset.name for preset in scan_positions()]
        self.position_view_box.clear()
        self.position_control_box.clear()
        self.position_view_box.addItem("")
        self.position_control_box.addItem("")
        for name in names:
            self.position_view_box.addItem(name)
            self.position_control_box.addItem(name)

    @staticmethod
    def _session_token(connection_name: str, mode: str) -> str:
        return f"{connection_name}|{mode}"

    def _populate_link_boxes(self, connection_name: str) -> None:
        self.link_view_box.clear()
        self.link_control_box.clear()
        self.link_view_box.addItem("", "")
        self.link_control_box.addItem("", "")
        current_view_token = self._session_token(connection_name, MODE_VIEW) if connection_name else ""
        current_control_token = self._session_token(connection_name, MODE_CONTROL) if connection_name else ""
        for entry in scan_connections():
            if entry.view_vnc_path is not None:
                token = self._session_token(entry.name, MODE_VIEW)
                label = f"{entry.name} [view]"
                if token != current_view_token:
                    self.link_view_box.addItem(label, token)
                if token != current_control_token:
                    self.link_control_box.addItem(label, token)
            if entry.control_vnc_path is not None:
                token = self._session_token(entry.name, MODE_CONTROL)
                label = f"{entry.name} [control]"
                if token != current_view_token:
                    self.link_view_box.addItem(label, token)
                if token != current_control_token:
                    self.link_control_box.addItem(label, token)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    @staticmethod
    def _looks_like_file_path(value: str) -> bool:
        text = value.strip()
        if not text:
            return False
        path = Path(text)
        if path.exists():
            return path.is_file()
        return bool(path.suffix)

    def _update_active_path_ui(self) -> None:
        folder_mode = self.ks_folder_checkbox.isChecked()
        self.ks_path_label.setText("Active Folder" if folder_mode else "Active File")
        self.ks_browse_btn.setText("Browse folder..." if folder_mode else "Browse file...")

    def _add_active_path_picker(self, form: QFormLayout, value: str) -> None:
        row = QHBoxLayout()
        self.ks_text = QLineEdit(value)
        self.ks_path_label = QLabel("Active Folder")
        self.ks_browse_btn = QPushButton("Browse...")
        self.ks_folder_checkbox = QCheckBox("Use folder browser")
        self.ks_folder_checkbox.setChecked(not self._looks_like_file_path(value))

        def browse() -> None:
            start_dir = self.ks_text.text().strip()
            if start_dir:
                current = Path(start_dir)
                if current.is_file():
                    start_dir = str(current.parent)
            if self.ks_folder_checkbox.isChecked():
                path = QFileDialog.getExistingDirectory(self, "Select Active Folder", start_dir or "")
            else:
                path, _selected_filter = QFileDialog.getOpenFileName(
                    self,
                    "Select Active File",
                    start_dir or "",
                    "All Files (*)",
                )
            if path:
                self.ks_text.setText(path)

        self.ks_browse_btn.clicked.connect(browse)
        self.ks_folder_checkbox.toggled.connect(lambda _checked: self._update_active_path_ui())
        row.addWidget(self.ks_text, 1)
        row.addWidget(self.ks_browse_btn)
        wrapper = QVBoxLayout()
        wrapper.addLayout(row)
        wrapper.addWidget(self.ks_folder_checkbox)
        form.addRow(self.ks_path_label, wrapper)
        self._update_active_path_ui()

    def _load_selected_target_settings(self) -> None:
        idx = self.load_target_box.currentIndex()
        if idx < 0 or idx >= len(self._load_targets):
            QMessageBox.information(self, "Sessions", "No connection selected.")
            return
        connection_name, mode = self._load_targets[idx]
        self._current_connection_name = connection_name
        settings = load_session_settings(config_path_for(connection_name, mode))
        view_settings = load_session_settings(config_path_for(connection_name, MODE_VIEW))
        control_settings = load_session_settings(config_path_for(connection_name, MODE_CONTROL))
        self.settings = settings
        self._populate_position_boxes()
        self._populate_link_boxes(connection_name)
        self.label_text.setText(settings.label_text)
        self.ks_text.setText(settings.ks)
        self.ks_button_text.setText(settings.ks_button_text)
        self._set_combo_text(self.position_view_box, view_settings.position_name)
        self._set_combo_text(self.position_control_box, control_settings.position_name)
        self._set_combo_data(self.link_view_box, view_settings.linked_session)
        self._set_combo_data(self.link_control_box, control_settings.linked_session)
        self._replace_sensor_editor(settings)

    def _replace_sensor_editor(self, settings: SessionSettings) -> None:
        old_editor = self.sensor_editor
        index = self._root_layout.indexOf(old_editor)
        self.sensor_editor = SensorMappingsEditor(settings, self)
        if index >= 0:
            self._root_layout.replaceWidget(old_editor, self.sensor_editor)
        old_editor.setParent(None)
        old_editor.deleteLater()

    def _collect_settings(self) -> SessionSettings:
        sensor_ids, sensor_mappings = self.sensor_editor.sensor_values()
        return SessionSettings(label_text=self.label_text.text().strip() or "Label", ks=self.ks_text.text().strip(), ks_button_text=self.ks_button_text.text().strip(), ha_sensors=sensor_ids, ha_sensor_icons=sensor_mappings)

    def _save_selected_target_settings(self) -> None:
        idx = self.load_target_box.currentIndex()
        if idx < 0 or idx >= len(self._load_targets):
            QMessageBox.information(self, "Sessions", "No connection selected.")
            return
        connection_name, mode = self._load_targets[idx]
        path = config_path_for(connection_name, mode)
        save_json(path, self._collect_settings().to_session_json())
        self._persist_position_and_link_settings(connection_name)
        QMessageBox.information(self, "Sessions", f"Saved settings to:\n{path}")

    def _persist_position_and_link_settings(self, connection_name: str) -> None:
        update_session_overrides(config_path_for(connection_name, MODE_VIEW), {"position_name": self.position_view_box.currentText().strip(), "linked_session": str(self.link_view_box.currentData() or "").strip()})
        update_session_overrides(config_path_for(connection_name, MODE_CONTROL), {"position_name": self.position_control_box.currentText().strip(), "linked_session": str(self.link_control_box.currentData() or "").strip()})

    def _apply_theme(self, mode: str) -> None:
        self.theme_mode = mode
        effective = "Dark" if mode == "Auto" and windows_prefers_dark() else ("Light" if mode == "Auto" else mode)
        base_button_style = "QPushButton{font-weight:700; padding:2px 6px 4px 6px; border:none; border-radius:4px;}"
        if effective == "Dark":
            self.setStyleSheet("QWidget{background:#1f2328;color:#e6edf3;} QLineEdit,QComboBox{background:#0d1117;color:#e6edf3;border:1px solid #30363d;}" + base_button_style)
        else:
            self.setStyleSheet(base_button_style)

    def set_theme_mode(self, mode: str) -> None:
        self._apply_theme(mode)

    def closeEvent(self, event) -> None:
        self._geometry_store.setValue("session_settings_window_geometry", self.saveGeometry())
        self.window_closed.emit()
        super().closeEvent(event)


def main() -> int:
    app = QApplication([])
    window = SessionSettingsWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
