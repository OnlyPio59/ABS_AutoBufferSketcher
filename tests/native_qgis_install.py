"""Run via qgis --code in a fresh temporary profile, never a personal profile.

ABS_NATIVE_ZIP points to the built package. ABS_NATIVE_RESULT is the JSON result.
This exercises the native ZIP installer and the real application iface.
"""
import json
import os
from pathlib import Path
import sqlite3
import traceback
from unittest.mock import patch
import zipfile

from qgis.core import (
    Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsFeature,
    QgsGeometry, QgsPointXY, QgsProject,
)
from qgis.PyQt.QtCore import QCoreApplication, QTimer, QT_VERSION_STR
from qgis.utils import iface

RESULT = Path(os.environ['ABS_NATIVE_RESULT'])
PACKAGE = Path(os.environ['ABS_NATIVE_ZIP'])
CHECKS = []


def check(name, passed):
    CHECKS.append({'check': name, 'passed': bool(passed)})
    print('ABS native:', name, bool(passed), flush=True)
    if not passed:
        raise AssertionError(name)


def run():
    import qgis.utils
    import pyplugin_installer
    result = {'qgis': Qgis.QGIS_VERSION, 'qt': QT_VERSION_STR, 'checks': CHECKS}
    try:
        profile = Path(QgsApplication.qgisSettingsDirPath())
        check('temporary_profile', profile.is_relative_to(Path('/tmp')))
        target = profile / 'python/plugins/auto_buffer_sketcher'
        check('plugin_not_preinstalled', not target.exists())
        with patch('pyplugin_installer.installer_data.Repositories.checkingOnStart', return_value=False):
            installer = pyplugin_installer.instance()
        check('native_zip_install', installer.installFromZipFile(str(PACKAGE)))
        check('plugin_started', qgis.utils.isPluginLoaded('auto_buffer_sketcher'))
        with zipfile.ZipFile(PACKAGE) as archive:
            entries = [name for name in archive.namelist() if not name.endswith('/')]
            check('installed_bytes', all(
                (target.parent / name).read_bytes() == archive.read(name) for name in entries
            ))
        plugin = qgis.utils.plugins['auto_buffer_sketcher']
        project = QgsProject.instance()
        project.setCrs(QgsCoordinateReferenceSystem('EPSG:32633'))
        plugin.run()
        from auto_buffer_sketcher.version import PLUGIN_VERSION
        check('version_badge', plugin.dock_panel.version_label.text() == 'v' + PLUGIN_VERSION)
        route = plugin._route_layer
        feature = QgsFeature(route.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(500000, 4500000), QgsPointXY(500500, 4500200),
            QgsPointXY(501000, 4500400),
        ]))
        check('add_route', route.dataProvider().addFeatures([feature])[0])
        route.updateExtents()
        check('calculate_buffers', plugin._on_recalc())
        panel = plugin.dock_panel
        panel.chk_diff_buffers.setChecked(True)
        segments = plugin._segments_layer
        first, second = sorted(segments.getFeatures(), key=lambda f: f['seg_id'])
        for feature, distance in [(first, 35), (second, 70)]:
            segments.selectByIds([feature.id()])
            panel.spin_pregeocage.setValue(distance)
            panel.btn_apply_segment.click()
        check('independent_segment_values',
              segments.getFeature(first.id())['pregeocage_m'] == 35 and
              segments.getFeature(second.id())['pregeocage_m'] == 70)

        def export(action, path):
            with patch('auto_buffer_sketcher.plugin.QFileDialog.getSaveFileName',
                       return_value=(str(path), '')):
                action()

        folder = RESULT.parent
        gpkg = folder / 'synthetic.gpkg'
        export(plugin._on_export, gpkg)
        check('gpkg_export', gpkg.exists())
        with sqlite3.connect(gpkg) as connection:
            check('four_buffers_exported', connection.execute(
                'SELECT count(*) FROM gpkg_contents').fetchone()[0] == 5)
        geojson = folder / 'synthetic.geojson'
        export(plugin._on_export_geojson, geojson)
        check('geojson_export', geojson.exists() and json.loads(geojson.read_text())['type'] == 'FeatureCollection')
        plan = folder / 'synthetic.plan'
        export(plugin._on_export_plan, plan)
        check('plan_export', plan.exists() and 'mission' in json.loads(plan.read_text()))
        export(plugin._on_make_persistent, folder / 'persistent.gpkg')
        check('persistent_route', plugin._route_layer.providerType() != 'memory')
        check('persistent_segments', plugin._segments_layer.providerType() != 'memory')
        project.setFileName(str(folder / 'synthetic.qgz'))
        check('save_project', project.write())
        plugin.unload()
        project.clear()
        check('reopen_project', project.read(str(folder / 'synthetic.qgz')))
        from auto_buffer_sketcher.branding import layer_role
        restored = [layer for layer in project.mapLayers().values()
                    if layer_role(layer) == 'ABC Segments']
        check('restored_segment_values', len(restored) == 1 and sorted(
            feature['pregeocage_m'] for feature in restored[0].getFeatures()) == [35, 70])
        project.clear()
        project.setDirty(False)
        result['passed'] = True
    except Exception:
        result['passed'] = False
        result['error'] = traceback.format_exc()
        print(result['error'], flush=True)
    finally:
        RESULT.write_text(json.dumps(result, indent=2))
        QCoreApplication.exit(0 if result['passed'] else 1)


QTimer.singleShot(1000, run)
QTimer.singleShot(60000, lambda: QCoreApplication.exit(3))
