import subprocess
from pathlib import Path
from typing import List, Optional, Dict

from utils.constants import DOCKLIKE_CONFIG_DIR, XFCE_PANEL_XML
from utils.logger import logger


class DocklikeService:

    def find_config_file(self) -> Optional[Path]:
        if not DOCKLIKE_CONFIG_DIR.exists():
            return None
        for f in DOCKLIKE_CONFIG_DIR.glob("docklike-*.rc"):
            return f
        if self.is_plugin_active():
            config_file = DOCKLIKE_CONFIG_DIR / "docklike-1.rc"
            DOCKLIKE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config_file.write_text("pinned=\n")
            return config_file
        return None

    def is_plugin_active(self) -> bool:
        if not XFCE_PANEL_XML.exists():
            return False
        try:
            content = XFCE_PANEL_XML.read_text(errors='replace').lower()
            return 'docklike' in content
        except Exception:
            return False

    def read_pinned(self) -> List[Dict]:
        config_file = self.find_config_file()
        if not config_file:
            return []

        pinned = []
        try:
            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith('pinned='):
                        continue
                    value = line[len('pinned='):]
                    for entry in value.split(';'):
                        entry = entry.strip()
                        if not entry:
                            continue
                        info = self._get_app_info(entry)
                        if info:
                            pinned.append(info)
        except Exception as e:
            logger.error(f"Error reading docklike config: {e}")

        return pinned

    def _get_app_info(self, desktop_path: str) -> Optional[Dict]:
        try:
            import gi

            app_info = self._resolve_app_info(desktop_path)
            if not app_info:
                return None

            icon_path = None
            icon = app_info.get_icon()
            if icon:
                try:
                    gi.require_version('Gtk', '3.0')
                    from gi.repository import Gtk
                    icon_theme = Gtk.IconTheme.get_default()
                    icon_info = icon_theme.lookup_by_gicon(icon, 32, 0)
                    if icon_info:
                        icon_path = icon_info.get_filename()
                except Exception:
                    pass

            return {
                'desktop_path': desktop_path,
                'name': app_info.get_display_name() or app_info.get_name() or desktop_path,
                'icon_path': icon_path,
            }
        except Exception:
            return {
                'desktop_path': desktop_path,
                'name': Path(desktop_path).stem,
                'icon_path': None,
            }

    @staticmethod
    def _resolve_app_info(entry: str):
        """Return a DesktopAppInfo for an entry that may be a full path or a bare app ID."""
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio

        p = Path(entry)

        # Full absolute path
        if p.is_absolute() and p.exists():
            return Gio.DesktopAppInfo.new_from_filename(str(p))

        # Bare ID stored by docklike (e.g. "google-chrome", "org.telegram.desktop")
        # GIO requires the .desktop suffix in new()
        for app_id in (entry + '.desktop', entry):
            try:
                ai = Gio.DesktopAppInfo.new(app_id)
                if ai:
                    return ai
            except Exception:
                pass

        # Manual fallback: search standard application directories
        search_dirs = [
            Path('/usr/share/applications'),
            Path.home() / '.local' / 'share' / 'applications',
            Path('/var/lib/flatpak/exports/share/applications'),
            Path.home() / '.local' / 'share' / 'flatpak' / 'exports' / 'share' / 'applications',
        ]
        for d in search_dirs:
            for candidate in (entry + '.desktop', entry):
                fp = d / candidate
                if fp.exists():
                    try:
                        return Gio.DesktopAppInfo.new_from_filename(str(fp))
                    except Exception:
                        pass
        return None

    def write_pinned(self, desktop_paths: List[str]) -> bool:
        config_file = self.find_config_file()
        if not config_file:
            return False
        try:
            pinned_value = ';'.join(desktop_paths)
            lines = []
            written = False
            if config_file.exists():
                with open(config_file, 'r') as f:
                    for line in f:
                        if line.startswith('pinned='):
                            lines.append(f"pinned={pinned_value};\n")
                            written = True
                        else:
                            lines.append(line)
            if not written:
                lines.append(f"pinned={pinned_value};\n")
            with open(config_file, 'w') as f:
                f.writelines(lines)
            logger.info("Docklike config saved")
            return True
        except Exception as e:
            logger.error(f"Error writing docklike config: {e}")
            return False

    def restart_panel(self) -> bool:
        try:
            subprocess.run(['xfce4-panel', '-r'], capture_output=True, timeout=10)
            return True
        except Exception as e:
            logger.error(f"Error restarting panel: {e}")
            return False

    def get_available_apps(self) -> List[Dict]:
        apps = []
        search_dirs = [
            Path('/usr/share/applications'),
            Path.home() / '.local' / 'share' / 'applications',
            Path('/var/lib/flatpak/exports/share/applications'),
            Path.home() / '.local' / 'share' / 'flatpak' / 'exports' / 'share' / 'applications',
        ]
        seen = set()
        for d in search_dirs:
            if not d.exists():
                continue
            for desktop_file in sorted(d.glob('*.desktop')):
                if desktop_file.name in seen:
                    continue
                seen.add(desktop_file.name)
                info = self._get_app_info(str(desktop_file))
                if info:
                    apps.append(info)
        return sorted(apps, key=lambda x: x['name'].lower())
