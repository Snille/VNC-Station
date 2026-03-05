# VNC Station Controller

Windows desktop app (PyQt5) for managing multiple TightVNC sessions in `view` and `control` mode, with station-to-station coordination over UDP and built-in chat.

## Screenshots

<table>
  <tr>
    <td align="center"><strong>Main</strong></td>
    <td align="center"><strong>Settings</strong></td>
    <td align="center"><strong>Chat</strong></td>
    <td align="center"><strong>Sizes Tool</strong></td>
  </tr>
  <tr>
    <td><a href="Example%20files/Screenshots/main.png"><img src="Example%20files/Screenshots/main.png" alt="Main Window" width="220"></a></td>
    <td><a href="Example%20files/Screenshots/settings.png"><img src="Example%20files/Screenshots/settings.png" alt="Settings Window" width="220"></a></td>
    <td><a href="Example%20files/Screenshots/chat.png"><img src="Example%20files/Screenshots/chat.png" alt="Chat Window" width="220"></a></td>
    <td><a href="Example%20files/Screenshots/sizes.png"><img src="Example%20files/Screenshots/sizes.png" alt="Sizes Tool Window" width="220"></a></td>
  </tr>
</table>

## License

This project is MIT licensed (see `LICENSE` in the repository root).

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
  default.json
  tvnviewer.exe
  requirements.txt
```

Note: `vnc-view/` and `vnc-control/` are intentionally git-ignored for station-specific files. The folders remain in the repo via `.gitkeep`.

## Example Files (Templates)

`Example files/` contains starter templates you can copy and rename:

- `dummy.vnc`
- `dummy.json`
- `udp-port-test.ps1`

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

## UDP Port Test Between Two Computers

Use `Example files/udp-port-test.ps1` to verify UDP `50000` works in both directions.

### Computer B (listener)

```powershell
.\Example files\udp-port-test.ps1 -Mode listen -Port 50000
```

### Computer A (sender)

```powershell
.\Example files\udp-port-test.ps1 -Mode send -Port 50000 -TargetIP <IP_OF_COMPUTER_B> -Message "Test from A"
```

Then swap roles and test back from B to A.

If it fails, allow UDP port `50000` in firewall (Admin PowerShell):

```powershell
New-NetFirewallRule -DisplayName "VNC Station UDP 50000" -Direction Inbound -Protocol UDP -LocalPort 50000 -Action Allow
```

Also make sure `python.exe` is allowed in Windows Defender Firewall.

## How To Use The App (Typical Flow)

1. Place `.vnc` target files in `vnc-view/` and/or `vnc-control/`.
2. Start the app on one or more stations.
3. Tag one or more targets.
4. Open `View` or `Control` sessions (single or tagged batch).
5. Use `Edit View` / `Edit Control` to tune window size and overlay label offset/style.
6. Use chat for coordination across stations.
7. Use `Take over session` if a target is already active on another station and must be force-opened.
8. Use `Validate config`, `Export config`, and `Import config` for maintenance.
9. Use `Sizes` (next to the theme selector) to open the visual layout tool for coarse window/label positioning and managing `vnc-positions` presets.
10. Select per-session `Pos V`/`Pos C`, then click `Setup Positions` to open all assigned sessions at their selected position and persist the selection.
11. Select per-session `Link V`/`Link C` to auto-open a linked session together with View/Control actions.
12. Configure `KS` folder paths in Edit dialogs; at click time the app opens the latest modified file in that folder.
13. Use the setup selector next to `Setup Positions` to load/save full setups (tags + selected positions + selected links).

Startup note:
- On launch, open actions are briefly locked while the app requests current session ownership from other stations.
- This prevents opening a session before ownership data is synchronized.

## Main Window Layout (Current)

- Default startup size: `250x830` (if no saved size exists in app settings)
- Connection list is the resizable/scrollable section
- Bottom control rows:
  1. `Setup Positions` + setup selector + `Save` + `Clear Setup`
  2. `Untag all` + `View all tagged` + `Control all tagged`
  3. `Chat` + `Close all tagged` + `Close all sessions`
  4. `Sizes` + `Validate config` + `Import config` + `Export config`
  5. `Take over session` + `Reconnect on drop`
  6. `Theme` + theme selector + `Font Size` + `Apply`

## Chat Commands

- `/help` show command help
- `/nick NewName` change station name
- `/topic #Topic` set global topic for all online stations
- `/me Action text` send action-style message
- `/away [Message]` set away status (clears when the local station types in chat again)
- `/notify [Message]` send a notification message that plays sound on receiving stations

## Features (And Why They Exist)

- Connection discovery from `vnc-view/` and `vnc-control/`: quick setup by file drop.
- Per-connection View/Control buttons: open the exact mode you need fast.
- Per-connection Close buttons: close one mode without disturbing others.
- Tagging + batch open/close actions: speed up repetitive multi-target operations.
- Per-connection settings editor: tune VNC window and label appearance/position.
- Position presets (`vnc-positions`): reusable window x/y/width/height layouts.
- Per-mode position assignment (`Pos V` / `Pos C`): assign a preset to each view/control session.
- Setup Positions action: opens all sessions with selected positions and persists those position references.
- Unique position assignment guard: one position cannot be selected by more than one session at the same time.
- Per-mode session linking (`Link V` / `Link C`): opens linked sessions together with view/control actions.
- Linked close behavior: closing a session also closes linked sessions recursively (loop-safe).
- Per-session `KS` folder/file buttons (`KS`, `KSV`, `KSC`) with direct open from the main list.
- Setup presets (`vnc-setups/*.json`) store and restore all row tags, selected positions, and selected links.
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
- Session cleanup on app exit: avoid orphaned VNC processes.
- Config validation tool: catch missing/malformed files before operation.
- Config import/export bundles: replicate JSON settings and VNC-files between stations quickly.
- Non-blocking toast notifications: reduce modal interruptions during operation.
- Structured rotating logs in `logs/app.log`: easier troubleshooting and post-incident review.

## Maintenance Tools

- `Validate config` checks for missing runtime files and malformed/mismatched JSON pairs.
- `Export config` writes a zip bundle with `default.json`, all per-connection `.json` and `.vnc` files, and all `vnc-positions/*.json`.
- `Import config` restores `default.json`, `vnc-view/*`, `vnc-control/*`, and `vnc-positions/*` files from a bundle and refreshes the list.
- `Sizes` opens the visual layout tool:
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
- Implement access to the Home Assistant API to fetch alarms from machine sensors.
