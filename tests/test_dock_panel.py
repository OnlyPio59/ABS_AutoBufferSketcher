"""Interaction checks for the redesigned dock, using real Qt hit testing."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtTest import QTest, QSignalSpy
from qgis.PyQt.QtWidgets import QStyle, QStyleOptionSpinBox, QMainWindow, QLabel
from auto_buffer_sketcher.dock_panel import BufferDockPanel
from auto_buffer_sketcher.version import PLUGIN_VERSION

APP = QgsApplication([], False)
APP.initQgis()

class DockTests(unittest.TestCase):
    def test_loaded_version_badge_is_visible_and_readable_in_compact_panel(self):
        self.panel.resize(360, 560)
        APP.processEvents()
        badge = self.panel.version_label
        self.assertEqual(badge.text(), f'v{PLUGIN_VERSION}')
        self.assertTrue(badge.isVisible())
        self.assertTrue(self.panel.rect().contains(badge.mapTo(self.panel, badge.rect().center())))
        self.assertLessEqual(badge.fontMetrics().horizontalAdvance(badge.text()), badge.contentsRect().width())
        self.assertIn(PLUGIN_VERSION, badge.accessibleName())

    def setUp(self):
        self.panel = BufferDockPanel()
        self.panel.resize(420, 830)
        self.panel.show()
        APP.processEvents()

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        APP.processEvents()

    def test_mouse_step_targets_all_distances_and_altitudes(self):
        for name in ('pregeocage', 'geocage', 'ground', 'adjacent', 'alt_flight', 'alt_pad'):
            with self.subTest(control=name):
                self.panel.tabs.setCurrentIndex(1 if name.startswith('alt_') else 0)
                spin = getattr(self.panel, 'spin_' + name)
                self.panel.tabs.currentWidget().ensureWidgetVisible(spin)
                APP.processEvents()
                option = QStyleOptionSpinBox()
                spin.initStyleOption(option)
                before = spin.value()
                up = spin.style().subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxUp, spin)
                down = spin.style().subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxDown, spin)
                for rect in (up, down):
                    self.assertGreaterEqual(rect.width(), 26)
                    self.assertGreaterEqual(rect.height(), 18)
                QTest.mouseClick(spin, Qt.LeftButton, pos=up.center())
                self.assertEqual(spin.value(), before + spin.singleStep())
                QTest.mouseClick(spin, Qt.LeftButton, pos=down.center())
                self.assertEqual(spin.value(), before)
                spin.setValue(0)
                QTest.mouseClick(spin, Qt.LeftButton, pos=down.center())
                self.assertEqual(spin.value(), 0)
                spin.setValue(spin.maximum())
                QTest.mouseClick(spin, Qt.LeftButton, pos=up.center())
                self.assertEqual(spin.value(), spin.maximum())

    def test_keyboard_values_and_silent_segment_loading(self):
        spin = self.panel.spin_pregeocage
        spy = QSignalSpy(self.panel.distances_changed)
        spin.setFocus()
        QTest.keyClick(spin, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(spin, '75.5')
        QTest.keyClick(spin, Qt.Key_Return)
        self.assertEqual(spin.value(), 75.5)
        self.assertGreater(len(spy), 0)
        count = len(spy)
        self.panel.set_distances({'pregeocage': 12.5})
        self.assertEqual(len(spy), count)
        self.assertEqual(spin.value(), 12.5)
        self.assertEqual(self.panel.get_mission_config(), {'alt_flight': 120.0, 'alt_pad': 40.0, 'geoid_offset': 39.27})

    def test_workflow_actions_forward_once(self):
        for button, signal in (
            ('btn_sketcher','sketcher_requested'), ('btn_edit','edit_requested'),
            ('btn_delete','delete_requested'), ('btn_recalc','recalc_requested'),
            ('btn_export','export_requested'), ('btn_export_plan','export_plan_requested'),
            ('btn_export_geojson','export_geojson_requested'),
            ('btn_make_persistent','make_persistent_requested'),
            ('btn_apply_all','apply_to_all_segments'),
        ):
            with self.subTest(action=button):
                spy = QSignalSpy(getattr(self.panel, signal))
                getattr(self.panel, button).click()
                self.assertEqual(len(spy), 1)
        spy = QSignalSpy(self.panel.apply_to_segment)
        self.panel.chk_diff_buffers.setChecked(True)
        self.assertTrue(self.panel.seg_group.isVisible())
        self.assertFalse(self.panel.btn_apply_segment.isEnabled())
        self.panel.set_segment_info(1)
        self.panel.btn_apply_segment.click()
        self.assertEqual(len(spy), 1)
        self.panel.chk_diff_buffers.setChecked(False)
        self.assertFalse(self.panel.seg_group.isVisible())
        self.assertFalse(self.panel.btn_apply_segment.isEnabled())

    def test_small_panel_scrolls_to_last_action_and_keeps_status(self):
        self.panel.resize(360, 560)
        self.panel.chk_diff_buffers.setChecked(True)
        APP.processEvents()
        for page, button in ((0,self.panel.btn_apply_all), (1,self.panel.btn_make_persistent)):
            self.panel.tabs.setCurrentIndex(page)
            area = self.panel.tabs.currentWidget()
            area.ensureWidgetVisible(button)
            APP.processEvents()
            self.assertGreater(area.verticalScrollBar().maximum(), 0)
            self.assertTrue(area.viewport().rect().contains(button.mapTo(area.viewport(),button.rect().center())))
            self.assertTrue(self.panel.status_label.isVisible())
            self.assertTrue(self.panel.rect().contains(self.panel.status_label.mapTo(self.panel,self.panel.status_label.rect().center())))

    def test_header_and_primary_button_keep_contrast_under_host_styles(self):
        host = QMainWindow()
        host.setStyleSheet("QWidget { color: black; }")
        panel = BufferDockPanel(host)
        host.setCentralWidget(panel)
        host.show()
        APP.processEvents()
        title = panel.findChild(QLabel, 'absTitle')
        self.assertEqual(title.palette().color(title.foregroundRole()).name(), '#f8fafc')
        self.assertEqual(panel.btn_sketcher.palette().color(QPalette.ButtonText).name(), '#ffffff')
        host.close()
        host.deleteLater()

    def test_segment_save_stays_visible_without_scrolling(self):
        self.panel.resize(360, 560)
        self.panel.chk_diff_buffers.setChecked(True)
        self.panel.set_segment_info(2)
        APP.processEvents()
        button = self.panel.btn_apply_segment
        self.assertTrue(button.isVisible())
        self.assertTrue(self.panel.rect().contains(button.mapTo(self.panel, button.rect().center())))
        self.panel.spin_geocage.setValue(125)
        self.assertTrue(self.panel.has_unsaved_segment_changes)
        self.assertIn('modifiche da salvare', self.panel.seg_info_label.text())
        self.panel.tabs.setCurrentIndex(1)
        self.assertFalse(self.panel.seg_group.isVisible())
        self.panel.tabs.setCurrentIndex(0)
        self.assertTrue(self.panel.seg_group.isVisible())

    def test_palette_switch_is_local(self):
        application_color = APP.palette().color(QPalette.Window)
        for dark in (True, False):
            palette = self.panel.palette()
            palette.setColor(QPalette.Window, QColor('#111827' if dark else '#FFFFFF'))
            self.panel.setPalette(palette)
            APP.processEvents()
            self.assertEqual(self.panel.container.palette().color(QPalette.Window).name(), '#111827' if dark else '#f3f5f8')
            self.assertEqual(APP.palette().color(QPalette.Window), application_color)

if __name__ == '__main__':
    unittest.main(verbosity=2)
