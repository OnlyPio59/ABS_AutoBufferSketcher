import os
import sys
import json

# Aggiunge la directory principale del plugin al path di importazione di Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Inizializza QGIS
from qgis.core import (
    QgsApplication,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsCoordinateReferenceSystem,
)

def run_test():
    # Inizializza QgsApplication in modalità non GUI
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        from auto_buffer_sketcher.plan_exporter import PlanExporter
        from auto_buffer_sketcher.geojson_exporter import GeoJSONExporter

        print("--- Creazione layer di test in memoria ---")
        crs = "EPSG:3857"
        route_layer = QgsVectorLayer("LineString?crs=" + crs, "Test Route", "memory")
        prov = route_layer.dataProvider()
        
        # Rotta a 4 punti
        p1 = QgsPointXY(2005000, 4866000)
        p2 = QgsPointXY(2006000, 4867000)
        p3 = QgsPointXY(2007000, 4868000)
        p4 = QgsPointXY(2008000, 4869000)
        
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([p1, p2, p3, p4]))
        prov.addFeatures([feat])
        route_layer.updateExtents()
        print(f"Layer rotta creato: {route_layer.featureCount()} feature.")

        # Crea i layer di buffer fittizi
        buffer_layers = {}
        for key, name in [
            ("pregeocage", "ABC Pregeocage Buffer"),
            ("geocage", "ABC Geocage Buffer"),
            ("ground", "ABC Ground Buffer"),
            ("adjacent", "ABC Adjacent Area Buffer")
        ]:
            lyr = QgsVectorLayer("Polygon?crs=" + crs, name, "memory")
            p_prov = lyr.dataProvider()
            f_buf = QgsFeature()
            
            offset_val = {"pregeocage": 50, "geocage": 100, "ground": 150, "adjacent": 5000}[key]
            
            poly_points = [
                QgsPointXY(2005000 - offset_val, 4866000 - offset_val),
                QgsPointXY(2008000 + offset_val, 4869000 + offset_val),
                QgsPointXY(2008000 + offset_val, 4869000 - offset_val),
                QgsPointXY(2005000 - offset_val, 4866000 - offset_val)
            ]
            f_buf.setGeometry(QgsGeometry.fromPolygonXY([poly_points]))
            p_prov.addFeatures([f_buf])
            lyr.updateExtents()
            buffer_layers[key] = lyr
            print(f"Layer buffer {key} creato: {lyr.featureCount()} feature.")

        # -----------------------------------------------------------------
        # TEST PLAN EXPORTER
        # -----------------------------------------------------------------
        print("\n=== TEST 1: PLAN EXPORTER ===")
        distances = {
            "pregeocage": 50.0,
            "geocage": 100.0,
            "ground": 150.0,
            "adjacent": 5000.0
        }
        config = {
            "alt_flight": 120.0,
            "alt_pad": 40.0,
            "geoid_offset": 39.27
        }
        output_plan = "/tmp/test_output.plan"

        exporter_plan = PlanExporter()
        success_plan = exporter_plan.export(route_layer, buffer_layers, distances, config, output_plan)
        assert success_plan, "L'esportazione plan ha fallito!"
        print(f"Esportazione plan riuscita! Scritto in {output_plan}")

        with open(output_plan, 'r') as f:
            plan_data = json.load(f)

        assert "uuid" in plan_data
        assert len(plan_data["geoFence"]["polygons"]) == 4
        assert len(plan_data["mission"]) == 5
        print("✅ Struttura .plan validata con successo")

        # -----------------------------------------------------------------
        # TEST GEOJSON EXPORTER
        # -----------------------------------------------------------------
        print("\n=== TEST 2: GEOJSON EXPORTER ===")
        output_geojson = "/tmp/test_output.geojson"
        
        exporter_geojson = GeoJSONExporter()
        success_geojson = exporter_geojson.export(route_layer, buffer_layers, output_geojson)
        assert success_geojson, "L'esportazione GeoJSON ha fallito!"
        print(f"Esportazione GeoJSON riuscita! Scritto in {output_geojson}")

        with open(output_geojson, 'r') as f:
            geojson_data = json.load(f)

        assert "type" in geojson_data and geojson_data["type"] == "FeatureCollection"
        assert "features" in geojson_data
        
        features = geojson_data["features"]
        print(f"Numero di features esportate in GeoJSON: {len(features)}")
        
        assert len(features) == 9, f"Dovrebbero esserci 9 feature, trovate {len(features)}"
        
        types = [f["geometry"]["type"] for f in features]
        assert types.count("LineString") == 1
        assert types.count("Point") == 4
        assert types.count("Polygon") == 4
        
        routes = [f for f in features if f["properties"].get("type") == "route"]
        waypoints = [f for f in features if f["properties"].get("type") == "waypoint"]
        buffers = [f for f in features if f["properties"].get("type") in ["pregeocage", "geocage", "ground", "adjacent"]]
        
        assert len(routes) == 1
        assert len(waypoints) == 4
        assert len(buffers) == 4
        
        seqs = sorted([w["properties"]["seq"] for w in waypoints])
        assert seqs == [1, 2, 3, 4]
        
        print("✅ Struttura GeoJSON validata con successo")

        print("\n🎉 TUTTI I TEST SONO PASSATI CON SUCCESSO!")

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    run_test()
