# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.1] - 2026-06-10

### ✨ Added
- **Theme scope selection**: when applying a theme, a dialog now asks whether to install assets for the current user (`~/.themes`, `~/.icons`, `~/.local/share/backgrounds`) or globally for all users (`/usr/share/themes`, `/usr/share/icons`, `/usr/share/backgrounds`). Global install uses `pkexec` for privilege elevation without running the application as root.
- **Export: file chooser dialog**: exporting a theme now opens a `FileChooserDialog` so the user can pick the destination path. Useful for sharing `.sth` files.

### 🔄 Changed
- **Theme bundle format v2** (breaking — old `.sth` files are not compatible): themes now bundle the actual asset directories (GTK theme, icon theme, cursor theme, wallpaper file) instead of xfconf property dumps. The bundle is a `.zip` archive instead of `.tar.gz`. Installed themes are stored unpacked under `~/.config/soplos-theme-manager/themes/` with a `metadata.json` + `theme.conf` + `assets/` + `preview/` structure.
- **Apply theme — visual-only xfconf changes**: `apply_theme` now sets only visual xfconf properties: GTK theme name, icon theme name, cursor theme, window manager theme, wallpaper path per monitor. It no longer touches keyboard shortcuts (`xfce4-keyboard-shortcuts`), desktop icon visibility, desktop right-click menu settings, or any other behavioral property.
- **Apply theme — no XML file copying**: `xfce4-desktop.xml` and `xfce4-panel.xml` are no longer overwritten during theme application. Panel layout and desktop behavior remain fully under user control.
- **Apply theme — no panel directory overwrite**: the `~/.config/xfce4/panel/` directory is no longer touched during theme application. Docklike pinned apps and all other plugin configurations are preserved.
- **Theme store location**: user themes moved from `~/.themes-backup/` to `~/.config/soplos-theme-manager/themes/`.
- **Preview directory**: renamed from `view/` to `preview/` inside each theme directory.
- **`core/application` — startup cleanup**: removed old `_migrate_conf_names` migration (Spanish→English conf filenames). `_ensure_user_dirs` now only creates the themes directory.

### 🐛 Fixed
- **Apply theme — keyboard shortcuts overwritten**: `shortcuts.conf` was being applied to `xfce4-keyboard-shortcuts`, replacing the user's Ctrl+Alt+T terminal shortcut (and all others) with whatever the theme creator had set.
- **Apply theme — desktop icons activated**: `wallpaper.conf` contained `/desktop-icons/` and `/desktop-menu/` xfconf properties mixed in with wallpaper settings. These were applied unconditionally, activating filesystem/removable icons and the desktop application menu even when the user had them disabled.
- **Apply theme — docklike pinned apps replaced**: copying the theme's `panel/` directory overwrote `docklike-*.rc`, replacing the user's pinned application list with the theme's default apps.
- **Apply theme — wallpaper paths hardcoded from source machine**: the old `wallpaper.conf` stored absolute paths from the machine where the theme was created (e.g. `/home/soplos/.themes-backup/Classic_White/wallpaper/006.jpg`), causing broken wallpapers on any other machine.
- **Apply theme — xfconfd cache ignores written XML**: xfconfd keeps panel configuration in memory; after writing `xfce4-panel.xml` the daemon was restarting from its cached copy instead of the new file. Fixed by killing xfconfd after `xfce4-panel --quit` so the daemon re-reads from disk on the next launch.
- **Apply theme — orphan panel plugin files from previous sessions**: panel files from prior theme saves (e.g. `docklike-26.rc`, `launcher-17/`) accumulated in `~/.config/xfce4/panel/` and bled into themes that had never used those IDs. `_apply_panel_config()` now calls `_cleanup_orphan_plugins()` after writing the theme's panel dir to remove any file whose numeric ID is not present in the current `xfce4-panel.xml`.
- **Save theme — orphan panel plugin files included in bundle**: `save_current_as_theme()` was copying the entire `~/.config/xfce4/panel/` directory, including orphan files from panels that no longer exist. Now reads valid plugin IDs from `xfce4-panel.xml` and only saves files whose ID appears there.
- **Apply/save theme — Firefox and GTK4 apps ignore dark mode**: `gtk-application-prefer-dark-theme` was not being saved or restored. `save_current_as_theme()` now reads the value from `~/.config/gtk-3.0/settings.ini` and stores it in `theme.conf` as `prefer_dark`. `_apply_visual_xfconf()` writes it back to both `~/.config/gtk-3.0/settings.ini` and `~/.config/gtk-4.0/settings.ini`.
- **Docklike service — config file matched wrong plugin ID**: `find_config_file()` used a glob (`docklike-*.rc`) that could return orphan `.rc` files from panels that had been deleted, pointing the dock tab at the wrong plugin. Now parses `xfce4-panel.xml` directly to find the ID assigned to the `docklike` plugin entry.
- **Docklike service — panel restart used removed flag**: `restart_panel()` called `xfce4-panel --restart`, a flag removed in XFCE 4.20. Replaced with `xfce4-panel --quit` + `Popen(['xfce4-panel'])` matching the pattern used elsewhere.

