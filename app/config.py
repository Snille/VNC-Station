"""Helpers for reading/writing JSON settings and discovering VNC files."""

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from .constants import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOCAL_CONFIG_PATH,
    VNC_CONTROL_DIR,
    VNC_POSITIONS_DIR,
    VNC_VIEW_DIR,
)
from .models import ConnectionEntry, PositionPreset, SessionSettings

LOGGER = logging.getLogger(__name__)
JsonWarningReporter = Callable[[str], None]

_JSON_CACHE: Dict[Path, Tuple[object, Dict[str, object]]] = {}
_JSON_WARNING_SIGNATURES: Dict[Path, object] = {}
_POSITION_CACHE_SIGNATURE: Optional[Tuple[Tuple[str, int, int], ...]] = None
_POSITION_CACHE_PRESETS: List[PositionPreset] = []
_JSON_WARNING_REPORTER: Optional[JsonWarningReporter] = None


def set_json_warning_reporter(reporter: Optional[JsonWarningReporter]) -> None:
    """Register an optional callback for malformed JSON warnings."""
    global _JSON_WARNING_REPORTER
    _JSON_WARNING_REPORTER = reporter


def clear_runtime_caches() -> None:
    """Reset cached JSON/position state. Intended for tests and full refreshes."""
    global _POSITION_CACHE_SIGNATURE
    _JSON_CACHE.clear()
    _JSON_WARNING_SIGNATURES.clear()
    _POSITION_CACHE_PRESETS.clear()
    _POSITION_CACHE_SIGNATURE = None


def _report_json_warning(path: Path, detail: str, signature: object) -> None:
    """Log malformed JSON once per file version and notify the UI if configured."""
    previous = _JSON_WARNING_SIGNATURES.get(path)
    if previous == signature:
        return
    _JSON_WARNING_SIGNATURES[path] = signature
    message = f"Invalid JSON in {path.name}; using defaults."
    LOGGER.warning("%s Detail: %s", message, detail)
    reporter = _JSON_WARNING_REPORTER
    if reporter is not None:
        reporter(message)


def _path_signature(path: Path) -> object:
    """Build a lightweight cache signature from the file stat result."""
    try:
        stat = path.stat()
    except OSError:
        return ("missing",)
    return ("file", stat.st_mtime_ns, stat.st_size)


