# Updates

Project: `VNC Station Controller`  
Latest version in repository: `1.7.3`

## Version Milestones

- `1.7.3` (`release`, 2026-06-30)
  - Added per-session `window_wait_ms` so slow VNC servers can wait longer before the first native viewer-window positioning attempt.
  - Initial VNC window positioning now retries up to three times, waiting the configured session delay between attempts and stopping as soon as the viewer window is found.
  - Added `Window wait` fields to the dedicated `Sessions` window and per-session edit dialog, with `600 ms` as the default.
  - Updated config validation, example JSON, README, build spec, and manuals for the new session timing behavior.

- `1.7.2` (`release`, 2026-03-19)
  - Added `Keep main window on top` to the main Settings window so operators can keep the controller visible above other applications.
  - Reordered related Settings checkboxes so `Follow links on tagged`, `Allow multiple instances on the same station`, and `Keep main window on top` are grouped together.
  - Fixed Settings persistence so station-level toggles, including `keep_main_window_on_top`, are written to `default.local.json` and survive restarts, export/import, and copied station configs.
  - Expanded the default JSON schema and refreshed the README, build spec, and manuals for the current Settings behavior.

- `1.7.1` (`release`, 2026-03-17)
  - Refined the `Sessions` window so each loaded mode only shows its own position and link fields, with clearer labels such as `View Position` and `Link Control`.
  - Added `Default is KS` placeholder guidance to active-button text fields in the session editors.
  - Added owner station names to the main-window in-use indicator tooltip for faster operator context.
  - Updated packaging so build output includes `Updates.md`, leaves all `vnc-*` runtime folders empty, and creates a versioned zip package.
  - Refreshed the manuals, README files, and screenshots for the current UI and packaging behavior.

- `1.7.0` (`release`, 2026-03-16)
  - Moved reusable VNC geometry and label visual settings into `vnc-positions/*.json`, while session JSON keeps `label_text`, links, active-path settings, and HA mappings.
  - Split the old combined layout tool into dedicated `Positions` and `Sessions` windows with their own workflows.
  - Added nested linked-session rows in the main window and updated tagged/control link-follow behavior.
  - Refined setup apply/clear so setup state stays in the live UI and no longer overwrites per-session JSON files.
  - Updated the position editor, session editor, window title, and documentation for the current UI.

- `1.6.0` (`release`, 2026-03-11)
  - Split `Positions & Sessions` into dedicated `Positions` and `Sessions` windows with separate saved geometries.
  - Reworked minimized session rows with bulk minimize/restore, inline action buttons, link/owner icons, and control-mode owner icon support.
  - Added `Follow links on tagged`, expanded Active Folder to support file or folder selection, and refreshed settings/session editor layouts.
- `1.5.3` (`release`, 2026-03-10)
  - Unified button padding/font styling across the app and aligned session-row action columns.
  - Removed the extra divider above the setup area in the main window.
  - Active Folder button toasts now show the full resolved opened path.
  - `Positions & Sessions` now shrinks back to a tighter size when switching from `Session` mode to `Position` mode.
- `1.5.2` (`release`, 2026-03-10)
  - Added global `Use button icons` toggle in Settings and refreshed utility-window button styling.
  - Updated the Settings and `Positions & Sessions` manuals/screenshots for the current UI.
  - Refined HA sensor search with `Enter` submit and wildcard matching examples such as `*m18*`.
- `1.5.1` (`release`, 2026-03-10)
  - Refined window naming, VNC sizing alignment, README screenshots, and HA sensor search behavior.
- `1.5.0` (`release`, 2026-03-09)
  - Reworked the lower main-window setup/session controls around a left-side setup list and right-side action panel.
  - Added draggable setup ordering, setup-name entry, and updated session-sharing/reconnect settings placement.
- `1.4.1` (`release`, 2026-03-08)
  - Refreshed the open Settings window immediately after importing a config bundle.
- `1.4.0` (`release`, 2026-03-08)
  - Hardened cross-station session/network handling and import safety.
  - Added safer malformed-JSON fallback warnings with logging and non-blocking toasts.
  - Reduced repeated config/position disk reads while keeping HA indicator refresh cadence unchanged.
  - Improved setup-open failure feedback when sessions are already held on another station.
  - Formatted owner age display as elapsed `s`, `m:ss`, `h:mm:ss`, or `d:hh:mm:ss`.
- `1.3.4` (`c7476d4`, 2026-03-08)
  - Configurable UDP port in settings and runtime network binding.
  - Added `Close all open View and Control Sessions` action in main window.
  - Added `Allow multiple instances on the same station` setting and startup single-instance enforcement when disabled.
  - Split manuals by role (`user`, `advanced`, `admin`) and refreshed documentation assets.
- `1.3.3` (`99eaec7`, 2026-03-08)
  - Integrated full manual screenshot set and documentation update pass.
- `1.3.2` (`0bfb61a`, 2026-03-07)
  - Home Assistant sensor UX improvements and settings/maintenance documentation updates.
- `1.0.0` (`25e63af`, 2026-03-04)
  - Initial release baseline.

## Full Commit History

| Date | Commit | Message |
|---|---|---|
| 2026-03-08 | `a135aba` | Updated admin guide and renewed some pictures. |
| 2026-03-08 | `c66da66` | docs: place figure captions below images in all guides |
| 2026-03-08 | `c7476d4` | feat: add configurable networking/session controls and split role-based manuals |
| 2026-03-08 | `99eaec7` | Bump to 1.3.3 and integrate full manual screenshot set |
| 2026-03-07 | `3d4077e` | Add CI check for README links |
| 2026-03-07 | `8cd03f8` | Fix README screenshot links for anonymous access |
| 2026-03-07 | `74c2086` | Removed internal HA link. |
| 2026-03-07 | `0bfb61a` | Release 1.3.2: HA sensor UX, docs, and settings/maintenance updates |
| 2026-03-07 | `9e3509a` | Added Home Assistant support. |
| 2026-03-06 | `dc07e29` | Fixed some layouts and icons, moved the udp test-script. |
| 2026-03-06 | `49b2779` | Adding new features and functions. |
| 2026-03-06 | `43e9ae5` | Removed user files |
| 2026-03-06 | `541ec97` | Added Setup feature. |
| 2026-03-05 | `7e735c9` | Change the laout of the main window and settings dialog, and update the icons used in the application. |
| 2026-03-05 | `8b098ae` | Folder selector |
| 2026-03-05 | `588a9c6` | Added possitioning and more. |
| 2026-03-04 | `4559d99` | Updated Readme added som colors. |
| 2026-03-04 | `0e03c55` | Updated the Readme with new screenshots. |
| 2026-03-04 | `25e63af` | Release v1.0.0 |

## Notes

- This file is generated from repository commit history and maintained manually.
- For source-level details, inspect each commit with `git show <hash>`.
