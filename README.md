# VNC Station Controller

Windows desktop app (PyQt5) for managing multiple TightVNC sessions in `view` and `control` mode, with station-to-station coordination over UDP and built-in chat.

Current version: `1.3.2`

## Screenshots

<table>
  <tr>
    <td align="center"><strong>Main (empty)</strong></td>
    <td align="center"><strong>Main with sessions</strong></td>
    <td align="center"><strong>Main Settings</strong></td>
    <td align="center"><strong>Chat</strong></td>
  </tr>
  <tr>
    <td><a href="Example%20files/Screenshots/main-empty.png"><img src="Example%20files/Screenshots/main-empty.png" alt="Main (empty)" width="200"></a></td>
    <td><a href="Example%20files/Screenshots/main-setup+link+tooltip.png"><img src="Example%20files/Screenshots/main-setup+link+tooltip.png" alt="Main with sessions" width="200"></a></td>
    <td><a href="Example%20files/Screenshots/main-settings.png"><img src="Example%20files/Screenshots/main-settings.png" alt="Main Settings" width="200"></a></td>
    <td><a href="Example%20files/Screenshots/station-chat.png"><img src="Example%20files/Screenshots/station-chat.png" alt="Chat" width="200"></a></td>
  </tr>
  <tr>
    <td align="center"><strong>Session Layout</strong></td>
    <td align="center"><strong>Position Layout</strong></td>
    <td align="center"><strong>Edit View</strong></td>
    <td align="center"><strong>Edit Control</strong></td>
  </tr>
  <tr>
    <td><a href="Example%20files/Screenshots/sessnon-layout+vncpreview+label.png"><img src="Example%20files/Screenshots/sessnon-layout+vncpreview+label.png" alt="Session Layout" width="200"></a></td>
    <td><a href="Example%20files/Screenshots/position-layout+vnc-preview.png"><img src="Example%20files/Screenshots/position-layout+vnc-preview.png" alt="Position Layout" width="200"></a></td>
    <td><a href="Example%20files/Screenshots/edit-session-view.png"><img src="Example%20files/Screenshots/edit-session-view.png" alt="Edit View" width="200"></a></td>
    <td><a href="Example%20files/Screenshots/edit-session-control.png"><img src="Example%20files/Screenshots/edit-session-control.png" alt="Edit Control" width="200"></a></td>
  </tr>
</table>

## Home Assistant Integration

<p>
  <a href="Example%20files/Screenshots/alarm-notifications-from-home-assistant.png">
    <img src="Example%20files/Screenshots/alarm-notifications-from-home-assistant.png" alt="Alarm notifications from Home Assistant" width="840">
  </a>
</p>

## What You Need Before Starting

- Windows 10/11
- Python 3.x
- TightVNC Viewer executable `tvnviewer.exe` in repo root
- Network where all control stations can exchange UDP traffic on port `50000`
- The following folders in the project root:
  - `vnc-view/` (contains per-target `.vnc` and optional `.json`)
  - `vnc-control/` (contains per-target `.vnc` and optional `.json`)
  - `vnc-positions/` (contains reusable position `.json` presets)
  - `vnc-setups/` (contains saved setup `.json` presets for tags/positions/links)

### Expected File Layout

