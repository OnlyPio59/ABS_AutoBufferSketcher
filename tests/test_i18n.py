"""Real Qt catalog loading, lifecycle, locale selection and source extraction."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from collections import Counter
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QSettings
from auto_buffer_sketcher.i18n import TranslationManager, tr
from update_translations import messages, update

APP = QCoreApplication.instance() or QCoreApplication([])
SOURCE = 'Disegna linea e genera buffer automatici'


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='abs-i18n-')
        self.folder = Path(self.temp.name)
        self.settings = QSettings(str(self.folder / 'settings.ini'), QSettings.Format.IniFormat)
        self.manager = TranslationManager(self.folder, self.settings)
        self.locale = QLocale()

    def tearDown(self):
        self.manager.unload()
        QLocale.setDefault(self.locale)
        self.temp.cleanup()

    def compile(self, locale='en', target='Draw line and generate automatic buffers'):
        executable = shutil.which('lrelease')
        self.assertIsNotNone(executable, 'Qt Linguist lrelease is required for catalog tests')
        source = self.folder / f'auto_buffer_sketcher_{locale}.ts'
        source.write_text(f'''<TS version="2.1" language="{locale}" sourcelanguage="it_IT">
<context><name>AutoBufferSketcher</name><message><source>{SOURCE}</source>
<translation>{target}</translation></message></context></TS>''', encoding='utf-8')
        subprocess.run([executable, '-nounfinished', str(source)], check=True, capture_output=True)

    def test_regional_locale_loads_base_catalog_and_unload_restores_source(self):
        self.compile()
        self.assertTrue(self.manager.load('en-GB'))
        self.assertEqual(self.manager.loaded_locale, 'en')
        self.assertEqual(tr(SOURCE), 'Draw line and generate automatic buffers')
        self.assertEqual(tr('Stringa non tradotta'), 'Stringa non tradotta')
        self.manager.unload()
        self.assertEqual(tr(SOURCE), SOURCE)

    def test_exact_catalog_precedes_base_and_reload_does_not_stack(self):
        self.compile()
        self.compile('en_US', 'US fixture')
        self.assertTrue(self.manager.load('en_US'))
        self.assertEqual(tr(SOURCE), 'US fixture')
        self.assertTrue(self.manager.load('en_GB'))
        self.assertEqual(tr(SOURCE), 'Draw line and generate automatic buffers')
        self.manager.load('it_IT')
        self.assertEqual(tr(SOURCE), SOURCE)

    def test_missing_invalid_and_unsupported_catalogs_fall_back_safely(self):
        (self.folder / 'auto_buffer_sketcher_en_US.qm').write_bytes(b'not a Qt catalog')
        for locale in ('en_US', 'fr_FR', '../../en', '', 'C'):
            with self.subTest(locale=locale):
                self.assertFalse(self.manager.load(locale))
                self.assertEqual(tr(SOURCE), SOURCE)
        self.compile()
        self.assertTrue(self.manager.load('en_US'))
        self.assertEqual(self.manager.loaded_locale, 'en')

    def test_qgis_override_is_used_without_modifying_settings_or_locale(self):
        self.compile()
        QLocale.setDefault(QLocale('it_IT'))
        self.settings.setValue('locale/overrideFlag', True)
        self.settings.setValue('locale/userLocale', 'en_GB')
        before = {key: self.settings.value(key) for key in self.settings.allKeys()}
        self.assertTrue(self.manager.load())
        self.assertEqual(QLocale().name(), 'it_IT')
        self.assertEqual(before, {key: self.settings.value(key) for key in self.settings.allKeys()})

    def test_disabled_override_uses_effective_qt_locale(self):
        self.compile()
        self.settings.setValue('locale/overrideFlag', False)
        self.settings.setValue('locale/userLocale', 'it_IT')
        QLocale.setDefault(QLocale('en_GB'))
        self.assertTrue(self.manager.load())
        QLocale.setDefault(QLocale('it_IT'))
        self.assertFalse(self.manager.load())
        self.assertEqual(tr(SOURCE), SOURCE)

    def test_load_without_application_is_safe(self):
        with patch('auto_buffer_sketcher.i18n.QCoreApplication.instance', return_value=None):
            self.assertFalse(self.manager.load('en'))

    def test_extraction_rejects_interpolation_before_translation(self):
        file = self.folder / 'module.py'
        file.write_text("tr('Segmento {id}').format(id=4)\nkey = 'abs/role'\n")
        self.assertEqual(list(messages(self.folder)), ['Segmento {id}'])
        file.write_text("tr(f'Segmento {4}')\n")
        with self.assertRaisesRegex(ValueError, 'literal string'):
            messages(self.folder)

    def test_catalog_update_preserves_translations_and_is_idempotent(self):
        self.compile()
        path = self.folder / 'auto_buffer_sketcher_en.ts'
        update(path, 'en', {SOURCE: [('plugin.py', 1)], 'Nuovo {nome}': [('dock_panel.py', 2)]})
        first = path.read_bytes()
        update(path, 'en', {SOURCE: [('plugin.py', 1)], 'Nuovo {nome}': [('dock_panel.py', 2)]})
        self.assertEqual(first, path.read_bytes())
        root = ET.parse(path).getroot()
        translations = {m.findtext('source'): m.find('translation') for m in root.findall('context/message')}
        self.assertEqual(translations[SOURCE].text, 'Draw line and generate automatic buffers')
        self.assertEqual(translations['Nuovo {nome}'].get('type'), 'unfinished')
        update(path, 'en', {})
        self.assertTrue(all(m.find('translation').get('type') == 'vanished' for m in ET.parse(path).findall('context/message')))
        update(path, 'en', {SOURCE: [('plugin.py', 5)]})
        restored = {m.findtext('source'): m.find('translation') for m in ET.parse(path).findall('context/message')}
        self.assertIsNone(restored[SOURCE].get('type'))

    def test_shipped_catalogs_cover_sources_preserve_placeholders_and_match_qm(self):
        sources = messages(ROOT / 'auto_buffer_sketcher')
        manager = TranslationManager(ROOT / 'auto_buffer_sketcher/i18n', self.settings)
        try:
            for language in ('it', 'en'):
                tree = ET.parse(ROOT / f'auto_buffer_sketcher/i18n/auto_buffer_sketcher_{language}.ts')
                entries = {m.findtext('source'): m.find('translation') for m in tree.findall('context/message')
                           if m.find('translation').get('type') != 'vanished'}
                self.assertEqual(set(entries), set(sources))
                self.assertEqual(tree.getroot().get('sourcelanguage'), 'it_IT')
                manager.load(language)
                for source, translation in entries.items():
                    with self.subTest(language=language, source=source):
                        self.assertIsNone(translation.get('type'))
                        self.assertTrue(translation.text)
                        fields = lambda text: Counter((f, s, c) for _, f, s, c in Formatter().parse(text) if f is not None)
                        self.assertEqual(fields(source), fields(translation.text))
                        self.assertEqual(tr(source), translation.text)
                        if language == 'it':
                            self.assertEqual(source, translation.text)
        finally:
            manager.unload()


if __name__ == '__main__':
    unittest.main(verbosity=2)
