# Soplos Theme Manager

[![License: GPL-3.0+](https://img.shields.io/badge/License-GPL--3.0%2B-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-2.0.0-green.svg)]()

Desktop theme manager for Soplos Linux Tyron (XFCE). Apply, create, export and import complete desktop themes with a single click.

## 📝 Description

Soplos Theme Manager is the official theme management tool for Soplos Linux Tyron. It provides a complete graphical interface to manage XFCE desktop themes, wallpapers, user avatar and panel dock configuration — all in one application.

## ✨ Features

- 🎨 **Theme Gallery**: Apply, create, export and import full XFCE desktop themes.
- 🖼️ **Wallpaper Browser**: Browse and apply wallpapers from system directories. Near-instant loading — thumbnails decoded in background thread.
- 👤 **User Manager**: Replace Mugshot — set user avatar with crop dialog, edit user data, and manage group membership with checkboxes (applied via polkit).
- 🔧 **Panel**: Full XFCE panel configuration — position, size, icon size, length, rows, auto-hide, dark mode, lock. Add, remove and reorder plugins.
- ⚓ **Dock**: Manage Docklike Taskbar pinned apps — add, remove and reorder from an available apps browser.
- 📦 **Theme Bundles**: Export and import themes as `.sth` files (tar.gz + manifest).
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
![Theme Gallery](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/main/assets/screenshots/screenshot1.png)

### Wallpaper Browser
![Wallpaper Browser](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/main/assets/screenshots/screenshot2.png)

### Avatar Manager
![Avatar Manager](https://raw.githubusercontent.com/SoplosLinux/soplos-theme-manager/main/assets/screenshots/screenshot3.png)

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
