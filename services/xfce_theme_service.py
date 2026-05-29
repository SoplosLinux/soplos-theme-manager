import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable

from utils.constants import (
    USER_THEMES_DIR, THEME_REQUIRED_FILES, THEME_REQUIRED_DIRS,
    XFCE_PANEL_DIR, XFCE_XFCONF_DIR,
    XFCE_PANEL_XML, XFCE_DESKTOP_XML,
)
from utils.logger import logger


class XfceThemeService:

    BACKUP_DIR = Path.home() / ".config" / "soplos-theme-manager" / "backup"

    def get_available_themes(self) -> List[Dict]:
        themes = []
        if not USER_THEMES_DIR.exists():
            return themes
        for d in sorted(USER_THEMES_DIR.iterdir()):
            if not d.is_dir():
                continue
            preview = d / "view" / "preview.png"
            thumbnail = d / "view" / "thumbnail.png"
            themes.append({
                'name': d.name,
                'path': str(d),
                'preview_path': str(preview) if preview.exists() else None,
                'thumbnail_path': str(thumbnail) if thumbnail.exists() else None,
                'valid': self._is_valid_theme(d),
            })
        return themes

    def _is_valid_theme(self, theme_dir: Path) -> bool:
        for f in THEME_REQUIRED_FILES:
            if not (theme_dir / f).exists():
                return False
        for d in THEME_REQUIRED_DIRS:
            if not (theme_dir / d).is_dir():
                return False
        return True

    def apply_theme(self, theme_name: str, progress_callback: Optional[Callable] = None) -> bool:
        theme_dir = USER_THEMES_DIR / theme_name
        if not theme_dir.exists():
            logger.error(f"Theme not found: {theme_name}")
            return False

        try:
            if progress_callback:
                progress_callback(0.1)

            self._backup_current_config()
            if progress_callback:
                progress_callback(0.2)

            # Apply xfconf settings (GTK theme, WM, etc.) — xfconfd must be alive
            self._apply_xfconf(theme_dir)
            if progress_callback:
                progress_callback(0.4)

            # Kill panel and xfconfd so we can replace the XML files safely
            subprocess.run(['xfce4-panel', '--quit'], capture_output=True, timeout=5)
            subprocess.run(['pkill', 'xfconfd'], capture_output=True)
            time.sleep(0.5)

            if progress_callback:
                progress_callback(0.55)

            self._apply_panel_xml(theme_dir)
            if progress_callback:
                progress_callback(0.7)

            # Apply desktop XML — this restarts xfconfd and fixes any invalid wallpaper paths
            self._apply_desktop_xml(theme_dir)
            if progress_callback:
                progress_callback(0.85)

            # Apply theme wallpaper now that xfconfd is running again
            self._apply_wallpaper(theme_dir)
            if progress_callback:
                progress_callback(0.95)

            subprocess.run(['xfdesktop', '--reload'], capture_output=True, timeout=5)
            time.sleep(0.3)
            subprocess.Popen(['xfce4-panel'])

            if progress_callback:
                progress_callback(1.0)

            logger.info(f"Theme applied: {theme_name}")
            return True

        except Exception as e:
            logger.error(f"Error applying theme {theme_name}: {e}", exc_info=True)
            return False

    def _backup_current_config(self):
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        files_to_backup = [
            XFCE_PANEL_XML,
            XFCE_DESKTOP_XML,
            XFCE_XFCONF_DIR / "xsettings.xml",
            XFCE_XFCONF_DIR / "xfwm4.xml",
        ]
        for src in files_to_backup:
            if src.exists():
                dest = self.BACKUP_DIR / src.name
                shutil.copy2(str(src), str(dest))

    def _apply_xfconf(self, theme_dir: Path):
        config_files = {
            'theme.conf': 'xsettings',
            'xfwm.conf': 'xfwm4',
            'wallpaper.conf': 'xfce4-desktop',
            'shortcuts.conf': 'xfce4-keyboard-shortcuts',
        }
        for filename, channel in config_files.items():
            conf_file = theme_dir / filename
            if not conf_file.exists():
                continue
            self._apply_conf_file(conf_file, channel)

    def _apply_conf_file(self, conf_file: Path, channel: str):
        try:
            with open(conf_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # xfconf-query -lv output: "/property/path    value"
                    parts = line.split(None, 1)
                    if len(parts) != 2:
                        continue
                    prop, value = parts[0].strip(), parts[1].strip()
                    if not prop.startswith('/'):
                        continue

                    prop_type = self._detect_xfconf_type(value)
                    cmd = ['xfconf-query', '-c', channel, '-p', prop,
                           '--create', '-t', prop_type, '-s', value]
                    subprocess.run(cmd, capture_output=True, timeout=5)
        except Exception as e:
            logger.warning(f"Error applying {conf_file.name}: {e}")

    def _detect_xfconf_type(self, value: str) -> str:
        if value.lower() in ('true', 'false'):
            return 'bool'
        try:
            int(value)
            return 'int'
        except ValueError:
            pass
        try:
            float(value)
            return 'double'
        except ValueError:
            pass
        return 'string'

    def _apply_panel_xml(self, theme_dir: Path):
        panel_xml = theme_dir / "xfce4-panel.xml"
        if not panel_xml.exists():
            return
        try:
            self._backup_panel_plugins()

            dest = XFCE_XFCONF_DIR / "xfce4-panel.xml"
            XFCE_XFCONF_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(panel_xml), str(dest))

            panel_plugins_src = theme_dir / "panel"
            if panel_plugins_src.is_dir():
                XFCE_PANEL_DIR.mkdir(parents=True, exist_ok=True)
                for plugin_file in panel_plugins_src.iterdir():
                    if plugin_file.is_file():
                        shutil.copy2(str(plugin_file), str(XFCE_PANEL_DIR / plugin_file.name))
                    elif plugin_file.is_dir():
                        dest_dir = XFCE_PANEL_DIR / plugin_file.name
                        if dest_dir.exists():
                            shutil.rmtree(str(dest_dir))
                        shutil.copytree(str(plugin_file), str(dest_dir))

        except Exception as e:
            logger.warning(f"Error applying panel XML: {e}")

    def _backup_panel_plugins(self):
        if not XFCE_PANEL_DIR.exists():
            return
        backup_panel = self.BACKUP_DIR / "panel"
        backup_panel.mkdir(parents=True, exist_ok=True)
        for f in XFCE_PANEL_DIR.iterdir():
            if f.is_file():
                shutil.copy2(str(f), str(backup_panel / f.name))
            elif f.is_dir():
                dest_dir = backup_panel / f.name
                if dest_dir.exists():
                    shutil.rmtree(str(dest_dir))
                shutil.copytree(str(f), str(dest_dir))

    def _apply_desktop_xml(self, theme_dir: Path):
        desktop_xml = theme_dir / "xfce4-desktop.xml"
        if not desktop_xml.exists():
            return
        try:
            XFCE_XFCONF_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(desktop_xml), str(XFCE_DESKTOP_XML))
            # Reload xfdesktop so it starts xfconfd and reads the new XML
            subprocess.run(['xfdesktop', '--reload'], capture_output=True, timeout=10)
            time.sleep(0.4)
            # Fix any wallpaper paths from the theme that don't exist on this system
            self._fix_invalid_wallpaper_paths()
        except Exception as e:
            logger.warning(f"Error applying desktop XML: {e}")

    _WALLPAPER_DIRS = [
        Path("/usr/share/wallpapers"),
        Path("/usr/share/backgrounds"),
        Path("/usr/share/xfce4/backdrops"),
    ]
    _WALLPAPER_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

    def _fix_invalid_wallpaper_paths(self):
        """Replace last-image paths that don't exist on this system with a local fallback."""
        try:
            result = subprocess.run(
                ['xfconf-query', '-c', 'xfce4-desktop', '-lv'],
                capture_output=True, text=True, timeout=5
            )
        except Exception as e:
            logger.warning(f"Could not read xfce4-desktop properties: {e}")
            return

        fallback = None
        for line in result.stdout.splitlines():
            if 'last-image' not in line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            prop, current = parts[0].strip(), parts[1].strip()
            if Path(current).exists():
                continue
            # Path is invalid — find a fallback the first time we need one
            if fallback is None:
                for d in self._WALLPAPER_DIRS:
                    if not d.exists():
                        continue
                    for f in sorted(d.rglob('*')):
                        if f.is_file() and f.suffix.lower() in self._WALLPAPER_EXTS:
                            fallback = str(f)
                            break
                    if fallback:
                        break
            if fallback:
                subprocess.run(
                    ['xfconf-query', '-c', 'xfce4-desktop', '-p', prop, '-s', fallback],
                    capture_output=True, timeout=5
                )
                logger.info(f"Fixed invalid wallpaper path: {current!r} → {fallback!r}")

    def _apply_wallpaper(self, theme_dir: Path):
        wallpaper_dir = theme_dir / "wallpaper"
        if not wallpaper_dir.is_dir():
            return
        wallpapers = list(wallpaper_dir.glob("*.png")) + list(wallpaper_dir.glob("*.jpg"))
        if not wallpapers:
            return
        wallpaper_path = str(wallpapers[0])
        try:
            # Aplicar a todos los monitores/escritorios detectados
            result = subprocess.run(
                ['xfconf-query', '-c', 'xfce4-desktop', '-lv'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if 'last-image' in line:
                    prop = line.split()[0]
                    subprocess.run(
                        ['xfconf-query', '-c', 'xfce4-desktop', '-p', prop, '-s', wallpaper_path],
                        capture_output=True, timeout=5
                    )
        except Exception as e:
            logger.warning(f"Error applying wallpaper: {e}")

    def save_current_as_theme(self, theme_name: str, progress_callback: Optional[Callable] = None) -> bool:
        theme_dir = USER_THEMES_DIR / theme_name
        try:
            theme_dir.mkdir(parents=True, exist_ok=True)
            for subdir in THEME_REQUIRED_DIRS:
                (theme_dir / subdir).mkdir(exist_ok=True)

            if progress_callback:
                progress_callback(0.2)

            self._save_xfconf_to_conf(theme_dir)
            if progress_callback:
                progress_callback(0.5)

            self._save_panel_xml(theme_dir)
            self._save_desktop_xml(theme_dir)
            if progress_callback:
                progress_callback(0.8)

            logger.info(f"Theme saved: {theme_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving theme {theme_name}: {e}", exc_info=True)
            return False

    def _save_xfconf_to_conf(self, theme_dir: Path):
        channels_files = {
            'xsettings': 'theme.conf',
            'xfwm4': 'xfwm.conf',
            'xfce4-desktop': 'wallpaper.conf',
            'xfce4-keyboard-shortcuts': 'shortcuts.conf',
        }
        for channel, filename in channels_files.items():
            try:
                result = subprocess.run(
                    ['xfconf-query', '-c', channel, '-lv'],
                    capture_output=True, text=True, timeout=10
                )
                with open(theme_dir / filename, 'w') as f:
                    f.write(result.stdout)
            except Exception as e:
                logger.warning(f"Could not dump xfconf channel {channel}: {e}")

    def _save_panel_xml(self, theme_dir: Path):
        if XFCE_PANEL_XML.exists():
            shutil.copy2(str(XFCE_PANEL_XML), str(theme_dir / "xfce4-panel.xml"))
        panel_dest = theme_dir / "panel"
        panel_dest.mkdir(exist_ok=True)
        if XFCE_PANEL_DIR.exists():
            for f in XFCE_PANEL_DIR.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(panel_dest / f.name))
                elif f.is_dir():
                    dest_dir = panel_dest / f.name
                    if dest_dir.exists():
                        shutil.rmtree(str(dest_dir))
                    shutil.copytree(str(f), str(dest_dir))

    def _save_desktop_xml(self, theme_dir: Path):
        if XFCE_DESKTOP_XML.exists():
            shutil.copy2(str(XFCE_DESKTOP_XML), str(theme_dir / "xfce4-desktop.xml"))

    def save_panel_conf(self, theme_dir: Path):
        try:
            result = subprocess.run(
                ['xfconf-query', '-c', 'xfce4-panel', '-lv'],
                capture_output=True, text=True, timeout=10
            )
            with open(theme_dir / 'panel.conf', 'w') as f:
                f.write(result.stdout)
        except Exception as e:
            logger.warning(f"Could not dump panel config: {e}")

    def remove_theme(self, theme_name: str) -> bool:
        theme_dir = USER_THEMES_DIR / theme_name
        if not theme_dir.exists():
            return False
        try:
            shutil.rmtree(str(theme_dir))
            logger.info(f"Theme removed: {theme_name}")
            return True
        except Exception as e:
            logger.error(f"Error removing theme {theme_name}: {e}")
            return False

    def get_current_wallpaper(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ['xfconf-query', '-c', 'xfce4-desktop', '-lv'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if 'last-image' in line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        return parts[1].strip()
        except Exception:
            pass
        return None

    def set_wallpaper(self, image_path: str) -> bool:
        try:
            result = subprocess.run(
                ['xfconf-query', '-c', 'xfce4-desktop', '-lv'],
                capture_output=True, text=True, timeout=5
            )
            changed = False
            for line in result.stdout.splitlines():
                if 'last-image' in line:
                    prop = line.split()[0]
                    subprocess.run(
                        ['xfconf-query', '-c', 'xfce4-desktop', '-p', prop, '-s', image_path],
                        capture_output=True, timeout=5
                    )
                    changed = True
            if changed:
                subprocess.run(['xfdesktop', '--reload'], capture_output=True, timeout=5)
            return changed
        except Exception as e:
            logger.error(f"Error setting wallpaper: {e}")
            return False
