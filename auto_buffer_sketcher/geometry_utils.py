"""Coordinate operations shared by the engine and exporters."""
import json
import math
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsProject


def transformed(geometry, source, destination):
    if not source.isValid() or not destination.isValid():
        raise ValueError('CRS non valido: definire il sistema di riferimento dei layer.')
    result = QgsGeometry(geometry)
    if source != destination and not result.isEmpty():
        operation = QgsCoordinateTransform(source, destination, QgsProject.instance())
        if result.transform(operation) != 0:
            raise ValueError('Trasformazione delle coordinate non riuscita.')
    for point in result.vertices():
        if not math.isfinite(point.x()) or not math.isfinite(point.y()):
            raise ValueError('Coordinate non finite dopo la trasformazione.')
    return result


def metric_crs(layer):
    """Local UTM for regional routes; preserve a suitable existing WGS84 UTM CRS.

    Explicitly reject wide extents/polar/antimeridian cases instead of buffering
    degrees, feet or Web Mercator coordinates as if they were ground metres.
    """
    wgs = QgsCoordinateReferenceSystem('EPSG:4326')
    points = []
    for feature in layer.getFeatures():
        g = transformed(feature.geometry(), layer.crs(), wgs)
        points.extend((p.x(), p.y()) for p in g.vertices())
    if not points:
        return layer.crs()
    xs, ys = zip(*points)
    lon, lat = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    if min(xs) < -180 or max(xs) > 180 or min(ys) < -80 or max(ys) > 84:
        raise ValueError('Calcolo metrico locale supportato fra 80° S e 84° N; verificare il CRS della rotta.')
    if max(xs)-min(xs) > 6 or max(ys)-min(ys) > 6:
        raise ValueError('Estensione troppo ampia per il calcolo UTM locale: suddividere la rotta in aree locali.')
    zone = max(1, min(60, int((lon+180)//6)+1))
    epsg = (32600 if lat >= 0 else 32700) + zone
    auth = layer.crs().authid()
    # Retain the original UTM coordinate system if it covers this local extent.
    if auth.startswith('EPSG:'):
        code = int(auth.split(':')[1])
        old_zone = code % 100
        if (32601 <= code <= 32660 or 32701 <= code <= 32760):
            centre = old_zone*6-183
            if min(xs) >= centre-3.1 and max(xs) <= centre+3.1 and (code < 32700) == (lat >= 0):
                epsg = code
    return QgsCoordinateReferenceSystem(f'EPSG:{epsg}')


def as_wgs84_json(geometry, crs):
    return json.loads(transformed(geometry, crs, QgsCoordinateReferenceSystem('EPSG:4326')).asJson(15))
