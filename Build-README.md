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
- supports intentional shared sessions when required

## 2. Required Runtime Files And Folder Layout

Create this structure at repository root:

```text
.
├─ app/
│  ├─ images/
│  │  ├─ icon.png
│  │  ├─ alarm.png
│  │  ├─ alarm-blue.gif
│  │  ├─ alarm-red.gif
│  │  ├─ battery.png
│  │  ├─ temp.png
│  │  ├─ chat.png
│  │  ├─ clear.png
│  │  ├─ cancel.png
│  │  ├─ delete.png
│  │  ├─ gear.png
│  │  ├─ ha.png
│  │  ├─ view.png
│  │  ├─ control.png
│  │  ├─ edit.png
│  │  ├─ import.png
│  │  ├─ export.png
│  │  ├─ validate.png
│  │  ├─ save.png
│  │  ├─ open.png
│  │  ├─ reset.png
│  │  ├─ untag.png
│  │  ├─ unlock.png
│  │  ├─ applysetup.png
│  │  ├─ spreadsheet.png
│  │  ├─ link.png
│  │  ├─ link-dark.png
│  │  ├─ link-light.png
│  │  ├─ monitor.png
│  │  ├─ user-dark.png
│  │  ├─ user-light.png
│  │  ├─ user-control.png
│  │  ├─ dooropen.png
│  │  └─ doorclosed.png
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
│  ├─ settings_window.py
│  └─ main_window.py
├─ manual/
│  ├─ user-guide.md
│  ├─ advanced-user-guide.md
│  ├─ admin-guide.md
│  └─ manual-assets/
│     └─ images/
├─ tests/
│  ├─ test_logic.py
│  ├─ test_config_merge.py
│  └─ scripts/
│     └─ udp-port-test.ps1
├─ packaging/
│  ├─ build.ps1
│  └─ cleanup.ps1
├─ Example files/
│  ├─ dummy.vnc
│  ├─ dummy.json
│  └─ TightVNC-Viewer-Help.txt
├─ vnc-view/
├─ vnc-control/
├─ vnc-positions/
├─ vnc-setups/
├─ logs/
├─ default.json
├─ default.local.json (optional, untracked local overrides)
├─ default.local.json.example (template committed to repo)
├─ README.md
├─ Build-README.md
├─ LICENSE.txt
├─ requirements.txt
└─ tvnviewer.exe
```

Notes:
- `vnc-view/` and `vnc-control/` contain operator-specific `.vnc` and `.json`.
- `vnc-positions/` contains reusable position presets (`*.json`).
- `vnc-setups/` contains saved setup snapshots (`*.json`) for selected positions + selected links.
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
- `ha_url`
- `ha_api_key`

`default.local.json` (optional):
- same key schema as `default.json`
- values override `default.json` at runtime
- intended for machine-local secrets such as `ha_api_key`
- file is untracked (ignored by git)
- create it by copying `default.local.json.example`

### 4.2 Per-connection config files

Location:
- `vnc-view/<ConnectionName>.json`
- `vnc-control/<ConnectionName>.json`

Same schema as above except `station_name` is optional/ignored.

Additional per-connection keys:
- `position_name` (selected position preset name from `vnc-positions`, optional)
- `linked_session` (token format `<ConnectionName>|view|control`, optional)
- `ks` (folder or file path, optional; if folder, open latest modified file at click time)
- clicking the row active button shows a toast with the full resolved opened path
- `ha_sensors` (list of selected entity IDs, optional)
- `ha_sensor_icons` (list of mappings, optional):
  - `entity_id`
  - `icon` (single icon for non-binary sensors)
  - `icon_on` (binary true/on icon)
  - `icon_off` (binary false/off icon)
  - `tooltip` (optional template supporting `{name}`, `{state}`, and `{entity_id}`)
  - `bg_state` (`on` or `off`; optional state selector for color rule)
  - `bg_color` (optional color applied when `bg_state` matches)

### 4.4 Setup files

Location:
- `vnc-setups/<SetupName>.json`

Schema:
- `name` (setup name)
- `connections` object keyed by connection name:
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
  - `Owner: ...` status line with elapsed age formatted as `s`, `m:ss`, `h:mm:ss`, or `d:hh:mm:ss`
  - position selectors (`V`/`C`)
  - link selectors (`V`/`C`)
- right column:
  - `[Active button(s) dynamic text]` (`KS` or stacked `KSV` / `KSC`)
  - `[View|Close] [Control|Close]` (text toggles with local session state)
  - `[Edit View] [Edit Control]`

Connection separators:
- horizontal line between entries

Button colors:
- View: green background
- Control: orange background (`#b87400`)
- Edit buttons: blue background
- Utility/setup/chat/save/close buttons: gray background (`#666666`)

Name button click:
- toggles tag checkbox

Bottom fixed controls (in this exact order):
1. lower setup/session area with:
   - left side: `Select setup` label + draggable setup list
   - right side rows:
     - `[Setup View|Close View] [Setup Control|Close Control]`
     - `[View tagged|Close tagged] [Control tagged|Close tagged]`
     - `[Close all sessions] [Untag all]`
     - `[Setup name]`
     - `[Save] [Clear] [Delete]`
     - `[Allow shared sessions checkbox]`
2. bottom row:
   - `[Chat] [Positions] [Sessions] [Settings]`

Setup list behavior:
- loads setup names from `vnc-setups/*.json`
- selecting setup immediately applies saved state
- setup apply resets all rows first, then applies saved values
- save uses `Setup name` and writes the current setup state
- clear resets the current setup-driven state in the UI
- delete removes selected setup JSON
- setup list supports drag-and-drop ordering
- custom setup list order is persisted and restored on next app start
- last selected setup is persisted and restored on next app start

`Positions` button behavior:
- opens `layout_tool.py` in dedicated position mode
- tool provides `Positions` selector for `vnc-positions/*.json`
- position `Load Pos`/`Save Pos` reads/writes `vnc-positions/*.json`
- label coordinates are not edited here

`Sessions` button behavior:
- opens `layout_tool.py` in dedicated session mode
- tool provides `Load settings` selector for `connection [view/control]`
- automatically loads the first available session when the window opens
- if selected target JSON is missing, load defaults from `default.json`
- top `Save` writes to selected target
- label coordinates are offsets from VNC window top-left (not absolute screen coordinates)

## 5.3 Edit Settings Dialog

Window title:
- `Edit View - <connection>` or `Edit Control - <connection>`

Default size:
- `620 x 820` when no saved geometry exists (otherwise restore last geometry)

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
- ks (folder path or file path with browse button and file-mode checkbox)
- HA sensor search + selected sensors list
- HA search supports `Enter` submit and `*` wildcards (for example `*m18*`)
- per-sensor icon mapping:
  - `Icon`
  - `Binary true`
  - `Binary false`
  - `Tooltip` template (`{name}`, `{state}`, `{entity_id}`)
  - `Sensor` row color rule (`on`/`off` + color selector)
  - `Selected Sensors` supports drag-and-drop reordering

Save behavior:
- writes JSON to corresponding mode folder
- preserves runtime fields such as `position_name` and `linked_session`
- persists `ha_sensors` and `ha_sensor_icons`

## 5.4 App Settings Window

Opened from main window `Settings`.

Window title:
- `Settings`

Default size:
- `460 x 760` when no saved geometry exists (otherwise restore last geometry)

Fields:
- theme selector (`Auto`/`Light`/`Dark`)
- font size + apply
- station name
- `Use button icons` checkbox
- `UDP Port`
- `Allow multiple instances on the same station`
- `Reconnect on drop`
- `Follow links on tagged`
- all `default.json` fields
- `Home Assistant URL`
- `HA API Key`
- `Test HA connection` button (`/api/` probe)
- `Validate config` button
- `Import config` button
- `Export config` button
- `Save`

