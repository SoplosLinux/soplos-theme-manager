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
            # HANDLES_OPEN: lets a .sth opened from a file manager route to
            # do_open() below, in this same already-running instance if one
            # exists (single-instance GApplication activation over D-Bus).
            flags=Gio.ApplicationFlags.HANDLES_OPEN
        )
        self.config = None
        self.main_window = None
        self._base_css_provider = None
        self._theme_css_provider = None

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

    def _detect_xfce_dark(self) -> bool:
        """True if the system's active GTK theme looks dark.

        Same heuristic already used elsewhere in the Soplos ecosystem
        (soplos-welcome's core/environment.py, and this app's own
        xfce_theme_service._write_gtk_prefer_dark): XFCE has no single
        'is dark' flag, so the active theme *name* containing 'dark' is
        the established proxy. Good enough for the themes this app itself
        ships and lists (Adwaita-dark, Orchis-*-Dark, etc.).
        """
        try:
            import subprocess
            result = subprocess.run(
                ['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return 'dark' in result.stdout.lower()
        except Exception:
            pass
        return True  # keep the historical default (dark) if detection fails

    def _apply_css(self):
        themes_dir = Path(__file__).parent.parent / "assets" / "themes"

        if self._base_css_provider is None:
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
                    self._base_css_provider = provider
                except Exception as e:
                    logger.error(f"Error loading base.css: {e}")

        # Explicit user choice (once the app exposes one) wins; otherwise
        # follow the system's actual active GTK theme instead of always
        # defaulting to dark regardless of what's really active.
        saved_choice = self.config.get('css_theme') if self.config else None
        if saved_choice in ('dark', 'light'):
            theme_name = saved_choice
        else:
            theme_name = 'dark' if self._detect_xfce_dark() else 'light'

        theme_path = themes_dir / f"{theme_name}.css"
        if not theme_path.exists():
            theme_path = themes_dir / "dark.css"

        if self._theme_css_provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(
                Gdk.Screen.get_default(), self._theme_css_provider
            )
            self._theme_css_provider = None

        if theme_path.exists():
            try:
                provider = Gtk.CssProvider()
                provider.load_from_path(str(theme_path))
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(),
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                self._theme_css_provider = provider
            except Exception as e:
                logger.error(f"Error loading {theme_path.name}: {e}")

    def reapply_css(self):
        """Re-detect the active system theme and swap dark.css/light.css live.

        Called after this app itself changes the active GTK theme (from the
        GTK Themes tab) so the app's own look updates immediately instead of
        only on next launch.
        """
        self._apply_css()

    def on_activate(self, app):
        try:
            self._ensure_window()
            self.main_window.present()
            import threading
            threading.Thread(target=self._seed_base_themes, daemon=True).start()
        except Exception as e:
            logger.critical(f"Error activating application: {e}", exc_info=True)
            self.quit()

    def _ensure_window(self):
        if not self.main_window:
            from ui.main_window import ThemeManagerWindow
            self.main_window = ThemeManagerWindow(
                application=self,
                config=self.config
            )

    def do_open(self, files, n_files, hint):
        """Invoked when a .sth is opened from a file manager (MimeType= in
        the .desktop + Exec=... %f). Routes to the already-running instance
        if there is one, since this app is a single-instance GApplication."""
        try:
            self._ensure_window()
            if n_files > 0:
                path = files[0].get_path()
                if path:
                    self.main_window.open_theme_bundle(path)
            self.main_window.present()
        except Exception as e:
            logger.error(f"Error opening file: {e}", exc_info=True)

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
