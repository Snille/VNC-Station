"""App-level settings window for theme/font/defaults and Home Assistant checks."""

import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict

from PyQt5.QtCore import QSettings, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .constants import GEARS_ICON_PATH, HA_ICON_PATH, SAVE_ICON_PATH
from .constants import EXPORT_ICON_PATH, IMPORT_ICON_PATH, VALIDATE_ICON_PATH

DEFAULT_BUTTON_STYLE = "background:#1971c2; color:white; font-weight:700; border-radius:4px;"
SUCCESS_BUTTON_STYLE = "background:#2f9e44; color:white; font-weight:700; border-radius:4px;"
ERROR_BUTTON_STYLE = "background:#c92a2a; color:white; font-weight:700; border-radius:4px;"
SAVE_BUTTON_STYLE = "background:#6741d9; color:white; font-weight:700; border-radius:4px;"


def _set_button_icon(button: QPushButton, icon_path: Path, size_px: int = 16) -> None:
    if not icon_path.exists():
        return
    button.setIcon(QIcon(str(icon_path)))
    button.setIconSize(QSize(size_px, size_px))


def _int_from_mapping(data: Dict[str, object], key: str, fallback: int) -> int:
    try:
        return int(str(data.get(key, fallback)))
    except (TypeError, ValueError):
        return fallback


