"""Maintenance tools: validation and config bundle import/export."""

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List

from .constants import DEFAULT_CONFIG_PATH, ROOT_DIR, VIEWER_EXE_PATH, VNC_CONTROL_DIR, VNC_VIEW_DIR

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
}


def validate_runtime_configuration() -> List[str]:
    """Validate important files/config and return findings."""
    findings: List[str] = []
    if not VIEWER_EXE_PATH.exists():
        findings.append(f"Missing viewer executable: {VIEWER_EXE_PATH}")
    if not DEFAULT_CONFIG_PATH.exists():
        findings.append(f"Missing default.json: {DEFAULT_CONFIG_PATH}")

    for folder in (VNC_VIEW_DIR, VNC_CONTROL_DIR):
        if not folder.exists():
            findings.append(f"Missing folder: {folder}")
            continue
        for json_path in folder.glob("*.json"):
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

        json_stems = {p.stem for p in folder.glob("*.json")}
        vnc_stems = {p.stem for p in folder.glob("*.vnc")}
        for missing_vnc in sorted(json_stems - vnc_stems):
            findings.append(f"{folder.name}: {missing_vnc}.json exists but {missing_vnc}.vnc is missing")
        for missing_json in sorted(vnc_stems - json_stems):
            findings.append(f"{folder.name}: {missing_json}.vnc exists but {missing_json}.json is missing (optional)")

    return findings


def export_config_bundle(destination_zip: Path) -> Path:
    """Export default and per-connection JSON/.vnc files into a zip bundle."""
    destination_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if DEFAULT_CONFIG_PATH.exists():
            zf.write(DEFAULT_CONFIG_PATH, arcname="default.json")
        for folder in (VNC_VIEW_DIR, VNC_CONTROL_DIR):
            for ext in ("*.json", "*.vnc"):
                for file_path in folder.glob(ext):
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
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            norm = member.replace("\\", "/")
            if norm == "default.json" or norm.startswith("vnc-view/") or norm.startswith("vnc-control/"):
                if not (norm.endswith(".json") or norm.endswith(".vnc")):
                    continue
                target = ROOT_DIR / Path(norm)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, target.open("wb") as dst:
                    dst.write(src.read())
                applied.append(str(target))
    return applied
