import os
from pathlib import Path

APPLICATION_ID = "org.soplos.thememanager"
APPLICATION_NAME = "Soplos Theme Manager"
APPLICATION_VERSION = "2.0.1"
APPLICATION_AUTHOR = "Sergi Perich"
APPLICATION_EMAIL = "info@soploslinux.com"

PROJECT_ROOT = Path(__file__).parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
LOCALE_DIR = PROJECT_ROOT / "locale"

APP_ICON = "org.soplos.thememanager"

# Theme store on disk (themes live here unpacked, ready to browse)
USER_THEMES_DIR = Path.home() / ".config" / "soplos-theme-manager" / "themes"

# Default (bundled) themes copied on first run
DEFAULT_THEMES_DIR = ASSETS_DIR / ".themes-backup"

# XFCE config paths
XFCE_CONFIG_DIR    = Path.home() / ".config" / "xfce4"
XFCE_PANEL_DIR     = XFCE_CONFIG_DIR / "panel"
XFCE_XFCONF_DIR    = XFCE_CONFIG_DIR / "xfconf" / "xfce-perchannel-xml"
XFCE_PANEL_XML     = XFCE_XFCONF_DIR / "xfce4-panel.xml"
XFCE_DESKTOP_XML   = XFCE_XFCONF_DIR / "xfce4-desktop.xml"
XFCE_XSETTINGS_XML = XFCE_XFCONF_DIR / "xsettings.xml"

# User-level asset install destinations (no root needed)
USER_GTK_DIR        = Path.home() / ".themes"
USER_ICONS_DIR      = Path.home() / ".icons"
USER_WALLPAPERS_DIR = Path.home() / ".local" / "share" / "backgrounds" / "soplos-themes"

# System-level asset install destinations (requires pkexec)
SYSTEM_GTK_DIR        = Path("/usr/share/themes")
SYSTEM_ICONS_DIR      = Path("/usr/share/icons")
SYSTEM_WALLPAPERS_DIR = Path("/usr/share/backgrounds/soplos-themes")

# Search order when locating installed theme assets
SYSTEM_GTK_SEARCH   = [Path.home() / ".themes",
                        Path("/usr/share/themes"),
                        Path("/usr/local/share/themes")]
SYSTEM_ICONS_SEARCH = [Path.home() / ".icons",
                        Path("/usr/share/icons"),
                        Path("/usr/local/share/icons")]

# Logging
LOG_DIR    = Path.home() / ".cache" / "soplos-theme-manager"
LOG_FILE   = LOG_DIR / "theme-manager.log"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL  = 'INFO'

# UI
WINDOW_DEFAULT_WIDTH  = 950
WINDOW_DEFAULT_HEIGHT = 580
CARD_WIDTH    = 160
CARD_HEIGHT   = 130
PREVIEW_WIDTH  = 150
PREVIEW_HEIGHT = 90

# New theme bundle format v2
THEME_BUNDLE_EXT     = ".sth"
THEME_BUNDLE_FORMAT  = "soplos-theme-bundle-v3"
THEME_REQUIRED_FILES = ["metadata.json", "theme.conf"]
THEME_REQUIRED_DIRS  = ["preview"]

# Screenshot sizes
SCREENSHOT_FULL      = None
SCREENSHOT_PREVIEW   = "640x360"
SCREENSHOT_THUMBNAIL = "150x90"

# Theme name validation
THEME_NAME_MAX           = 50
THEME_NAME_MIN           = 3
THEME_NAME_ALLOWED_EXTRA = '-_ '

# Docklike plugin config (used by panel_tab)
DOCKLIKE_CONFIG_DIR = XFCE_PANEL_DIR