class SettingsWindow(QDialog):
    """Settings editor for global app preferences and default session values."""

    ha_test_finished = pyqtSignal(bool, str)

    def __init__(
        self,
        theme_mode: str,
        font_size: int,
        defaults: Dict[str, object],
        apply_theme: Callable[[str], None],
        apply_font_size: Callable[[int], None],
        save_defaults: Callable[[Dict[str, str]], str],
        show_toast: Callable[[str], None],
        run_validation: Callable[[], None],
        import_config: Callable[[], None],
        export_config: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setModal(False)
        self._apply_theme = apply_theme
        self._apply_font_size = apply_font_size
        self._save_defaults = save_defaults
        self._show_toast = show_toast
        self._run_validation = run_validation
        self._import_config = import_config
        self._export_config = export_config
        self._fields: Dict[str, object] = {}
        self._default_values = defaults
        self._theme_mode = theme_mode
        self._font_size = font_size
        self._ha_test_pending = False
        self._ha_style_timer = QTimer(self)
        self._ha_style_timer.setSingleShot(True)
        self._ha_style_timer.timeout.connect(self._restore_ha_button_style)

        self.setWindowTitle("Settings")
        if GEARS_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(GEARS_ICON_PATH)))
        self._geometry_store = QSettings("VNCStation", "Controller")
        saved_geometry = self._geometry_store.value("settings_window_geometry")
        if not saved_geometry or not self.restoreGeometry(saved_geometry):
            self.resize(460, 760)

        root = QVBoxLayout(self)

        appearance_label = QLabel("Appearance")
        appearance_label.setStyleSheet("font-weight:700;")
        root.addWidget(appearance_label)

        appearance_row = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Auto", "Light", "Dark"])
        self.theme_combo.setCurrentText(self._theme_mode if self._theme_mode in ("Auto", "Light", "Dark") else "Auto")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 32)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setValue(max(8, min(32, int(self._font_size))))
        self.apply_btn = QPushButton("Apply")
        _set_button_icon(self.apply_btn, SAVE_ICON_PATH)
        self.apply_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.apply_btn.clicked.connect(self._apply_appearance)
        appearance_row.addWidget(QLabel("Theme:"))
        appearance_row.addWidget(self.theme_combo)
        appearance_row.addWidget(QLabel("Font Size:"))
        appearance_row.addWidget(self.font_size_spin)
        appearance_row.addWidget(self.apply_btn)
        root.addLayout(appearance_row)

        defaults_label = QLabel("Default Session Values")
        defaults_label.setStyleSheet("font-weight:700;")
        root.addWidget(defaults_label)

        form = QFormLayout()
        root.addLayout(form)

        self._add_spin(form, "x", "Window X", _int_from_mapping(defaults, "x", 1), -10000, 10000)
        self._add_spin(form, "y", "Window Y", _int_from_mapping(defaults, "y", 1), -10000, 10000)
        self._add_spin(form, "width", "Window Width", _int_from_mapping(defaults, "width", 1300), 100, 6000)
        self._add_spin(form, "height", "Window Height", _int_from_mapping(defaults, "height", 880), 100, 6000)
        self._add_text(form, "label_text", "Label Text", str(defaults.get("label_text", "Default")))
        self._add_spin(form, "label_x", "Label Offset X", _int_from_mapping(defaults, "label_x", 10), -10000, 10000)
        self._add_spin(form, "label_y", "Label Offset Y", _int_from_mapping(defaults, "label_y", 10), -10000, 10000)
        self._add_text(form, "label_bg", "Label Background", str(defaults.get("label_bg", "white")))
        self._add_spin(form, "label_width", "Label Width", _int_from_mapping(defaults, "label_width", 200), 30, 4000)
        self._add_spin(form, "label_height", "Label Height", _int_from_mapping(defaults, "label_height", 100), 20, 2000)
        self._add_spin(form, "label_font", "Label Font Size", _int_from_mapping(defaults, "label_font", 18), 8, 180)
        self._add_text(form, "label_font_color", "Label Font Color", str(defaults.get("label_font_color", "black")))
        self._add_spin(form, "label_border_size", "Label Border Size", _int_from_mapping(defaults, "label_border_size", 5), 0, 40)
        self._add_text(form, "label_border_color", "Label Border Color", str(defaults.get("label_border_color", "yellow")))
        self._add_text(form, "station_name", "Station Name", str(defaults.get("station_name", "Station 01")))

        ha_label = QLabel("Home Assistant")
        ha_label.setStyleSheet("font-weight:700;")
        root.addWidget(ha_label)

        self.ha_url_input = QLineEdit(str(defaults.get("ha_url", "")))
        self.ha_api_key_input = QLineEdit(str(defaults.get("ha_api_key", "")))
        self.ha_api_key_input.setEchoMode(QLineEdit.Password)
        root.addWidget(QLabel("Home Assistant URL"))
        root.addWidget(self.ha_url_input)
        root.addWidget(QLabel("HA API Key"))
        root.addWidget(self.ha_api_key_input)

        test_row = QHBoxLayout()
        test_row.addStretch(1)
        self.test_ha_btn = QPushButton("Test HA connection")
        _set_button_icon(self.test_ha_btn, HA_ICON_PATH)
        self.test_ha_btn.setStyleSheet(DEFAULT_BUTTON_STYLE)
        self.test_ha_btn.clicked.connect(self._start_ha_test)
        test_row.addWidget(self.test_ha_btn)
        test_row.addStretch(1)
        root.addLayout(test_row)

        maintenance_label = QLabel("Maintenance")
        maintenance_label.setStyleSheet("font-weight:700;")
        root.addWidget(maintenance_label)
        maintenance_row = QHBoxLayout()
        maintenance_row.addStretch(1)
        self.validate_btn = QPushButton("Validate config")
        _set_button_icon(self.validate_btn, VALIDATE_ICON_PATH)
        self.validate_btn.setStyleSheet("background:#006b57; color:white; font-weight:700; border-radius:4px;")
        self.validate_btn.clicked.connect(self._run_validation)
        self.import_btn = QPushButton("Import config")
        _set_button_icon(self.import_btn, IMPORT_ICON_PATH)
        self.import_btn.setStyleSheet("background:#006b57; color:white; font-weight:700; border-radius:4px;")
        self.import_btn.clicked.connect(self._import_config)
        self.export_btn = QPushButton("Export config")
        _set_button_icon(self.export_btn, EXPORT_ICON_PATH)
        self.export_btn.setStyleSheet("background:#006b57; color:white; font-weight:700; border-radius:4px;")
        self.export_btn.clicked.connect(self._export_config)
        maintenance_row.addWidget(self.validate_btn)
        maintenance_row.addWidget(self.import_btn)
        maintenance_row.addWidget(self.export_btn)
        maintenance_row.addStretch(1)
        root.addLayout(maintenance_row)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_btn = QPushButton("Save")
        _set_button_icon(self.save_btn, SAVE_ICON_PATH)
        self.save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_btn.clicked.connect(self._save)
        save_row.addWidget(self.save_btn)
        save_row.addStretch(1)
        root.addLayout(save_row)

        self.ha_test_finished.connect(self._on_ha_test_finished)

    def _add_spin(self, form: QFormLayout, key: str, label: str, value: int, low: int, high: int) -> None:
        field = QSpinBox()
        field.setRange(low, high)
        field.setValue(value)
        self._fields[key] = field
        form.addRow(label, field)

    def _add_text(self, form: QFormLayout, key: str, label: str, value: str) -> None:
        field = QLineEdit(value)
        self._fields[key] = field
        form.addRow(label, field)

    def _apply_appearance(self) -> None:
        self._apply_theme(self.theme_combo.currentText().strip() or "Auto")
        self._apply_font_size(self.font_size_spin.value())
        self._show_toast(f"Appearance applied: {self.font_size_spin.value()} pt")

    def _collect_save_payload(self) -> Dict[str, str]:
        return {
            "x": str(self._fields["x"].value()),
            "y": str(self._fields["y"].value()),
            "width": str(self._fields["width"].value()),
            "height": str(self._fields["height"].value()),
            "label_text": self._fields["label_text"].text().strip() or "Default",
            "label_x": str(self._fields["label_x"].value()),
            "label_y": str(self._fields["label_y"].value()),
            "label_bg": self._fields["label_bg"].text().strip() or "white",
            "label_width": str(self._fields["label_width"].value()),
            "label_height": str(self._fields["label_height"].value()),
            "label_font": str(self._fields["label_font"].value()),
            "label_font_color": self._fields["label_font_color"].text().strip() or "black",
            "label_border_size": str(self._fields["label_border_size"].value()),
            "label_border_color": self._fields["label_border_color"].text().strip() or "yellow",
            "station_name": self._fields["station_name"].text().strip() or "Station 01",
            "ha_url": self.ha_url_input.text().strip(),
            "ha_api_key": self.ha_api_key_input.text().strip(),
        }

    def _save(self) -> None:
        payload = self._collect_save_payload()
        message = self._save_defaults(payload)
        self._show_toast(message)
        self.close()

    def _start_ha_test(self) -> None:
        if self._ha_test_pending:
            return
        url = self.ha_url_input.text().strip()
        token = self.ha_api_key_input.text().strip()
        if not url or not token:
            self._show_toast("Home Assistant URL and HA API Key are required.")
            self._flash_ha_button(False)
            return
        self._ha_test_pending = True
        self.test_ha_btn.setEnabled(False)
        self.test_ha_btn.setText("Testing...")
        thread = threading.Thread(target=self._run_ha_test, args=(url, token), daemon=True)
        thread.start()

    def _run_ha_test(self, base_url: str, token: str) -> None:
        url = base_url.rstrip("/") + "/api/"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                code = int(response.getcode())
                payload = response.read(300).decode("utf-8", errors="replace").strip()
                if 200 <= code <= 299:
                    message = f"HA connection OK ({code})."
                    self.ha_test_finished.emit(True, message)
                    return
                self.ha_test_finished.emit(False, f"HA connection failed ({code}): {payload}")
                return
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read(300).decode("utf-8", errors="replace").strip()
            except Exception:
                body = ""
            detail = body or str(exc)
            self.ha_test_finished.emit(False, f"HA HTTP error {exc.code}: {detail}")
            return
        except urllib.error.URLError as exc:
            self.ha_test_finished.emit(False, f"HA connection error: {exc.reason}")
            return
        except Exception as exc:  # Keep UI responsive on unexpected failures.
            self.ha_test_finished.emit(False, f"HA test failed: {exc}")

    def _on_ha_test_finished(self, success: bool, message: str) -> None:
        self._ha_test_pending = False
        self.test_ha_btn.setEnabled(True)
        self.test_ha_btn.setText("Test HA connection")
        self._flash_ha_button(success)
        self._show_toast(message)

    def _flash_ha_button(self, success: bool) -> None:
        self.test_ha_btn.setStyleSheet(SUCCESS_BUTTON_STYLE if success else ERROR_BUTTON_STYLE)
        self._ha_style_timer.start(3000)

    def _restore_ha_button_style(self) -> None:
        self.test_ha_btn.setStyleSheet(DEFAULT_BUTTON_STYLE)

    def closeEvent(self, event) -> None:
        self._geometry_store.setValue("settings_window_geometry", self.saveGeometry())
        super().closeEvent(event)