### 💄 UI
- **Themes gallery — boxed dark content area**: the theme card grid is now wrapped in a dark rounded box (`soplos-content` class on the `ScrolledWindow`), matching the Plymouth Manager visual style and separating the gallery from the window chrome.
- **Themes gallery — selection border**: the selected theme card now shows a thin 1px orange border with no glow effect. Fixed `FlowBoxChild` container being painted solid orange by GTK's default `*:selected` rule via `flowboxchild:selected { background-color: transparent }`.

### 🔍 Themes tab — audit fixes (2026-06-12)
- **Apply theme — panel structure never applied**: `_apply_panel_config()` called `_read_docklike_apps(panel_dir, xml_path)` but the method only accepted one argument. The resulting `TypeError` was swallowed by the outer `try/except`, so the panel layout, dark mode, and plugin configuration were silently left unchanged on every theme apply. Fixed: `_read_docklike_apps` now accepts `xml_path` as an optional second parameter and uses `_find_docklike_plugin_id(xml_path)` to locate the correct `docklike-N.rc`, falling back to a sorted glob only when the XML is unavailable.
- **Apply/save theme — prefer_dark not saved when settings.ini was absent**: `_read_gtk_prefer_dark()` returned `None` if `~/.config/gtk-3.0/settings.ini` did not exist or lacked the `gtk-application-prefer-dark-theme` key. The value was then omitted from `theme.conf`, and `_write_gtk_prefer_dark()` was never called on apply. Fixed: if settings.ini has no value, `prefer_dark` is inferred from whether the GTK theme name contains `"dark"` (case-insensitive). Old themes without the key in `theme.conf` are also handled: on apply the inference runs from the stored `gtk_theme` name.
- **Install global — pkexec script leaked temp dir on tar failure**: `_pkexec_install_tar()` used `set -e` but had no cleanup trap. If `tar -xzf` failed mid-extraction the script aborted, leaving `TMPEXTR` in `/tmp` until reboot. Fixed: `trap 'rm -rf "$TMPEXTR"' EXIT` added immediately after `mktemp -d`.

### 📦 Export / Install (bundle format v3)
- **Export — icon themes with symlinks bundled broken**: icon themes such as Tela use relative symlinks between variant directories (e.g. `Tela-ubuntu-dark/ → ../Tela-ubuntu/`). The old export copied only the selected variant with `cp -r`, leaving symlinks pointing to a missing sibling in the temp dir. Python's zipfile skipped those broken symlinks, producing a nearly empty bundle. On install the good system directory was deleted and replaced with the empty one. Fixed: export now creates a tar with `tar -czf -C base_dir` preserving symlinks in their original context.
- **Export — icon theme family incomplete**: only the selected icon theme dir was exported, not its parent themes. Symlinks in the bundle were then unresolvable on the target machine. Fixed: `_find_icon_dependencies()` reads the `Inherits=` field in `index.theme` recursively (excluding standard themes: hicolor, locolor, gnome, etc.) and bundles the entire family in a single `icons.tar`.
- **Install global — existing system assets destroyed**: `_global_install()` ran `rm -rf` on the destination before copying. An incomplete or empty bundle would destroy a correctly installed system asset. Fixed: each tar is now extracted to a temp dir; each top-level directory is moved to the destination only if it does not already exist there. Existing assets are never touched.
- **Install global — wrong owner on installed files**: `cp -rp` preserved the ownership of the temp dir (user `soplos`) when installing to `/usr/share/`. Files in `/usr/share/themes/` and `/usr/share/icons/` ended up owned by the user instead of root, with group-writable permissions. Fixed: tar extraction without preservation flags gives root ownership and correct permissions by default; `chmod -R a+rX` is applied after each move.
- **Bundle format**: bumped to `soplos-theme-bundle-v3`. Bundles now contain `assets/gtk.tar`, `assets/icons.tar` and `assets/cursor.tar` instead of raw directory trees. Old v2 bundles are rejected on import.