def _dir_entry_signature(path: Path) -> Tuple[str, int, int]:
    """Build a stable directory-entry signature for cache invalidation."""
    try:
        stat = path.stat()
        return (path.name.lower(), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        return (path.name.lower(), -1, -1)


def _load_json(path: Path) -> Dict[str, object]:
    """Load a JSON object from disk, returning {} on missing/invalid files."""
    signature = _path_signature(path)
    cached = _JSON_CACHE.get(path)
    if cached is not None and cached[0] == signature:
        return dict(cached[1])
    if signature == ("missing",):
        _JSON_CACHE[path] = (signature, {})
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                _JSON_CACHE[path] = (signature, dict(data))
                _JSON_WARNING_SIGNATURES.pop(path, None)
                return dict(data)
            _report_json_warning(path, "JSON root must be an object.", signature)
    except (OSError, json.JSONDecodeError) as exc:
        _report_json_warning(path, str(exc), signature)
    _JSON_CACHE[path] = (signature, {})
    return {}


def save_json(path: Path, data: Dict[str, object]) -> None:
    """Persist JSON data with UTF-8 encoding and stable indentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    _JSON_CACHE.pop(path, None)
    _JSON_WARNING_SIGNATURES.pop(path, None)
    global _POSITION_CACHE_SIGNATURE
    if path.parent == VNC_POSITIONS_DIR:
        _POSITION_CACHE_SIGNATURE = None


def _to_int(value: object, fallback: int) -> int:
    """Parse int-like values found in JSON strings/numbers."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def load_default_settings() -> SessionSettings:
    """Read defaults from default.json + optional default.local.json."""
    return SessionSettings.from_mapping(load_default_mapping())


def load_default_mapping() -> Dict[str, object]:
    """Load default settings with local overrides applied."""
    merged = _load_json(DEFAULT_CONFIG_PATH)
    local = _load_json(DEFAULT_LOCAL_CONFIG_PATH)
    merged.update(local)
    return merged


def load_session_settings(config_path: Path) -> SessionSettings:
    """Load per-session settings merged on top of default settings."""
    defaults = load_default_settings()
    merged = defaults.to_json()
    merged["station_name"] = defaults.station_name
    merged.update(_load_json(config_path))
    return SessionSettings.from_mapping(merged)


def load_session_overrides(config_path: Path) -> Dict[str, object]:
    """Load only explicit per-session overrides from JSON."""
    return _load_json(config_path)


def update_session_overrides(config_path: Path, updates: Mapping[str, object]) -> None:
    """Merge/update per-session override keys and persist to disk."""
    data = _load_json(config_path)
    for key, value in updates.items():
        data[key] = value
    save_json(config_path, data)


def scan_connections() -> List[ConnectionEntry]:
    """Build the unified connection list from vnc-control/ and vnc-view/."""
    # Ensure both folders exist so first run does not fail.
    VNC_CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    VNC_VIEW_DIR.mkdir(parents=True, exist_ok=True)

    control = {p.stem: p for p in VNC_CONTROL_DIR.glob("*.vnc")}
    view = {p.stem: p for p in VNC_VIEW_DIR.glob("*.vnc")}

    names = sorted(set(control.keys()).union(view.keys()), key=str.lower)
    return [
        ConnectionEntry(name=n, view_vnc_path=view.get(n), control_vnc_path=control.get(n))
        for n in names
    ]


def scan_positions() -> List[PositionPreset]:
    """Read all position definitions from vnc-positions/*.json."""
    VNC_POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(VNC_POSITIONS_DIR.glob("*.json"), key=lambda p: p.name.lower())
    signature = tuple(_dir_entry_signature(path) for path in files)
    global _POSITION_CACHE_SIGNATURE
    if _POSITION_CACHE_SIGNATURE == signature:
        return list(_POSITION_CACHE_PRESETS)
    presets: List[PositionPreset] = []
    defaults = load_default_settings()
    for path in files:
        data = _load_json(path)
        if not data:
            continue
        fallback_name = path.stem
        name = str(data.get("name", fallback_name)).strip() or fallback_name
        presets.append(
            PositionPreset(
                name=name,
                x=_to_int(data.get("x"), 1),
                y=_to_int(data.get("y"), 1),
                width=max(100, _to_int(data.get("width"), 1300)),
                height=max(100, _to_int(data.get("height"), 880)),
                path=path,
                label_x=_to_int(data.get("label_x"), defaults.label_x),
                label_y=_to_int(data.get("label_y"), defaults.label_y),
                label_bg=str(data.get("label_bg", defaults.label_bg)),
                label_width=max(30, _to_int(data.get("label_width"), defaults.label_width)),
                label_height=max(20, _to_int(data.get("label_height"), defaults.label_height)),
                label_font=max(8, _to_int(data.get("label_font"), defaults.label_font)),
                label_font_color=str(data.get("label_font_color", defaults.label_font_color)),
                label_border_size=max(0, _to_int(data.get("label_border_size"), defaults.label_border_size)),
                label_border_color=str(data.get("label_border_color", defaults.label_border_color)),
            )
        )
    _POSITION_CACHE_PRESETS[:] = presets
    _POSITION_CACHE_SIGNATURE = signature
    return list(_POSITION_CACHE_PRESETS)


def position_by_name(name: str) -> Optional[PositionPreset]:
    """Resolve one position preset by its display name."""
    cleaned = name.strip().lower()
    if not cleaned:
        return None
    for preset in scan_positions():
        if preset.name.strip().lower() == cleaned:
            return preset
    return None


def config_path_for(connection_name: str, mode: str) -> Path:
    """Return the JSON config path for a given connection and mode."""
    directory = VNC_VIEW_DIR if mode == "view" else VNC_CONTROL_DIR
    return directory / f"{connection_name}.json"


def resolve_ks_target(ks_value: str) -> Tuple[Optional[Path], str]:
    """Resolve configured KS value to an openable file path.

    `ks_value` can be either:
    - a direct file path (legacy behavior), or
    - a folder path; in this case the latest modified file in that folder is used.
    """
    cleaned = ks_value.strip()
    if not cleaned:
        return None, "No Active Folder configured."

    target = Path(cleaned)
    if target.is_file():
        return target, ""
    if target.is_dir():
        files: List[Path] = []
        for child in target.iterdir():
            if child.is_file():
                files.append(child)
        if not files:
            return None, f"No files found in Active Folder: {target}"
        latest = max(files, key=lambda p: p.stat().st_mtime)
        return latest, ""

    return None, f"Active Folder path not found: {target}"
