import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.constants import USER_GTK_DIR, SYSTEM_GTK_DIR
from utils.logger import logger

ARCHIVE_SUFFIXES = ('.tar.gz', '.tgz', '.tar.xz', '.tar.bz2', '.tar', '.zip')

# Themes always present as system fallbacks — never listable as "installed"
_SKIP_THEME_NAMES = {'default', 'default-hdpi', 'default-xhdpi', 'emacs'}


class GtkThemeService:
    """Lists, activates and installs GTK widget themes.

    A directory counts as a GTK theme if it has a gtk-3.0/ or gtk-2.0/
    subdirectory — many real-world theme packages (Nordic, Orchis, Adwaita…)
    ship without an index.theme at all, so that file can't be relied on the
    way it can for icon themes. Directories that are xfwm4-only (window
    decoration) or xfce-notify-only packages are not GTK themes and are
    skipped.
    """

    # ------------------------------------------------------------------ #
    # Listing installed themes                                           #
    # ------------------------------------------------------------------ #

    def list_gtk_themes(self) -> List[Dict]:
        seen: Dict[str, Dict] = {}
        for base in (SYSTEM_GTK_DIR, USER_GTK_DIR):
            if not base.exists():
                continue
            try:
                entries = sorted(base.iterdir())
            except OSError:
                continue
            for d in entries:
                if d.name in seen or d.name.lower() in _SKIP_THEME_NAMES:
                    continue
                if not d.is_dir() or not self._is_gtk_theme_dir(d):
                    continue
                seen[d.name] = {
                    'name':          d.name,
                    'path':          str(d),
                    'display_name':  self._read_theme_name(d) or d.name,
                    'system':        base == SYSTEM_GTK_DIR,
                    'has_gtk3':      (d / 'gtk-3.0').is_dir(),
                    'has_xfwm4':     (d / 'xfwm4').is_dir(),
                }
        return sorted(seen.values(), key=lambda t: t['display_name'].lower())

    @staticmethod
    def _is_gtk_theme_dir(d: Path) -> bool:
        return (d / 'gtk-3.0').is_dir() or (d / 'gtk-2.0').is_dir()

    @staticmethod
    def _read_theme_name(theme_dir: Path) -> Optional[str]:
        index_path = theme_dir / 'index.theme'
        if not index_path.exists():
            return None
        try:
            for line in index_path.read_text(errors='replace').splitlines():
                if line.startswith('Name='):
                    return line[len('Name='):].strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    # Active theme (xfconf / xsettings + xfwm4)                          #
    # ------------------------------------------------------------------ #

    def get_active_gtk_theme(self) -> Optional[str]:
        return self._xfconf_get('xsettings', '/Net/ThemeName')

    def set_active_gtk_theme(self, name: str, also_set_wm_theme: bool = True) -> bool:
        ok = self._xfconf_set('xsettings', '/Net/ThemeName', name)
        if ok and also_set_wm_theme and self._theme_has_xfwm4(name):
            self._xfconf_set('xfwm4', '/general/theme', name)
        return ok

    def _theme_has_xfwm4(self, name: str) -> bool:
        for base in (SYSTEM_GTK_DIR, USER_GTK_DIR):
            if (base / name / 'xfwm4').is_dir():
                return True
        return False

    @staticmethod
    def _xfconf_get(channel: str, prop: str) -> Optional[str]:
        try:
            r = subprocess.run(
                ['xfconf-query', '-c', channel, '-p', prop],
                capture_output=True, text=True, timeout=5,
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    @staticmethod
    def _xfconf_set(channel: str, prop: str, value: str) -> bool:
        try:
            r = subprocess.run(
                ['xfconf-query', '-c', channel, '-p', prop,
                 '--create', '-t', 'string', '-s', value],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
        except Exception as e:
            logger.error(f"Error setting {channel} {prop}: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Package extraction — .tar.gz/.tar.xz/.tar.bz2/.zip                 #
    # ------------------------------------------------------------------ #

    def extract_package(self, archive_path: str) -> Tuple[Optional[Path], List[Dict]]:
        """Extract archive_path to an isolated temp dir and find installable candidates.

        Scans recursively for gtk-3.0/ or gtk-2.0/ subdirectories so wrapper
        folders and several variants bundled in one package are all found.
        Packages that need a build/install script to produce a real theme
        (no ready gtk-3.0/gtk-2.0 anywhere) yield no candidates — we never
        execute scripts from a downloaded package.

        Returns (tmp_dir, candidates); caller must call cleanup(tmp_dir)
        once done, whether or not the install happened.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix='soplos-gtk-pkg-'))
        try:
            self._safe_extract(archive_path, tmp_dir)
        except Exception as e:
            logger.error(f"Error extracting package {archive_path}: {e}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None, []

        candidates = []
        seen_dirs = set()
        for marker in ('gtk-3.0', 'gtk-2.0'):
            for marker_dir in sorted(tmp_dir.rglob(marker)):
                theme_dir = marker_dir.parent
                if theme_dir in seen_dirs:
                    continue
                seen_dirs.add(theme_dir)
                candidates.append({
                    'name':         theme_dir.name,
                    'path':         theme_dir,
                    'kind':         'gtk',
                    'display_name': self._read_theme_name(theme_dir) or theme_dir.name,
                    'has_xfwm4':    (theme_dir / 'xfwm4').is_dir(),
                })
        candidates.sort(key=lambda c: c['display_name'].lower())
        return tmp_dir, candidates

    def _safe_extract(self, archive_path: str, dest: Path):
        if archive_path.lower().endswith('.zip'):
            with zipfile.ZipFile(archive_path) as zf:
                self._check_zip_paths(zf, dest)
                zf.extractall(dest)
        else:
            with tarfile.open(archive_path) as tf:
                self._check_tar_paths(tf, dest)
                tf.extractall(dest, filter='data')

    @staticmethod
    def _check_tar_paths(tf: tarfile.TarFile, dest: Path):
        dest = dest.resolve()
        for member in tf.getmembers():
            target = (dest / member.name).resolve()
            if target != dest and dest not in target.parents:
                raise ValueError(f"Unsafe path in archive: {member.name}")

    @staticmethod
    def _check_zip_paths(zf: zipfile.ZipFile, dest: Path):
        dest = dest.resolve()
        for name in zf.namelist():
            target = (dest / name).resolve()
            if target != dest and dest not in target.parents:
                raise ValueError(f"Unsafe path in archive: {name}")

    def cleanup(self, tmp_dir: Optional[Path]):
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # Installing chosen candidates                                       #
    # ------------------------------------------------------------------ #

    def install_candidates(self, candidates: List[Dict], system: bool) -> Tuple[bool, List[str]]:
        """Copy the chosen candidate directories into place.

        system=True installs to /usr/share/themes via a single pkexec call;
        system=False installs to ~/.themes directly. Existing theme
        directories are never overwritten.

        Returns (ok, skipped_names) where skipped_names lists candidates
        that already existed at the destination and were left untouched.
        """
        dest_base = SYSTEM_GTK_DIR if system else USER_GTK_DIR
        try:
            if system:
                skipped = self._install_system(candidates, dest_base)
            else:
                skipped = self._install_user(candidates, dest_base)
            return True, skipped
        except Exception as e:
            logger.error(f"Error installing GTK theme package: {e}")
            return False, []

    def _install_user(self, candidates: List[Dict], dest_base: Path) -> List[str]:
        dest_base.mkdir(parents=True, exist_ok=True)
        skipped = []
        for c in candidates:
            dest = dest_base / c['name']
            if dest.exists() or (SYSTEM_GTK_DIR / c['name']).exists():
                skipped.append(c['display_name'])
                continue
            shutil.copytree(c['path'], dest)
        return skipped

    def _install_system(self, candidates: List[Dict], dest_base: Path) -> List[str]:
        to_install = [c for c in candidates if not (dest_base / c['name']).exists()]
        skipped = [c['display_name'] for c in candidates if c not in to_install]
        if not to_install:
            return skipped

        lines = ["#!/bin/sh", "set -e"]
        for c in to_install:
            src  = shlex.quote(str(c['path']))
            dest = shlex.quote(str(dest_base / c['name']))
            lines.append(f'cp -r {src} {dest}')
            lines.append(f'chmod -R a+rX {dest}')
        self._run_pkexec_script(lines)
        return skipped

    @staticmethod
    def _run_pkexec_script(lines: list):
        fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='soplos-gtk-')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(script_path, 0o700)
            subprocess.run(['pkexec', 'sh', script_path], check=True, timeout=180)
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass
