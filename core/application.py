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
            self._cleanup_legacy()
            self._apply_css()
            from gi.repository import GdkPixbuf
            from utils.constants import ASSETS_DIR
            icon_path = ASSETS_DIR / "icons" / f"{APPLICATION_ID}.png"
            if icon_path.exists():
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(icon_path))
                Gtk.Window.set_default_icon(pixbuf)
            else:
                Gtk.Window.set_default_icon_name(APPLICATION_ID)
        except Exception as e:
            logger.critical(f"Error during startup: {e}", exc_info=True)
            self.quit()

    def _ensure_user_dirs(self):
        from utils.constants import USER_THEMES_DIR
        USER_THEMES_DIR.mkdir(parents=True, exist_ok=True)

    def _cleanup_legacy(self):
        import shutil
        config_dir = Path.home() / ".config" / "soplos-theme-manager"
        marker = config_dir / ".v2_migration_done"
        if marker.exists():
            return

        removals = [
            Path.home() / "xfce-panel-backup",
            Path.home() / ".themes-backup",
            config_dir / "logs",
        ]
        for path in removals:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
                logger.debug(f"Legacy cleanup: removed {path}")

        marker.touch()

    def _seed_base_themes(self):
        import zipfile
        import json
        from utils.constants import USER_THEMES_DIR
        from services.theme_export_service import ThemeExportService

        from utils.constants import ASSETS_DIR
        base_dir = ASSETS_DIR / "base-themes"
        if not base_dir.exists():
            return

        sth_files = list(base_dir.glob("*.sth"))
        if not sth_files:
            return

        export_service = ThemeExportService()
        for sth in sth_files:
            try:
                with zipfile.ZipFile(str(sth), "r") as zf:
                    names = zf.namelist()
                    candidates = [n for n in names if n.endswith("/metadata.json") or n == "metadata.json"]
                    if not candidates:
                        continue
                    with zf.open(candidates[0]) as mf:
                        metadata = json.loads(mf.read().decode("utf-8"))
                theme_name = metadata.get("name")
                if not theme_name or (USER_THEMES_DIR / theme_name).exists():
                    continue
                ok, msg = export_service.import_theme(str(sth), scope="user")
                if ok:
                    logger.info(f"Theme imported: {theme_name} (scope=user)")
                else:
                    logger.warning(f"Failed to import base theme {sth.name}: {msg}")
            except Exception as e:
                logger.warning(f"Error seeding base theme {sth.name}: {e}")

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
            import threading
            threading.Thread(target=self._seed_base_themes, daemon=True).start()
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
