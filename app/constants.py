"""Central constants for paths, network settings, and mode labels."""

from pathlib import Path
import sys

APP_VERSION = "1.0.1"


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
NOTICE_SOUND_PATH = APP_DIR / "sounds" / "notice.wav"

# Runtime/user-managed paths.
VNC_CONTROL_DIR = ROOT_DIR / "vnc-control"
VNC_VIEW_DIR = ROOT_DIR / "vnc-view"
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_CONFIG_PATH = ROOT_DIR / "default.json"
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
