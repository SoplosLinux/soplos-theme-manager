import os
import locale
import gettext
from pathlib import Path
from typing import Dict, Optional


class I18nManager:
    SUPPORTED_LANGUAGES = {
        'es': 'Spanish',
        'en': 'English',
        'fr': 'French',
        'de': 'German',
        'pt': 'Portuguese',
        'it': 'Italian',
        'ro': 'Romanian',
        'ru': 'Russian'
    }
    FALLBACK_CHAIN = ['en', 'es']

    def __init__(self, locale_dir: str, domain: str = 'soplos-theme-manager'):
        self.locale_dir = Path(locale_dir)
        self.domain = domain
        self.current_language = None
        self.translations = {}
        self.fallback_translation = None

        self.locale_dir.mkdir(parents=True, exist_ok=True)
        self._load_translations()
        self.set_language(self.detect_system_language())

    def _load_translations(self):
        for lang_code in self.SUPPORTED_LANGUAGES:
            mo_file = self.locale_dir / lang_code / 'LC_MESSAGES' / f'{self.domain}.mo'
            if mo_file.exists():
                try:
                    with open(mo_file, 'rb') as f:
                        self.translations[lang_code] = gettext.GNUTranslations(f)
                except Exception as e:
                    print(f"Error loading translation for {lang_code}: {e}")

        self.fallback_translation = (
            self.translations.get('en') or gettext.NullTranslations()
        )

    def detect_system_language(self) -> str:
        env_vars = ['LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG']
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                code = value.split('_')[0].split('.')[0].split('@')[0].lower()
                if code in self.SUPPORTED_LANGUAGES:
                    return code
        try:
            system_locale = locale.getdefaultlocale()[0]
            if system_locale:
                code = system_locale.split('_')[0].lower()
                if code in self.SUPPORTED_LANGUAGES:
                    return code
        except Exception:
            pass
        return 'en'

    def set_language(self, language_code: str) -> bool:
        if language_code not in self.SUPPORTED_LANGUAGES:
            return False
        if language_code in self.translations:
            self.current_language = language_code
            self.translations[language_code].install()
            return True
        for fallback in self.FALLBACK_CHAIN:
            if fallback in self.translations:
                self.current_language = fallback
                self.translations[fallback].install()
                return True
        self.current_language = 'en'
        self.fallback_translation.install()
        return False

    def get_translation(self, message: str, **kwargs) -> str:
        translated = message
        if self.current_language and self.current_language in self.translations:
            try:
                translated = self.translations[self.current_language].gettext(message) or message
            except Exception:
                pass
        if translated == message and self.fallback_translation:
            try:
                translated = self.fallback_translation.gettext(message) or message
            except Exception:
                pass
        if kwargs:
            try:
                translated = translated.format(**kwargs)
            except Exception:
                pass
        return translated

    def get_plural_translation(self, singular: str, plural: str, count: int, **kwargs) -> str:
        translated = singular if count == 1 else plural
        if self.current_language and self.current_language in self.translations:
            try:
                translated = self.translations[self.current_language].ngettext(singular, plural, count)
            except Exception:
                pass
        kwargs['count'] = count
        if kwargs:
            try:
                translated = translated.format(**kwargs)
            except Exception:
                pass
        return translated

    def get_current_language(self) -> str:
        return self.current_language or 'en'

    def _(self, message: str, **kwargs) -> str:
        return self.get_translation(message, **kwargs)


_i18n_manager: Optional[I18nManager] = None


def get_i18n_manager(locale_dir: str = None, domain: str = 'soplos-theme-manager') -> I18nManager:
    global _i18n_manager
    if _i18n_manager is None:
        if locale_dir is None:
            locale_dir = Path(__file__).parent.parent / 'locale'
        _i18n_manager = I18nManager(str(locale_dir), domain)
    return _i18n_manager


def _(message: str, **kwargs) -> str:
    return get_i18n_manager().get_translation(message, **kwargs)


def ngettext(singular: str, plural: str, count: int, **kwargs) -> str:
    return get_i18n_manager().get_plural_translation(singular, plural, count, **kwargs)


def initialize_i18n(locale_dir: str = None, domain: str = 'soplos-theme-manager') -> str:
    return get_i18n_manager(locale_dir, domain).get_current_language()
