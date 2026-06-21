# Soplos Theme Manager

[![License: GPL-3.0+](https://img.shields.io/badge/License-GPL--3.0%2B-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-2.0.1--3-green.svg)]()

Desktop theme manager for Soplos Linux Tyron (XFCE). Apply, create, export and import complete desktop themes with a single click.

## 📝 Description

Soplos Theme Manager is the official theme management tool for Soplos Linux Tyron. It provides a complete graphical interface to manage XFCE desktop themes, wallpapers, user avatar and panel dock configuration — all in one application.

## ✨ Features

- 🎨 **Theme Gallery**: Apply, create, export and import full XFCE desktop themes.
- 🖼️ **Wallpaper Browser**: Browse and apply wallpapers from system directories. Near-instant loading — thumbnails decoded in background thread.
- 👤 **User Manager**: Replace Mugshot — set user avatar with crop dialog, edit user data, and manage group membership with checkboxes (applied via polkit).
- 🔧 **Panel**: Full XFCE panel configuration — position, size, icon size, length, rows, auto-hide, dark mode, lock. Add, remove and reorder plugins. Settings button opens each plugin's own configuration dialog via gdb process injection into the plugin wrapper (works for any plugin generically; requires gdb).
- ⚓ **Dock**: Manage Docklike Taskbar pinned apps — add, remove and reorder from an available apps browser.
- 📦 **Theme Bundles**: Export and import portable `.sth` files — each bundle contains the actual GTK theme, icon theme, cursor theme and wallpaper, making themes fully self-contained and shareable across machines.
- 📸 **Screenshot Previews**: Automatic screenshot capture with desktop minimize for theme cards.
- 📊 **Footer Progress Bar**: Soplos-standard progress indicator for all operations.
- 🌍 **Multi-language**: 8 languages (es, en, fr, pt, de, it, ru, ro).
- 🖥️ **Exclusive for XFCE**: Optimized for Soplos Linux Tyron — no multi-DE overhead.

## 🛠️ Requirements

- Python 3.6+
- GTK 3.0 / python3-gi
- XFCE4 (xfce4-panel, xfconf, xfwm4, xfdesktop4)
- scrot + imagemagick (for screenshot previews)
- wmctrl + libnotify-bin (for desktop minimize on screenshot)

## 📥 Installation

Available in the official Soplos Linux repositories:

```bash
sudo apt update
sudo apt install soplos-theme-manager
```

## 🚀 Usage

```bash
soplos-theme-manager
```

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Q` | Quit |
| `F1` | About dialog |

## 📸 Screenshots

### Theme Gallery
![Theme Gallery](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/master/assets/screenshots/screenshot1.png)

### Wallpaper Browser
![Wallpaper Browser](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/master/assets/screenshots/screenshot2.png)

### Avatar Manager
![Avatar Manager](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/master/assets/screenshots/screenshot3.png)

### Panel Configuration
![Panel Configuration](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/master/assets/screenshots/screenshot4.png)

### Dock Manager
![Dock Manager](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/master/assets/screenshots/screenshot5.png)

## 🌐 Supported Languages

| Language | Code |
|----------|------|
| Spanish  | es   |
| English  | en   |
| French   | fr   |
| Portuguese | pt |
| German   | de   |
| Italian  | it   |
| Russian  | ru   |
| Romanian | ro   |

## 📄 License

This project is licensed under [GPL-3.0+](https://www.gnu.org/licenses/gpl-3.0.html).

## 👥 Developer

Developed by Sergi Perich (<info@soploslinux.com>)

## 🔗 Links

- [Website](https://soplos.org/)
- [Report Issues](https://github.com/SoplosLinux/soplos-theme-manager/issues)
- [Help](https://soplos.org/wiki)
- [Donate](https://www.paypal.com/paypalme/isubdes)

## 📦 Versions

### v2.0.1-2 (2026-06-19)
- Themes tab: bundled base themes auto-imported on first launch. Deleted base themes are not reimposed automatically.
- Themes tab: new "Restore" button reimports any missing base themes on demand.
- Startup: one-time cleanup of v1.x legacy artifacts on upgrade (`~/xfce-panel-backup/`, `~/.themes-backup/`, legacy logs).
- Fixed: user-scope install was duplicating system assets (icon themes, GTK themes) to `~/.icons/` and `~/.themes/` even when already present in `/usr/share/`. Assets that exist at system level are now skipped.
- Fixed: `debian/control` had unnecessary polkit-related dependencies — reduced to just `polkit`.
- Fixed: base themes seed and Restore button used wrong asset path (`soplos-base-themes/` instead of `base-themes/`).

### v2.0.1 (2026-06-10)
- Theme bundle format v2: bundles now contain the actual GTK theme, icon theme, cursor theme and wallpaper directories. Fully portable across machines. Format changed from tar.gz to zip.
- Apply theme: now only sets visual xfconf properties (GTK theme, icons, cursor, WM decorations, wallpaper). No longer touches keyboard shortcuts, desktop icon settings, desktop menu visibility, panel directory or any behavioral configuration.
- Install scope dialog: when applying a theme, user chooses between installing assets for the current user (`~/.themes`, `~/.icons`) or globally for all users (`/usr/share/themes`, `/usr/share/icons`) via pkexec.
- Export: file chooser dialog lets the user pick the destination path for the `.sth` file.
- Fixed: shortcuts overwritten on theme apply. Fixed: desktop icons and right-click menu activated on theme apply. Fixed: docklike pinned apps replaced on theme apply. Fixed: wallpaper paths hardcoded from source machine.
- Fixed: xfconfd served cached panel config after apply — xfconfd is now killed after panel quit so it re-reads XML from disk.
- Fixed: orphan panel plugin files from old panels bled into saved themes and applied themes — save and apply now filter by IDs present in `xfce4-panel.xml`, and orphan files are removed after apply.
- Fixed: Firefox and GTK4 apps ignored the saved dark mode setting — `prefer_dark` is now saved in `theme.conf` and restored to `~/.config/gtk-3.0/settings.ini` and `~/.config/gtk-4.0/settings.ini` on apply.
- Fixed: Docklike service matched wrong plugin ID via glob — now parses `xfce4-panel.xml` to find the active docklike plugin ID.
- Fixed: Docklike panel restart used the removed `--restart` flag (XFCE 4.20+) — replaced with quit + Popen.
- UI: Themes gallery wrapped in a dark rounded box (`soplos-content`), matching Plymouth Manager style.
- UI: Theme card selection now shows a thin 1px orange border; fixed GTK FlowBoxChild painting the container orange on selection.
- Fixed: panel structure, dark mode and plugin config never changed on theme apply — `_read_docklike_apps` was called with two arguments but only accepted one, causing a silent `TypeError` that aborted `_apply_panel_config` on every run.
- Fixed: `prefer_dark` not saved when `~/.config/gtk-3.0/settings.ini` was absent — now inferred from GTK theme name as fallback; old themes without the key also handled correctly on apply.
- Fixed: pkexec install script leaked temp dir in `/tmp` on tar failure — `trap 'rm -rf "$TMPEXTR"' EXIT` added for guaranteed cleanup.
- Fixed: export broke icon themes that use symlinks between variant dirs (e.g. Tela-ubuntu-dark → Tela-ubuntu) — export now creates tars with `tar -czf -C base_dir` preserving symlinks in context.
- Fixed: export only bundled the selected icon theme dir, not its parent themes — `_find_icon_dependencies()` reads `Inherits=` in `index.theme` recursively and bundles the full family in `icons.tar`.
- Fixed: install global destroyed existing system assets with `rm -rf` before copying — now extracts tar to temp and moves only dirs that do not already exist at destination.
- Fixed: install global left files owned by the user in `/usr/share/` due to `cp -rp` — tar extraction without preserve flags gives correct root ownership; `chmod -R a+rX` applied after install.
- Bundle format bumped to v3: assets are now stored as tars (`gtk.tar`, `icons.tar`, `cursor.tar`) instead of raw directory trees.

### v2.0.0-2 (2026-06-04)
- Panel tab: move/remove/add plugins now applied live (xfconf + panel restart), no more "Save & Apply" needed for plugin changes.
- Panel tab: new Settings button to open each plugin's own configuration dialog (under investigation for full compatibility).
- Panel tab: fixed plugin module names (filename stem, not X-XFCE-Module value), fixed apply order (write xfconf before restart), fixed new/delete panel teardown sequence.
- Panel tab: threading lock to serialize hot-apply operations; error dialog on apply failure; reload after successful apply.
- Dock tab: fixed icon size when pinning an app (reloaded at correct size from stored path).
- Docklike service: filtered hidden/no-display apps, improved icon resolution fallback, fixed broken entries on exception.
- Theme service: xfce4-panel now launched with cwd=HOME to avoid wrong working directory.
- core/application: theme conf migration now uses copy2+delete instead of rename (handles root-owned files).

### v2.0.0-1 (2026-05-29)
- Panel tab: fixed width not respected, alignment combo added, struts for top/bottom panels.
- Panel tab: fixed delete-all-panels bug (`--force-array`), plugin ID collision on new panel, windows maximizing under top panel.
- Panel tab: fixed async reload clearing user-added plugins, new panel default position calculated from screen resolution.
- Desktop file was empty — app now appears correctly in the XFCE menu.
- Ctrl+Tab / Ctrl+Shift+Tab keyboard shortcuts for tab switching.
- Launcher wrapper simplified to standard Soplos pattern.
- Theme conf filenames renamed from Spanish to English (`theme.conf`, `wallpaper.conf`, `shortcuts.conf`) with automatic migration on startup.
- Metainfo screenshots corrected to Tyron repo URLs. Added Panel and Dock screenshots.

### v2.0.0 (2026-04-24)
- Complete modular rewrite: `core/`, `services/`, `ui/tabs/`, `config/`, `utils/` architecture.
- New tabbed interface: Themes, Wallpapers, User, Panel, Dock — all in one window.
- Wallpaper browser with lazy-loading and symlink deduplication.
- Avatar manager replacing Mugshot: crop dialog, editable user data, group membership via polkit.
- Panel tab: full XFCE panel configuration and plugin management (add, remove, reorder).
- Dock tab: dedicated Docklike pinned apps manager.
- Theme bundles (.sth): export and import as tar.gz with manifest.json.
- Screenshot previews with desktop minimize/restore via wmctrl.
- Footer progress bar following Soplos standard.
- gettext-based i18n with 8 languages.
- App ID migrated to `org.soplos.thememanager`.

### v1.0.7 (2025-07-27)
- Program icon updated to new design.
- Developer updated to Sergi Perich.

### v1.0.6 (2025-05-08)
- Reverted icon and desktop file naming back to `com.soplos.thememanager` convention.

### v1.0.5 (2025-05-07)
- Fixed metainfo App ID: restored `com.soplos.thememanager` (dot notation).

### v1.0.4 (2025-05-07)
- Unified `APP_ID` constant in `main.py`.
- Added `WMCLASS` environment variable support.
- Added `window.realize()` call for proper desktop integration.

### v1.0.3 (2025-05-06)
- Re-injected Soplos Packager App ID block.
- Corrected base directory path to `/usr/share/soplos-theme-manager`.

### v1.0.2 (2025-05-05)
- Renamed all assets to `soplos-theme-manager` naming convention (desktop file, metainfo, icons, WM_CLASS).
- Removed `debug_wmclass.py`.

### v1.0.1 (2025-05-13)
- Desktop file: added `OnlyShowIn=XFCE;` and `X-XfcePluggable=true`.
- Updated categories to XFCE-specific settings.

### v1.0.0 (2025-05-08)
- Initial release.