### Research (2026-06-13)
- **Panel tab — Settings button — investigation complete**: Full reverse-engineering of xfce4-panel 4.20 internals (source cloned and studied). Root cause: the only mechanism to trigger a plugin's configure dialog is the internal D-Bus signal `Set{uint32 14, <false>}` (PROVIDER_PROP_TYPE_ACTION_SHOW_CONFIGURE) on `/org/xfce/Panel/Wrapper/<id>`, emitted exclusively by the panel process itself. The wrapper's `GDBusProxy` subscribes with the panel's unique bus name as sender filter — signals from any other process are dropped by the D-Bus daemon before reaching the wrapper callback. No public D-Bus method exists for SHOW_CONFIGURE. `PluginEvent("configure")` via `org.xfce.Panel` maps to `remote_event`, not `show_configure`, and is rejected by plugins. Planned implementation: inject the call via `gdb --batch -p <wrapper_pid>` calling `xfce_panel_plugin_provider_show_configure(gtk_bin_get_child(gtk_window_list_toplevels()->data))` — works for any plugin generically without knowing it in advance. Fallback: ship a small C helper using ptrace directly if gdb is unavailable.

## [2.0.0-2] - 2026-06-04

### ✨ Added
- **Panel tab — hot apply for plugins**: moving up/down, removing, and adding plugins now takes effect immediately via xfconf + panel restart, without needing "Save & Apply". No more placeholder ID=0 — new plugins get a real ID assigned at add time.
- **Panel tab — Settings button**: gear button added to the active plugins list to open a plugin's own configuration dialog. Currently under investigation — xfce4-panel 4.20 removed the `--plugin-event` CLI flag; D-Bus approach (`org.xfce.Panel.PluginEvent`) works for some plugins but not all.
- **Panel tab — error dialog on apply failure**: `_on_apply_done` now shows a warning dialog if any xfconf write fails, instead of silently succeeding.
- **Panel tab — `_panel_restart()` helper**: extracted the `xfce4-panel --restart` + wait-for-PID loop into a shared function, replacing the repeated quit+sleep+Popen pattern across all callers.
- **Panel tab — `_build_module_map()` helper**: single scan of plugin .desktop files, used by both `_read_active_plugins` and `_on_plugin_settings` to avoid repeated disk reads.
- **Panel tab — threading lock**: `self._panel_lock` serializes all xfconf write + panel restart operations to prevent races between concurrent hot-apply threads.

