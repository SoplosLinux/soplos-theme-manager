import gi
import os
import sys
from pathlib import Path

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio

from utils.constants import APPLICATION_ID, APPLICATION_NAME, LOCALE_DIR
from utils.logger import logger
from core.i18n_manager import initialize_i18n
from config.settings import get_config


class ThemeManagerApp(Gtk.Application):

    def __init__(self):
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.config = None
        self.main_window = None

        self.connect('startup', self.on_startup)
        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_shutdown)

    def on_startup(self, app):
        logger.info("Starting Soplos Theme Manager")
        try:
            initialize_i18n(str(LOCALE_DIR))
            self._cleanup_pycache()
            self.config = get_config()
            self._ensure_user_dirs()
            self._apply_css()
            Gtk.Window.set_default_icon_name(APPLICATION_ID)
        except Exception as e:
            logger.critical(f"Error during startup: {e}", exc_info=True)
            self.quit()

    def _ensure_user_dirs(self):
        import shutil
        from utils.constants import USER_THEMES_DIR, DEFAULT_THEMES_DIR
        if not USER_THEMES_DIR.exists():
            if DEFAULT_THEMES_DIR.exists():
                shutil.copytree(str(DEFAULT_THEMES_DIR), str(USER_THEMES_DIR))
                logger.info(f"Initialized themes directory from defaults")
            else:
                USER_THEMES_DIR.mkdir(parents=True, exist_ok=True)
        else:
            self._migrate_conf_names(USER_THEMES_DIR)

    def _migrate_conf_names(self, themes_dir: Path):
        """Rename Spanish conf filenames to English for users upgrading from v2.0.0."""
        renames = {
            'tema.conf':   'theme.conf',
            'fondo.conf':  'wallpaper.conf',
            'atajos.conf': 'shortcuts.conf',
        }
        for theme_dir in themes_dir.iterdir():
            if not theme_dir.is_dir():
                continue
            for old, new in renames.items():
                old_path = theme_dir / old
                new_path = theme_dir / new
                if old_path.exists() and not new_path.exists():
                    old_path.rename(new_path)
                    logger.info(f"Migrated {theme_dir.name}/{old} → {new}")
                elif old_path.exists() and new_path.exists():
                    old_path.unlink()
                    logger.info(f"Removed duplicate {theme_dir.name}/{old}")

    def _apply_css(self):
        themes_dir = Path(__file__).parent.parent / "assets" / "themes"

        base_css = themes_dir / "base.css"
        if base_css.exists():
            try:
                provider = Gtk.CssProvider()
                provider.load_from_path(str(base_css))
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(),
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            except Exception as e:
                logger.error(f"Error loading base.css: {e}")

        # En Tyron (XFCE) siempre dark.css por defecto; respetar preferencia guardada
        theme_name = self.config.get('css_theme', 'dark') if self.config else 'dark'
        theme_path = themes_dir / f"{theme_name}.css"
        if not theme_path.exists():
            theme_path = themes_dir / "dark.css"

        if theme_path.exists():
            try:
                provider = Gtk.CssProvider()
                provider.load_from_path(str(theme_path))
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(),
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            except Exception as e:
                logger.error(f"Error loading {theme_path.name}: {e}")

    def on_activate(self, app):
        try:
            if not self.main_window:
                from ui.main_window import ThemeManagerWindow
                self.main_window = ThemeManagerWindow(
                    application=self,
                    config=self.config
                )
            self.main_window.present()
        except Exception as e:
            logger.critical(f"Error activating application: {e}", exc_info=True)
            self.quit()

    def on_shutdown(self, app):
        logger.info("Shutting down Soplos Theme Manager")
        if self.config:
            try:
                self.config.save()
            except Exception as e:
                logger.error(f"Error saving config: {e}")
        self._cleanup_pycache()

    def _cleanup_pycache(self):
        import shutil
        root = Path(__file__).parent.parent
        for dirpath, dirs, _ in os.walk(root):
            if '__pycache__' in dirs:
                try:
                    shutil.rmtree(os.path.join(dirpath, '__pycache__'), ignore_errors=True)
                except Exception:
                    pass


def run_application() -> int:
    app = ThemeManagerApp()
    return app.run(sys.argv)
