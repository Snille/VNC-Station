# VNC Station Controller

Windows desktop app (PyQt5) for managing multiple TightVNC sessions in `view` and `control` mode, with station-to-station coordination over UDP and built-in chat.

Current version: `1.6.0`

## Table Of Contents

- [Screenshots](#screenshots)
- [Home Assistant Integration](#home-assistant-integration)
- [User Manual](#user-manual)
- [What You Need Before Starting](#what-you-need-before-starting)
- [Example Files (Templates)](#example-files-templates)
- [Clone And Set Up Virtual Environment](#clone-and-set-up-virtual-environment)
- [Install Dependencies](#install-dependencies)
- [Start The App](#start-the-app)
- [Local Secrets (Recommended)](#local-secrets-recommended)
- [UDP Port Test Between Two Computers](#udp-port-test-between-two-computers)
- [How To Use The App (Typical Flow)](#how-to-use-the-app-typical-flow)
- [Main Window Layout (Current)](#main-window-layout-current)
- [Chat Commands](#chat-commands)
- [Features (And Why They Exist)](#features-and-why-they-exist)
- [Custom Sensor Icon Guidelines](#custom-sensor-icon-guidelines)
- [Maintenance Tools](#maintenance-tools)
- [Testing](#testing)
- [Packaging (Optional)](#packaging-optional)
- [How It Works (Short Technical Summary)](#how-it-works-short-technical-summary)
- [TODO](#todo)
- [License](#license)

## Screenshots

Current interface examples:

<table>
  <tr>
    <td align="center"><strong>Main Operator Window</strong></td>
    <td align="center"><strong>Chat</strong></td>
    <td align="center"><strong>Station Settings</strong></td>
  </tr>
  <tr>
    <td><a href="manual/manual-assets/images/1.6.0/01-main-window-setup-area.png"><img src="manual/manual-assets/images/1.6.0/01-main-window-setup-area.png" alt="Main window" width="260"></a></td>
    <td><a href="manual/manual-assets/images/1.6.0/02-chat-window.png"><img src="manual/manual-assets/images/1.6.0/02-chat-window.png" alt="Chat window" width="260"></a></td>
    <td><a href="manual/manual-assets/images/1.6.0/03-settings-window-network-and-maintenance.png"><img src="manual/manual-assets/images/1.6.0/03-settings-window-network-and-maintenance.png" alt="Settings window" width="260"></a></td>
  </tr>
  <tr>
    <td align="center"><strong>Session Editor</strong></td>
    <td align="center"><strong>Position Editor</strong></td>
    <td align="center"><strong>Documentation</strong></td>
  </tr>
  <tr>
    <td><a href="manual/manual-assets/images/1.6.0/04-layout-tool-session-ha-search.png"><img src="manual/manual-assets/images/1.6.0/04-layout-tool-session-ha-search.png" alt="Session layout tool" width="260"></a></td>
    <td><a href="manual/manual-assets/images/1.6.0/05-layout-tool-position-mode.png"><img src="manual/manual-assets/images/1.6.0/05-layout-tool-position-mode.png" alt="Position layout tool" width="260"></a></td>
    <td align="center">See <code>manual/</code> for the current role-based guides, workflows, and reference material.</td>
  </tr>
</table>

## Home Assistant Integration

Home Assistant integration is configured per session and can drive:

- row indicator icons
- binary true/false icon changes
- tooltip text
- alarm color rules for row indicators and session labels

See `manual/advanced-user-guide.md` for the current configuration workflow.

## User Manual

Manuals are split by role:

- Production users: `manual/user-guide.md`
- Advanced users: `manual/advanced-user-guide.md`
- Admin/deployment: `manual/admin-guide.md`

## What You Need Before Starting

- Windows 10/11
- Python 3.x
- TightVNC Viewer executable `tvnviewer.exe` in repo root
- Network where all control stations can exchange UDP traffic on one shared UDP port (default `50000`, configurable in `Settings`)
- The following folders in the project root:
  - `vnc-view/` (contains per-target `.vnc` and optional `.json`)
  - `vnc-control/` (contains per-target `.vnc` and optional `.json`)
  - `vnc-positions/` (contains reusable position `.json` presets)
  - `vnc-setups/` (contains saved setup `.json` presets for positions/links)

### Expected File Layout

```text
VNC-Station/
  app/
  manual/
  vnc-view/
  vnc-control/
  vnc-positions/
  vnc-setups/
  Example files/
  tests/scripts/
  default.json
  default.local.json.example
  tvnviewer.exe
  requirements.txt
```

Note: `vnc-view/` and `vnc-control/` are intentionally git-ignored for station-specific files. The folders remain in the repo via `.gitkeep`.

## Example Files (Templates)

`Example files/` contains starter templates you can copy, rename and edit:

- `dummy.vnc`
- `dummy.json`

Suggested usage:

1. Copy `dummy.vnc` to `vnc-view/<TargetName>.vnc` and/or `vnc-control/<TargetName>.vnc`.
2. Open the copied `.vnc` in TightVNC Viewer and set host/password, then save.
3. Copy `dummy.json` to matching `<TargetName>.json` if you want custom window/label defaults.

Informational reference in the same folder:
- `TightVNC-Viewer-Help.txt`

## Clone And Set Up Virtual Environment

```powershell
git clone <your-repo-url>
cd VNC-Station
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy RemoteSigned
```

## Install Dependencies

```powershell
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Start The App

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

## Local Secrets (Recommended)

- Keep `default.json` sanitized for git.
- Put machine-local secrets/overrides in `default.local.json` (not tracked by git).
- Start from `default.local.json.example`.
- `default.local.json` overrides `default.json` at runtime.
- Keep `default.local.json.example` in repo root as template; do not move it.

Example `default.local.json`:

```json
{
  "ha_url": "http://home.assistant.you:8123",
  "ha_api_key": "YOUR_REAL_HA_TOKEN"
}
```

Safety notes:
- `default.local.json` is ignored by git via `.gitignore`.
- It will not be pushed unless force-added manually (`git add -f default.local.json`).

Optional git hook setup (blocks committing real `ha_api_key` in `default.json`/`default.local.json`):

```powershell
git config core.hooksPath .githooks
```

## UDP Port Test Between Two Computers

Use `tests/scripts/udp-port-test.ps1` to verify the configured UDP port (default `50000`) works in both directions.

### Computer B (listener)

```powershell
.\tests\scripts\udp-port-test.ps1 -Mode listen -Port <UDP_PORT>
```

### Computer A (sender)

```powershell
.\tests\scripts\udp-port-test.ps1 -Mode send -Port <UDP_PORT> -TargetIP <IP_OF_COMPUTER_B> -Message "Test from A"
```

Then swap roles and test back from B to A.

If it fails, allow the configured UDP port in firewall (Admin PowerShell example for `50000`):

```powershell
New-NetFirewallRule -DisplayName "VNC Station UDP 50000" -Direction Inbound -Protocol UDP -LocalPort 50000 -Action Allow
```

Also make sure `python.exe` is allowed in Windows Defender Firewall.

## How To Use The App (Typical Flow)

1. Place `.vnc` files in `vnc-view/` and/or `vnc-control/`.
2. Start the app on one or more stations.
3. (Optional) assign position presets with `Pos V` / `Pos C`.
4. Use row `View` / `Control` buttons to toggle one session at a time.
5. Use `View tagged` / `Control tagged` to open or close tagged sessions per mode.
6. Use `Close all sessions` to immediately close every open local session.
7. Use `Setup View` / `Setup Control` to open (or close) all sessions for that mode that have a position selected.
8. Use `Edit View` / `Edit Control` for per-session window + overlay settings.
9. Use `Positions` for visual position editing and `Sessions` for per-session visual settings.
10. Use setup presets from the setup list on the lower left; click one to apply it immediately, drag to reorder it, and use `Setup name` + `Save` / `Clear` / `Delete` on the right.
11. Use `Settings` and run `Validate config`, `Export config`, or `Import config` from the Settings window.
12. Configure `Active Folder` / `Active Path/File` and optional `Active Button Text` in Edit dialogs; the active button(s) open the configured file, or the latest file in a folder, and the toast reports the full resolved path that was opened.
13. Use `Settings` to open app settings (theme, font size, station name, `Use button icons`, UDP port, reconnect-on-drop, `Follow links on tagged`, allow-multiple-instances option, defaults, HA URL/key, HA connection test, maintenance tools).
14. In `Edit View` / `Edit Control`, add HA sensors and map icons (single icon or binary true/false icons), reorder `Selected Sensors` by drag-and-drop, and optionally set binary state color rules.
15. In the HA sensor search field, press `Enter` to search immediately and use wildcard patterns such as `*m18*` or `*door*m18*`.

Startup note:
- On launch, open actions are briefly locked while the app requests current session ownership from other stations.
- This prevents opening a session before ownership data is synchronized.
- If setup actions are blocked because sessions are already open on another station, the toast now includes the blocked session names/reasons.

## Main Window Layout (Current)

- Default startup size: `250x830` (if no saved size exists in app settings)
- Connection list is the resizable/scrollable section
- Lower setup/session area:
  - left side: `Select setup` title + draggable setup list
  - right side top rows: `Setup View` / `Close View` + `Setup Control` / `Close Control`
  - `View tagged` / `Close tagged` + `Control tagged` / `Close tagged`
  - `Close all sessions` + `Untag all`
  - `Setup name`
  - `Save` + `Clear` + `Delete`
  - `Allow shared sessions`
- Bottom row:
  - `Chat` + `Positions` + `Sessions` + `Settings`

## Chat Commands

- `/help` show command help
- `/nick NewName` change station name
- `/topic #Topic` set global topic for all online stations
- `/me Action text` send action-style message
- `/away [Message]` set away status (clears when the local station types in chat again)
- `/notify [Message]` send a notification message that plays sound on receiving stations

## Features (And Why They Exist)

- Connection discovery from `vnc-view/` and `vnc-control/`: quick setup by file drop.
- Per-connection View/Control toggle buttons: open/close one mode from one button.
- Tagging + mode-specific tagged toggles: batch open/close tagged sessions by mode.
- Global close-all action: close every currently open local View/Control session with one click.
- Per-connection settings editor: tune VNC window and label appearance/position.
- Position presets (`vnc-positions`): reusable window x/y/width/height layouts.
- Per-mode position assignment (`Pos V` / `Pos C`): assign a preset to each view/control session.
- Setup View/Control actions: open/close setup sessions by mode (position-selected rows only).
- Unique position assignment guard on View mode: prevents duplicate View position assignment.
- Per-mode session linking (`Link V` / `Link C`): opens linked sessions together with view/control actions.
- Linked close behavior: closing a session also closes linked sessions recursively (loop-safe).
- Per-session `Active Folder` / `Active Path/File` buttons with optional custom button text per mode.
- When an Active Folder button opens a file, the toast reports the full resolved path.
- App-level `Settings` window for theme, font size, station name, UDP port, reconnect-on-drop, `Follow links on tagged`, allow-multiple-instances option, defaults, HA connectivity, and maintenance tools.
- Global `Use button icons` preference: show or hide button icons across the main window and utility windows.
- Single-instance protection by default: blocks launching a second app instance on the same station unless explicitly enabled in settings.
- HA connection testing (`/api/`) with toast feedback and success/fail button color feedback.
- `Edit View`/`Edit Control` HA sensor search from Home Assistant (`/api/states`).
- HA sensor search supports `Enter` submit and `*` wildcard patterns against entity IDs, names, and state text.
- Per-sensor icon mapping: one icon for generic sensors, separate true/false icons for binary sensors.
- Per-sensor tooltip templates with `{name}`, `{state}`, and `{entity_id}` placeholders.
- Drag-and-drop ordering in `Selected Sensors`; icon display order follows the saved list order.
- Binary sensor state color rules can color the icon display area and session overlay label background.
- Binary sensor state color rules do not change `View`/`Control` button colors.
- Multi-icon row indicators: multiple mapped sensors can display side-by-side in each connection row.
- Animated GIF indicators supported in the main window.
- `input_boolean.*` is treated as binary for true/false icon mapping.
- Setup presets (`vnc-setups/*.json`) store and restore selected positions and selected links.
- Setup presets are shown in a draggable list, and custom list order is persisted across restarts.
- Last selected setup is persisted across restarts.
- Overlay labels that follow VNC windows: keep session identity visible on screen.
- Session lock awareness across stations: avoid accidental duplicate control/view.
- Optional shared-session override mode: allow opening a session already held by another station when needed.
- Reconnect on drop option in `Settings`: automatically restore sessions after unexpected viewer exits.
- Owner line age display scales from seconds to `m:ss`, `h:mm:ss`, and `d:hh:mm:ss`.
- Invalid per-session/default JSON is reported once in a toast and logged, while the app falls back safely to defaults.
- Built-in station chat: coordinate operators without external tools.
- Direct messages + broadcast chat: target one station or all.
- Notify messages with sound: raise attention only when explicitly requested.
- Global topic: keep all stations aligned on current context.
- Station nick/away visibility: improve operational awareness.
- Windows theme support (Auto/Light/Dark): keep UI consistent with operator environment.
- Main/Chat/Settings/Edit/Layout windows restore last position+size on reopen.
- Session cleanup on app exit: avoid orphaned VNC processes.
- Config validation tool: catch missing/malformed files before operation.
- Config import/export bundles: replicate JSON and VNC files (including setup presets) between stations quickly.
- Open Settings window refreshes immediately after importing a config bundle.
- Non-blocking toast notifications: reduce modal interruptions during operation.
- Structured rotating logs in `logs/app.log`: easier troubleshooting and post-incident review.

## Custom Sensor Icon Guidelines

When adding your own status icons for HA sensors:

- File types: use `.png` or `.gif`
- Background: use transparent background
- Recommended size: `256x256` pixels
- Location: place files in `app/images/` (icon picker is restricted to this folder)

For binary-style entities (`binary_sensor.*`, `input_boolean.*`):
- use `Binary true` and/or `Binary false` icon fields
- if only one of true/false is set, icon is shown only for that state

## Maintenance Tools

- `Validate config` checks:
  - missing `tvnviewer.exe` / `default.json`
  - malformed `default.local.json` (if file exists)
  - malformed JSON in `default.json`, `vnc-view`, `vnc-control`, `vnc-positions`, and `vnc-setups`
  - unknown keys and missing `.json`/`.vnc` pairings for view/control session configs
- `Export config` bundles:
  - `default.json`
  - `default.local.json` (if present)
  - `vnc-view/*.json` + `vnc-view/*.vnc`
  - `vnc-control/*.json` + `vnc-control/*.vnc`
  - `vnc-positions/*.json`
  - `vnc-setups/*.json`
- `Import config` restores the same set from bundle zip and refreshes the UI.
- `Positions` opens the dedicated position editor:
  - movable frameless `VNC Preview` window (cross-screen(s))
  - edits only VNC geometry and position load/save
  - `Positions` selector with `Load Pos` / `Save Pos` for `vnc-positions/*.json`
- `Sessions` opens the dedicated session editor:
  - movable frameless `VNC Preview` window (cross-screen(s))
  - movable/resizable frameless `Label Preview` window (always-on-top)
  - label coordinates are offsets relative to the VNC window top-left
  - loads the first available session automatically on open
  - `Load` target selector (`connection [view/control]`) with default fallback if JSON is missing
  - top `Save` saves to current selected target
  - bottom save allows saving to another target
  - `Active Folder` can now be toggled between folder-only and file-path mode
  - utility buttons use the same gray style as the Settings window; config import/export/validate remains distinct in Settings only

## Testing

Run the included unit tests:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

## Packaging (Optional)

Build a distributable folder with PyInstaller:

```powershell
.\packaging\build.ps1
```

Note: packaging builds a windowed app (`--windowed`), so no black console window appears for users.

Cleanup generated build artifacts:

```powershell
.\packaging\cleanup.ps1
```

## How It Works (Short Technical Summary)

- At startup, the app scans `.vnc` files in `vnc-view/` and `vnc-control/` and builds one merged connection list.
- Launching a session starts `tvnviewer.exe -optionsfile=<file.vnc>`.
- JSON settings are loaded per connection/mode (`<name>.json`), with fallback to `default.json`.
- If a session has `position_name` set, that position preset overrides launch `x/y/width/height`.
- Overlay label `label_x`/`label_y` are treated as offsets from the VNC window top-left.
- If a session has `linked_session` set, linked sessions are auto-opened for View/Control actions.
- Closing a session also follows `linked_session` and closes linked sessions recursively.
- A small always-on-top overlay label is created and periodically repositioned to follow the VNC window.
- Setup presets are loaded from `vnc-setups/*.json`; applying a setup resets rows first, then applies saved positions/links.
- Stations communicate over UDP broadcast on the configured `udp_port` (default `50000`):
  - presence discovery (`hello`)
  - session open/close state
  - chat/direct/notify messages
  - global topic updates
  - away status updates
  - takeover notices
- Session lock logic prevents opening a connection already active on another station, unless `Allow shared sessions` is enabled.
- Setup View/Control reports why sessions could not open when blocked by another station or missing files.
- The app stores UI preferences (theme, window sizes, reconnect toggle) via Windows `QSettings`.
- At startup, the app performs a short session-sync handshake (`session_sync_request`) before enabling open actions.

## TODO

- Validate full production multi-monitor behavior on real hardware:
  - 3-4x 4K screens
  - 1-2x Full HD screens
  - mixed-DPI setup checks for VNC window placement and label overlay alignment
- Local language support

## License

This project is MIT licensed (see `LICENSE` in the repository root).
