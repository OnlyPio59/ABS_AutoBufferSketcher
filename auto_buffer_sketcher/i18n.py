"""Qt translation lifecycle. Italian source text is the fallback language."""
from pathlib import Path
import re

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QSettings, QTranslator

CONTEXT = 'AutoBufferSketcher'
LANGUAGE_SETTING = 'ABS/language'
SUPPORTED_LANGUAGES = ('it', 'en', 'es', 'pt_BR', 'fr', 'de')
LANGUAGE_NAMES = (
    ('it', 'Italiano'), ('en', 'English'), ('es', 'Español'),
    ('pt_BR', 'Português (Brasil)'), ('fr', 'Français'), ('de', 'Deutsch'),
)


def tr(text):
    """Translate a literal template before applying named format placeholders."""
    return QCoreApplication.translate(CONTEXT, text)


class TranslationManager:
    """Keep the translator alive and remove it when the plugin is unloaded.

    Read QGIS's explicit locale override when enabled, otherwise Qt's effective
    locale. Do not change the host locale, settings or other translators.
    """

    def __init__(self, catalog_dir=None, settings=None):
        self.catalog_dir = Path(catalog_dir) if catalog_dir is not None else Path(__file__).parent / 'i18n'
        self.settings = settings if settings is not None else QSettings()
        self.translator = None
        self.loaded_locale = None

    @property
    def preference(self):
        value = self.settings.value(LANGUAGE_SETTING, 'auto', type=str)
        return value if value in ('auto', *SUPPORTED_LANGUAGES) else 'auto'

    def set_preference(self, language):
        if language not in ('auto', *SUPPORTED_LANGUAGES):
            raise ValueError('Unsupported ABS language')
        self.settings.setValue(LANGUAGE_SETTING, language)
        self.settings.sync()
        return self.load()

    def load(self, locale=None):
        self.unload()
        if QCoreApplication.instance() is None:
            return False
        if locale is None:
            if self.preference != 'auto':
                locale = self.preference
            elif self.settings.value('locale/overrideFlag', False, type=bool):
                locale = self.settings.value('locale/userLocale', '', type=str)
            else:
                locale = QLocale().name()
        locale = str(locale).replace('-', '_')
        # Treat locale values as identifiers, never as paths.
        if not re.fullmatch(r'[A-Za-z]{2,3}(?:_[A-Za-z0-9]{2,8}){0,2}', locale):
            return False
        parts = locale.split('_')
        parts[0] = parts[0].lower()
        if len(parts) > 1 and len(parts[1]) == 2:
            parts[1] = parts[1].upper()
        if parts[0] == 'it':
            return False
        candidates = ['_'.join(parts), parts[0]]
        if parts[0] == 'pt':
            candidates.append('pt_BR')
        for candidate in dict.fromkeys(candidates):
            translator = QTranslator()
            path = self.catalog_dir / f'auto_buffer_sketcher_{candidate}.qm'
            if path.is_file() and translator.load(str(path)) and QCoreApplication.installTranslator(translator):
                self.translator = translator
                self.loaded_locale = candidate
                return True
        return False

    def unload(self):
        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
        self.translator = None
        self.loaded_locale = None
