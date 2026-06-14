import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Dict

from utils.constants import DOCKLIKE_CONFIG_DIR, XFCE_PANEL_XML
from utils.logger import logger


class DocklikeService:

    def find_config_file(self) -> Optional[Path]:
        """Return the RC file for the active docklike plugin, resolved from xfce4-panel.xml."""
        plugin_id = self._find_docklike_id_from_xml()
        if plugin_id:
            rc_path = DOCKLIKE_CONFIG_DIR / f"docklike-{plugin_id}.rc"
            if not rc_path.exists():
                DOCKLIKE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                rc_path.write_text("[user]\npinned=\n")
            return rc_path
        # Fallback: glob if XML parsing fails (e.g. panel not yet started)
        if DOCKLIKE_CONFIG_DIR.exists():
            for f in sorted(DOCKLIKE_CONFIG_DIR.glob("docklike-*.rc")):
                return f
        return None

    def _find_docklike_id_from_xml(self) -> Optional[str]:
        """Parse the active xfce4-panel.xml and return the plugin ID of docklike."""
        if not XFCE_PANEL_XML.exists():
            return None
        try:
            tree = ET.parse(str(XFCE_PANEL_XML))
            root = tree.getroot()
            plugins_prop = root.find(".//property[@name='plugins']")
            if plugins_prop is None:
                return None
            for child in plugins_prop:
                name = child.get("name", "")
                value = child.get("value", "")
                if value == "docklike" and name.startswith("plugin-"):
                    return name[len("plugin-"):]
        except Exception as e:
            logger.warning(f"Could not parse panel XML for docklike ID: {e}")
        return None

    def is_plugin_active(self) -> bool:
        return self._find_docklike_id_from_xml() is not None

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
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk

            app_info = self._resolve_app_info(desktop_path)
            if not app_info:
                return None

            # Skip apps not meant to be shown (NoDisplay=true, Hidden=true, etc.)
            if not app_info.should_show():
                return None

            icon_path = None
            icon = app_info.get_icon()
            if icon:
                try:
                    icon_theme = Gtk.IconTheme.get_default()
                    icon_info = icon_theme.lookup_by_gicon(icon, 32, 0)
                    if icon_info:
                        icon_path = icon_info.get_filename()
                except Exception:
                    pass

            # Fallback: resolve by icon name string
            if not icon_path:
                try:
                    icon_name = app_info.get_string('Icon')
                    if icon_name:
                        icon_theme = Gtk.IconTheme.get_default()
                        icon_info = icon_theme.lookup_icon(icon_name, 32, 0)
                        if icon_info:
                            icon_path = icon_info.get_filename()
                except Exception:
                    pass

            name = app_info.get_display_name() or app_info.get_name()
            if not name:
                return None

            return {
                'desktop_path': desktop_path,
                'name': name,
                'icon_path': icon_path,
            }
        except Exception:
            return None

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
        import os
        import time
        try:
            subprocess.run(["xfce4-panel", "--quit"], capture_output=True, timeout=5)
            time.sleep(0.3)
            subprocess.Popen(
                ["xfce4-panel"],
                env={**os.environ, "HOME": str(Path.home())},
                cwd=str(Path.home()),
                start_new_session=True,
            )
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
