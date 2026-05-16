import tarfile
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Tuple

from utils.constants import (
    USER_THEMES_DIR, THEME_BUNDLE_EXT,
    APPLICATION_VERSION, APPLICATION_AUTHOR
)
from utils.logger import logger


class ThemeExportService:

    def export_theme(
        self,
        theme_name: str,
        dest_path: str,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[bool, str]:
        theme_dir = USER_THEMES_DIR / theme_name
        if not theme_dir.exists():
            return False, f"Theme not found: {theme_name}"

        dest = Path(dest_path)
        if not dest.suffix == THEME_BUNDLE_EXT:
            dest = dest.with_suffix(THEME_BUNDLE_EXT)

        try:
            if progress_callback:
                progress_callback(0.1)

            manifest = {
                'name': theme_name,
                'author': APPLICATION_AUTHOR,
                'created': datetime.now().isoformat(),
                'app_version': APPLICATION_VERSION,
                'format': 'soplos-theme-bundle-v1',
            }

            with tarfile.open(str(dest), 'w:gz') as tar:
                import io
                manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8')
                info = tarfile.TarInfo(name='manifest.json')
                info.size = len(manifest_bytes)
                tar.addfile(info, io.BytesIO(manifest_bytes))

                if progress_callback:
                    progress_callback(0.4)

                tar.add(str(theme_dir), arcname=theme_name)

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
        progress_callback: Optional[Callable] = None
    ) -> Tuple[bool, str]:
        bundle = Path(bundle_path)
        if not bundle.exists():
            return False, "File not found"

        if not tarfile.is_tarfile(str(bundle)):
            return False, "Invalid .sth file (not a valid archive)"

        try:
            if progress_callback:
                progress_callback(0.1)

            with tarfile.open(str(bundle), 'r:gz') as tar:
                # Verificar manifest
                try:
                    manifest_member = tar.getmember('manifest.json')
                    manifest_file = tar.extractfile(manifest_member)
                    manifest = json.loads(manifest_file.read().decode('utf-8'))
                except KeyError:
                    return False, "Invalid bundle: missing manifest.json"

                theme_name = manifest.get('name')
                if not theme_name:
                    return False, "Invalid manifest: missing theme name"

                if progress_callback:
                    progress_callback(0.3)

                # Verificar que no sobreescriba temas predeterminados
                dest_dir = USER_THEMES_DIR / theme_name
                if dest_dir.exists():
                    shutil.rmtree(str(dest_dir))

                if progress_callback:
                    progress_callback(0.5)

                # Extraer solo el directorio del tema (sin manifest.json)
                USER_THEMES_DIR.mkdir(parents=True, exist_ok=True)
                for member in tar.getmembers():
                    if member.name == 'manifest.json':
                        continue
                    # Sanitizar rutas (evitar path traversal)
                    member_path = Path(member.name)
                    if member_path.is_absolute() or '..' in member_path.parts:
                        logger.warning(f"Skipping unsafe path in bundle: {member.name}")
                        continue
                    tar.extract(member, path=str(USER_THEMES_DIR))

                if progress_callback:
                    progress_callback(1.0)

            logger.info(f"Theme imported: {theme_name}")
            return True, theme_name

        except tarfile.TarError as e:
            return False, f"Archive error: {e}"
        except Exception as e:
            logger.error(f"Error importing theme: {e}", exc_info=True)
            return False, str(e)
