import configparser
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

from utils.logger import logger

CONFIG_PATH = Path('/etc/lightdm/lightdm-gtk-greeter.conf')
SECTION = 'greeter'

# Keys this tab is allowed to touch — anything else already present in the
# file (indicators, multi-monitor setup, accessibility, etc.) is left
# untouched.
EDITABLE_KEYS = (
    'background', 'theme-name', 'icon-theme-name', 'cursor-theme-name',
    'default-user-image', 'font-name', 'position', 'hide-user-image',
    'user-background', 'clock-format',
)


class LightdmService:
    """Reads and writes the LightDM GTK greeter's own config file.

    This is a system file (root:root, 644) so writes always go through
    pkexec — there is no meaningful "current user" scope for a login
    screen, unlike GTK/icon/cursor themes.
    """

    def read_config(self) -> Dict[str, str]:
        parser = self._make_parser()
        values: Dict[str, str] = {}
        if CONFIG_PATH.exists():
            try:
                parser.read(CONFIG_PATH)
                if parser.has_section(SECTION):
                    values = dict(parser.items(SECTION))
            except Exception as e:
                logger.error(f"Error reading {CONFIG_PATH}: {e}")
        return values

    def write_config(self, updates: Dict[str, str]) -> bool:
        parser = self._make_parser()
        if CONFIG_PATH.exists():
            try:
                parser.read(CONFIG_PATH)
            except Exception as e:
                logger.warning(f"Could not parse existing {CONFIG_PATH}, rewriting: {e}")
        if not parser.has_section(SECTION):
            parser.add_section(SECTION)

        for key in EDITABLE_KEYS:
            if key not in updates:
                continue
            value = updates[key]
            if value:
                parser.set(SECTION, key, value)
            elif parser.has_option(SECTION, key):
                parser.remove_option(SECTION, key)

        fd, tmp_path = tempfile.mkstemp(suffix='.conf', prefix='soplos-lightdm-')
        try:
            with os.fdopen(fd, 'w') as f:
                parser.write(f, space_around_delimiters=True)
            self._install_via_pkexec(tmp_path)
            return True
        except Exception as e:
            logger.error(f"Error writing {CONFIG_PATH}: {e}")
            return False
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _make_parser() -> configparser.ConfigParser:
        # interpolation=None: the greeter's own "position" value contains
        # literal '%' characters (e.g. "5%,start 50%,center"), which the
        # default BasicInterpolation would try (and fail) to parse.
        return configparser.ConfigParser(interpolation=None, strict=False)

    @staticmethod
    def _install_via_pkexec(tmp_path: str):
        lines = [
            "#!/bin/sh", "set -e",
            f'mkdir -p {shlex.quote(str(CONFIG_PATH.parent))}',
            f'cp {shlex.quote(tmp_path)} {shlex.quote(str(CONFIG_PATH))}',
            f'chmod 644 {shlex.quote(str(CONFIG_PATH))}',
            f'chown root:root {shlex.quote(str(CONFIG_PATH))}',
        ]
        fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='soplos-lightdm-')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(script_path, 0o700)
            subprocess.run(['pkexec', 'sh', script_path], check=True, timeout=60)
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass
