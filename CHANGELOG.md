# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
