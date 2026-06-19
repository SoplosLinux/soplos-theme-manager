import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from utils.constants import (
    USER_THEMES_DIR,
    USER_GTK_DIR, USER_ICONS_DIR, USER_WALLPAPERS_DIR,
    SYSTEM_GTK_DIR, SYSTEM_ICONS_DIR, SYSTEM_WALLPAPERS_DIR,
    SYSTEM_GTK_SEARCH, SYSTEM_ICONS_SEARCH,
    THEME_BUNDLE_EXT, THEME_BUNDLE_FORMAT,
)
from utils.logger import logger

_SYSTEM_DIRS = frozenset([
    Path("/usr/share/themes"),
    Path("/usr/share/icons"),
    Path("/usr/local/share/themes"),
    Path("/usr/local/share/icons"),
])

_STANDARD_ICON_THEMES = frozenset([
    "hicolor", "locolor", "gnome", "HighContrast", "Adwaita",
])


class ThemeExportService:

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def export_theme(
        self,
        theme_name: str,
        dest_path: str,
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[bool, str]:
        theme_dir = USER_THEMES_DIR / theme_name
        if not theme_dir.exists():
            return False, f"Theme not found: {theme_name}"

        dest = Path(dest_path)
        if dest.suffix != THEME_BUNDLE_EXT:
            dest = dest.with_suffix(THEME_BUNDLE_EXT)

        try:
            if progress_callback:
                progress_callback(0.05)

            conf = self._read_theme_conf(theme_dir / "theme.conf")

            gtk_theme    = conf.get("gtk_theme")
            icon_theme   = conf.get("icon_theme")
            cursor_theme = conf.get("cursor_theme")
            wallpaper    = conf.get("wallpaper")

            gtk_base    = self._find_asset_base(gtk_theme,    SYSTEM_GTK_SEARCH)   if gtk_theme    else None
            icon_base   = self._find_asset_base(icon_theme,   SYSTEM_ICONS_SEARCH) if icon_theme   else None
            cursor_base = self._find_asset_base(cursor_theme, SYSTEM_ICONS_SEARCH) if (cursor_theme and cursor_theme != icon_theme) else None
            wallpaper_src = Path(wallpaper) if wallpaper and Path(wallpaper).exists() else None

            if progress_callback:
                progress_callback(0.1)

            with tempfile.TemporaryDirectory(prefix="soplos-theme-export-") as tmp:
                tmp_path = Path(tmp)

                # Build tar ops: (base_dir, members, tar_path)
                # Icon themes may depend on parent themes via Inherits — bundle the full family.
                # GTK and cursor themes are self-contained — bundle the single dir.
                tar_ops: list = []
                if gtk_base and gtk_theme:
                    tar_ops.append((gtk_base, [gtk_theme], tmp_path / "gtk.tar"))
                if icon_base and icon_theme:
                    family = self._find_icon_dependencies(icon_base, icon_theme)
                    tar_ops.append((icon_base, family, tmp_path / "icons.tar"))
                if cursor_base and cursor_theme:
                    tar_ops.append((cursor_base, [cursor_theme], tmp_path / "cursor.tar"))

                # Create tars — pkexec for system dirs, direct for user dirs
                system_ops = [(b, m, t) for b, m, t in tar_ops if b in _SYSTEM_DIRS]
                user_ops   = [(b, m, t) for b, m, t in tar_ops if b not in _SYSTEM_DIRS]

                if system_ops:
                    self._pkexec_create_tars(system_ops, tmp_path)
                for base_dir, members, tar_path in user_ops:
                    self._create_tar(base_dir, members, tar_path)

                if progress_callback:
                    progress_callback(0.35)

                with zipfile.ZipFile(str(dest), "w", zipfile.ZIP_DEFLATED) as zf:

                    # metadata.json
                    meta_path = theme_dir / "metadata.json"
                    if meta_path.exists():
                        zf.write(str(meta_path), f"{theme_name}/metadata.json")

                    # theme.conf — wallpaper stored as filename; original path preserved
                    # so that install on the same machine can reuse it without copying.
                    bundle_conf = dict(conf)
                    if wallpaper_src:
                        bundle_conf["wallpaper"] = wallpaper_src.name
                        bundle_conf["wallpaper_source_path"] = str(wallpaper_src)
                    else:
                        bundle_conf.pop("wallpaper", None)
                        bundle_conf.pop("wallpaper_source_path", None)
                    zf.writestr(
                        f"{theme_name}/theme.conf",
                        "".join(f"{k}={v}\n" for k, v in bundle_conf.items()),
                    )

                    # preview/
                    preview_dir = theme_dir / "preview"
                    if preview_dir.exists():
                        for f in preview_dir.rglob("*"):
                            if f.is_file():
                                zf.write(str(f), f"{theme_name}/preview/{f.name}")

                    # panel assets
                    panel_assets = theme_dir / "assets" / "panel"
                    if panel_assets.exists():
                        for f in panel_assets.rglob("*"):
                            if f.is_file():
                                rel = f.relative_to(theme_dir)
                                zf.write(str(f), f"{theme_name}/{rel}")

                    if progress_callback:
                        progress_callback(0.45)

                    # Asset tars
                    for _, _, tar_path in tar_ops:
                        if tar_path.exists():
                            zf.write(str(tar_path), f"{theme_name}/assets/{tar_path.name}")

                    # Wallpaper
                    if wallpaper_src:
                        zf.write(
                            str(wallpaper_src),
                            f"{theme_name}/assets/wallpaper/{wallpaper_src.name}",
                        )

                if progress_callback:
                    progress_callback(1.0)

            logger.info(f"Theme exported: {dest}")
            return True, str(dest)

        except Exception as e:
            logger.error(f"Error exporting theme {theme_name}: {e}", exc_info=True)
            if dest.exists():
                dest.unlink()
            return False, str(e)

    def import_theme(
        self,
        bundle_path: str,
        scope: str = "global",
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[bool, str]:
        bundle = Path(bundle_path)
        if not bundle.exists():
            return False, "File not found"

        if not zipfile.is_zipfile(str(bundle)):
            return False, "Invalid .sth file (not a valid zip archive)"

        try:
            if progress_callback:
                progress_callback(0.05)

            with zipfile.ZipFile(str(bundle), "r") as zf:
                names = zf.namelist()
                metadata_candidates = [n for n in names if n.endswith("/metadata.json") or n == "metadata.json"]
                if not metadata_candidates:
                    return False, "Invalid bundle: missing metadata.json"

                meta_entry = metadata_candidates[0]
                theme_root = meta_entry[:-len("metadata.json")].rstrip("/")

                with zf.open(meta_entry) as mf:
                    metadata = json.loads(mf.read().decode("utf-8"))

                if metadata.get("format") != THEME_BUNDLE_FORMAT:
                    return False, f"Unsupported bundle format: {metadata.get('format')!r}"

                theme_name = metadata.get("name")
                if not theme_name:
                    return False, "Invalid metadata: missing theme name"

                if progress_callback:
                    progress_callback(0.1)

                conf_entry = f"{theme_root}/theme.conf" if theme_root else "theme.conf"
                conf: dict = {}
                if conf_entry in names:
                    with zf.open(conf_entry) as cf:
                        for line in cf.read().decode("utf-8").splitlines():
                            line = line.strip()
                            if line and "=" in line:
                                k, _, v = line.partition("=")
                                conf[k.strip()] = v.strip()

                if scope == "global":
                    gtk_base       = SYSTEM_GTK_DIR
                    icons_base     = SYSTEM_ICONS_DIR
                    wallpaper_base = SYSTEM_WALLPAPERS_DIR / theme_name
                else:
                    gtk_base       = USER_GTK_DIR
                    icons_base     = USER_ICONS_DIR
                    wallpaper_base = USER_WALLPAPERS_DIR / theme_name

                if progress_callback:
                    progress_callback(0.15)

                with tempfile.TemporaryDirectory(prefix="soplos-theme-import-") as tmp:
                    tmp_path = Path(tmp)
                    zf.extractall(tmp)

                    bundle_theme_dir = tmp_path / theme_root if theme_root else tmp_path

                    # Determine which tars exist in the bundle
                    tar_pairs = []
                    for tar_name, dest_base in [
                        ("gtk.tar",    gtk_base),
                        ("icons.tar",  icons_base),
                        ("cursor.tar", icons_base),
                    ]:
                        tar_path = bundle_theme_dir / "assets" / tar_name
                        if tar_path.exists():
                            tar_pairs.append((tar_path, dest_base))

                    # Determine wallpaper source/dest.
                    # If the original path still exists on this machine (same-machine
                    # install, e.g. Tyron base themes), reference it directly — no copy.
                    # Otherwise fall back to installing the bundled file.
                    wallpaper = conf.get("wallpaper")
                    wallpaper_dest: Optional[Path] = None
                    wallpaper_src: Optional[Path] = None
                    if wallpaper:
                        source_path = conf.get("wallpaper_source_path")
                        if source_path and Path(source_path).is_file():
                            # Original file present — use it, nothing to install
                            wallpaper_dest = Path(source_path)
                        else:
                            _src = bundle_theme_dir / "assets" / "wallpaper" / wallpaper
                            if _src.exists():
                                wallpaper_src = _src
                                wallpaper_dest = wallpaper_base / wallpaper

                    # Single pkexec for all global asset installs (one auth prompt)
                    global_tar_pairs = [(t, d) for t, d in tar_pairs if d in _SYSTEM_DIRS]
                    user_tar_pairs   = [(t, d) for t, d in tar_pairs if d not in _SYSTEM_DIRS]

                    if global_tar_pairs or (scope == "global" and wallpaper_src):
                        self._pkexec_install_all_global(
                            global_tar_pairs,
                            wallpaper_src   if scope == "global" else None,
                            wallpaper_dest  if scope == "global" else None,
                        )

                    for tar_path, dest_base in user_tar_pairs:
                        self._install_tar_user(tar_path, dest_base)

                    # User wallpaper — same skip-if-exists logic as tars
                    if scope != "global" and wallpaper_src and wallpaper_dest:
                        if not wallpaper_dest.exists():
                            wallpaper_dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(wallpaper_src), str(wallpaper_dest))

                    if progress_callback:
                        progress_callback(0.8)

                    # Create local theme entry
                    theme_dir = USER_THEMES_DIR / theme_name
                    if theme_dir.exists():
                        shutil.rmtree(str(theme_dir))
                    (theme_dir / "preview").mkdir(parents=True, exist_ok=True)

                    preview_src = bundle_theme_dir / "preview"
                    if preview_src.exists():
                        for f in preview_src.iterdir():
                            if f.is_file():
                                shutil.copy2(str(f), str(theme_dir / "preview" / f.name))

                    panel_src = bundle_theme_dir / "assets" / "panel"
                    if panel_src.exists():
                        shutil.copytree(str(panel_src), str(theme_dir / "assets" / "panel"))

                    local_conf = dict(conf)
                    if wallpaper_dest:
                        local_conf["wallpaper"] = str(wallpaper_dest)
                    elif "wallpaper" in local_conf:
                        del local_conf["wallpaper"]

                    with open(theme_dir / "theme.conf", "w", encoding="utf-8") as f:
                        for k, v in local_conf.items():
                            f.write(f"{k}={v}\n")

                    with open(theme_dir / "metadata.json", "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)

            if progress_callback:
                progress_callback(1.0)

            logger.info(f"Theme imported: {theme_name} (scope={scope})")
            return True, theme_name

        except zipfile.BadZipFile as e:
            return False, f"Archive error: {e}"
        except Exception as e:
            logger.error(f"Error importing theme: {e}", exc_info=True)
            return False, str(e)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _find_asset_base(self, name: str, search_dirs) -> Optional[Path]:
        """Return the base directory that contains the named asset dir."""
        for base in search_dirs:
            if (Path(base) / name).is_dir():
                return Path(base)
        return None

    def _find_icon_dependencies(self, base_dir: Path, name: str) -> List[str]:
        """Return the icon theme and all non-standard Inherits dependencies (recursive)."""
        family = [name]
        to_check = [name]
        while to_check:
            current = to_check.pop(0)
            index = base_dir / current / "index.theme"
            try:
                with open(str(index), encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("Inherits="):
                            deps = [d.strip() for d in line[len("Inherits="):].split(",")]
                            for dep in deps:
                                if (dep and dep not in _STANDARD_ICON_THEMES
                                        and dep not in family
                                        and (base_dir / dep).is_dir()):
                                    family.append(dep)
                                    to_check.append(dep)
                            break
            except (IOError, OSError):
                pass
        return sorted(family)

    def _create_tar(self, base_dir: Path, members: List[str], tar_path: Path):
        """Create a tar from user-owned dirs directly (no pkexec needed)."""
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["tar", "-czf", str(tar_path), "-C", str(base_dir)] + members,
            check=True, timeout=120,
        )

    def _pkexec_create_tars(self, ops: list, tmp_path: Path):
        """Create tars from system dirs via pkexec. ops = [(base_dir, members, tar_path)]"""
        uid = os.getuid()
        gid = os.getgid()
        lines = ["#!/bin/sh", "set -e"]
        for base_dir, members, tar_path in ops:
            members_str = " ".join(f'"{m}"' for m in members)
            lines.append(f'tar -czf "{tar_path}" -C "{base_dir}" {members_str}')
        tar_files = " ".join(f'"{t}"' for _, _, t in ops)
        lines.append(f'chown {uid}:{gid} {tar_files}')
        self._run_pkexec_script(lines)

    def _pkexec_install_all_global(
        self,
        tar_ops: list,
        wallpaper_src: Optional[Path],
        wallpaper_dest: Optional[Path],
    ):
        """Install all global assets in a single pkexec call (one auth prompt).

        tar_ops: [(tar_path, dest_base), ...]
        Each tar is extracted to an isolated slot; only missing dirs are moved.
        Wallpaper is copied only if the destination file does not already exist.
        """
        lines = [
            "#!/bin/sh", "set -e",
            "TMPEXTR=$(mktemp -d)",
            "trap 'rm -rf \"$TMPEXTR\"' EXIT",
        ]
        for i, (tar_path, dest_base) in enumerate(tar_ops):
            slot = f'"$TMPEXTR/slot_{i}"'
            lines += [
                f'mkdir -p {slot}',
                f'tar -xzf "{tar_path}" -C {slot}',
                f'for dir in {slot}/*/; do',
                '  [ -d "$dir" ] || continue',
                '  name=$(basename "$dir")',
                f'  if [ ! -d "{dest_base}/$name" ]; then',
                f'    mv "$dir" "{dest_base}/$name"',
                f'    chmod -R a+rX "{dest_base}/$name"',
                '  fi',
                'done',
            ]
        if wallpaper_src and wallpaper_dest:
            lines += [
                f'if [ ! -f "{wallpaper_dest}" ]; then',
                f'  mkdir -p "{wallpaper_dest.parent}"',
                f'  chmod a+rX "{wallpaper_dest.parent.parent}" "{wallpaper_dest.parent}"',
                f'  cp "{wallpaper_src}" "{wallpaper_dest}"',
                f'  chmod a+r "{wallpaper_dest}"',
                'fi',
            ]
        self._run_pkexec_script(lines)

    def _pkexec_install_tar(self, tar_path: Path, dest_base: Path):
        """Extract tar to system dest via pkexec, skipping dirs that already exist."""
        lines = [
            "#!/bin/sh", "set -e",
            'TMPEXTR=$(mktemp -d)',
            'trap \'rm -rf "$TMPEXTR"\' EXIT',
            f'tar -xzf "{tar_path}" -C "$TMPEXTR"',
            'for dir in "$TMPEXTR"/*/; do',
            '  name=$(basename "$dir")',
            f'  if [ ! -d "{dest_base}/$name" ]; then',
            f'    mv "$dir" "{dest_base}/$name"',
            f'    chmod -R a+rX "{dest_base}/$name"',
            '  fi',
            'done',
        ]
        self._run_pkexec_script(lines)

    def _install_tar_user(self, tar_path: Path, dest_base: Path):
        """Extract tar to user dest, skipping dirs that already exist at user or system level."""
        from utils.constants import USER_ICONS_DIR, SYSTEM_ICONS_DIR, USER_GTK_DIR, SYSTEM_GTK_DIR
        if dest_base == USER_ICONS_DIR:
            system_base = SYSTEM_ICONS_DIR
        elif dest_base == USER_GTK_DIR:
            system_base = SYSTEM_GTK_DIR
        else:
            system_base = None

        with tempfile.TemporaryDirectory(prefix="soplos-tar-") as tmp:
            tmp_path = Path(tmp)
            subprocess.run(
                ["tar", "-xzf", str(tar_path), "-C", str(tmp_path)],
                check=True, timeout=120,
            )
            dest_base.mkdir(parents=True, exist_ok=True)
            for item in tmp_path.iterdir():
                if item.is_dir():
                    dest = dest_base / item.name
                    if dest.exists():
                        continue
                    if system_base and (system_base / item.name).exists():
                        continue
                    shutil.move(str(item), str(dest))

    def _pkexec_install_file(self, src: Path, dest: Path):
        """Copy a single file to a system path via pkexec."""
        lines = [
            "#!/bin/sh", "set -e",
            f'mkdir -p "{dest.parent}"',
            f'cp "{src}" "{dest}"',
        ]
        self._run_pkexec_script(lines)

    def _run_pkexec_script(self, lines: list):
        fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="soplos-theme-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(script_path, 0o700)
            subprocess.run(["pkexec", "sh", script_path], check=True, timeout=180)
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _read_theme_conf(self, conf_path: Path) -> dict:
        conf: dict = {}
        try:
            with open(conf_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        k, _, v = line.partition("=")
                        conf[k.strip()] = v.strip()
        except Exception:
            pass
        return conf
