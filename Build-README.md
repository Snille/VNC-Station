# Build Specification: Rebuild VNC Station Controller From Scratch

This document is a complete implementation spec for rebuilding the application from zero.

Target platform:
- Windows 10/11
- Python 3.x
- PyQt5 desktop GUI
- TightVNC Viewer (`tvnviewer.exe`)
- `pywin32` for native window handling

## 1. Product Goal

Build a Windows GUI tool that:
- discovers VNC targets from filesystem folders
- launches TightVNC in `view` or `control` mode from `.vnc` files
- overlays per-session labels that follow VNC windows
- coordinates multiple operator stations over UDP to prevent duplicate usage
- provides built-in station chat with command support
- supports forced takeover when required

## 2. Required Runtime Files And Folder Layout

Create this structure at repository root:

```text
.
├─ app/
│  ├─ images/
│  │  ├─ icon.png
│  │  ├─ chat.png
│  │  ├─ gear.png
│  │  ├─ view.png
│  │  ├─ control.png
│  │  ├─ edit.png
│  │  ├─ import.png
│  │  ├─ export.png
│  │  ├─ validate.png
│  │  ├─ save.png
│  │  ├─ untag.png
│  │  ├─ unlock.png
│  │  ├─ applysetup.png
│  │  ├─ spreadsheet.png
│  │  ├─ link.png
│  │  └─ monitor.png
│  ├─ sounds/
│  │  └─ notice.wav
│  ├─ __init__.py
│  ├─ main.py
│  ├─ constants.py
│  ├─ logging_setup.py
│  ├─ logic.py
│  ├─ models.py
│  ├─ config.py
│  ├─ theme.py
│  ├─ network.py
│  ├─ vnc.py
│  ├─ toast.py
│  ├─ tools.py
│  ├─ layout_tool.py
│  ├─ chat_window.py
│  ├─ settings_dialog.py
│  └─ main_window.py
├─ tests/
│  ├─ test_logic.py
│  └─ test_config_merge.py
├─ packaging/
│  ├─ build.ps1
│  └─ cleanup.ps1
├─ vnc-view/
├─ vnc-control/
├─ vnc-positions/
├─ vnc-setups/
├─ logs/
├─ default.json
├─ requirements.txt
└─ tvnviewer.exe
```

Notes:
- `vnc-view/` and `vnc-control/` contain operator-specific `.vnc` and `.json`.
- `vnc-positions/` contains reusable position presets (`*.json`).
- `vnc-setups/` contains saved setup snapshots (`*.json`) for tags + selected positions + selected links.
- These folders must exist even when empty.
- `tvnviewer.exe` must be in project root.

## 3. Dependencies

`requirements.txt` must include at minimum:

```txt
PyQt5>=5.15.9
pywin32>=306
```

## 4. Data Model And Config Schema

### 4.1 `default.json`

Contains defaults and station identity. Numeric values are stored as strings.

Required keys:
- `x`, `y`, `width`, `height`
- `label_text`
- `label_x`, `label_y`
- `label_bg`
- `label_width`, `label_height`
- `label_font`
- `label_font_color`
- `label_border_size`
- `label_border_color`
- `station_name`

### 4.2 Per-connection config files

Location:
- `vnc-view/<ConnectionName>.json`
- `vnc-control/<ConnectionName>.json`

Same schema as above except `station_name` is optional/ignored.

Additional per-connection keys:
- `position_name` (selected position preset name from `vnc-positions`, optional)
- `linked_session` (token format `<ConnectionName>|view|control`, optional)
- `ks` (folder or file path, optional; if folder, open latest modified file at click time)

### 4.4 Setup files

Location:
- `vnc-setups/<SetupName>.json`

Schema:
- `name` (setup name)
- `connections` object keyed by connection name:
  - `tagged` (bool)
  - `position_view` (string)
  - `position_control` (string)
  - `link_view` (string session token or empty)
  - `link_control` (string session token or empty)

### 4.3 Position preset files

Location:
- `vnc-positions/<AnyName>.json`

Required keys:
- `x`, `y`, `width`, `height`, `name`

### 4.5 Connection identity

A connection is identified by filename stem of `.vnc`.

Examples:
- `vnc-view/Linux Mint-01.vnc` -> connection name `Linux Mint-01`
- `vnc-control/Linux Mint-01.vnc` -> same logical connection, different mode file

## 5. Core App Behavior

## 5.1 Startup

On startup:
1. Load defaults from `default.json`.
2. Determine station name from `station_name`.
3. Scan both `vnc-view/` and `vnc-control/` for `.vnc`.
4. Scan `vnc-positions/` for available position presets.
5. Build merged connection list by unique filename stem.
6. Initialize network UDP bus.
7. Initialize session manager and chat window.
8. Apply theme before first render:
   - `Auto` reads Windows theme via registry key:
     - `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`
     - `0 => dark`, `1 => light`
9. Send immediate `session_sync_request` packets to peers and temporarily disable open actions.
10. Re-enable open actions after short sync window (or sooner when session state arrives).

## 5.2 Main Window Layout (must match)

Main window title:
- exactly station name text (no prefix)

Default size:
- width `250`, height `830`

Connection list is scrollable and is the only section that expands on manual resize.

For each connection, render compact two-column card rows including:
- left column:
  - `[tag-checkbox] [Name button]`
  - `Owner: ...` status line
  - position selectors (`V`/`C`)
  - link selectors (`V`/`C`)
- right column:
  - `[KS|KSV|KSC (dynamic)]`
  - `[View|Close] [Control|Close]` (text toggles with local session state)
  - `[Edit View] [Edit Control]`

Connection separators:
- horizontal line between entries

Button colors:
- View: green background
- Control: red background
- Edit buttons: blue background

Name button click:
- toggles tag checkbox

Bottom fixed controls (in this exact order):
1. `[setup selector editable] [Save] [Clear Setup] [Delete]`
2. `[Setup View|Close View] [Setup Control|Close Control]`
3. `[View tagged|Close tagged] [Control tagged|Close tagged]`
4. `[Untag all] [Chat] [Positions & Sizes]`
5. `[Validate config] [Import config] [Export config]`
6. `[Take over session checkbox] [Reconnect on drop checkbox]`
7. `[Theme label] [Theme selector Auto/Light/Dark] [Font Size] [Apply]`

Setup selector behavior:
- loads setup names from `vnc-setups/*.json`
- selecting setup immediately applies saved state
- setup apply resets all rows first, then applies saved values
- save writes current tags + selected positions + selected links
- clear resets tags + selected positions + selected links
- delete removes selected setup JSON
- last selected setup is persisted and restored on next app start

`Positions & Sizes` button behavior:
- opens `layout_tool.py` UI for visual pre-placement of VNC/label settings
- tool provides `Load settings` selector for `connection [view/control]`
- tool provides `Positions` selector for `vnc-positions/*.json`
- if selected target JSON is missing, load defaults from `default.json`
- top `Save` writes to selected target
- position `Load Pos`/`Save Pos` reads/writes `vnc-positions/*.json`
- label coordinates are offsets from VNC window top-left (not absolute screen coordinates)

## 5.3 Settings Dialog

Window title:
- `Edit View - <connection>` or `Edit Control - <connection>`

Default size:
- `290 x 415`

Window icon:
- `app/images/gear.png`

Fields:
- x, y, width, height
- label_text
- label_x, label_y (offset from VNC window top-left)
- label_width, label_height
- label_bg
- label_font
- label_font_color
- label_border_size
- label_border_color
- ks (folder path with browse button)

Save behavior:
- writes JSON to corresponding mode folder
- value types saved as strings

## 5.4 Chat Window

Window title:
- `VNC Chat - <station-name>`

Window icon:
- `app/images/chat.png`

Core controls:
- target dropdown with first item `All stations`
- `Refresh` button (send discovery packet)
- topic label
- read-only plain text log (`QPlainTextEdit`, not rich text)
- multiline input box (`QTextEdit`)

Input key behavior:
- `Enter` = send
- `Shift+Enter` = newline
- `Up/Down` = sent-message history

Away clear rule:
- away is cleared only by local keyboard interaction in input box
- incoming remote messages must not clear away

Chat popup behavior:
- receiving a message auto-shows and focuses chat window
- sets target dropdown to sender if found

