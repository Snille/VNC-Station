"""Central constants for paths, network settings, and mode labels."""

from pathlib import Path
import sys

APP_VERSION = "1.3.3"


# Base directory for user/runtime files.
# - Source run: repo root
# - Frozen run: folder containing VNC-Station-Controller.exe
if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_ROOT = ROOT_DIR

# Resource/data paths packaged with the app.
APP_DIR = RESOURCE_ROOT / "app"
ICON_PATH = APP_DIR / "images" / "icon.png"
CHAT_ICON_PATH = APP_DIR / "images" / "chat.png"
GEARS_ICON_PATH = APP_DIR / "images" / "gear.png"
HA_ICON_PATH = APP_DIR / "images" / "ha.png"
VIEW_ICON_PATH = APP_DIR / "images" / "view.png"
CONTROL_ICON_PATH = APP_DIR / "images" / "control.png"
EDIT_ICON_PATH = APP_DIR / "images" / "edit.png"
IMPORT_ICON_PATH = APP_DIR / "images" / "import.png"
EXPORT_ICON_PATH = APP_DIR / "images" / "export.png"
VALIDATE_ICON_PATH = APP_DIR / "images" / "validate.png"
SAVE_ICON_PATH = APP_DIR / "images" / "save.png"
OPEN_ICON_PATH = APP_DIR / "images" / "open.png"
CANCEL_ICON_PATH = APP_DIR / "images" / "cancel.png"
DELETE_ICON_PATH = APP_DIR / "images" / "delete.png"
CLEAR_ICON_PATH = APP_DIR / "images" / "clear.png"
RESET_ICON_PATH = APP_DIR / "images" / "reset.png"
UNTAG_ICON_PATH = APP_DIR / "images" / "untag.png"
UNLOCK_ICON_PATH = APP_DIR / "images" / "unlock.png"
APPLYSETUP_ICON_PATH = APP_DIR / "images" / "applysetup.png"
SPREADSHEET_ICON_PATH = APP_DIR / "images" / "spreadsheet.png"
LINK_ICON_PATH = APP_DIR / "images" / "link.png"
MONITOR_ICON_PATH = APP_DIR / "images" / "monitor.png"
NOTICE_SOUND_PATH = APP_DIR / "sounds" / "notice.wav"
INDICATOR_DOOR_OPEN_ICON_PATH = APP_DIR / "images" / "indicator-dooropen.png"
INDICATOR_DOOR_CLOSED_ICON_PATH = APP_DIR / "images" / "indicator-doorclosed.png"

# Runtime/user-managed paths.
VNC_CONTROL_DIR = ROOT_DIR / "vnc-control"
VNC_VIEW_DIR = ROOT_DIR / "vnc-view"
VNC_POSITIONS_DIR = ROOT_DIR / "vnc-positions"
VNC_SETUPS_DIR = ROOT_DIR / "vnc-setups"
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_CONFIG_PATH = ROOT_DIR / "default.json"
DEFAULT_LOCAL_CONFIG_PATH = ROOT_DIR / "default.local.json"
VIEWER_EXE_PATH = ROOT_DIR / "tvnviewer.exe"

# UDP settings for station discovery/chat/session coordination.
UDP_PORT = 50000
UDP_BUFFER = 65535
STATION_TIMEOUT_SECONDS = 45
HELLO_INTERVAL_MS = 7000
SESSION_BROADCAST_INTERVAL_MS = 15000
STATION_PRESENCE_CHECK_MS = 5000

# Logical mode keys used across UI/config/network.
MODE_VIEW = "view"
MODE_CONTROL = "control"
