import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Set

from utils.constants import (
    USER_THEMES_DIR,
    XFCE_PANEL_DIR, XFCE_PANEL_XML,
    APPLICATION_VERSION, APPLICATION_AUTHOR,
    THEME_BUNDLE_FORMAT,
)
from utils.logger import logger


class XfceThemeService:

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_available_themes(self) -> List[Dict]:
        themes = []
        if not USER_THEMES_DIR.exists():
            return themes
        for d in sorted(USER_THEMES_DIR.iterdir()):
            if not d.is_dir():
                continue
            metadata_file = d / "metadata.json"
            if not metadata_file.exists():
                continue
            preview   = d / "preview" / "preview.png"
            thumbnail = d / "preview" / "thumbnail.png"
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                metadata = {"name": d.name}
            themes.append({
                "name":           d.name,
                "path":           str(d),
                "preview_path":   str(preview)   if preview.exists()   else None,
                "thumbnail_path": str(thumbnail) if thumbnail.exists() else None,
                "valid":          True,
                "metadata":       metadata,
            })
        return themes

    def apply_theme(
        self,
        theme_name: str,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        theme_dir = USER_THEMES_DIR / theme_name
        if not theme_dir.exists():
            logger.error(f"Theme not found: {theme_name}")
            return False

        conf = self._read_theme_conf(theme_dir / "theme.conf")
        if not conf:
            logger.error(f"Invalid theme.conf for: {theme_name}")
            return False

        try:
            if progress_callback:
                progress_callback(0.2)

            # Wallpaper path is stored as absolute path on this system
            wallpaper_path = conf.get("wallpaper") or None

            if progress_callback:
                progress_callback(0.3)

            # Apply panel first — kills and restarts xfconfd
            panel_ok = True
            if conf.get("has_panel_config") == "true":
                panel_ok = self._apply_panel_config(theme_dir)
                if not panel_ok:
                    logger.warning(f"Panel config apply failed for theme: {theme_name}")

            if progress_callback:
                progress_callback(0.7)

            # Apply visual xfconf properties after panel — xfconfd is already up
            self._apply_visual_xfconf(conf, wallpaper_path)

            if progress_callback:
                progress_callback(0.95)

            subprocess.run(["xfdesktop", "--reload"], capture_output=True, timeout=5)

            if progress_callback:
                progress_callback(1.0)

            logger.info(f"Theme applied: {theme_name}")
            return True

        except Exception as e:
            logger.error(f"Error applying theme {theme_name}: {e}", exc_info=True)
            return False

    def save_current_as_theme(
        self,
        theme_name: str,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        theme_dir = USER_THEMES_DIR / theme_name
        try:
            (theme_dir / "preview").mkdir(parents=True, exist_ok=True)

            if progress_callback:
                progress_callback(0.2)

            # Read current visual settings from xfconf
            gtk_theme     = self._xfconf_get("xsettings", "/Net/ThemeName")
            icon_theme    = self._xfconf_get("xsettings", "/Net/IconThemeName")
            cursor_theme  = self._xfconf_get("xsettings", "/Gtk/CursorThemeName")
            gtk_font      = self._xfconf_get("xsettings", "/Gtk/FontName")
            cursor_size   = self._xfconf_get("xsettings", "/Gtk/CursorThemeSize")
            wm_theme      = self._xfconf_get("xfwm4", "/general/theme")
            wm_btn_layout = self._xfconf_get("xfwm4", "/general/button_layout")
            wm_title_font = self._xfconf_get("xfwm4", "/general/title_font")

            conf: Dict[str, str] = {}
            if gtk_theme:     conf["gtk_theme"]       = gtk_theme
            if icon_theme:    conf["icon_theme"]       = icon_theme
            if cursor_theme:  conf["cursor_theme"]     = cursor_theme
            if gtk_font:      conf["gtk_font"]         = gtk_font
            if cursor_size:   conf["cursor_size"]      = cursor_size
            if wm_theme:      conf["wm_theme"]         = wm_theme
            if wm_btn_layout: conf["wm_button_layout"] = wm_btn_layout
            if wm_title_font: conf["wm_title_font"]    = wm_title_font

            # Wallpaper — store absolute path (already on this system)
            wallpaper = self.get_current_wallpaper()
            if wallpaper:
                conf["wallpaper"] = wallpaper

            if progress_callback:
                progress_callback(0.6)

            # Panel configuration
            if self._save_panel_config(theme_dir):
                conf["has_panel_config"] = "true"

            self._write_theme_conf(theme_dir / "theme.conf", conf)

            metadata = {
                "name":        theme_name,
                "version":     "1.0",
                "author":      APPLICATION_AUTHOR,
                "created":     datetime.now().isoformat(),
                "app_version": APPLICATION_VERSION,
                "format":      THEME_BUNDLE_FORMAT,
            }
            with open(theme_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            if progress_callback:
                progress_callback(1.0)

            logger.info(f"Theme saved: {theme_name}")
            return True

        except Exception as e:
            logger.error(f"Error saving theme {theme_name}: {e}", exc_info=True)
            return False

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
                ["xfconf-query", "-c", "xfce4-desktop", "-lv"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "last-image" in line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        path = parts[1].strip()
                        if path and Path(path).exists():
                            return path
        except Exception:
            pass
        return None

    def set_wallpaper(self, image_path: str) -> bool:
        try:
            changed = False
            result = subprocess.run(
                ["xfconf-query", "-c", "xfce4-desktop", "-lv"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "last-image" in line:
                    prop = line.split()[0]
                    subprocess.run(
                        ["xfconf-query", "-c", "xfce4-desktop", "-p", prop, "-s", image_path],
                        capture_output=True, timeout=5
                    )
                    changed = True
            if changed:
                subprocess.run(["xfdesktop", "--reload"], capture_output=True, timeout=5)
            return changed
        except Exception as e:
            logger.error(f"Error setting wallpaper: {e}")
            return False

    # ------------------------------------------------------------------ #
    # xfconf helpers                                                       #
    # ------------------------------------------------------------------ #

    def _xfconf_get(self, channel: str, prop: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["xfconf-query", "-c", channel, "-p", prop],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass
        return None

    def _xfconf_set(self, channel: str, prop: str, value: str, prop_type: str = "string"):
        try:
            subprocess.run(
                ["xfconf-query", "-c", channel, "-p", prop,
                 "--create", "-t", prop_type, "-s", value],
                capture_output=True, timeout=10
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"xfconf-query timed out: {channel} {prop}")

    def _apply_visual_xfconf(self, conf: Dict[str, str], wallpaper_path: Optional[str]):
        # GTK visual
        if conf.get("gtk_theme"):
            self._xfconf_set("xsettings", "/Net/ThemeName", conf["gtk_theme"])
        if conf.get("icon_theme"):
            self._xfconf_set("xsettings", "/Net/IconThemeName", conf["icon_theme"])
        if conf.get("cursor_theme"):
            self._xfconf_set("xsettings", "/Gtk/CursorThemeName", conf["cursor_theme"])
        if conf.get("gtk_font"):
            self._xfconf_set("xsettings", "/Gtk/FontName", conf["gtk_font"])
        if conf.get("cursor_size"):
            self._xfconf_set("xsettings", "/Gtk/CursorThemeSize", conf["cursor_size"], "int")

        # Window manager decorations
        wm_theme = conf.get("wm_theme") or conf.get("gtk_theme")
        if wm_theme:
            self._xfconf_set("xfwm4", "/general/theme", wm_theme)
        if conf.get("wm_button_layout"):
            self._xfconf_set("xfwm4", "/general/button_layout", conf["wm_button_layout"])
        if conf.get("wm_title_font"):
            self._xfconf_set("xfwm4", "/general/title_font", conf["wm_title_font"])

        # Wallpaper — only backdrop properties, nothing else
        if wallpaper_path:
            try:
                result = subprocess.run(
                    ["xfconf-query", "-c", "xfce4-desktop", "-lv"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if "last-image" in line:
                        prop = line.split()[0]
                        subprocess.run(
                            ["xfconf-query", "-c", "xfce4-desktop",
                             "-p", prop, "-s", wallpaper_path],
                            capture_output=True, timeout=5
                        )
            except Exception as e:
                logger.warning(f"Error setting wallpaper via xfconf: {e}")

    # ------------------------------------------------------------------ #
    # theme.conf read / write                                              #
    # ------------------------------------------------------------------ #

    def _read_theme_conf(self, conf_path: Path) -> Dict[str, str]:
        conf: Dict[str, str] = {}
        try:
            with open(conf_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        conf[key.strip()] = value.strip()
        except Exception as e:
            logger.warning(f"Could not read theme.conf at {conf_path}: {e}")
        return conf

    def _write_theme_conf(self, conf_path: Path, conf: Dict[str, str]):
        with open(conf_path, "w", encoding="utf-8") as f:
            for key, value in conf.items():
                f.write(f"{key}={value}\n")

    # ------------------------------------------------------------------ #
    # Panel config save / apply                                            #
    # ------------------------------------------------------------------ #

    def _save_panel_config(self, theme_dir: Path) -> bool:
        """Copy xfce4-panel.xml and only the plugin files referenced by it into the theme bundle."""
        try:
            panel_assets = theme_dir / "assets" / "panel"
            panel_assets.mkdir(parents=True, exist_ok=True)

            if XFCE_PANEL_XML.exists():
                shutil.copy2(str(XFCE_PANEL_XML), str(panel_assets / "xfce4-panel.xml"))

            valid_ids = self._get_plugin_ids_from_xml(XFCE_PANEL_XML)

            plugins_dest = panel_assets / "plugins"
            if plugins_dest.exists():
                shutil.rmtree(str(plugins_dest))
            plugins_dest.mkdir(parents=True, exist_ok=True)

            if XFCE_PANEL_DIR.exists():
                _id_re = re.compile(r'-(\d+)(?:\.\w+)?$')
                for item in XFCE_PANEL_DIR.iterdir():
                    m = _id_re.search(item.name)
                    if not m or m.group(1) not in valid_ids:
                        continue
                    dest = plugins_dest / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(dest))
                    else:
                        shutil.copy2(str(item), str(dest))

            return True
        except Exception as e:
            logger.warning(f"Could not save panel config: {e}")
            return False

    def _apply_panel_config(self, theme_dir: Path) -> bool:
        """Apply panel structure from theme, preserving user plugins and docklike apps."""
        panel_assets = theme_dir / "assets" / "panel"
        theme_xml    = panel_assets / "xfce4-panel.xml"
        if not theme_xml.exists():
            return False

        try:
            # 1. Backup user's current docklike pinned apps.
            # Read from the CURRENT XML (before overwriting it) to get the active plugin ID.
            user_docklike_apps = self._read_docklike_apps(XFCE_PANEL_DIR, XFCE_PANEL_XML)

            # 2. Backup user's current plugin files (preserving their config)
            user_plugins = self._read_user_plugins(XFCE_PANEL_DIR)

            # 3. Kill panel and xfconfd before touching files.
            # xfconfd caches channel values in memory — it must be restarted so it
            # re-reads the new xfce4-panel.xml from disk when the panel comes back up.
            subprocess.run(["xfce4-panel", "--quit"], capture_output=True, timeout=5)
            subprocess.run(["pkill", "-f", "xfconfd"], capture_output=True, timeout=5)
            time.sleep(0.5)

            # 4. Write theme panel XML
            XFCE_PANEL_XML.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(theme_xml), str(XFCE_PANEL_XML))

            # 5. Copy theme plugin files (launchers, etc.) — docklike will be overwritten next
            if (panel_assets / "plugins").exists():
                if XFCE_PANEL_DIR.exists():
                    shutil.rmtree(str(XFCE_PANEL_DIR))
                shutil.copytree(str(panel_assets / "plugins"), str(XFCE_PANEL_DIR))
            else:
                XFCE_PANEL_DIR.mkdir(parents=True, exist_ok=True)

            # 6. Get valid plugin IDs from the theme XML now on disk.
            valid_ids = self._get_plugin_ids_from_xml(XFCE_PANEL_XML)

            # 6a. Remove orphan plugin files copied from the theme — handles themes
            # that were saved when the panel directory was already dirty.
            self._cleanup_orphan_plugins(XFCE_PANEL_DIR, valid_ids)

            # 6b. Restore user plugin configs only for IDs that exist in the new XML.
            self._restore_user_plugins(XFCE_PANEL_DIR, user_plugins, valid_ids)

            # 7. Restore user docklike apps to the docklike plugin from the theme XML
            if user_docklike_apps:
                docklike_id = self._find_docklike_plugin_id(theme_xml)
                if docklike_id:
                    self._write_docklike_apps(
                        XFCE_PANEL_DIR / f"docklike-{docklike_id}.rc",
                        user_docklike_apps,
                    )

            # 8. Restart panel with HOME as cwd so launchers inherit the correct directory
            subprocess.Popen(
                ["xfce4-panel"],
                env={**os.environ, "HOME": str(Path.home())},
                cwd=str(Path.home()),
                start_new_session=True,
            )
            time.sleep(1.5)
            return True

        except Exception as e:
            logger.error(f"Error applying panel config: {e}", exc_info=True)
            return False

    def _find_docklike_plugin_id(self, xml_path: Path) -> Optional[str]:
        """Return the plugin ID (string) of the docklike plugin in an xfce4-panel XML."""
        try:
            tree = ET.parse(str(xml_path))
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

    def _read_docklike_apps(self, panel_dir: Path, xml_path: Optional[Path] = None) -> Optional[str]:
        """Read pinned apps from the docklike rc matching the active plugin ID in xml_path."""
        if not panel_dir.exists():
            return None
        docklike_id = self._find_docklike_plugin_id(xml_path) if xml_path else None
        if docklike_id:
            rc = panel_dir / f"docklike-{docklike_id}.rc"
            try:
                for line in rc.read_text(encoding="utf-8").splitlines():
                    if line.startswith("pinned="):
                        return line[len("pinned="):]
            except Exception:
                pass
            return None
        # Fallback: glob (only used when XML is unavailable)
        for rc in sorted(panel_dir.glob("docklike-*.rc")):
            try:
                for line in rc.read_text(encoding="utf-8").splitlines():
                    if line.startswith("pinned="):
                        return line[len("pinned="):]
            except Exception:
                pass
        return None

    def _write_docklike_apps(self, rc_path: Path, apps: str):
        """Write pinned apps into a docklike-*.rc file."""
        try:
            content = "[user]\n" + f"pinned={apps}\n"
            rc_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not write docklike apps to {rc_path}: {e}")

    def _read_user_plugins(self, panel_dir: Path) -> Dict[str, bytes]:
        """
        Read all non-docklike plugin config files/dirs from the user's panel dir.
        Returns a dict of relative_path -> file_content (files only).
        Directories (launcher-N/) are included recursively.
        """
        result: Dict[str, bytes] = {}
        if not panel_dir.exists():
            return result
        for item in panel_dir.iterdir():
            if item.name.startswith("docklike-"):
                continue
            if item.is_file():
                try:
                    result[item.name] = item.read_bytes()
                except Exception:
                    pass
            elif item.is_dir():
                for subfile in item.rglob("*"):
                    if subfile.is_file():
                        rel = str(subfile.relative_to(panel_dir))
                        try:
                            result[rel] = subfile.read_bytes()
                        except Exception:
                            pass
        return result

    def _restore_user_plugins(self, panel_dir: Path, user_plugins: Dict[str, bytes],
                               valid_ids: Optional[Set[str]] = None):
        """Write user plugin files back into panel_dir, overwriting theme defaults.

        If valid_ids is provided, only files whose plugin ID is in that set are
        restored — this prevents orphan configs from accumulating when switching
        between themes with different panel structures.
        """
        _id_re = re.compile(r'-(\d+)')
        for rel_path, data in user_plugins.items():
            if valid_ids is not None:
                # Extract plugin ID from filename: launcher-5/item.desktop → "5"
                top = rel_path.split('/')[0].split('\\')[0]
                m = _id_re.search(top)
                if not m or m.group(1) not in valid_ids:
                    continue
            dest = panel_dir / rel_path
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            except Exception as e:
                logger.warning(f"Could not restore plugin file {rel_path}: {e}")

    def _get_plugin_ids_from_xml(self, xml_path: Path) -> Set[str]:
        """Return the set of plugin IDs defined in an xfce4-panel.xml."""
        ids: Set[str] = set()
        try:
            tree = ET.parse(str(xml_path))
            root = tree.getroot()
            plugins_prop = root.find(".//property[@name='plugins']")
            if plugins_prop is not None:
                for child in plugins_prop:
                    name = child.get("name", "")
                    if name.startswith("plugin-"):
                        ids.add(name[len("plugin-"):])
        except Exception as e:
            logger.warning(f"Could not parse plugin IDs from {xml_path}: {e}")
        return ids

    def _cleanup_orphan_plugins(self, panel_dir: Path, valid_ids: Set[str]):
        """Remove plugin files/dirs whose ID is not in valid_ids.

        Called after copying theme plugins to disk — removes files that were saved
        into the theme when the panel directory was dirty (accumulated from previous themes).
        """
        _id_re = re.compile(r'-(\d+)(?:\.\w+)?$')
        for item in list(panel_dir.iterdir()):
            m = _id_re.search(item.name)
            if not m:
                continue
            if m.group(1) not in valid_ids:
                try:
                    if item.is_dir():
                        shutil.rmtree(str(item))
                    else:
                        item.unlink()
                except Exception as e:
                    logger.warning(f"Could not remove orphan plugin {item.name}: {e}")