```text
VNC-Station/
  app/
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
  "ha_url": "http://ha.spectrogon.com/",
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

Use `tests/scripts/udp-port-test.ps1` to verify UDP `50000` works in both directions.

### Computer B (listener)

```powershell
.\tests\scripts\udp-port-test.ps1 -Mode listen -Port 50000
```

### Computer A (sender)

```powershell
.\tests\scripts\udp-port-test.ps1 -Mode send -Port 50000 -TargetIP <IP_OF_COMPUTER_B> -Message "Test from A"
```

Then swap roles and test back from B to A.

If it fails, allow UDP port `50000` in firewall (Admin PowerShell):

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
6. Use `Setup View` / `Setup Control` to open (or close) all sessions for that mode that have a position selected.
7. Use `Edit View` / `Edit Control` for per-session window + overlay settings.
8. Use `Positions & Sizes` for visual layout editing and position preset management.
9. Use setup presets: selector + `Save` / `Clear Setup` / `Delete`.
10. Use `Change Settings` and run `Validate config`, `Export config`, or `Import config` from the Settings window.
11. Configure `KS` in Edit dialogs; `KS/KSV/KSC` opens the configured file (or latest file in folder).
12. Use `Change Settings` to open app settings (theme, font size, defaults, HA URL/key, HA connection test, maintenance tools).
13. In `Edit View` / `Edit Control`, add HA sensors and map icons (single icon or binary true/false icons), reorder `Selected Sensors` by drag-and-drop, and optionally set binary state color rules.

Startup note:
- On launch, open actions are briefly locked while the app requests current session ownership from other stations.
- This prevents opening a session before ownership data is synchronized.

## Main Window Layout (Current)

- Default startup size: `250x830` (if no saved size exists in app settings)
- Connection list is the resizable/scrollable section
- Bottom control rows:
  1. setup selector + `Save` + `Clear Setup` + `Delete`
  2. `Setup View` / `Close View` + `Setup Control` / `Close Control`
  3. `View tagged` / `Close tagged` + `Control tagged` / `Close tagged`
  4. `Untag all` + `Chat` + `Positions & Sizes`
  5. `Take over session` + `Reconnect on drop`
  6. `Change Settings`

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
- Per-connection settings editor: tune VNC window and label appearance/position.
- Position presets (`vnc-positions`): reusable window x/y/width/height layouts.
- Per-mode position assignment (`Pos V` / `Pos C`): assign a preset to each view/control session.
- Setup View/Control actions: open/close setup sessions by mode (position-selected rows only).
- Unique position assignment guard on View mode: prevents duplicate View position assignment.
- Per-mode session linking (`Link V` / `Link C`): opens linked sessions together with view/control actions.
- Linked close behavior: closing a session also closes linked sessions recursively (loop-safe).
- Per-session `KS` folder/file buttons (`KS`, `KSV`, `KSC`) with direct open from the main list.
- App-level `Change Settings` window for theme, font size, defaults, HA connectivity, and maintenance tools.
- HA connection testing (`/api/`) with toast feedback and success/fail button color feedback.
- `Edit View`/`Edit Control` HA sensor search from Home Assistant (`/api/states`).
- Per-sensor icon mapping: one icon for generic sensors, separate true/false icons for binary sensors.
- Per-sensor tooltip templates with `{name}`, `{state}`, and `{entity_id}` placeholders.
- Drag-and-drop ordering in `Selected Sensors`; icon display order follows the saved list order.
- Binary sensor state color rules can color the icon display area and session overlay label background.
- Binary sensor state color rules do not change `View`/`Control` button colors.
- Multi-icon row indicators: multiple mapped sensors can display side-by-side in each connection row.
- Animated GIF indicators supported in the main window.
- `input_boolean.*` is treated as binary for true/false icon mapping.
- Setup presets (`vnc-setups/*.json`) store and restore all row tags, selected positions, and selected links.
- Last selected setup is persisted across restarts.
- Overlay labels that follow VNC windows: keep session identity visible on screen.
- Session lock awareness across stations: avoid accidental duplicate control/view.
- Optional takeover mode: allow controlled override when needed.
- Reconnect on drop option: automatically restore sessions after unexpected viewer exits.
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
- `Positions & Sizes` opens the visual layout tool:
  - movable frameless `VNC Preview` window (cross-screen(s))
  - movable/resizable frameless `Label Preview` window (always-on-top)
  - two edit modes:
    - `Position`: only VNC geometry editing and position load/save
    - `Session`: full VNC + label settings editing
  - label coordinates are offsets relative to the VNC window top-left
  - `Load` target selector (`connection [view/control]`) with default fallback if JSON is missing
  - `Positions` selector with `Load Pos` / `Save Pos` for `vnc-positions/*.json`
  - top `Save` saves to current selected target
  - bottom save allows saving to another target

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
- Setup presets are loaded from `vnc-setups/*.json`; applying a setup resets rows first, then applies saved tags/positions/links.
- Stations communicate over UDP broadcast on port `50000`:
  - presence discovery (`hello`)
  - session open/close state
  - chat/direct/notify messages
  - global topic updates
  - away status updates
  - takeover notices
- Session lock logic prevents opening a connection already active on another station, unless `Take over session` is enabled.
- The app stores UI preferences (theme, window sizes, reconnect toggle) via Windows `QSettings`.
- At startup, the app performs a short session-sync handshake (`session_sync_request`) before enabling open actions.

## TODO

- Validate full production multi-monitor behavior on real hardware:
  - 3-4x 4K screens
  - 1-2x Full HD screens
  - mixed-DPI setup checks for VNC window placement and label overlay alignment
- Write a complete user manual for the whole application.

## License

This project is MIT licensed (see `LICENSE` in the repository root).
