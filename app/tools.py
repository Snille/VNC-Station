"""Maintenance tools: validation and config bundle import/export."""

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from .constants import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOCAL_CONFIG_PATH,
    ROOT_DIR,
    VIEWER_EXE_PATH,
    VNC_CONTROL_DIR,
    VNC_POSITIONS_DIR,
    VNC_SETUPS_DIR,
    VNC_VIEW_DIR,
)

_SETTINGS_KEYS = {
    "x",
    "y",
    "width",
    "height",
    "label_text",
    "label_x",
    "label_y",
    "label_bg",
    "label_width",
    "label_height",
    "label_font",
    "label_font_color",
    "label_border_size",
    "label_border_color",
    "position_name",
    "linked_session",
    "ks",
    "ks_button_text",
    "ha_sensors",
    "ha_sensor_icons",
}

_BUNDLE_RULES = (
    ("vnc-view", VNC_VIEW_DIR, (".json", ".vnc")),
    ("vnc-control", VNC_CONTROL_DIR, (".json", ".vnc")),
    ("vnc-positions", VNC_POSITIONS_DIR, (".json",)),
    ("vnc-setups", VNC_SETUPS_DIR, (".json",)),
)


def _validate_json_files_in_folder(folder: Path, findings: List[str]) -> int:
    """Validate that all JSON files in folder parse as JSON objects."""
    if not folder.exists():
        findings.append(f"Missing folder: {folder}")
        return 0
    checked = 0
    for json_path in folder.glob("*.json"):
        checked += 1
        try:
            with json_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                findings.append(f"Invalid JSON object in {json_path}")
        except Exception as exc:
            findings.append(f"Failed to parse {json_path}: {exc}")
    return checked


def validate_runtime_configuration() -> List[str]:
    """Validate important files/config and return findings."""
    findings, _checked_files = validate_runtime_configuration_details()
    return findings


def validate_runtime_configuration_details() -> Tuple[List[str], int]:
    """Validate important files/config and return (findings, checked_files)."""
    findings: List[str] = []
    checked_files = 0
    checked_files += 1
    if not VIEWER_EXE_PATH.exists():
        findings.append(f"Missing viewer executable: {VIEWER_EXE_PATH}")
    checked_files += 1
    if not DEFAULT_CONFIG_PATH.exists():
        findings.append(f"Missing default.json: {DEFAULT_CONFIG_PATH}")
    else:
        try:
            with DEFAULT_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                findings.append(f"Invalid JSON object in {DEFAULT_CONFIG_PATH}")
        except Exception as exc:
            findings.append(f"Failed to parse {DEFAULT_CONFIG_PATH}: {exc}")
    if DEFAULT_LOCAL_CONFIG_PATH.exists():
        checked_files += 1
        try:
            with DEFAULT_LOCAL_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                findings.append(f"Invalid JSON object in {DEFAULT_LOCAL_CONFIG_PATH}")
        except Exception as exc:
            findings.append(f"Failed to parse {DEFAULT_LOCAL_CONFIG_PATH}: {exc}")

    for folder in (VNC_VIEW_DIR, VNC_CONTROL_DIR):
        if folder.exists():
            for json_path in folder.glob("*.json"):
                checked_files += 1
                try:
                    with json_path.open("r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    if not isinstance(data, dict):
                        findings.append(f"Invalid JSON object in {json_path}")
                        continue
                    unknown = set(data.keys()) - _SETTINGS_KEYS
                    if unknown:
                        findings.append(f"Unknown keys in {json_path.name}: {', '.join(sorted(unknown))}")
                except Exception as exc:
                    findings.append(f"Failed to parse {json_path}: {exc}")
        else:
            findings.append(f"Missing folder: {folder}")
            continue

        json_files = list(folder.glob("*.json"))
        vnc_files = list(folder.glob("*.vnc"))
        checked_files += len(vnc_files)
        json_stems = {p.stem for p in json_files}
        vnc_stems = {p.stem for p in vnc_files}
        for missing_vnc in sorted(json_stems - vnc_stems):
            findings.append(f"{folder.name}: {missing_vnc}.json exists but {missing_vnc}.vnc is missing")
        for missing_json in sorted(vnc_stems - json_stems):
            findings.append(f"{folder.name}: {missing_json}.vnc exists but {missing_json}.json is missing (optional)")

    checked_files += _validate_json_files_in_folder(VNC_POSITIONS_DIR, findings)
    checked_files += _validate_json_files_in_folder(VNC_SETUPS_DIR, findings)

    return findings, checked_files


def export_config_bundle(destination_zip: Path) -> Path:
    """Export default and per-connection JSON/.vnc files into a zip bundle."""
    destination_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if DEFAULT_CONFIG_PATH.exists():
            zf.write(DEFAULT_CONFIG_PATH, arcname="default.json")
        if DEFAULT_LOCAL_CONFIG_PATH.exists():
            zf.write(DEFAULT_LOCAL_CONFIG_PATH, arcname="default.local.json")
        for _prefix, folder, suffixes in _BUNDLE_RULES:
            for suffix in suffixes:
                for file_path in folder.glob(f"*{suffix}"):
                    rel = file_path.relative_to(ROOT_DIR)
                    zf.write(file_path, arcname=str(rel))
    return destination_zip


def suggested_export_name() -> str:
    """Return timestamped filename for config exports."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"vnc-station-config-{stamp}.zip"


def import_config_bundle(zip_path: Path) -> List[str]:
    """Import config JSON/.vnc files from a bundle zip and return applied file list."""
    applied: List[str] = []
    allowed_paths = {prefix: set(suffixes) for prefix, _folder, suffixes in _BUNDLE_RULES}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            norm = member.replace("\\", "/")
            if norm == "default.json":
                target = ROOT_DIR / Path(norm)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, target.open("wb") as dst:
                    dst.write(src.read())
                applied.append(str(target))
                continue
            if norm == "default.local.json":
                target = ROOT_DIR / Path(norm)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, target.open("wb") as dst:
                    dst.write(src.read())
                applied.append(str(target))
                continue
            for prefix, suffixes in allowed_paths.items():
                prefix_path = f"{prefix}/"
                if not norm.startswith(prefix_path):
                    continue
                path_obj = Path(norm)
                if path_obj.suffix.lower() not in suffixes:
                    break
                target = ROOT_DIR / path_obj
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, target.open("wb") as dst:
                    dst.write(src.read())
                applied.append(str(target))
                break
    return applied
