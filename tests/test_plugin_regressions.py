"""Regression tests for the QGIS plugin. Real QGIS/Qt components, offscreen iface adapter.
Run with QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_plugin_regressions.py
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qgis.core import (QgsApplication,QgsProject,QgsVectorLayer,QgsFeature,QgsGeometry,QgsPointXY,
    QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsRectangle,QgsField,Qgis,QgsWkbTypes)
from qgis.gui import QgsMapCanvas,QgsMapToolEmitPoint,QgsRubberBand
from qgis.PyQt.QtCore import Qt,QPoint,QVariant
from qgis.PyQt.QtWidgets import QMainWindow,QAction
from qgis.PyQt.QtTest import QTest
from auto_buffer_sketcher import classFactory
from auto_buffer_sketcher.buffer_engine import *
from auto_buffer_sketcher.geojson_exporter import GeoJSONExporter
from auto_buffer_sketcher.plan_exporter import PlanExporter
from auto_buffer_sketcher.geometry_utils import transformed
from auto_buffer_sketcher.file_io import write_geopackage
from auto_buffer_sketcher.segment_sync import ROUTE_KEY,PART,POSITION
from auto_buffer_sketcher.sketcher_tool import LineSketcherTool
APP=QgsApplication([],False);APP.initQgis()
PROJECT=QgsProject.instance()
BASE=[(500000,4500000),(501000,4500000),(502000,4500000)]
KEEP=[]

class Iface:
    def __init__(self):
        self.window=QMainWindow();self.canvas=QgsMapCanvas(self.window);self.window.setCentralWidget(self.canvas)
        self.canvas.resize(800,600);self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32634'))
        self.select=QAction(self.window);self.vertex=QAction(self.window);self.icons=[];self.menus=[]
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def addToolBarIcon(self,a):self.icons.append(a)
    def removeToolBarIcon(self,a):self.icons.remove(a)
    def addPluginToMenu(self,m,a):self.menus.append((m,a))
    def removePluginMenu(self,m,a):self.menus.remove((m,a))
    def addDockWidget(self,w,d):self.window.addDockWidget(w,d)
    def removeDockWidget(self,d):self.window.removeDockWidget(d)
    def setActiveLayer(self,l):self.active=l
    def actionSelect(self):return self.select
    def actionVertexTool(self):return self.vertex

def layer(wkts,crs='EPSG:32634',kind='LineString',name='synthetic'):
    l=QgsVectorLayer(f'{kind}?crs={crs}',name,'memory');assert l.isValid()
    for wkt in wkts:
        f=QgsFeature(l.fields());f.setGeometry(QgsGeometry.fromWkt(wkt))
        ok,_=l.dataProvider().addFeatures([f]);assert ok
    l.updateExtents();KEEP.append(l);return l

def line(points=BASE):return QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in points])
def geometry(l):return next(l.getFeatures()).geometry()
def managed(role):
    return [l for l in PROJECT.mapLayers().values() if l.customProperty('abs/role',l.name())==role]
def tables(path):
    with sqlite3.connect(path) as con:return [x[0] for x in con.execute('SELECT table_name FROM gpkg_contents')]

class Tests(unittest.TestCase):
    def setUp(self):
        PROJECT.clear();PROJECT.setCrs(QgsCoordinateReferenceSystem('EPSG:32634'))
        self.tmp=tempfile.TemporaryDirectory(prefix='abs-phase2-');self.folder=Path(self.tmp.name)
        self.iface=Iface();KEEP.append(self.iface)
        self.p=classFactory(self.iface);self.p.initGui();self.p._ensure_route_layer()
    def tearDown(self):
        if self.p.dock_panel is not None:self.p.unload()
        PROJECT.clear();self.iface.window.close();QTest.qWait(1);self.tmp.cleanup()
    def seed(self,points=BASE):
        f=QgsFeature(self.p._route_layer.fields());f.setGeometry(line(points))
        ok,fs=self.p._route_layer.dataProvider().addFeatures([f]);self.assertTrue(ok)
        self.p._route_layer.updateExtents();self.assertTrue(self.p._on_recalc());return fs[0].id()
    def diff(self,first=20):
        self.p.dock_panel.chk_diff_buffers.setChecked(True)
        s=self.p._segments_layer;self.assertIsNotNone(s)
        f=next(s.getFeatures());s.selectByIds([f.id()])
        self.p.dock_panel.set_distances(dict(DEFAULT_DISTANCES,pregeocage=first))
        self.p.dock_panel.btn_apply_segment.click()
        return s
    def buffer(self):return geometry(managed(LAYER_NAME_PREGEOCAGE)[0])
    def choose(self,path,action):
        with patch('auto_buffer_sketcher.plugin.QFileDialog.getSaveFileName',return_value=(str(path),'')):action()
    def test_save_two_segments_independently_and_reopen(self):
        self.seed()
        panel = self.p.dock_panel
        panel.chk_diff_buffers.setChecked(True)
        segments = self.p._segments_layer
        features = sorted(segments.getFeatures(), key=lambda f: f[SEG_FIELD_ID])
        first, second = features[0], features[1]
        segments.selectByIds([first.id()])
        panel.spin_pregeocage.setValue(25)
        panel.spin_geocage.setValue(80)
        self.assertTrue(panel.has_unsaved_segment_changes)
        panel.btn_apply_segment.click()
        self.assertFalse(panel.has_unsaved_segment_changes)
        self.assertIn('distanze salvate', panel.status_label.text())
        segments.selectByIds([second.id()])
        self.assertEqual(panel.spin_pregeocage.value(), 50)
        panel.spin_pregeocage.setValue(40)
        panel.spin_geocage.setValue(90)
        panel.btn_apply_segment.click()
        segments.selectByIds([first.id()])
        self.assertEqual(panel.spin_pregeocage.value(), 25)
        self.assertEqual(panel.spin_geocage.value(), 80)
        self.assertEqual(segments.getFeature(second.id())[SEG_FIELD_PRECAGE], 40)
        self.choose(self.folder/'saved-segments.gpkg', self.p._on_make_persistent)
        project_path = str(self.folder/'saved-segments.qgs')
        self.assertTrue(PROJECT.write(project_path))
        self.assertTrue(PROJECT.read(project_path))
        self.assertTrue(self.p._on_recalc())
        values = BufferEngine._read_segment_distances(self.p._segments_layer)
        self.assertEqual(values[first[SEG_FIELD_ID]]['pregeocage'], 25)
        self.assertEqual(values[first[SEG_FIELD_ID]]['geocage'], 80)
        self.assertEqual(values[second[SEG_FIELD_ID]]['pregeocage'], 40)
        self.assertEqual(values[second[SEG_FIELD_ID]]['geocage'], 90)

    def test_failed_segment_save_does_not_report_success(self):
        self.seed()
        segments = self.diff(20)
        panel = self.p.dock_panel
        panel.spin_pregeocage.setValue(33)
        with patch('auto_buffer_sketcher.plugin.checked', side_effect=ValueError('controlled failure')):
            self.assertFalse(self.p._apply_segment_values(False))
        self.assertIn('Salvataggio distanze non riuscito', panel.status_label.text())
        self.assertEqual(BufferEngine._read_segment_distances(segments)[0]['pregeocage'], 20)
        self.assertTrue(panel.has_unsaved_segment_changes)

    def test_saved_segment_with_failed_recalc_reports_both_states(self):
        self.seed()
        self.diff(20)
        panel = self.p.dock_panel
        panel.spin_pregeocage.setValue(33)
        with patch.object(self.p, '_on_recalc', return_value=False):
            panel.set_status('Ricalcolo interrotto: controlled failure')
            self.assertTrue(self.p._apply_segment_values(False))
        self.assertIn('distanze salvate, ma', panel.status_label.text())
        self.assertIn('controlled failure', panel.status_label.text())
        self.assertFalse(panel.has_unsaved_segment_changes)
        self.assertEqual(BufferEngine._read_segment_distances(self.p._segments_layer)[0]['pregeocage'], 33)

    def test_metric_default_and_zero(self):
        self.seed(BASE[:2]);g=self.buffer()
        self.assertAlmostEqual(g.boundingBox().height(),100)
        self.assertLess(abs(g.area()-(100000+math.pi*2500))/(100000+math.pi*2500),.01)
        self.p.dock_panel.set_distances({k:0 for k in DEFAULT_DISTANCES});self.assertTrue(self.p._on_recalc())
        self.assertTrue(all(l.featureCount()==0 for l in self.p.buffer_engine._output_layers.values()))
    def test_geographic_feet_webmercator_metric_buffers(self):
        for target,metric in [('EPSG:4326','EPSG:32634'),('EPSG:3857','EPSG:32634'),('EPSG:2227','EPSG:32610')]:
            with self.subTest(crs=target):
                ref=QgsCoordinateReferenceSystem(metric);src=QgsCoordinateReferenceSystem(target)
                local=line(BASE[:2]);input_geometry=transformed(local,ref,src)
                route=layer([input_geometry.asWkt(15)],target)
                result=BufferEngine().build_all_buffers(route)[LAYER_NAME_PREGEOCAGE]
                recovered=transformed(result,src,ref)
                self.assertAlmostEqual(recovered.boundingBox().height(),100,delta=.05)
                self.assertLess(abs(recovered.area()-local.buffer(50,8).area()),10)
    def test_unsupported_extent_explicit(self):
        route=layer(['LINESTRING(10 40,30 40)'],'EPSG:4326')
        with self.assertRaisesRegex(ValueError,'Estensione'):BufferEngine().build_all_buffers(route)
    def test_canvas_layer_transform(self):
        self.iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        self.iface.canvas.setExtent(QgsRectangle(18,40,18.02,40.02))
        tool=LineSketcherTool(self.iface.canvas,self.p._route_layer)
        class Click:
            def __init__(self,x):self.x=x
            def button(self):return Qt.LeftButton
            def pos(self):return QPoint(self.x,200)
        tool.canvasPressEvent(Click(250));tool.canvasPressEvent(Click(350))
        expected=tool.toLayerCoordinates(self.p._route_layer,tool._vertices[0])
        tool._finalize_line();actual=geometry(self.p._route_layer).asPolyline()[0]
        self.assertLess(actual.distance(expected),.01)
    def test_auto_manual_segment_equivalence(self):
        fid=self.seed();self.diff(10)
        self.p._route_layer.startEditing();self.p._route_layer.changeGeometry(fid,line([(x,y+10) for x,y in BASE]))
        QTest.qWait(450);automatic=self.buffer()
        self.assertTrue(self.p._on_recalc());manual=self.buffer()
        self.assertLess(automatic.symDifference(manual).area(),1e-5)
        self.assertEqual(BufferEngine._read_segment_distances(self.p._segments_layer)[1]['pregeocage'],50)
    def test_split_inherits_and_moves_update(self):
        fid=self.seed();self.diff(20)
        self.p._route_layer.startEditing()
        self.p._route_layer.changeGeometry(fid,line([BASE[0],(500500,4500100),BASE[1],BASE[2]]))
        self.assertTrue(self.p._on_recalc())
        s=self.p._segments_layer;self.assertEqual(s.featureCount(),3)
        self.assertEqual([v['pregeocage'] for v in BufferEngine._read_segment_distances(s).values()],[20,20,50])
        self.assertTrue(self.p._route_layer.commitChanges())
    def test_conflicting_merge_keeps_last_valid_result(self):
        fid=self.seed();s=self.diff(20);before=self.buffer()
        self.p._route_layer.startEditing();self.p._route_layer.changeGeometry(fid,line([BASE[0],BASE[-1]]))
        self.assertFalse(self.p._on_recalc());self.assertIn('distanze diverse',self.p.dock_panel.status_label.text())
        self.assertEqual(s.featureCount(),2);self.assertTrue(before.equals(self.buffer()))
        self.p.dock_panel.set_distances(dict(DEFAULT_DISTANCES,pregeocage=30))
        self.p.dock_panel.btn_apply_all.click();self.assertEqual(s.featureCount(),1)
        self.assertEqual(BufferEngine._read_segment_distances(s)[0]['pregeocage'],30)
    def test_diff_rollback_restores_attributes_and_topology(self):
        fid=self.seed();s=self.diff(20);before=self.buffer()
        self.p._route_layer.startEditing()
        self.p._route_layer.changeGeometry(fid,line([BASE[0],(500500,4500000),BASE[1],BASE[2]]));self.assertTrue(self.p._on_recalc())
        self.assertEqual(s.featureCount(),3)
        self.assertTrue(self.p._route_layer.rollBack());QTest.qWait(450)
        self.assertEqual(s.featureCount(),2)
        self.assertLess(before.symDifference(self.buffer()).area(),1e-5)
        self.assertEqual(BufferEngine._read_segment_distances(s)[0]['pregeocage'],20)
    def test_multiple_routes_delete_retains_other_route_values(self):
        first=self.seed();second=self.seed([(x+10000,y) for x,y in BASE]);s=self.diff(20)
        owners={str(f[ROUTE_KEY]) for f in s.getFeatures()};self.assertEqual(len(owners),2)
        self.p._route_layer.startEditing();self.p._route_layer.deleteFeature(second);self.assertTrue(self.p._on_recalc())
        self.assertEqual(s.featureCount(),2);self.assertEqual(BufferEngine._read_segment_distances(s)[0]['pregeocage'],20)
    def test_invalid_segment_schema_explicit(self):
        self.seed();self.diff();s=self.p._segments_layer
        s.dataProvider().deleteAttributes([s.fields().indexFromName('ground_m')]);s.updateFields()
        self.assertFalse(self.p._on_recalc());self.assertIn('Schema',self.p.dock_panel.status_label.text())
    def test_unload_disconnects_only_own_segment_callback(self):
        self.seed();s=self.diff();called=[]
        callback=lambda *args:called.append(1)
        s.selectionChanged.connect(callback);before=s.receivers(s.selectionChanged)
        self.p.unload()
        self.assertEqual(s.receivers(s.selectionChanged),before-1)
        s.removeSelection();self.assertTrue(called)
        self.assertFalse(self.iface.icons);self.assertFalse(self.iface.menus)
    def test_persistence_preserves_unrelated_table_and_reopen_state(self):
        self.seed();self.diff(20);before=self.buffer()
        path=self.folder/'persist.gpkg';sentinel=layer(['LINESTRING(1 1,2 2)'],name='unrelated')
        write_geopackage([sentinel],path,PROJECT)
        self.choose(path,self.p._on_make_persistent)
        self.assertEqual(len(tables(path)),7)
        self.assertIn('unrelated',tables(path))
        self.assertEqual(self.p._route_layer.providerType(),'ogr')
        qgs=self.folder/'state.qgs';self.assertTrue(PROJECT.write(str(qgs)))
        self.p.unload();PROJECT.clear();self.assertTrue(PROJECT.read(str(qgs)))
        self.p=classFactory(self.iface);self.p.initGui();self.p._ensure_route_layer()
        self.assertTrue(self.p.dock_panel.is_diff_buffers)
        self.p.event_handler.force_update()
        self.assertLess(before.symDifference(self.buffer()).area(),1e-4)
    def test_persistence_cancel_and_failure_keep_project_and_file(self):
        self.seed();ids=set(PROJECT.mapLayers());self.choose('',self.p._on_make_persistent)
        self.assertEqual(set(PROJECT.mapLayers()),ids)
        path=self.folder/'failed.gpkg';sentinel=layer(['LINESTRING(1 1,2 2)'],name='unrelated')
        write_geopackage([sentinel],path,PROJECT);before=path.read_bytes()
        with patch('auto_buffer_sketcher.file_io.QgsVectorFileWriter.writeAsVectorFormatV3',return_value=(1,'simulated error','','')):
            self.choose(path,self.p._on_make_persistent)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(set(PROJECT.mapLayers()),ids)
        self.assertEqual(self.p._route_layer.providerType(),'memory')
    def test_refuse_overwriting_open_datasource(self):
        self.seed();path=self.folder/'persist.gpkg';self.choose(path,self.p._on_make_persistent)
        before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'già aperto'):
            write_geopackage([self.p._route_layer],path,PROJECT)
        self.assertEqual(path.read_bytes(),before)
    def test_standard_export_preserves_unrelated_and_explains_scope(self):
        self.seed();self.diff();path=self.folder/'export.gpkg'
        sentinel=layer(['LINESTRING(1 1,2 2)'],name='unrelated');write_geopackage([sentinel],path,PROJECT)
        self.choose(path,self.p._on_export)
        self.assertEqual(len(tables(path)),6);self.assertIn('unrelated',tables(path))
        self.assertIn('segmenti',self.p.dock_panel.status_label.text())
    def test_geojson_all_routes_multipart_holes_and_crs(self):
        route=layer(['MULTILINESTRING((500000 4500000,501000 4500000),(510000 4500000,511000 4500000))','MULTILINESTRING((520000 4500000,521000 4500000))'],kind='MultiLineString')
        poly=layer(['MULTIPOLYGON(((18 40,18.1 40,18.1 40.1,18 40.1,18 40),(18.02 40.02,18.02 40.04,18.04 40.04,18.04 40.02,18.02 40.02)),((19 40,19.1 40,19.1 40.1,19 40.1,19 40)))'],'EPSG:4326',kind='MultiPolygon')
        path=self.folder/'export.geojson';ex=GeoJSONExporter();self.assertTrue(ex.export(route,{'pregeocage':poly},str(path)),ex.last_error)
        features=json.loads(path.read_text())['features'];routes=[f for f in features if f['properties']['type']=='route']
        self.assertEqual(len(routes),2);self.assertEqual(routes[0]['geometry']['type'],'MultiLineString')
        polygons=[f for f in features if f['properties']['type']=='pregeocage'][0]['geometry']
        self.assertEqual(polygons['type'],'MultiPolygon');self.assertEqual(len(polygons['coordinates']),2)
        self.assertEqual(len(polygons['coordinates'][0]),2);self.assertEqual(polygons['coordinates'][0][0][0],[18,40])
        waypoints=[f for f in features if f['properties']['type']=='waypoint'];self.assertEqual(len(waypoints),6)
        self.assertEqual([f['properties']['seq'] for f in waypoints],list(range(1,7)))
    def test_plan_short_missing_or_unsupported_does_not_replace_file(self):
        path=self.folder/'existing.plan';path.write_text('keep original')
        ex=PlanExporter();short=layer([line(BASE[:2]).asWkt()])
        self.assertFalse(ex.export(short,{},DEFAULT_DISTANCES,{},str(path)))
        self.assertIn('3 vertici',ex.last_error);self.assertEqual(path.read_text(),'keep original')
        valid=layer([line().asWkt()]);self.assertFalse(ex.export(valid,{},DEFAULT_DISTANCES,{},str(path)))
        self.assertIn('mancante',ex.last_error);self.assertEqual(path.read_text(),'keep original')
    def test_plan_multiple_routes_require_explicit_selection(self):
        route=layer([line().asWkt(),line([(x+10000,y) for x,y in BASE]).asWkt()])
        ex=PlanExporter()
        with self.assertRaisesRegex(ValueError,'selezionare'):ex._build_mission_items(route,{})
        route.selectByIds([list(route.getFeatures())[1].id()])
        items=ex._build_mission_items(route,{})
        first=items[0];expected=QgsCoordinateTransform(route.crs(),QgsCoordinateReferenceSystem('EPSG:4326'),PROJECT).transform(QgsPointXY(510000,4500000))
        self.assertAlmostEqual(first['lon'],expected.x());self.assertEqual(items[-1]['command'],21)
    def test_plan_rejects_holes_and_disconnected_parts(self):
        poly=layer(['MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)),((2 0,3 0,3 1,2 1,2 0)))'],kind='MultiPolygon')
        with self.assertRaisesRegex(ValueError,'parti separate'):PlanExporter()._build_geofence({'ground':poly},poly.crs(),{})
        hole=layer(['POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,2 4,4 4,4 2,2 2))'],kind='Polygon')
        with self.assertRaisesRegex(ValueError,'buchi'):PlanExporter()._build_geofence({'ground':hole},hole.crs(),{})
    def test_plan_geofence_uses_own_crs_and_disabled_omitted(self):
        route=layer([line(BASE+[(503000,4500000)]).asWkt()])
        poly=layer(['POLYGON((18 40,18.01 40,18.01 40.01,18 40.01,18 40))'],'EPSG:4326',kind='Polygon')
        path=self.folder/'valid.plan';ex=PlanExporter()
        self.assertTrue(ex.export(route,{'pregeocage':poly},dict(pregeocage=50,geocage=0,ground=0,adjacent=0),{},str(path)),ex.last_error)
        data=json.loads(path.read_text());self.assertEqual(len(data['geoFence']['polygons']),1)
        self.assertEqual(data['geoFence']['polygons'][0]['vertices'][0],{'lat':40,'lon':18})
        self.assertEqual([x['command'] for x in data['mission']],[22,3000,16,3000,21])
    def test_route_removed_recreated_and_callbacks_reload(self):
        self.seed();old=self.p._route_layer.id();PROJECT.removeMapLayer(old);self.p._ensure_route_layer()
        self.assertNotEqual(self.p._route_layer.id(),old)
        for _ in range(3):
            self.p.unload();self.p=classFactory(self.iface);self.p.initGui();self.p._ensure_route_layer()
            self.assertEqual(len(self.iface.icons),1)

    def test_selected_route_buffers_do_not_include_other_routes(self):
        self.seed();second=self.seed([(x+20000,y) for x,y in BASE]);self.diff(20)
        self.p._route_layer.selectByIds([second])
        route,buffers=self.p._plan_export_layers()
        g=geometry(buffers['pregeocage'])
        self.assertGreater(g.boundingBox().xMinimum(),519900)
        self.assertAlmostEqual(g.boundingBox().height(),100)
        self.assertEqual(route.featureCount(),1)
    def test_renamed_layers_remain_managed(self):
        self.seed();self.diff(20)
        self.p._route_layer.setName('My route')
        self.p._segments_layer.setName('My segments')
        before=self.buffer();self.p._ensure_route_layer();self.assertEqual(self.p._route_layer.name(),'My route')
        self.assertTrue(self.p._on_recalc());self.assertTrue(before.equals(self.buffer()))
        self.assertEqual(self.p._segments_layer.name(),'My segments')
        path=self.folder/'renamed.gpkg';self.choose(path,self.p._on_make_persistent)
        self.assertEqual(self.p._route_layer.name(),'My route')
        self.assertEqual(self.p._route_layer.providerType(),'ogr')
        self.assertEqual(self.p._segments_layer.name(),'My segments')
    def test_ui_export_refreshes_deleted_buffer(self):
        self.seed();old=managed(LAYER_NAME_PREGEOCAGE)[0]
        PROJECT.removeMapLayer(old.id())
        path=self.folder/'ui.geojson';self.choose(path,self.p._on_export_geojson)
        self.assertTrue(path.exists(),self.p.dock_panel.status_label.text())
        kinds={f['properties']['type'] for f in json.loads(path.read_text())['features']}
        self.assertTrue({'pregeocage','geocage','ground','adjacent'} <= kinds)
    def test_persistence_refuses_active_edits(self):
        self.seed();self.p._route_layer.startEditing()
        self.p._route_layer.changeGeometry(next(self.p._route_layer.getFeatures()).id(),line([(x,y+5) for x,y in BASE]))
        path=self.folder/'edit.gpkg';self.choose(path,self.p._on_make_persistent)
        self.assertFalse(path.exists());self.assertTrue(self.p._route_layer.isEditable())
        self.assertIn('modifiche',self.p.dock_panel.status_label.text())
    def test_invalid_distances_fail_explicitly(self):
        route=layer([line().asWkt()])
        for value in (float('nan'),float('inf'),-1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'non negativi'):
                BufferEngine().build_all_buffers(route,dict(DEFAULT_DISTANCES,pregeocage=value))
    def test_plan_enabled_segment_buffer_is_not_dropped_for_zero_global_distance(self):
        route=layer([line().asWkt()]);poly=layer(['POLYGON((18 40,18.01 40,18.01 40.01,18 40.01,18 40))'],'EPSG:4326',kind='Polygon')
        path=self.folder/'nonempty.plan';ex=PlanExporter()
        self.assertTrue(ex.export(route,{'pregeocage':poly},{k:0 for k in DEFAULT_DISTANCES},{},str(path)),ex.last_error)
        self.assertEqual(len(json.loads(path.read_text())['geoFence']['polygons']),1)
    def test_edit_and_delete_buttons_preserve_other_pending_edits(self):
        first=self.seed();self.seed([(x+10000,y) for x,y in BASE])
        self.p._route_layer.startEditing()
        self.p._route_layer.changeGeometry(first,line([(x,y+100) for x,y in BASE]))
        self.p._route_layer.selectByIds([first]);self.p._delete_pending=True
        self.p._on_delete_requested()
        self.assertTrue(self.p._route_layer.isEditable())
        self.assertEqual(self.p._route_layer.featureCount(),1)
        self.assertTrue(self.p._route_layer.rollBack())
        self.assertEqual(self.p._route_layer.featureCount(),2)

    def _check_delete_leaves_edit_tool(self, count):
        first = self.seed()
        if count == 2:
            self.seed([(x+10000,y) for x,y in BASE])
        canvas = self.iface.canvas
        route = self.p._route_layer

        class EditTool(QgsMapToolEmitPoint):
            # Exercise the public map-tool lifecycle; the native vertex tool is
            # additionally checked in the isolated QGIS application integration.
            def __init__(self):
                super().__init__(canvas)
                self.band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
                self.band.setToGeometry(line(), route)
            def deactivate(self):
                self.band.hide()
                super().deactivate()

        edit = EditTool()
        select = QgsMapToolEmitPoint(canvas)
        other = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        other.setToGeometry(line(), self.p._route_layer)
        KEEP.extend((edit, select, other))
        self.iface.vertex.triggered.connect(lambda: canvas.setMapTool(edit))
        self.iface.select.triggered.connect(lambda: canvas.setMapTool(select))
        self.p._on_edit_requested()
        self.assertIs(canvas.mapTool(), edit)
        self.assertTrue(edit.band.isVisible())
        self.p._route_layer.changeGeometry(first, line([(x,y+100) for x,y in BASE]))
        self.p._on_delete_requested()
        self.assertIs(canvas.mapTool(), select)
        self.assertFalse(edit.band.isVisible())
        self.assertTrue(other.isVisible())  # Do not sweep other tools' overlays.
        self.p._route_layer.selectByIds([first])
        self.p._on_delete_requested()
        self.assertEqual(self.p._route_layer.featureCount(), count-1)
        self.assertTrue(self.p._route_layer.isEditable())
        self.assertTrue(self.p._route_layer.rollBack())
        self.assertEqual(self.p._route_layer.featureCount(), count)
        other.hide()

    def test_single_route_delete_clears_edit_overlay_without_committing_user_edits(self):
        self._check_delete_leaves_edit_tool(1)

    def test_multiple_route_delete_clears_only_the_edit_tools_overlay(self):
        self._check_delete_leaves_edit_tool(2)

    def test_loaded_plugin_restores_project_read_without_duplicate_actions(self):
        self.seed();self.diff(20);path=self.folder/'restore.gpkg'
        self.choose(path,self.p._on_make_persistent)
        before=self.buffer();qgs=self.folder/'restore.qgs';self.assertTrue(PROJECT.write(str(qgs)))
        self.assertTrue(PROJECT.read(str(qgs)))
        self.assertTrue(self.p.dock_panel.is_diff_buffers)
        self.p.event_handler.force_update()
        self.assertLess(before.symDifference(self.buffer()).area(),1e-4)
        self.assertEqual(len(self.iface.icons),1)
    def test_legacy_polygon_memory_layer_keeps_disconnected_buffers(self):
        self.seed();old=managed(LAYER_NAME_PREGEOCAGE)[0]
        PROJECT.removeMapLayer(old.id())
        legacy=layer([],kind='Polygon',name=LAYER_NAME_PREGEOCAGE);PROJECT.addMapLayer(legacy)
        self.seed([(x+20000,y) for x,y in BASE])
        self.assertTrue(self.p._on_recalc())
        self.assertEqual(legacy.featureCount(),2)
        union=QgsGeometry.unaryUnion([f.geometry() for f in legacy.getFeatures()])
        self.assertEqual(len(union.asGeometryCollection()),2)

    def test_corrupted_segment_selection_reports_error_without_escaping_qt(self):
        self.seed();s=self.diff();s.removeSelection()
        s.dataProvider().deleteAttributes([s.fields().indexFromName('ground_m')]);s.updateFields()
        s.selectByIds([next(s.getFeatures()).id()])
        self.assertIn('Schema',self.p.dock_panel.status_label.text())
        self.assertFalse(self.p.dock_panel.btn_apply_segment.isEnabled())

    def test_legacy_project_adopted_in_place_with_segment_distances(self):
        self.p.unload();PROJECT.clear()
        old_route=layer([line().asWkt()],name='ABC Route Line');PROJECT.addMapLayer(old_route)
        engine=BufferEngine();segments=engine.create_segments_layer(old_route,DEFAULT_DISTANCES,PROJECT)
        segments.setName('ABC Segments');segments.removeCustomProperty('abs/role')
        first=next(segments.getFeatures())
        segments.dataProvider().changeAttributeValues({first.id():{segments.fields().indexFromName('pregeocage_m'):20}})
        expected=engine.build_all_buffers(old_route,DEFAULT_DISTANCES,segments)
        engine.update_output_layers(PROJECT,expected,old_route.crs())
        for role,l in engine._output_layers.items():
            l.setName(role);l.removeCustomProperty('abs/role')
        ids=set(PROJECT.mapLayers());route_fids=[f.id() for f in old_route.getFeatures()]
        self.p=classFactory(self.iface);self.p.initGui();self.p._ensure_route_layer()
        self.assertEqual(self.p.dock_panel.windowTitle(),'ABS - AutoBufferSketcher')
        self.assertEqual(self.p.actions[0].text(),'ABS - AutoBufferSketcher')
        self.assertTrue(self.p.dock_panel.is_diff_buffers)
        self.assertTrue(self.p._on_recalc())
        self.assertEqual(set(PROJECT.mapLayers()),ids)
        self.assertEqual(self.p._route_layer.name(),'ABS - Rotta')
        self.assertEqual(self.p._segments_layer.name(),'ABS - Segmenti')
        self.assertEqual(managed(LAYER_NAME_PREGEOCAGE)[0].name(),'ABS - Pregeocage')
        self.assertEqual([f.id() for f in old_route.getFeatures()],route_fids)
        values=BufferEngine._read_segment_distances(self.p._segments_layer)
        self.assertEqual(values[0]['pregeocage'],20)
        self.assertEqual(values[1]['pregeocage'],50)
        self.assertLess(expected[LAYER_NAME_PREGEOCAGE].symDifference(self.buffer()).area(),1e-5)
    def test_abs_layer_titles_recognized_without_custom_properties(self):
        self.seed();self.diff(20);before=self.buffer();ids=set(PROJECT.mapLayers())
        self.p.unload()
        for l in PROJECT.mapLayers().values():
            for key in list(l.customPropertyKeys()):l.removeCustomProperty(key)
        self.p=classFactory(self.iface);self.p.initGui();self.p._ensure_route_layer()
        self.assertTrue(self.p.dock_panel.is_diff_buffers)
        self.assertTrue(self.p._on_recalc())
        self.assertEqual(set(PROJECT.mapLayers()),ids)
        self.assertLess(before.symDifference(self.buffer()).area(),1e-5)
    def test_legacy_geopackage_rename_preserves_uri_table_and_features(self):
        self.p.unload();PROJECT.clear()
        legacy=layer([line().asWkt()],name='ABC Route Line');PROJECT.addMapLayer(legacy)
        path=self.folder/'legacy.gpkg';write_geopackage([legacy],path,PROJECT);PROJECT.clear()
        restored=QgsVectorLayer(f'{path}|layername=ABC Route Line','ABC Route Line','ogr')
        self.assertTrue(restored.isValid());PROJECT.addMapLayer(restored)
        uri=restored.source();features=[(f.id(),f.geometry().asWkt()) for f in restored.getFeatures()]
        layer_id=restored.id()
        self.p=classFactory(self.iface);self.p.initGui();self.p._ensure_route_layer()
        self.assertEqual(self.p._route_layer.id(),layer_id)
        self.assertEqual(restored.name(),'ABS - Rotta');self.assertEqual(restored.source(),uri)
        self.assertTrue(self.p._on_recalc())
        self.assertEqual(tables(path),['ABC Route Line'])
        self.assertEqual(features,[(f.id(),f.geometry().asWkt()) for f in restored.getFeatures()])

if __name__=='__main__':
    print('QGIS',Qgis.QGIS_VERSION,flush=True)
    unittest.main(verbosity=2)
