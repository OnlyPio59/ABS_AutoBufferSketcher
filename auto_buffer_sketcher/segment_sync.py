"""Stable route ownership and explicit distance inheritance during topology edits."""

from .i18n import tr
from .qt_compat import field_type
import uuid
import math
from qgis.core import QgsField, QgsFeature, QgsGeometry
from qgis.PyQt.QtCore import QMetaType, QSignalBlocker
from .layer_edits import edit_layer, checked

ROUTE_KEY = 'abs_route'
PART = 'abs_part'
POSITION = 'abs_pos'
DISTANCE_FIELDS = ('pregeocage_m','geocage_m','ground_m','adjacent_m')
REQUIRED = ('seg_id',) + DISTANCE_FIELDS


def validate(layer):
    if not layer.isValid() or layer.geometryType() != 1:
        raise ValueError(tr('Layer segmenti non lineare o non valido.'))
    missing = set(REQUIRED) - set(layer.fields().names())
    if missing:
        raise ValueError(tr('Schema segmenti incompleto: ')+', '.join(sorted(missing)))
    seen = set()
    for feature in layer.getFeatures():
        try:
            identifier = int(feature['seg_id'])
            values = [float(feature[field]) for field in DISTANCE_FIELDS]
        except (TypeError, ValueError):
            raise ValueError(tr('Attributi dei segmenti non numerici o mancanti.'))
        if identifier in seen:
            raise ValueError(tr('Identificatori dei segmenti duplicati.'))
        seen.add(identifier)
        if any(not math.isfinite(value) or value < 0 or value > 50000 for value in values):
            raise ValueError(tr('Distanze dei segmenti non valide (intervallo 0–50000 m).'))


def parts(geometry):
    if geometry.isEmpty():
        return []
    return geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]


def _key(point):
    # Coordinates are in the route CRS. Rounding is only used to match unchanged vertices.
    return (round(point.x(), 8), round(point.y(), 8))


def synchronize(source, segments, defaults):
    from .buffer_engine import BufferEngine
    validate(segments)
    if source.crs() != segments.crs():
        raise ValueError(tr('CRS rotta/segmenti differenti: ripristinare il layer segmenti originale.'))
    if ROUTE_KEY not in source.fields().names():
        with edit_layer(source, tr('Identificatori stabili delle rotte')):
            checked(source.addAttribute(QgsField(ROUTE_KEY, field_type(QMetaType.Type.QString), len=36)), tr('Campo identificatore non creato.'))
    seen = set()
    needs = []
    for feature in source.getFeatures():
        value = str(feature[ROUTE_KEY]) if feature[ROUTE_KEY] else ''
        if value in ('NULL','None') or not value or value in seen:
            value = str(uuid.uuid4());needs.append((feature.id(), value))
        seen.add(value)
    if needs:
        with edit_layer(source, tr('Identificatori delle rotte')):
            for fid, value in needs:
                checked(source.changeAttributeValue(fid, source.fields().indexFromName(ROUTE_KEY), value), tr('Identificatore rotta non salvato.'))
    route_parts = []
    for feature in source.getFeatures():
        for part_index, points in enumerate(parts(feature.geometry())):
            route_parts.append((str(feature[ROUTE_KEY]), part_index, points))
    old = list(segments.getFeatures())
    modern = all(f in segments.fields().names() for f in (ROUTE_KEY, PART, POSITION))
    by_part = {}
    if modern:
        for f in old:
            by_part.setdefault((str(f[ROUTE_KEY]), int(f[PART])), []).append(f)
        for features in by_part.values():
            features.sort(key=lambda f: int(f[POSITION]))
    else:
        # Legacy seg_id was global across route features. Migration happens before editing.
        legacy = sorted(old, key=lambda f: f['seg_id'])
        offset = 0
        for key, part_index, points in route_parts:
            count = max(0, len(points)-1)
            candidates = legacy[offset:offset+count]
            if len(candidates) != count or any(not f.geometry().equals(QgsGeometry.fromPolylineXY(points[n:n+2])) for n,f in enumerate(candidates)):
                raise ValueError(tr('Segmenti storici non allineati alla rotta: ripristinare il progetto prima della modifica o uniformare i buffer.'))
            by_part[(key,part_index)] = candidates
            offset += count
        if offset != len(legacy):
            raise ValueError(tr('Segmenti storici non associabili alla rotta corrente.'))
    rows = []
    for key, part_index, points in route_parts:
        existing = by_part.get((key,part_index), [])
        old_points = []
        for f in existing:
            p = f.geometry().asPolyline()
            if not old_points:
                old_points.append(p[0])
            old_points.append(p[-1])
        old_keys = [_key(p) for p in old_points]
        new_keys = [_key(p) for p in points]
        for pos in range(len(points)-1):
            geometry = QgsGeometry.fromPolylineXY(points[pos:pos+2])
            matches = [f for f in existing if f.geometry().equals(geometry)]
            if not matches and len(existing) == len(points)-1:
                matches = [existing[pos]]
            if not matches:
                # Split: both old endpoints still exist in the new vertex chain.
                for n, f in enumerate(existing):
                    if old_keys[n] in new_keys and old_keys[n+1] in new_keys:
                        lo, hi = sorted((new_keys.index(old_keys[n]),new_keys.index(old_keys[n+1])))
                        if lo <= pos < hi:
                            matches = [f];break
            if not matches and new_keys[pos] in old_keys and new_keys[pos+1] in old_keys:
                lo,hi = sorted((old_keys.index(new_keys[pos]),old_keys.index(new_keys[pos+1])))
                matches = existing[lo:hi]
            values = [tuple(float(f[name]) for name in DISTANCE_FIELDS) for f in matches]
            if len(set(values)) > 1:
                raise ValueError(tr('Unione di segmenti con distanze diverse: scegliere i valori e usare Applica a Tutti i Segmenti, oppure annullare la modifica.'))
            if not values and existing:
                raise ValueError(tr('Topologia segmenti ambigua: annullare la modifica o disattivare e riattivare la modalità differenziata per usare distanze uniformi.'))
            distances = values[0] if values else tuple(defaults[k] for k in ('pregeocage','geocage','ground','adjacent'))
            rows.append((key,part_index,pos,geometry,distances))
    if modern and len(old)==len(rows):
        ordered=sorted(old,key=lambda f:f['seg_id'])
        if all(str(f[ROUTE_KEY])==key and int(f[PART])==pi and int(f[POSITION])==pos and f.geometry().equals(g) and tuple(float(f[n]) for n in DISTANCE_FIELDS)==values for f,(key,pi,pos,g,values) in zip(ordered,rows)):
            return
    selected = {(str(f[ROUTE_KEY]),int(f[PART]),int(f[POSITION])) for f in segments.selectedFeatures()} if modern else set()
    blocker = QSignalBlocker(segments)
    try:
        with edit_layer(segments, tr('Riallinea segmenti alla rotta')):
            for name, typ in ((ROUTE_KEY,QMetaType.Type.QString),(PART,QMetaType.Type.Int),(POSITION,QMetaType.Type.Int)):
                if name not in segments.fields().names():
                    checked(segments.addAttribute(QgsField(name,field_type(typ))), tr('Schema segmenti non aggiornato.'))
            checked(segments.deleteFeatures([f.id() for f in old]), tr('Segmenti precedenti non sostituiti.'))
            for index,(key,pi,pos,g,values) in enumerate(rows):
                f=QgsFeature(segments.fields());f.setGeometry(g)
                f['seg_id']=index;f[ROUTE_KEY]=key;f[PART]=pi;f[POSITION]=pos
                for name,value in zip(DISTANCE_FIELDS,values):f[name]=value
                checked(segments.addFeature(f), tr('Segmento non salvato.'))
        segments.updateExtents()
        ids=[f.id() for f in segments.getFeatures() if (str(f[ROUTE_KEY]),int(f[PART]),int(f[POSITION])) in selected]
        segments.selectByIds(ids)
    finally:
        del blocker
