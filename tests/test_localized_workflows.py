"""Bilingual UI workflows with real QGIS layers and deterministic export comparison."""
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_plugin_regressions import APP, PROJECT, Iface, line, managed
from auto_buffer_sketcher import classFactory
from auto_buffer_sketcher.buffer_engine import (
    DEFAULT_DISTANCES, SEG_FIELD_ID, SEG_FIELD_PRECAGE, SEG_FIELD_GEOCAGE,
    LAYER_NAME_PREGEOCAGE, BufferEngine,
)
from auto_buffer_sketcher.geojson_exporter import GeoJSONExporter
from auto_buffer_sketcher.plan_exporter import PlanExporter
from qgis.core import QgsFeature, QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QStyle, QStyleOptionButton


class LocalizedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='abs-languages-')
        self.folder = Path(self.temp.name)
        self.plugin = None
        self.iface = None

    def tearDown(self):
        self.close_plugin()
        self.temp.cleanup()

    def close_plugin(self):
        if self.plugin is not None:
            self.plugin.unload()
            self.plugin = None
        PROJECT.clear()
        if self.iface is not None:
            self.iface.window.close()
            self.iface = None
        APP.processEvents()

    def create(self, language):
        self.close_plugin()
        PROJECT.setCrs(QgsCoordinateReferenceSystem('EPSG:32634'))
        self.iface = Iface()
        self.plugin = classFactory(self.iface)
        settings = QSettings(str(self.folder / 'locale.ini'), QSettings.IniFormat)
        settings.setValue('locale/overrideFlag', True)
        settings.setValue('locale/userLocale', language)
        self.plugin._translations.settings = settings
        self.plugin.initGui()
        self.plugin._ensure_route_layer()
        return self.plugin, self.plugin.dock_panel

    def seed(self):
        route = self.plugin._route_layer
        feature = QgsFeature(route.fields())
        feature.setGeometry(line())
        self.assertTrue(route.dataProvider().addFeatures([feature])[0])
        route.updateExtents()
        self.assertTrue(self.plugin._on_recalc())

    def test_buttons_edit_states_errors_and_dialogs_follow_language(self):
        for language, draw, save, delete, error, title in (
            ('it_IT', 'Disegna linea', 'Salva modifiche', 'Conferma eliminazione', 'Nessuna linea da eliminare.', 'Esporta piano per RigiCloud (.plan)'),
            ('en_GB', 'Draw line', 'Save changes', 'Confirm deletion', 'No lines to delete.', 'Export plan for RigiCloud (.plan)'),
        ):
            with self.subTest(language=language):
                p, panel = self.create(language)
                self.assertEqual(panel.btn_sketcher.text(), draw)
                p._on_delete_requested()
                self.assertEqual(panel.status_label.text(), error)
                self.seed()
                p._on_edit_requested()
                self.assertEqual(panel.btn_edit.text(), save)
                p._on_edit_requested()
                p._on_delete_requested()
                self.assertEqual(panel.btn_delete.text(), delete)
                with patch('auto_buffer_sketcher.plugin.QFileDialog.getSaveFileName', return_value=('', '')) as dialog:
                    p._on_export_plan()
                self.assertEqual(dialog.call_args.args[1], title)
                self.assertEqual(dialog.call_args.args[3], 'RigiCloud Plan (*.plan)')

    def test_two_segment_values_survive_switching_persistence_and_language_change(self):
        p, panel = self.create('it_IT')
        self.seed()
        panel.chk_diff_buffers.setChecked(True)
        segments = p._segments_layer
        first, second = sorted(segments.getFeatures(), key=lambda f: f[SEG_FIELD_ID])
        for feature, distance in ((first, 25), (second, 40)):
            segments.selectByIds([feature.id()])
            panel.spin_pregeocage.setValue(distance)
            panel.btn_apply_segment.click()
        gpkg = self.folder / 'segments.gpkg'
        with patch('auto_buffer_sketcher.plugin.QFileDialog.getSaveFileName', return_value=(str(gpkg), '')):
            p._on_make_persistent()
        project = str(self.folder / 'saved.qgs')
        self.assertTrue(PROJECT.write(project))
        p, panel = self.create('en_US')
        self.assertTrue(PROJECT.read(project))
        self.assertTrue(p._on_recalc())
        values = BufferEngine._read_segment_distances(p._segments_layer)
        self.assertEqual(values[first[SEG_FIELD_ID]]['pregeocage'], 25)
        self.assertEqual(values[second[SEG_FIELD_ID]]['pregeocage'], 40)
        current = sorted(p._segments_layer.getFeatures(), key=lambda f: f[SEG_FIELD_ID])
        p._segments_layer.selectByIds([current[1].id()])
        panel.spin_geocage.setValue(110)
        self.assertIn('unsaved changes', panel.seg_info_label.text())
        panel.btn_apply_segment.click()
        self.assertIn('distances saved in the layer', panel.status_label.text())
        p._segments_layer.selectByIds([current[0].id()])
        self.assertEqual(panel.spin_pregeocage.value(), 25)
        self.assertEqual(panel.spin_geocage.value(), 100)
        self.assertEqual(p._segments_layer.getFeature(current[1].id())[SEG_FIELD_GEOCAGE], 110)

    def test_exports_geometry_fields_and_parameters_are_identical_in_both_languages(self):
        snapshots = []
        for language in ('it_IT', 'en_US'):
            p, panel = self.create(language)
            self.seed()
            route, buffers = p._plan_export_layers()
            path = self.folder / 'route.plan'
            ids = itertools.count(1)
            with patch('auto_buffer_sketcher.plan_exporter.uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(ids))):
                exporter = PlanExporter()
                self.assertTrue(exporter.export(route, buffers, DEFAULT_DISTANCES, panel.get_mission_config(), str(path)), exporter.last_error)
            plan = json.loads(path.read_text())
            geojson = self.folder / 'route.geojson'
            exporter = GeoJSONExporter()
            self.assertTrue(exporter.export(route, buffers, str(geojson)), exporter.last_error)
            snapshots.append((plan, json.loads(geojson.read_text()), panel.get_distances(), panel.get_mission_config(),
                p._route_layer.fields().names(), [(layer.name(), layer.customProperty('abs/role')) for layer in managed(LAYER_NAME_PREGEOCAGE)]))
        self.assertEqual(snapshots[0], snapshots[1])

    def test_compact_panel_actions_remain_readable_and_reachable(self):
        for language in ('it_IT', 'en_US'):
            _, panel = self.create(language)
            # Detach from the host adapter to test a fixed compact dock size.
            panel.setParent(None)
            panel.resize(360, 560)
            panel.show()
            panel.chk_diff_buffers.setChecked(True)
            panel.set_segment_info(123)
            APP.processEvents()
            bar = panel.tabs.tabBar()
            for index in (0, 1):
                self.assertTrue(bar.rect().contains(bar.tabRect(index)))
            self.assertEqual(panel.tabs.widget(0).horizontalScrollBar().maximum(), 0)
            for button in (panel.btn_apply_segment, panel.btn_sketcher, panel.btn_export_plan, panel.btn_make_persistent):
                option = QStyleOptionButton()
                option.initFrom(button)
                rect = button.style().subElementRect(QStyle.SE_PushButtonContents, option, button)
                self.assertLessEqual(button.fontMetrics().horizontalAdvance(button.text()), rect.width(), button.text())
            self.assertTrue(panel.rect().contains(panel.btn_apply_segment.mapTo(panel, panel.btn_apply_segment.rect().center())))
            panel.tabs.setCurrentIndex(1)
            page = panel.tabs.currentWidget()
            page.ensureWidgetVisible(panel.btn_make_persistent)
            APP.processEvents()
            self.assertTrue(page.viewport().rect().contains(panel.btn_make_persistent.mapTo(page.viewport(), panel.btn_make_persistent.rect().center())))


if __name__ == '__main__':
    unittest.main(verbosity=2)
