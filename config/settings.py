import json
from pathlib import Path
from typing import Any, Dict, Optional
from utils.logger import logger


class Config:
    def __init__(self, config_file: Optional[str] = None):
        if config_file:
            self.config_file = Path(config_file)
        else:
            config_dir = Path.home() / ".config" / "soplos-theme-manager"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file = config_dir / "settings.json"

        self._settings: Dict[str, Any] = {}
        self.load()

    def load(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._settings = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error loading config: {e}")
            self._settings = {}

    def save(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        self._settings[key] = value
        self.save()

    def delete(self, key: str):
        if key in self._settings:
            del self._settings[key]
            self.save()

    def get_all(self) -> Dict[str, Any]:
        return self._settings.copy()

    def reset(self):
        self._settings = {}
        self.save()


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
