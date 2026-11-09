"""Lossless GeoJSON geometry export in WGS84, including all parts and rings."""
from qgis.core import QgsMessageLog, Qgis
from .branding import PLUGIN_NAME
from .geometry_utils import as_wgs84_json
from .file_io import write_json


class GeoJSONExporter:
    def __init__(self):
        self.last_error = ''

    def export(self, route_layer, buffer_layers_dict, output_path):
        try:
            if not route_layer or not route_layer.isValid():
                raise ValueError('Layer rotta non valido.')
            features = []
            sequence = 0
            for route in route_layer.getFeatures():
                geom = route.geometry()
                if geom.isNull() or geom.isEmpty():
                    continue
                geometry = as_wgs84_json(geom, route_layer.crs())
                if geometry['type'] not in ('LineString', 'MultiLineString'):
                    raise ValueError('La rotta deve essere una geometria lineare.')
                features.append({'type': 'Feature', 'geometry': geometry, 'properties': {
                    'name': route_layer.name(), 'type': 'route', 'route_id': route.id()}})
                parts = geometry['coordinates'] if geometry['type'] == 'MultiLineString' else [geometry['coordinates']]
                for part_index, points in enumerate(parts):
                    for point in points:
                        sequence += 1
                        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': point},
                            'properties': {'seq': sequence, 'type': 'waypoint', 'name': f'Waypoint {sequence}',
                                'route_id': route.id(), 'part': part_index}})
            if not features:
                raise ValueError('Nessuna rotta da esportare.')
            for key, layer in buffer_layers_dict.items():
                if layer is None or not layer.isValid():
                    continue
                for feature in layer.getFeatures():
                    geom = feature.geometry()
                    if geom.isNull() or geom.isEmpty():
                        continue
                    geometry = as_wgs84_json(geom, layer.crs())
                    if geometry['type'] not in ('Polygon', 'MultiPolygon'):
                        raise ValueError(f'Geometria buffer non poligonale: {layer.name()}')
                    features.append({'type': 'Feature', 'geometry': geometry,
                        'properties': {'name': layer.name(), 'type': key}})
            write_json(output_path, {'type': 'FeatureCollection', 'features': features})
            self.last_error = ''
            return True
        except Exception as error:
            self.last_error = str(error)
            QgsMessageLog.logMessage(self.last_error, PLUGIN_NAME, Qgis.Critical)
            return False
