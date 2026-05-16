import subprocess
import time
from pathlib import Path
from typing import Optional, Callable

from core.i18n_manager import _
from utils.constants import SCREENSHOT_PREVIEW, SCREENSHOT_THUMBNAIL
from utils.logger import logger


class ScreenshotService:

    def take_theme_screenshots(
        self,
        theme_dir: Path,
        delay: int = 2,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        view_dir = theme_dir / "view"
        view_dir.mkdir(exist_ok=True)

        full_path = view_dir / "preview_full.png"
        preview_path = view_dir / "preview.png"
        thumbnail_path = view_dir / "thumbnail.png"

        try:
            if progress_callback:
                progress_callback(0.1)

            # Notify the user and show the desktop before capturing
            subprocess.run(
                ['notify-send', '-t', '3000',
                 'Soplos Theme Manager',
                 _('Taking screenshot in {n} seconds…').format(n=delay)],
                capture_output=True
            )
            subprocess.run(['wmctrl', '-k', 'on'], capture_output=True)

            if delay > 0:
                time.sleep(delay)

            if progress_callback:
                progress_callback(0.3)

            # Full screenshot
            result = subprocess.run(
                ['scrot', str(full_path)],
                capture_output=True, timeout=15
            )
            if result.returncode != 0:
                logger.error(f"scrot failed: {result.stderr.decode()}")
                return False

            if progress_callback:
                progress_callback(0.6)

            # Redimensionar a preview (640x360)
            subprocess.run(
                ['convert', str(full_path),
                 '-resize', SCREENSHOT_PREVIEW + '^',
                 '-gravity', 'Center',
                 '-extent', SCREENSHOT_PREVIEW,
                 str(preview_path)],
                capture_output=True, timeout=10
            )

            if progress_callback:
                progress_callback(0.8)

            # Redimensionar a thumbnail (150x90)
            subprocess.run(
                ['convert', str(full_path),
                 '-resize', SCREENSHOT_THUMBNAIL + '^',
                 '-gravity', 'Center',
                 '-extent', SCREENSHOT_THUMBNAIL,
                 str(thumbnail_path)],
                capture_output=True, timeout=10
            )

            # Restore all windows
            subprocess.run(['wmctrl', '-k', 'off'], capture_output=True)

            if progress_callback:
                progress_callback(1.0)

            logger.info(f"Screenshots saved to {view_dir}")
            return True

        except FileNotFoundError as e:
            logger.error(f"Required tool not found (scrot/convert): {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Screenshot timed out")
            return False
        except Exception as e:
            logger.error(f"Screenshot error: {e}", exc_info=True)
            return False

    def check_tools_available(self) -> dict:
        tools = {}
        for tool in ('scrot', 'convert', 'wmctrl', 'notify-send'):
            result = subprocess.run(['which', tool], capture_output=True)
            tools[tool] = result.returncode == 0
        return tools