### 🐛 Fixed
- **Panel tab — move up/down not applied live**: swapping rows in the active plugins list now immediately writes the new order to xfconf and restarts the panel.
- **Panel tab — remove plugin not applied live**: removing a plugin from the list now immediately removes it from xfconf (plugin-ids array + plugin entry) and restarts the panel.
- **Panel tab — add plugin not applied live**: adding a plugin now immediately writes it to xfconf with a real unique ID (computed across all panels) and restarts the panel.
- **Panel tab — apply killed panel before writing xfconf**: the old `--quit` before writing allowed xfce4-panel to save its in-memory state on top of our changes. Now writes to xfconf first, then restarts only if plugin IDs changed.
- **Panel tab — new panel: panel list written before plugin config**: xfce4-panel saw an incomplete config when `/panels` was updated before the individual `panel-N/` properties. Fixed by writing all properties first, then `_set_array('/panels', ...)` last.
- **Panel tab — delete panel: wrong teardown order**: plugin xfconf entries are now removed before updating `/panels` and restarting, avoiding orphaned config keys.
- **Panel tab — plugin modules used wrong key**: `_scan_available_plugins` was using the `X-XFCE-Module` value from the .desktop file as the module name, but xfconf stores the `.desktop` filename stem (e.g. `xfce4-clipman-plugin`, not the internal module string). Fixed to use `f.stem`.
- **Panel tab — reload after successful apply**: plugin list is reloaded after a successful "Save & Apply" so any ID=0 placeholders are replaced with the real IDs now in xfconf.
- **Dock tab — added app icon wrong size**: the pixbuf reused from the small "available" list (32px) was shown at 48px in the pinned list, causing blurry icons. Now reloaded at LIST_ICON_SIZE from the stored icon path.
- **Dock tab — apps_store missing icon_path column**: `apps_store` only had 3 columns; `icon_path` was not stored, making it impossible to reload at a different size. Added as column 3.
- **Docklike service — hidden apps shown in available list**: apps with `NoDisplay=true` or `Hidden=true` were included. Now filtered via `app_info.should_show()`.
- **Docklike service — icon resolution fallback**: if `lookup_by_gicon` fails, now falls back to `lookup_icon` by icon name string. Fixes missing icons for apps that store the icon as a plain name in the .desktop file.
- **Docklike service — failed app info returned partial dict**: on exception, a dict with the filename stem as name was returned, polluting the list with non-functional entries. Now returns `None`.
- **Theme service — xfce4-panel launched from wrong directory**: `Popen(['xfce4-panel'])` inherited the process working directory (project root). Fixed by passing `cwd=Path.home()`.
- **core/application — theme conf migration failed on root-owned files**: `Path.rename()` fails with `OSError` across filesystems or on files owned by root. Replaced with `shutil.copy2` + `unlink`, wrapped in `try/except OSError` per file.

## [2.0.0-1] - 2026-05-29

### 🐛 Fixed
- **Panel tab — width not respected**: `length-adjust` was not written back when length was unchanged, causing XFCE to default to 100%. Fixed by preserving the original `length-adjust` value and recalculating when length changes.
- **Panel tab — locale decimal separator**: `xfconf-query` returns `52,083333` on Spanish locale; `float()` raised `ValueError`. Fixed by replacing `,` with `.` before parsing (`si()` helper).
- **Panel tab — plugin ID collision on new panel**: new panel's plugin IDs started from 1, overwriting main panel plugins. Fixed by computing `next_id` across all panels.
- **Panel tab — wrong p values**: position string p values were incorrect (invented). Corrected from confirmed Soplos theme XMLs: `p=6`=top, `p=8`=bottom, `p=10`=left, `p=1`=right.
- **Panel tab — alignment ignored for snapped panels**: switched to `p=0` floating with center coordinates for partial-width panels so XFCE respects position on all hardware. Full-width panels use snapped p values so the WM receives `_NET_WM_STRUT` hints.
- **Panel tab — windows maximizing under top panel**: `enable-struts` property was not being set. Now written as `true` on every apply and new panel creation.
- **Panel tab — async reload cleared user-added plugins**: `_reload_worker` called after new panel creation wiped plugins the user had just added. Fixed by reading settings synchronously in `_on_new_panel_done`.
- **Panel tab — delete panel removed all panels**: `_set_array` wrote single-element arrays as xfconf scalars; xfce4-panel could not read `/panels` as a list. Fixed by adding `--force-array` flag to all `_set_array` calls.
- **Panel tab — length change did not trigger position recalculation**: switching from 100% to partial width (or vice versa) did not update the position string. Fixed by including `length_changed` in the recalculation condition.
- **Desktop file empty**: `debian/org.soplos.thememanager.desktop` was 0 bytes — app did not appear in the XFCE menu and GLib emitted a warning on startup. Rewritten with full `[Desktop Entry]` content.
- **Keyboard shortcuts Ctrl+Tab / Ctrl+Shift+Tab not working**: GTK intercepts these inside child widgets before `AccelGroup` fires. Fixed by connecting `key-press-event` on the main window.
- **Wrapper script oversized**: launcher was an inline Python script duplicating logic already in `main.py`. Simplified to the standard Soplos wrapper pattern (`exec python3 main.py`). `Gdk.set_program_class` moved to `main.py`.

### 🔄 Changed
- **Theme conf filenames**: renamed from Spanish (`tema.conf`, `fondo.conf`, `atajos.conf`) to English (`theme.conf`, `wallpaper.conf`, `shortcuts.conf`). Automatic migration runs on startup to rename existing user theme files and remove duplicates.
- **Metainfo screenshots**: corrected URLs from `soplos-theme-manager/master/assets/` to `tyron/main/media/soplos-theme-manager/screenshots/` (standard Soplos pattern). Added screenshot4 (Panel) and screenshot5 (Dock).
- **Panel tab — alignment combo**: added Left/Center/Right alignment control. Alignment is derived from coordinates on load and applied when building the position string.
- **Panel tab — new panel default position**: replaced hardcoded `p=2` with `_build_position_string('top', 1, 100, 30)` so coordinates are calculated from actual screen resolution.

## [2.0.0] - 2026-04-24

### 🎉 Added
- **Complete modular rewrite**: core/, services/, ui/tabs/, config/, utils/ architecture.
- **Tabbed interface**: Themes, Wallpapers, User, Panel, Dock — all in one window.
- **Wallpaper browser**: Scans system wallpaper directories, deduplicates symlinks, lazy-loads on tab activation.
- **Avatar manager**: Replaces Mugshot. Crop dialog for non-square images, writes to `~/.face` and AccountsService. Editable user data fields (Full Name, Email, Phone, Location).
- **User tab — Groups column**: Third column for group membership management. Shows all groups the user belongs to with checkboxes. Applies changes via `pkexec usermod -G` (standard polkit dialog, no manual password prompt).
- **Panel tab**: Full XFCE panel configuration — position (top/bottom/left/right), size, icon size, length, rows, auto-hide, dark mode, lock. Plugin management: view active plugins in order, move up/down, remove, add from available system plugins (searchable).
- **Dock tab**: Dedicated tab for Docklike pinned apps (separated from Panel). Shows pinned apps with icons, move up/down/remove, add from available apps browser.
- **Theme bundles (.sth)**: Export and import themes as tar.gz archives with manifest.json.
- **Screenshot previews**: `scrot` + `imagemagick` capture with `notify-send` notification, `wmctrl` desktop minimize/restore, and window iconify/deiconify.
- **Footer progress bar**: Soplos-standard `Gtk.Revealer` + `Gtk.ProgressBar` revealed for all operations.
- **Theme apply**: Correct XFCE restart sequence — `xfce4-panel --quit` + `pkill xfconfd` + apply + `xfdesktop --reload` + `Popen(xfce4-panel)`.
- **xfconf parsing**: Fixed parser to read `xfconf-query -lv` format (space-separated) instead of `key=value`.
- **Panel subdirectory support**: `launcher-N/` plugin directories handled with `copytree` on apply, backup and save.
- **Symlink deduplication**: Wallpaper scanner resolves symlinks via `Path.resolve()` to avoid duplicate entries.
- **App ID**: Migrated from `com.soplos.thememanager` to `org.soplos.thememanager`.
- **i18n**: gettext-based internationalization replacing legacy dict strings, 8 languages.
- **CSS**: Updated to Soplos welcome standard (entry, filechooser, treeview, notebook borders, etc.).

### 🔄 Changed
- Theme directory: `~/.themes-backup` (backwards compatible with v1 legacy).
- Default theme CSS: always dark for Soplos Linux Tyron, configurable via `settings.json`.
- Window decorations: SSD (no CSD), `GTK_CSD=0`.
- **Wallpaper browser**: Pixbuf decoding moved entirely to background thread — gallery renders instantly regardless of the number of wallpapers. Reload button removed (load is automatic on tab activation and folder change).
- **User tab**: Renamed from "Avatar" to "User". Apply button moved inside the form column; groups column added alongside.
- **Panel & Dock**: Split into two independent tabs — Panel (settings + plugins) and Dock (Docklike pinned apps).