Sound behavior:
- play `notice.wav` only for `/notify` messages
- no sound for normal chat

Status messages:
- show non-blocking toast notifications in main window (not modal message boxes)

## 6. Session Launch And Overlay

Use TightVNC documented option-file launch:

```txt
tvnviewer.exe -optionsfile=<path-to-vnc-file>
```

Per session:
1. Validate `tvnviewer.exe` exists.
2. Validate requested `.vnc` exists.
3. Spawn process.
4. Create always-on-top, frameless, click-through label window.
5. Locate VNC native window by process ID.
6. Move/resize VNC window to config `x,y,width,height`.
7. Track overlay offset from VNC window and keep synced on timer.
8. If `position_name` is set and found in `vnc-positions`, it overrides launch `x,y,width,height`.

Open behavior additions:
- if `linked_session` is set, opening a session also opens the linked session.
- `Setup View` opens all view sessions that currently have `Pos V` selected; `Setup Control` does the same for `Pos C`.
- setup buttons toggle to close-only-that-mode behavior for local sessions.
- position uniqueness guard applies to View assignments (Control duplicates allowed).
- selecting a setup applies saved tags + selected positions + selected links immediately.

Closing:
- close overlay
- terminate process (terminate -> short wait -> kill if needed)
- broadcast session close on network
- if `linked_session` is set, closing follows link chain recursively (loop-safe)

App exit:
- close all open sessions and overlays

Reconnect behavior:
- if `Reconnect on drop` is enabled, unexpected VNC process exits auto-relaunch after short delay

## 7. Session Locking Rules (multi-station)

Lock scope is per connection across both modes.

Meaning:
- if any other station has `Connection X` open in view or control,
  this station cannot open `Connection X` in either mode,
  unless `Take over session` checkbox is enabled.
- lock decisions must use station ID identity, not station display name text.

When takeover is used and launch succeeds:
- local chat logs takeover notice
- takeover notice is broadcast to other stations

## 8. UDP Network Protocol

Transport:
- UDP broadcast
- port `50000`

Packet format:
- JSON object UTF-8
- all packets include:
  - `id` (stable station UUID for app run)
  - `station` (current station display name)
  - `ts` timestamp

Ignore own packets by matching `id`.

Station tracking:
- keyed by station `id`, not by name
- maintain `station_id -> (name, ip, last_seen)`
- this ensures nick changes replace old name correctly

Expiry:
- stations older than timeout are excluded from active list

Packet types:
- `hello` presence broadcast
- `session` `{connection, mode, opened}`
- `session_sync_request` (ask peers to immediately rebroadcast currently open sessions)
- `chat` `{to, text, is_action, is_notify}`
- `topic` `{topic}`
- `away` `{is_away, message}`
- `takeover` `{connection, previous_holder}`

Presence behavior:
- chat logs station online/offline notices based on active-station set deltas
- peers respond to `session_sync_request` by rebroadcasting active sessions

## 9. Chat Command Requirements

Required commands:
- `/help`
  - print all command help lines in chat
- `/nick NewName`
  - update local station name
  - update main window title and chat window title
  - persist to `default.json` (`station_name`)
  - broadcast hello with new name
  - all other stations must log rename notice:
    - `<old> is now known as <new>`
- `/topic #Topic`
  - global topic, broadcast to all online stations
  - all stations update topic label and log notice
- `/me Action text`
  - action-style message
- `/away [Message]`
  - set local away marker by appending ` (Away)` to station name
  - broadcast away status to others
  - others log `<station> is away: <message>` (or without message)
  - clears only when local user types in local chat input
  - on clear: remove ` (Away)`, broadcast back status
  - others log `<station> is back`
- `/notify [Message]`
  - send message flagged as notify
  - receiving stations play sound
  - default message text when omitted: `Notification`

Direct vs broadcast:
- target dropdown `All stations` => broadcast
- selected station name => direct only

## 10. Theme Requirements

Theme modes:
- `Auto`, `Light`, `Dark`

`Auto`:
- resolves from Windows setting (see section 5.1)
- must be applied before main window is shown

Theme consistency:
- apply same style to both main window and chat window

## 11. Icons

