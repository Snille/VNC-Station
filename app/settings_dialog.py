"""Dialog used to edit per-connection window and overlay settings."""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QSettings, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .config import load_default_mapping
from .constants import APP_DIR, CANCEL_ICON_PATH, GEARS_ICON_PATH, HA_ICON_PATH, SAVE_ICON_PATH
from .models import SessionSettings


def _set_button_icon(button: QPushButton, icon_path: Path, size_px: int = 14) -> None:
    if not icon_path.exists():
        return
    button.setIcon(QIcon(str(icon_path)))
    button.setIconSize(QSize(size_px, size_px))


class SettingsDialog(QDialog):
    """Simple form-based editor for SessionSettings values."""

    sensor_search_finished = pyqtSignal(bool, object, str)
    SENSOR_MAPPING_ROLE = Qt.UserRole + 1
    ICONS_DIR = APP_DIR / "images"

    def __init__(self, title: str, settings: SessionSettings, parent=None) -> None:
        """Build the settings form and prefill it from an existing settings object."""
        super().__init__(parent)
        self.setWindowTitle(title)
        if GEARS_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(GEARS_ICON_PATH)))
        self.setModal(True)
        self._geometry_store = QSettings("VNCStation", "Controller")
        saved_geometry = self._geometry_store.value("edit_session_dialog_geometry")
        if not saved_geometry or not self.restoreGeometry(saved_geometry):
            self.resize(620, 820)
        self.setStyleSheet("QPushButton{padding:2px 6px;}")
        self._fields: Dict[str, object] = {}
        self._search_pending = False
        self._ha_url, self._ha_api_key = self._load_ha_credentials()
        self._sensor_editor_syncing = False
        self._sensor_mappings: Dict[str, Dict[str, str]] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._add_spin(form, "x", "Window X", settings.x, -10000, 10000)
        self._add_spin(form, "y", "Window Y", settings.y, -10000, 10000)
        self._add_spin(form, "width", "Window Width", settings.width, 100, 6000)
        self._add_spin(form, "height", "Window Height", settings.height, 100, 6000)
        self._add_text(form, "label_text", "Label Text", settings.label_text)
        self._add_spin(form, "label_x", "Label Offset X", settings.label_x, -10000, 10000)
        self._add_spin(form, "label_y", "Label Offset Y", settings.label_y, -10000, 10000)
        self._add_spin(form, "label_width", "Label Width", settings.label_width, 30, 4000)
        self._add_spin(form, "label_height", "Label Height", settings.label_height, 20, 2000)
        self._add_text(form, "label_bg", "Label Background", settings.label_bg)
        self._add_spin(form, "label_font", "Label Font Size", settings.label_font, 8, 180)
        self._add_text(form, "label_font_color", "Label Font Color", settings.label_font_color)
        self._add_spin(form, "label_border_size", "Label Border Size", settings.label_border_size, 0, 40)
        self._add_text(form, "label_border_color", "Label Border Color", settings.label_border_color)
        self._add_folder_picker(form, "ks", "Active Folder", settings.ks)
        self._add_text(form, "ks_button_text", "Active Button Text", settings.ks_button_text)

        sensors_label = QLabel("HA Sensors")
        sensors_label.setStyleSheet("font-weight:700;")
        layout.addWidget(sensors_label)

        search_row = QHBoxLayout()
        self.sensor_search_input = QLineEdit()
        self.sensor_search_input.setPlaceholderText("Search sensors (e.g. temperature, door)")
        self.sensor_search_btn = QPushButton("Search")
        _set_button_icon(self.sensor_search_btn, HA_ICON_PATH)
        self.sensor_search_btn.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        self.sensor_search_btn.clicked.connect(self._start_sensor_search)
        search_row.addWidget(self.sensor_search_input, 1)
        search_row.addWidget(self.sensor_search_btn)
        layout.addLayout(search_row)

        results_label = QLabel("Search Results")
        layout.addWidget(results_label)
        self.sensor_results_list = QListWidget()
        self.sensor_results_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sensor_results_list.itemDoubleClicked.connect(self._add_selected_result_sensor)
        layout.addWidget(self.sensor_results_list)

        selected_label = QLabel("Selected Sensors")
        layout.addWidget(selected_label)
        self.sensor_selected_list = QListWidget()
        self.sensor_selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.sensor_selected_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.sensor_selected_list.setDefaultDropAction(Qt.MoveAction)
        self.sensor_selected_list.setDragEnabled(True)
        self.sensor_selected_list.setAcceptDrops(True)
        self.sensor_selected_list.setDropIndicatorShown(True)
        self.sensor_selected_list.currentItemChanged.connect(self._on_selected_sensor_changed)
        self.sensor_selected_list.itemClicked.connect(self._on_selected_sensor_clicked)
        layout.addWidget(self.sensor_selected_list)

        sensors_buttons = QHBoxLayout()
        self.sensor_add_btn = QPushButton("Add Selected")
        self.sensor_remove_btn = QPushButton("Remove Selected")
        self.sensor_clear_btn = QPushButton("Clear")
        self.sensor_add_btn.clicked.connect(self._add_selected_result_sensor)
        self.sensor_remove_btn.clicked.connect(self._remove_selected_saved_sensors)
        self.sensor_clear_btn.clicked.connect(self._clear_all_sensor_mappings)
        sensors_buttons.addWidget(self.sensor_add_btn)
        sensors_buttons.addWidget(self.sensor_remove_btn)
        sensors_buttons.addWidget(self.sensor_clear_btn)
        layout.addLayout(sensors_buttons)

        icon_map_label = QLabel("Icon Mapping for Selected Sensor")
        icon_map_label.setStyleSheet("font-weight:700;")
        layout.addWidget(icon_map_label)

        icon_form = QFormLayout()
        layout.addLayout(icon_form)

        self.sensor_entity_display = QLineEdit()
        self.sensor_entity_display.setReadOnly(True)
        self.bg_state_combo = QComboBox()
        self.bg_state_combo.addItem("on")
        self.bg_state_combo.addItem("off")
        self.bg_state_combo.setFixedWidth(58)
        self.bg_state_combo.currentTextChanged.connect(self._on_icon_field_edited)
        self.bg_color_input = QLineEdit()
        self.bg_color_input.setPlaceholderText("bg color")
        self.bg_color_input.setFixedWidth(100)
        self.bg_color_input.textEdited.connect(self._on_icon_field_edited)
        self.bg_color_btn = QPushButton("Pick color")
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        sensor_row = QHBoxLayout()
        sensor_row.addWidget(self.sensor_entity_display, 1)
        sensor_row.addWidget(self.bg_state_combo)
        sensor_row.addWidget(self.bg_color_input)
        sensor_row.addWidget(self.bg_color_btn)
        icon_form.addRow("Sensor", sensor_row)

        self.icon_default_input = QLineEdit()
        self.icon_default_input.textEdited.connect(self._on_icon_field_edited)
        self.icon_default_btn = QPushButton("Pick icon")
        self.icon_default_btn.clicked.connect(lambda: self._pick_icon_for_field(self.icon_default_input))
        icon_default_row = QHBoxLayout()
        icon_default_row.addWidget(self.icon_default_input, 1)
        icon_default_row.addWidget(self.icon_default_btn)
        icon_form.addRow("Icon", icon_default_row)

        self.icon_on_input = QLineEdit()
        self.icon_on_input.textEdited.connect(self._on_icon_field_edited)
        self.icon_on_btn = QPushButton("Pick true icon")
        self.icon_on_btn.clicked.connect(lambda: self._pick_icon_for_field(self.icon_on_input))
        icon_on_row = QHBoxLayout()
        icon_on_row.addWidget(self.icon_on_input, 1)
        icon_on_row.addWidget(self.icon_on_btn)
        icon_form.addRow("Binary true", icon_on_row)

        self.icon_off_input = QLineEdit()
        self.icon_off_input.textEdited.connect(self._on_icon_field_edited)
        self.icon_off_btn = QPushButton("Pick false icon")
        self.icon_off_btn.clicked.connect(lambda: self._pick_icon_for_field(self.icon_off_input))
        icon_off_row = QHBoxLayout()
        icon_off_row.addWidget(self.icon_off_input, 1)
        icon_off_row.addWidget(self.icon_off_btn)
        icon_form.addRow("Binary false", icon_off_row)

        self.tooltip_template_input = QLineEdit()
        self.tooltip_template_input.setPlaceholderText(
            "Optinal template, e.g. Temp on: {name} is {state} with entity id: {entity_id}."
        )
        self.tooltip_template_input.textEdited.connect(self._on_icon_field_edited)
        icon_form.addRow("Tooltip", self.tooltip_template_input)

        note = QLabel("Binary sensors should use true/false icons. Other sensors can use a single icon.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._load_saved_sensors(settings)

        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        _set_button_icon(cancel, CANCEL_ICON_PATH)
        cancel.setStyleSheet("background:#1971c2; color:white; font-weight:700; border-radius:4px;")
        _set_button_icon(save, SAVE_ICON_PATH)
        save.setStyleSheet("background:#6741d9; color:white; font-weight:700; border-radius:4px;")
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        self.sensor_search_finished.connect(self._on_sensor_search_finished)
        self._set_icon_editor_enabled(False)

    def closeEvent(self, event) -> None:
        self._geometry_store.setValue("edit_session_dialog_geometry", self.saveGeometry())
        super().closeEvent(event)

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

    def _add_folder_picker(self, form: QFormLayout, key: str, label: str, value: str) -> None:
        row = QHBoxLayout()
        field = QLineEdit(value)
        browse_btn = QPushButton("Browse...")

        def browse() -> None:
            start_dir = field.text().strip()
            if start_dir:
                current = Path(start_dir)
                if current.is_file():
                    start_dir = str(current.parent)
            path = QFileDialog.getExistingDirectory(self, "Select Active Folder", start_dir or "")
            if path:
                field.setText(path)

        browse_btn.clicked.connect(browse)
        row.addWidget(field, 1)
        row.addWidget(browse_btn)
        wrapper = QVBoxLayout()
        wrapper.addLayout(row)
        self._fields[key] = field
        form.addRow(label, wrapper)

    @staticmethod
    def _load_ha_credentials() -> Tuple[str, str]:
        try:
            data = load_default_mapping()
            if not isinstance(data, dict):
                return "", ""
        except Exception:
            return "", ""
        return str(data.get("ha_url", "")).strip(), str(data.get("ha_api_key", "")).strip()

    def _load_saved_sensors(self, settings: SessionSettings) -> None:
        self.sensor_selected_list.blockSignals(True)
        mappings = list(settings.ha_sensor_icons)
        if not mappings:
            for sensor in settings.ha_sensors:
                text = str(sensor).strip()
                if text:
                    mappings.append(
                        {
                            "entity_id": text,
                            "icon": "",
                            "icon_on": "",
                            "icon_off": "",
                            "tooltip": "",
                            "bg_state": "",
                            "bg_color": "",
                        }
                    )

        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            entity_id = str(mapping.get("entity_id", "")).strip()
            if not entity_id:
                continue
            self._sensor_mappings[entity_id] = {
                "entity_id": entity_id,
                "icon": str(mapping.get("icon", "")).strip(),
                "icon_on": str(mapping.get("icon_on", "")).strip(),
                "icon_off": str(mapping.get("icon_off", "")).strip(),
                "tooltip": str(mapping.get("tooltip", "")).strip(),
                "bg_state": str(mapping.get("bg_state", "")).strip().lower(),
                "bg_color": str(mapping.get("bg_color", "")).strip(),
            }
            item = QListWidgetItem(entity_id)
            item.setData(self.SENSOR_MAPPING_ROLE, dict(self._sensor_mappings[entity_id]))
            self.sensor_selected_list.addItem(item)

        # Keep the editor empty on open; user action should drive first populate.
        self.sensor_selected_list.clearSelection()
        self.sensor_selected_list.setCurrentItem(None)
        self.sensor_selected_list.setCurrentRow(-1)
        self.sensor_selected_list.blockSignals(False)

    def _start_sensor_search(self) -> None:
        if self._search_pending:
            return
        if not self._ha_url or not self._ha_api_key:
            QMessageBox.warning(self, "HA not configured", "Set Home Assistant URL and HA API Key in Settings first.")
            return
        self._search_pending = True
        self.sensor_search_btn.setEnabled(False)
        self.sensor_search_btn.setText("Searching...")
        query = self.sensor_search_input.text().strip()
        thread = threading.Thread(target=self._run_sensor_search, args=(query,), daemon=True)
        thread.start()

    def _run_sensor_search(self, query: str) -> None:
        url = self._ha_url.rstrip("/") + "/api/states"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._ha_api_key}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            if not isinstance(payload, list):
                self.sensor_search_finished.emit(False, [], "Unexpected HA API response.")
                return
            lowered = query.strip().lower()
            preferred: List[Tuple[str, str]] = []
            fallback: List[Tuple[str, str]] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                entity_id = str(item.get("entity_id", "")).strip()
                if not entity_id:
                    continue
                state_text = str(item.get("state", "")).strip()
                attributes = item.get("attributes", {})
                friendly_name = ""
                if isinstance(attributes, dict):
                    friendly_name = str(attributes.get("friendly_name", "")).strip()
                searchable = " ".join([entity_id, friendly_name, state_text]).lower()
                if lowered and lowered not in searchable:
                    continue
                display = entity_id
                if friendly_name:
                    display = f"{entity_id} - {friendly_name}"
                if state_text:
                    display = f"{display} [{state_text}]"
                domain = entity_id.split(".", 1)[0].lower() if "." in entity_id else ""
                if domain in {"sensor", "binary_sensor"}:
                    preferred.append((entity_id, display))
                else:
                    fallback.append((entity_id, display))

            merged = preferred if preferred else fallback
            deduped: List[Tuple[str, str]] = []
            seen = set()
            for entity_id, display in sorted(merged, key=lambda t: t[0].lower()):
                if entity_id.lower() in seen:
                    continue
                seen.add(entity_id.lower())
                deduped.append((entity_id, display))
            message = f"Found {len(deduped)} sensor(s)." if preferred else f"Found {len(deduped)} matching entities."
            self.sensor_search_finished.emit(True, deduped, message)
        except urllib.error.HTTPError as exc:
            self.sensor_search_finished.emit(False, [], f"HA HTTP error {exc.code}")
        except urllib.error.URLError as exc:
            self.sensor_search_finished.emit(False, [], f"HA connection error: {exc.reason}")
        except Exception as exc:
            self.sensor_search_finished.emit(False, [], f"Sensor search failed: {exc}")

    def _on_sensor_search_finished(self, success: bool, results_obj: object, message: str) -> None:
        self._search_pending = False
        self.sensor_search_btn.setEnabled(True)
        self.sensor_search_btn.setText("Search")
        self.sensor_results_list.clear()
        if success:
            results = list(results_obj) if isinstance(results_obj, list) else []
            for result in results:
                entity_id = ""
                display = ""
                if isinstance(result, tuple) and len(result) == 2:
                    entity_id = str(result[0]).strip()
                    display = str(result[1]).strip()
                elif isinstance(result, str):
                    entity_id = result.strip()
                    display = entity_id
                if not entity_id:
                    continue
                item = QListWidgetItem(display or entity_id)
                item.setData(Qt.UserRole, entity_id)
                self.sensor_results_list.addItem(item)
            if message:
                QMessageBox.information(self, "HA sensor search", message)
            return
        if message:
            QMessageBox.warning(self, "HA sensor search", message)

    def _add_selected_result_sensor(self, _item: QListWidgetItem = None) -> None:
        item = self.sensor_results_list.currentItem()
        if item is None:
            return
        entity_id = str(item.data(Qt.UserRole) or item.text()).strip()
        if not entity_id:
            return
        if entity_id not in self._sensor_mappings:
            self._sensor_mappings[entity_id] = {
                "entity_id": entity_id,
                "icon": "",
                "icon_on": "",
                "icon_off": "",
                "tooltip": "",
                "bg_state": "",
                "bg_color": "",
            }
            new_item = QListWidgetItem(entity_id)
            new_item.setData(self.SENSOR_MAPPING_ROLE, dict(self._sensor_mappings[entity_id]))
            self.sensor_selected_list.addItem(new_item)
        for idx in range(self.sensor_selected_list.count()):
            if self.sensor_selected_list.item(idx).text().strip().lower() == entity_id.lower():
                self.sensor_selected_list.setCurrentRow(idx)
                break

    def _remove_selected_saved_sensors(self) -> None:
        selected = self.sensor_selected_list.selectedItems()
        for item in selected:
            entity_id = item.text().strip()
            self._sensor_mappings.pop(entity_id, None)
            row = self.sensor_selected_list.row(item)
            self.sensor_selected_list.takeItem(row)
        if self.sensor_selected_list.count() == 0:
            self._set_icon_editor_enabled(False)

    def _clear_all_sensor_mappings(self) -> None:
        self._sensor_mappings.clear()
        self.sensor_selected_list.clear()
        self._set_icon_editor_enabled(False)

    def _set_icon_editor_enabled(self, enabled: bool) -> None:
        self.sensor_entity_display.setEnabled(enabled)
        self.icon_default_input.setEnabled(enabled)
        self.icon_default_btn.setEnabled(enabled)
        self.icon_on_input.setEnabled(enabled)
        self.icon_on_btn.setEnabled(enabled)
        self.icon_off_input.setEnabled(enabled)
        self.icon_off_btn.setEnabled(enabled)
        self.tooltip_template_input.setEnabled(enabled)
        self.bg_state_combo.setEnabled(enabled)
        self.bg_color_input.setEnabled(enabled)
        self.bg_color_btn.setEnabled(enabled)
        if not enabled:
            self.sensor_entity_display.setText("")
            self.icon_default_input.setText("")
            self.icon_on_input.setText("")
            self.icon_off_input.setText("")
            self.tooltip_template_input.setText("")
            self.bg_state_combo.setCurrentText("on")
            self.bg_color_input.setText("")

    def _on_selected_sensor_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        self._save_icon_editor_to_mapping(previous)
        if current is None:
            self._set_icon_editor_enabled(False)
            return
        self._populate_icon_fields_for_item(current)

    def _on_selected_sensor_clicked(self, item: QListWidgetItem) -> None:
        """Always repopulate icon fields on click, even if current item did not change."""
        if item is None:
            return
        self._populate_icon_fields_for_item(item)

    def _populate_icon_fields_for_item(self, item: QListWidgetItem) -> None:
        entity_id = item.text().strip()
        if not entity_id:
            self._set_icon_editor_enabled(False)
            return
        mapping_obj = item.data(self.SENSOR_MAPPING_ROLE)
        mapping = dict(mapping_obj) if isinstance(mapping_obj, dict) else self._sensor_mappings.get(entity_id)
        if mapping is None:
            mapping = {
                "entity_id": entity_id,
                "icon": "",
                "icon_on": "",
                "icon_off": "",
                "tooltip": "",
                "bg_state": "",
                "bg_color": "",
            }
            self._sensor_mappings[entity_id] = mapping
        else:
            mapping["entity_id"] = entity_id
            self._sensor_mappings[entity_id] = mapping
            item.setData(self.SENSOR_MAPPING_ROLE, dict(mapping))
        self._sensor_editor_syncing = True
        self._set_icon_editor_enabled(True)
        self.sensor_entity_display.setText(entity_id)
        self.icon_default_input.setText(str(mapping.get("icon", "")))
        self.icon_on_input.setText(str(mapping.get("icon_on", "")))
        self.icon_off_input.setText(str(mapping.get("icon_off", "")))
        self.tooltip_template_input.setText(str(mapping.get("tooltip", "")))
        saved_state = str(mapping.get("bg_state", "")).strip().lower()
        self.bg_state_combo.setCurrentText(saved_state if saved_state in {"on", "off"} else "on")
        self.bg_color_input.setText(str(mapping.get("bg_color", "")))
        self._sensor_editor_syncing = False

    def _on_icon_field_edited(self, _text: str = "") -> None:
        if self._sensor_editor_syncing:
            return
        self._save_icon_editor_to_mapping()

    def _save_icon_editor_to_mapping(self, target_item: Optional[QListWidgetItem] = None) -> None:
        if not self.sensor_entity_display.isEnabled():
            return
        item = target_item if target_item is not None else self.sensor_selected_list.currentItem()
        if item is None:
            return
        entity_id = item.text().strip()
        if not entity_id:
            return
        mapping = self._sensor_mappings.get(entity_id)
        if mapping is None:
            mapping = {
                "entity_id": entity_id,
                "icon": "",
                "icon_on": "",
                "icon_off": "",
                "tooltip": "",
                "bg_state": "",
                "bg_color": "",
            }
            self._sensor_mappings[entity_id] = mapping
        mapping["icon"] = self.icon_default_input.text().strip()
        mapping["icon_on"] = self.icon_on_input.text().strip()
        mapping["icon_off"] = self.icon_off_input.text().strip()
        mapping["tooltip"] = self.tooltip_template_input.text().strip()
        mapping["bg_state"] = self.bg_state_combo.currentText().strip().lower()
        mapping["bg_color"] = self.bg_color_input.text().strip()
        item.setData(self.SENSOR_MAPPING_ROLE, dict(mapping))

    def _pick_bg_color(self) -> None:
        chosen = QColorDialog.getColor(parent=self)
        if not chosen.isValid():
            return
        self.bg_color_input.setText(chosen.name())
        self._save_icon_editor_to_mapping()

    def _pick_icon_for_field(self, target_input: QLineEdit) -> None:
        current = self.sensor_selected_list.currentItem()
        if current is None:
            return
        start_dir = str(self.ICONS_DIR)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            start_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            selected = Path(file_path).resolve()
            icons_dir = self.ICONS_DIR.resolve()
            if icons_dir not in selected.parents:
                QMessageBox.warning(
                    self,
                    "Invalid icon location",
                    f"Please select an icon from:\n{icons_dir}",
                )
                return
        except OSError:
            QMessageBox.warning(self, "Invalid icon", "Could not resolve selected icon path.")
            return
        target_input.setText(file_path)
        self._save_icon_editor_to_mapping()

    def values(self) -> SessionSettings:
        """Read all current UI fields back into a SessionSettings object."""
        try:
            self._save_icon_editor_to_mapping()
            sensor_ids: List[str] = []
            sensor_mappings: List[Dict[str, str]] = []
            for idx in range(self.sensor_selected_list.count()):
                entity_id = self.sensor_selected_list.item(idx).text().strip()
                if not entity_id:
                    continue
                sensor_ids.append(entity_id)
                mapping = self._sensor_mappings.get(entity_id, {})
                sensor_mappings.append(
                    {
                        "entity_id": entity_id,
                        "icon": str(mapping.get("icon", "")).strip(),
                        "icon_on": str(mapping.get("icon_on", "")).strip(),
                        "icon_off": str(mapping.get("icon_off", "")).strip(),
                        "tooltip": str(mapping.get("tooltip", "")).strip(),
                        "bg_state": str(mapping.get("bg_state", "")).strip().lower(),
                        "bg_color": str(mapping.get("bg_color", "")).strip(),
                    }
                )

            return SessionSettings(
                x=self._fields["x"].value(),
                y=self._fields["y"].value(),
                width=self._fields["width"].value(),
                height=self._fields["height"].value(),
                label_text=self._fields["label_text"].text().strip() or "Label",
                label_x=self._fields["label_x"].value(),
                label_y=self._fields["label_y"].value(),
                label_bg=self._fields["label_bg"].text().strip() or "white",
                label_width=self._fields["label_width"].value(),
                label_height=self._fields["label_height"].value(),
                label_font=self._fields["label_font"].value(),
                label_font_color=self._fields["label_font_color"].text().strip() or "black",
                label_border_size=self._fields["label_border_size"].value(),
                label_border_color=self._fields["label_border_color"].text().strip() or "black",
                station_name="",
                ks=self._fields["ks"].text().strip(),
                ks_button_text=self._fields["ks_button_text"].text().strip(),
                ha_sensors=list(dict.fromkeys(sensor_ids)),
                ha_sensor_icons=sensor_mappings,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Input", f"Could not read values: {exc}")
            return SessionSettings()
