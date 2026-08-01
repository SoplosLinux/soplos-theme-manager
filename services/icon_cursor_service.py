import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.constants import USER_ICONS_DIR, SYSTEM_ICONS_DIR
from utils.logger import logger

# Themes that always exist as fallback/base themes — never listable as "installed"
_SKIP_THEME_NAMES = {'hicolor', 'default', 'locolor'}

ARCHIVE_SUFFIXES = ('.tar.gz', '.tgz', '.tar.xz', '.tar.bz2', '.tar', '.zip')


class IconCursorService:
    """Lists, activates and installs icon and cursor themes.

    A directory counts as a theme if it has an index.theme file. It is
    classified as a cursor theme if it also has a cursors/ subdirectory
    (the freedesktop Xcursor convention), otherwise as an icon theme.
    """

    # ------------------------------------------------------------------ #
    # Listing installed themes                                           #
    # ------------------------------------------------------------------ #

    def list_icon_themes(self) -> List[Dict]:
        return self._list_themes(want_cursor=False)

    def list_cursor_themes(self) -> List[Dict]:
        return self._list_themes(want_cursor=True)

    def _list_themes(self, want_cursor: bool) -> List[Dict]:
        seen: Dict[str, Dict] = {}
        for base in (SYSTEM_ICONS_DIR, USER_ICONS_DIR):
            if not base.exists():
                continue
            try:
                entries = sorted(base.iterdir())
            except OSError:
                continue
            for d in entries:
                if d.name in seen or d.name.lower() in _SKIP_THEME_NAMES:
                    continue
                index = d / 'index.theme'
                if not d.is_dir() or not index.exists():
                    continue
                is_cursor = (d / 'cursors').is_dir()
                if is_cursor != want_cursor:
                    continue
                seen[d.name] = {
                    'name':         d.name,
                    'path':         str(d),
                    'display_name': self._read_theme_name(index) or d.name,
                    'system':       base == SYSTEM_ICONS_DIR,
                }
        return sorted(seen.values(), key=lambda t: t['display_name'].lower())

    @staticmethod
    def _read_theme_name(index_path: Path) -> Optional[str]:
        try:
            for line in index_path.read_text(errors='replace').splitlines():
                if line.startswith('Name='):
                    return line[len('Name='):].strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    # Active theme (xfconf / xsettings)                                  #
    # ------------------------------------------------------------------ #

    def get_active_icon_theme(self) -> Optional[str]:
        return self._xfconf_get('xsettings', '/Net/IconThemeName')

    def set_active_icon_theme(self, name: str) -> bool:
        return self._xfconf_set('xsettings', '/Net/IconThemeName', name)

    def get_active_cursor_theme(self) -> Optional[str]:
        return self._xfconf_get('xsettings', '/Gtk/CursorThemeName')

    def set_active_cursor_theme(self, name: str) -> bool:
        return self._xfconf_set('xsettings', '/Gtk/CursorThemeName', name)

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

        Scans recursively for index.theme so wrapper folders (a repo tarball
        with the theme one level deep, several variants bundled together,
        etc.) are all discovered. Directories that need a build/install
        script to become a real theme (no ready index.theme anywhere) yield
        no candidates — we never execute scripts from a downloaded package.

        Returns (tmp_dir, candidates); caller must call cleanup(tmp_dir)
        once done, whether or not the install happened.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix='soplos-icon-pkg-'))
        try:
            self._safe_extract(archive_path, tmp_dir)
        except Exception as e:
            logger.error(f"Error extracting package {archive_path}: {e}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None, []

        candidates = []
        for index_path in sorted(tmp_dir.rglob('index.theme')):
            theme_dir = index_path.parent
            is_cursor = (theme_dir / 'cursors').is_dir()
            candidates.append({
                'name':         theme_dir.name,
                'path':         theme_dir,
                'kind':         'cursor' if is_cursor else 'icon',
                'display_name': self._read_theme_name(index_path) or theme_dir.name,
            })
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

        system=True installs to /usr/share/icons via a single pkexec call
        (available to every user); system=False installs to ~/.icons
        directly. Existing theme directories are never overwritten — this
        mirrors the rule already used for .sth bundle installs.

        Returns (ok, skipped_names) where skipped_names lists candidates
        that already existed at the destination and were left untouched.
        """
        dest_base = SYSTEM_ICONS_DIR if system else USER_ICONS_DIR
        try:
            if system:
                skipped = self._install_system(candidates, dest_base)
            else:
                skipped = self._install_user(candidates, dest_base)
            return True, skipped
        except Exception as e:
            logger.error(f"Error installing icon/cursor package: {e}")
            return False, []

    def _install_user(self, candidates: List[Dict], dest_base: Path) -> List[str]:
        dest_base.mkdir(parents=True, exist_ok=True)
        skipped = []
        for c in candidates:
            dest = dest_base / c['name']
            if dest.exists() or (SYSTEM_ICONS_DIR / c['name']).exists():
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
        fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='soplos-icon-')
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