### 🐛 Fixed
- Startup freeze: wallpapers now lazy-load via GTK `map` signal.
- Wrong startup tab: `set_current_page(0)` called after `show_all()` + `GLib.idle_add` safety net. Removed `show_all()` from Panel and Dock tab constructors (caused GTK Notebook to prefer them over Themes on startup).
- Theme detection: reads `~/.themes-backup` (same as v1) instead of new separate directory.
- Avatar detection: checks `~/.face` → AccountsService icons → `Icon=` field in user file.
- Panel apply error: `[Errno 21] Is a directory` on `launcher-N/` subdirectories.
- Progress bar not visible: moved revealer before `ScrolledWindow` (footer pattern).
- pkexec password prompts on avatar: removed all `pkexec` — `~/.face` is sufficient on XFCE.
- D-Bus AccountsService blocking main thread: split into sync (LibreOffice + GECOS) and async (D-Bus via thread + `GLib.idle_add`) in the User tab.
- xfconf-query timeout on theme apply: xfconf-query now runs before `pkill xfconfd`, not after.
- Docklike pinned app icons not showing: bare app IDs (e.g. `google-chrome`) now resolved via `Gio.DesktopAppInfo.new(id + '.desktop')` with multi-directory fallback.
- Groups not detected: replaced `grp.getgrall()` member lookup with `id -Gn` (reads all NSS sources).

---

## [1.0.7] - 2025-07-27

### 🎨 Changed
- Program icon updated to new design.
- Developer updated to Sergi Perich.

## [1.0.6] - 2025-05-08

### 🔧 Fixed
- Reverted icon and desktop file naming back to `com.soplos.thememanager` convention for consistency.
- Desktop file path restored to `/usr/share/applications/com.soplos.thememanager.desktop`.

## [1.0.5] - 2025-05-07

### 🐛 Fixed
- Metainfo: corrected App ID from `com.soplosthememanager` back to `com.soplos.thememanager` (dot restored).

## [1.0.4] - 2025-05-07

### ✨ Added
- Unified App ID constant (`APP_ID = "com.soplos.thememanager"`) in `main.py`.
- `WMCLASS` environment variable support for consistent window class assignment.
- `window.realize()` call before show for proper window property propagation.

## [1.0.3] - 2025-05-06

### 🔧 Fixed
- Re-injected Soplos Packager App ID initialization block (regression from 1.0.2 cleanup).
- Corrected base directory path back to `/usr/share/soplos-theme-manager`.

## [1.0.2] - 2025-05-05

### 🔄 Changed
- Renamed all assets from `com.soplos.thememanager` to `soplos-theme-manager` naming convention (desktop file, metainfo, icons, WM_CLASS).
- WM_CLASS fixed to static strings `"soplos-theme-manager", "Soplos Theme Manager"`.
- Removed `debug_wmclass.py`.
- Cleaned up Soplos Packager App ID injection block from `main.py`.

## [1.0.1] - 2025-05-13

### 🔄 Changed
- Desktop file: added `OnlyShowIn=XFCE;` and `X-XfcePluggable=true`.
- Updated categories to XFCE-specific (`XFCE;GTK;Settings;DesktopSettings;X-XFCE-SettingsDialog;X-XFCE-PersonalSettings;`).

## [1.0.0] - 2025-05-08

### 🎉 Initial Release
- Graphical interface for managing XFCE desktop themes.
- Create, save and apply desktop themes.
- Compatible with Soplos Linux Tyron.
- Translations for 8 languages.

---

## Types of Changes

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for features to be removed soon
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** in case of vulnerabilities

## Contribute

To report bugs or request features:
- **Issues**: https://github.com/SoplosLinux/soplos-theme-manager/issues
- **Email**: info@soploslinux.com

## Support

- **Documentation**: https://soplos.org/wiki
- **Community**: https://soplos.org/
- **Support**: info@soploslinux.com