## 5.5 Chat Window

Window title:
- `Chat - <station-name>`

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
- selecting a setup applies its saved state immediately.

Closing:
- close overlay
- terminate process (terminate -> deferred kill if still alive after short grace period)
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
  unless `Allow shared sessions` checkbox is enabled.
- lock decisions must use station ID identity, not station display name text.

When a shared-session override is used and launch succeeds:
- local chat logs the shared-session notice
- the notice is broadcast to other stations

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
  - persist to `default.local.json` (`station_name`)
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
- Settings, `Positions`, and `Sessions` utility buttons use the same gray button styling, except the Settings config maintenance buttons which stay distinct.

## 11. Icons

Required icons:
- main app icon: `app/images/icon.png`
- chat window icon: `app/images/chat.png`
- settings dialog icon: `app/images/gear.png`
- app settings window icon: `app/images/gear.png`
- HA icon: `app/images/ha.png`
- default status icons: `app/images/dooropen.png`, `app/images/doorclosed.png`
- button icons:
  - `view.png`, `control.png`, `edit.png`, `import.png`, `export.png`,
    `validate.png`, `save.png`, `open.png`, `cancel.png`, `delete.png`,
    `untag.png`, `unlock.png`, `applysetup.png`,
    `spreadsheet.png`, `link.png`, `link-dark.png`, `link-light.png`,
    `monitor.png`, `user-dark.png`, `user-light.png`, `user-control.png`

Custom HA sensor status icons (user-provided):
- place files in `app/images/`
- supported formats: `.png` and `.gif`
- use transparent background
- recommended size: `256x256` pixels

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
- build output must include runtime folder: `logs`.
- build output should preserve any existing `vnc-view/*.json|*.vnc` and `vnc-control/*.json|*.vnc`.
- build output must copy any existing `vnc-positions/*.json` presets into `dist`.
- build output should preserve any existing `vnc-setups/*.json` presets into `dist`.

## 16. Verification Checklist (must all pass)

- App starts with no exceptions.
- Main title equals station name.
- Main default size is `250x830` when no saved geometry exists.
- Edit settings dialog default size is `620x820` (when no saved geometry exists) with gear icon.
- App settings window default size is `460x760` when no saved geometry exists.
- Chat window uses chat icon.
- Connection list layout and bottom controls match section 5.2.
- `Settings` opens app settings window.
- `.vnc` launch uses `-optionsfile=...`.
- Overlay follows moved VNC window.
- Overlay uses label offsets relative to VNC window.
- Session lock blocks cross-station duplicate opens unless `Allow shared sessions` is checked.
- Setup View/Control open and close only the intended mode for selected-position rows.
- Position selectors prevent duplicate assignment for View mode.
- Linked sessions open together with View/Control actions.
- Linked sessions close together with row mode toggle close actions.
- Setup list loads/saves from `vnc-setups` and applies saved setup state.
- Active button text logic:
  - one visible button => custom `ks_button_text` (or fallback `KS`)
  - two visible buttons => per-mode custom `ks_button_text` (or fallback `KSV`/`KSC`)
  - when two visible buttons are shown, `KSV` and `KSC` stack vertically in the same action column as `View` and `Control`
- Shared-session overrides log in local and remote chat.
- `/help`, `/nick`, `/topic`, `/me`, `/away`, `/notify` work as specified.
- Notify sound plays only for `/notify`.
- Nick change updates station list and removes old name.
- Topic changes propagate to all online stations.
- Away does not clear from remote activity, only local input.
- HA connection test works with URL + token.
- Edit dialogs can search HA sensors and persist `ha_sensor_icons`.
- Main row indicators can display multiple icons simultaneously.
- GIF indicators animate in main row indicator area.
- UDP test script can validate two-way connectivity on port 50000.
- Export/import bundles include `default.json`, `vnc-view/*`, `vnc-control/*`, `vnc-positions/*.json`, and `vnc-setups/*.json`.
