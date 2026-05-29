import os
from pathlib import Path

APPLICATION_ID = "org.soplos.thememanager"
APPLICATION_NAME = "Soplos Theme Manager"
APPLICATION_VERSION = "2.0.0"
APPLICATION_AUTHOR = "Sergi Perich"
APPLICATION_EMAIL = "info@soploslinux.com"

PROJECT_ROOT = Path(__file__).parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
DEFAULT_THEMES_DIR = ASSETS_DIR / ".themes-backup"
LOCALE_DIR = PROJECT_ROOT / "locale"

APP_ICON = "org.soplos.thememanager"

# Single themes directory — same as legacy v1
USER_THEMES_DIR = Path.home() / ".themes-backup"

# XFCE config paths
XFCE_CONFIG_DIR = Path.home() / ".config" / "xfce4"
XFCE_PANEL_DIR = XFCE_CONFIG_DIR / "panel"
XFCE_XFCONF_DIR = XFCE_CONFIG_DIR / "xfconf" / "xfce-perchannel-xml"
XFCE_PANEL_XML = XFCE_XFCONF_DIR / "xfce4-panel.xml"
XFCE_DESKTOP_XML = XFCE_XFCONF_DIR / "xfce4-desktop.xml"
XFCE_XSETTINGS_XML = XFCE_XFCONF_DIR / "xsettings.xml"

# Docklike plugin config
DOCKLIKE_CONFIG_DIR = XFCE_PANEL_DIR

# Logging
LOG_DIR = Path.home() / ".cache" / "soplos-theme-manager"
LOG_FILE = LOG_DIR / "theme-manager.log"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'

# UI
WINDOW_DEFAULT_WIDTH = 950
WINDOW_DEFAULT_HEIGHT = 580
CARD_WIDTH = 160
CARD_HEIGHT = 130
PREVIEW_WIDTH = 150
PREVIEW_HEIGHT = 90

# Required theme file structure
THEME_REQUIRED_FILES = [
    "theme.conf", "panel.conf", "xfwm.conf",
    "wallpaper.conf", "shortcuts.conf",
    "xfce4-panel.xml", "xfce4-desktop.xml"
]
THEME_REQUIRED_DIRS = ["panel", "view", "wallpaper"]

# Screenshot sizes
SCREENSHOT_FULL = None
SCREENSHOT_PREVIEW = "640x360"
SCREENSHOT_THUMBNAIL = "150x90"

# Soplos theme bundle extension
THEME_BUNDLE_EXT = ".sth"

# Theme name validation
THEME_NAME_MAX = 50
THEME_NAME_MIN = 3
THEME_NAME_ALLOWED_EXTRA = '-_ '

# xfconf channel mapping per config file
XFCONF_CHANNELS = {
    'theme.conf': 'xsettings',
    'panel.conf': 'xfce4-panel',
    'xfwm.conf': 'xfwm4',
    'wallpaper.conf': 'xfce4-desktop',
    'shortcuts.conf': 'xfce4-keyboard-shortcuts',
}