Required icons:
- main app icon: `app/images/icon.png`
- chat window icon: `app/images/chat.png`
- settings dialog icon: `app/images/gear.png`
- button icons:
  - `view.png`, `control.png`, `edit.png`, `import.png`, `export.png`,
    `validate.png`, `save.png`, `open.png`, `cancel.png`, `delete.png`,
    `untag.png`, `unlock.png`, `applysetup.png`,
    `spreadsheet.png`, `link.png`, `monitor.png`

## 12. Example Files Package

Create `Example files/` with:
- `dummy.vnc` template
- `dummy.json` template
- `TightVNC-Viewer-Help.txt` reference

Create `tests/scripts/udp-port-test.ps1` for network verification.

`udp-port-test.ps1` must support:
- listen mode: wait on UDP port and send ACK
- send mode: send packet to target IP and wait ACK
- help output for firewall rule if blocked

## 13. Error Handling Requirements

Use non-blocking main-window notifications and logs for user-facing failures:
- missing `.vnc` file
- missing `tvnviewer.exe`
- invalid settings read
- no tagged rows for tagged actions

Behavioral fallbacks:
- missing or invalid JSON => fallback to defaults

## 14. Minimal File Responsibilities

- `main.py`: QApplication entrypoint
- `constants.py`: paths/constants/timers/ports
- `logging_setup.py`: rotating logs in `logs/app.log`
- `logic.py`: pure helpers for command parsing and lock checks
- `models.py`: dataclasses for connection/settings/session
- `config.py`: scan/load/save settings and paths
- `theme.py`: Windows dark/light detection
- `network.py`: UDP socket thread + signal bridge
- `vnc.py`: launch/close viewer + overlay tracking
- `toast.py`: transient non-blocking notifications
- `tools.py`: validation and config bundle import/export
- `layout_tool.py`: frameless preview positioning tool for generating JSON settings
- `chat_window.py`: chat UI widgets and input behavior
- `settings_dialog.py`: edit dialog UI and value extraction
- `main_window.py`: orchestrates UI, sessions, chat, network events

## 15. Build And Run Procedure

1. Create venv:

```powershell
python -m venv .venv
```

2. Activate:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install:

```powershell
pip install -r requirements.txt
```

4. Launch:

```powershell
python -m app.main
```

5. Run tests:

```powershell
python -m unittest discover -s tests -v
```

6. Optional packaging:

```powershell
.\packaging\build.ps1
```

Packaging requirement:
- build must use windowed mode (`--windowed`) so end users do not see a console window.
- build output must include runtime folders: `vnc-view`, `vnc-control`, `vnc-positions`.
- build output must include runtime folder: `vnc-setups`.
- build output must copy any existing `vnc-positions/*.json` presets into `dist`.
- build output should preserve any existing `vnc-setups/*.json` presets into `dist`.

## 16. Verification Checklist (must all pass)

- App starts with no exceptions.
- Main title equals station name.
- Main default size is `250x830`.
- Settings window default size is `290x415` with gear icon.
- Settings window icon path is `app/images/gear.png`.
- Chat window uses chat icon.
- Connection list layout and bottom controls match section 5.2.
- `.vnc` launch uses `-optionsfile=...`.
- Overlay follows moved VNC window.
- Overlay uses label offsets relative to VNC window.
- Session lock blocks cross-station duplicate opens unless takeover checked.
- Setup View/Control open and close only the intended mode for selected-position rows.
- Position selectors prevent duplicate assignment for View mode.
- Linked sessions open together with View/Control actions.
- Linked sessions close together with row mode toggle close actions.
- Setup selector loads/saves from `vnc-setups` and applies tags/positions/links.
- KS button naming logic:
  - one visible button => `KS`
  - two visible buttons => `KSV` and `KSC`
- Takeover logs in local and remote chat.
- `/help`, `/nick`, `/topic`, `/me`, `/away`, `/notify` work as specified.
- Notify sound plays only for `/notify`.
- Nick change updates station list and removes old name.
- Topic changes propagate to all online stations.
- Away does not clear from remote activity, only local input.
- UDP test script can validate two-way connectivity on port 50000.
- Export/import bundles include `default.json`, `vnc-view/*`, `vnc-control/*`, `vnc-positions/*.json`, and `vnc-setups/*.json`.
