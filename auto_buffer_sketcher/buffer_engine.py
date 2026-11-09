"""
buffer_engine.py — Motore di generazione buffer per ABS - AutoBufferSketcher.

Responsabilità:
- Segmentazione linea in tratti (vertice → vertice)
- Generazione buffer per segmento (pregeocage, geocage, ground)
- Supporto distanze differenziate per segmento
- Dissolve dei buffer in geometrie unificate
- Aggiornamento/creazione layer di output
"""

import math

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsSymbol,
    QgsFillSymbol,
    QgsSimpleFillSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsMessageLog,
    Qgis,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from .branding import PLUGIN_NAME, layer_role, layer_title, adopt_layer
from .geometry_utils import metric_crs, transformed
from .segment_sync import ROUTE_KEY, PART, POSITION, parts

# Nomi layer di output
LAYER_NAME_ROUTE = "ABC Route Line"
LAYER_NAME_SEGMENTS = "ABC Segments"
LAYER_NAME_PREGEOCAGE = "ABC Pregeocage Buffer"
LAYER_NAME_GEOCAGE = "ABC Geocage Buffer"
LAYER_NAME_GROUND = "ABC Ground Buffer"
LAYER_NAME_ADJACENT = "ABC Adjacent Area Buffer"

# Campi attributo segmento
SEG_FIELD_ID = "seg_id"
SEG_FIELD_PRECAGE = "pregeocage_m"
SEG_FIELD_GEOCAGE = "geocage_m"
SEG_FIELD_GROUND = "ground_m"
SEG_FIELD_ADJACENT = "adjacent_m"

# Distanze default (metri)
DEFAULT_DISTANCES = {
    "pregeocage": 50.0,
    "geocage": 100.0,
    "ground": 150.0,
    "adjacent": 5000.0,
}

# Stili buffer: (colore, opacità bordo, opacità riempimento)
BUFFER_STYLES = {
    LAYER_NAME_PREGEOCAGE: ("#22C55E", 180, 70),   # Verde
    LAYER_NAME_GEOCAGE: ("#FFD700", 180, 55),       # Giallo
    LAYER_NAME_GROUND: ("#DC143C", 180, 45),        # Rosso
    LAYER_NAME_ADJACENT: ("#6f63c2", 180, 25),      # Celeste/viola
}

TAG = PLUGIN_NAME


def log(msg, level=Qgis.Info):
    """Logging centralizzato verso QGIS Log Messages."""
    QgsMessageLog.logMessage(msg, TAG, level=level)
    print(f"[{TAG}] {msg}")


class BufferEngine:
    """Motore di generazione buffer con segmentazione e dissolve."""

    def __init__(self):
        self._output_layers = {}  # name → QgsVectorLayer

    @staticmethod
    def _is_layer_alive(layer):
        """Verifica che il layer Python wrapper punti ancora a un oggetto C++ valido."""
        if layer is None:
            return False
        try:
            layer.id()
            return True
        except RuntimeError:
            return False

    # ─────────────────────────────────────────────
    #  Segmentazione
    # ─────────────────────────────────────────────

    @staticmethod
    def segmentize_line(geometry):
        """Spezza una LineString nei suoi segmenti (vertice → vertice).

        Args:
            geometry: QgsGeometry di tipo LineString o MultiLineString.

        Returns:
            Lista di QgsGeometry, ciascuna un singolo segmento a 2 vertici.
        """
        if geometry.isNull() or geometry.isEmpty():
            return []

        # Estrai i punti della linea
        if geometry.isMultipart():
            polylines = geometry.asMultiPolyline()
        else:
            polylines = [geometry.asPolyline()]

        segments = []
        for polyline in polylines:
            for i in range(len(polyline) - 1):
                seg = QgsGeometry.fromPolylineXY([polyline[i], polyline[i + 1]])
                segments.append(seg)

        return segments

    # ─────────────────────────────────────────────
    #  Generazione buffer
    # ─────────────────────────────────────────────

    @staticmethod
    def generate_segment_buffers(segment_geom, distances):
        """Genera 4 buffer per un singolo segmento.

        Args:
            segment_geom: QgsGeometry del segmento (LineString a 2 vertici).
            distances: dict con chiavi 'pregeocage', 'geocage', 'ground', 'adjacent' e valori in metri.

        Returns:
            dict con chiavi = nomi buffer, valori = QgsGeometry del buffer poligonale.
        """
        buffers = {}
        for key, layer_name in [
            ("pregeocage", LAYER_NAME_PREGEOCAGE),
            ("geocage", LAYER_NAME_GEOCAGE),
            ("ground", LAYER_NAME_GROUND),
            ("adjacent", LAYER_NAME_ADJACENT),
        ]:
            dist = float(distances.get(key, DEFAULT_DISTANCES[key]))
            if not math.isfinite(dist) or dist < 0:
                raise ValueError("Le distanze dei buffer devono essere numeri finiti non negativi.")
            if dist > 0:
                buf = segment_geom.buffer(dist, 8)  # 8 segmenti per quarto di cerchio
                if buf and not buf.isEmpty():
                    buffers[layer_name] = buf
        return buffers

    # ─────────────────────────────────────────────
    #  Pipeline completa
    # ─────────────────────────────────────────────

    def build_all_buffers(self, source_layer, default_distances=None, segments_layer=None):
        """Pipeline: per ogni feature del layer sorgente → segmenta → buffer.

        Args:
            source_layer: QgsVectorLayer con le linee sorgente.
            default_distances: dict con le distanze globali.
            segments_layer: QgsVectorLayer opzionale con distanze per-segmento.

        Returns:
            dict con chiave = nome layer buffer, valore = QgsGeometry dissolto.
        """
        if default_distances is None:
            default_distances = dict(DEFAULT_DISTANCES)

        working_crs = metric_crs(source_layer)

        # Se c'è un segments_layer valido, usa le distanze per-segmento
        per_seg_distances = {}
        if segments_layer and self._is_layer_alive(segments_layer) and segments_layer.featureCount() > 0:
            per_seg_distances = self._read_segment_distances(segments_layer)

        owned_distances = {}
        if segments_layer is not None and self._is_layer_alive(segments_layer) and all(name in segments_layer.fields().names() for name in (ROUTE_KEY,PART,POSITION)):
            for f in segments_layer.getFeatures():
                owned_distances[(str(f[ROUTE_KEY]),int(f[PART]),int(f[POSITION]))] = per_seg_distances[f[SEG_FIELD_ID]]

        all_buffers = {
            LAYER_NAME_PREGEOCAGE: [],
            LAYER_NAME_GEOCAGE: [],
            LAYER_NAME_GROUND: [],
            LAYER_NAME_ADJACENT: [],
        }

        global_seg_idx = 0
        for feature in source_layer.getFeatures():
            geom = feature.geometry()
            if geom.isNull() or geom.isEmpty():
                continue

            segments = [(pi,pos,QgsGeometry.fromPolylineXY(points[pos:pos+2]))
                for pi,points in enumerate(parts(geom)) for pos in range(len(points)-1)]

            for part_index, position, seg in segments:
                # Usa distanze per-segmento se disponibili, altrimenti globali
                owner = (str(feature[ROUTE_KEY]),part_index,position) if ROUTE_KEY in source_layer.fields().names() else None
                if owner in owned_distances:
                    dist = owned_distances[owner]
                elif global_seg_idx in per_seg_distances:
                    dist = per_seg_distances[global_seg_idx]
                else:
                    dist = default_distances

                metric_segment = transformed(seg, source_layer.crs(), working_crs)
                seg_buffers = self.generate_segment_buffers(metric_segment, dist)
                for name, buf_geom in seg_buffers.items():
                    all_buffers[name].append(buf_geom)
                global_seg_idx += 1

        # Dissolve: unisci tutti i buffer dello stesso tipo in un'unica geometria
        dissolved = {}
        for name, geom_list in all_buffers.items():
            if geom_list:
                merged = QgsGeometry.unaryUnion(geom_list)
                dissolved[name] = transformed(merged, working_crs, source_layer.crs())
            else:
                dissolved[name] = QgsGeometry()

        return dissolved

    @staticmethod
    def _read_segment_distances(segments_layer):
        """Legge le distanze per-segmento dal layer segmenti.

        Returns:
            dict {seg_id: {'pregeocage': val, 'geocage': val, 'ground': val, 'adjacent': val}}
        """
        result = {}
        for feat in segments_layer.getFeatures():
            seg_id = feat[SEG_FIELD_ID]
            result[seg_id] = {
                'pregeocage': feat[SEG_FIELD_PRECAGE],
                'geocage': feat[SEG_FIELD_GEOCAGE],
                'ground': feat[SEG_FIELD_GROUND],
                'adjacent': feat[SEG_FIELD_ADJACENT],
            }
        return result

    def create_segments_layer(self, source_layer, default_distances, project):
        """Crea/aggiorna il layer dei segmenti a partire dalla linea sorgente.

        Ogni segmento (vertice→vertice) diventa una feature con attributi di distanza editabili.

        Returns:
            QgsVectorLayer del layer segmenti.
        """
        crs = source_layer.crs()

        # Rimuovi il vecchio layer segmenti se esiste
        for lyr in list(project.mapLayers().values()):
            try:
                if layer_role(lyr) == LAYER_NAME_SEGMENTS:
                    project.removeMapLayer(lyr.id())
            except RuntimeError:
                continue

        # Crea nuovo memory layer
        uri = f"LineString?crs={crs.authid()}"
        seg_layer = QgsVectorLayer(uri, layer_title(LAYER_NAME_SEGMENTS), "memory")
        seg_layer.setCrs(crs)
        prov = seg_layer.dataProvider()

        # Aggiungi campi
        prov.addAttributes([
            QgsField(SEG_FIELD_ID, QVariant.Int),
            QgsField(SEG_FIELD_PRECAGE, QVariant.Double),
            QgsField(SEG_FIELD_GEOCAGE, QVariant.Double),
            QgsField(SEG_FIELD_GROUND, QVariant.Double),
            QgsField(SEG_FIELD_ADJACENT, QVariant.Double),
        ])
        seg_layer.updateFields()

        # Popola con i segmenti
        features = []
        seg_idx = 0
        for route_feat in source_layer.getFeatures():
            geom = route_feat.geometry()
            if geom.isNull() or geom.isEmpty():
                continue
            for seg_geom in self.segmentize_line(geom):
                feat = QgsFeature(seg_layer.fields())
                feat.setGeometry(seg_geom)
                feat.setAttribute(SEG_FIELD_ID, seg_idx)
                feat.setAttribute(SEG_FIELD_PRECAGE, default_distances.get('pregeocage', 50.0))
                feat.setAttribute(SEG_FIELD_GEOCAGE, default_distances.get('geocage', 100.0))
                feat.setAttribute(SEG_FIELD_GROUND, default_distances.get('ground', 150.0))
                feat.setAttribute(SEG_FIELD_ADJACENT, default_distances.get('adjacent', 5000.0))
                features.append(feat)
                seg_idx += 1

        prov.addFeatures(features)
        seg_layer.updateExtents()

        # Stile: linea magenta spessa per distinguerla dalla route blu
        from qgis.core import QgsLineSymbol
        symbol = QgsLineSymbol.createSimple({
            'color': '#FF00FF',
            'width': '2.0',
            'line_style': 'dash',
            'capstyle': 'round',
        })
        seg_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        adopt_layer(seg_layer, LAYER_NAME_SEGMENTS)
        project.addMapLayer(seg_layer)
        log(f"Creato layer '{seg_layer.name()}' con {seg_idx} segmenti.")
        return seg_layer

    # ─────────────────────────────────────────────
    #  Gestione layer di output
    # ─────────────────────────────────────────────

    def update_output_layers(self, project, dissolved_buffers, crs):
        """Crea o aggiorna i 3 layer buffer nel progetto QGIS.

        Args:
            project: QgsProject.instance()
            dissolved_buffers: dict {nome_layer: QgsGeometry} dal dissolve.
            crs: QgsCoordinateReferenceSystem del layer sorgente.
        """
        for layer_name, geom in dissolved_buffers.items():
            layer = self._get_or_create_layer(project, layer_name, "MultiPolygon", crs)
            self._replace_layer_content(layer, transformed(geom, crs, layer.crs()))
            self._apply_style(layer, layer_name)

        # Riordina i layer: ground sotto, poi geocage, poi pregeocage, poi route sopra
        self._reorder_layers(project)

    def _get_or_create_layer(self, project, name, geom_type, crs):
        """Recupera un layer esistente per nome, o ne crea uno nuovo in memoria."""
        # Controlla se esiste già nel cache interno
        if name in self._output_layers:
            cached = self._output_layers[name]
            if self._is_layer_alive(cached) and project.mapLayer(cached.id()):
                return adopt_layer(cached, name)
            else:
                # Riferimento stale — rimuovi dal cache
                del self._output_layers[name]

        # Cerca per nome nel progetto (caso di reload plugin)
        for lyr in project.mapLayers().values():
            try:
                if layer_role(lyr) == name and lyr.type() == Qgis.LayerType.Vector:
                    self._output_layers[name] = lyr
                    return adopt_layer(lyr, name)
            except RuntimeError:
                continue

        # Crea nuovo memory layer
        crs_auth = crs.authid()
        uri = f"{geom_type}?crs={crs_auth}"
        layer = QgsVectorLayer(uri, layer_title(name), "memory")
        layer.setCrs(crs)

        if not layer.isValid():
            log(f"Errore: impossibile creare layer '{name}'", Qgis.Critical)
            return None

        adopt_layer(layer, name)
        project.addMapLayer(layer)
        self._output_layers[name] = layer
        log(f"Creato layer '{layer.name()}' ({crs_auth})")
        return layer

    @staticmethod
    def _replace_layer_content(layer, geometry):
        from .layer_edits import edit_layer, checked
        if layer is None:
            raise ValueError('Layer buffer non disponibile.')
        geometry = QgsGeometry(geometry)
        geometries = []
        if not geometry.isEmpty():
            if QgsWkbTypes.isMultiType(layer.wkbType()):
                geometry.convertToMultiType()
                geometries = [geometry]
            elif geometry.isMultipart():
                # Preserve legacy single-Polygon schemas without losing disconnected areas.
                geometries = geometry.asGeometryCollection()
            else:
                geometries = [geometry]
        with edit_layer(layer, 'Aggiorna buffer'):
            checked(layer.deleteFeatures([f.id() for f in layer.getFeatures()]), 'Buffer precedenti non sostituiti.')
            for part in geometries:
                feat = QgsFeature(layer.fields())
                feat.setGeometry(part)
                checked(layer.addFeature(feat), 'Buffer non inserito.')
        layer.triggerRepaint()

    @staticmethod
    def _apply_style(layer, layer_name):
        """Applica uno stile colore/trasparenza predefinito al layer."""
        if layer is None or layer_name not in BUFFER_STYLES:
            return

        color_hex, border_alpha, fill_alpha = BUFFER_STYLES[layer_name]
        color = QColor(color_hex)

        # Crea simbolo con riempimento trasparente
        fill_color = QColor(color)
        fill_color.setAlpha(fill_alpha)

        border_color = QColor(color)
        border_color.setAlpha(border_alpha)

        symbol = QgsFillSymbol.createSimple({
            'color': fill_color.name(QColor.HexArgb),
            'outline_color': border_color.name(QColor.HexArgb),
            'outline_width': '0.4',
            'outline_style': 'solid',
        })

        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def _reorder_layers(self, project):
        """Riordina i layer nel pannello: route sopra, poi pregeocage, geocage, ground, adjacent sotto."""
        root = project.layerTreeRoot()
        desired_order = [
            LAYER_NAME_ROUTE,
            LAYER_NAME_PREGEOCAGE,
            LAYER_NAME_GEOCAGE,
            LAYER_NAME_GROUND,
            LAYER_NAME_ADJACENT,
        ]

        # Raccogli i nodi presenti
        nodes_by_name = {}
        for child in root.children():
            if hasattr(child, 'layer') and child.layer():
                nodes_by_name[layer_role(child.layer())] = child

        # Sposta in ordine (il primo nella lista va in cima)
        insert_pos = 0
        for name in desired_order:
            if name in nodes_by_name:
                node = nodes_by_name[name]
                clone = node.clone()
                root.insertChildNode(insert_pos, clone)
                root.removeChildNode(node)
                insert_pos += 1

    def clear_output_layers(self, project):
        """Rimuove tutti i layer di output dal progetto."""
        for name, layer in list(self._output_layers.items()):
            try:
                if self._is_layer_alive(layer) and project.mapLayer(layer.id()):
                    project.removeMapLayer(layer.id())
            except RuntimeError:
                pass
        self._output_layers.clear()
        log("Layer di output rimossi.")

    def get_route_layer(self, project, crs=None):
        """Recupera o crea il layer sorgente della rotta.

        Args:
            project: QgsProject.instance()
            crs: CRS opzionale. Se None, usa il CRS del progetto.

        Returns:
            QgsVectorLayer per la linea sorgente.
        """
        # Cerca nel progetto
        for lyr in project.mapLayers().values():
            try:
                if layer_role(lyr) == LAYER_NAME_ROUTE and lyr.type() == Qgis.LayerType.Vector:
                    return adopt_layer(lyr, LAYER_NAME_ROUTE)
            except RuntimeError:
                continue

        # Crea nuovo
        if crs is None:
            crs = project.crs()

        uri = f"LineString?crs={crs.authid()}"
        layer = QgsVectorLayer(uri, layer_title(LAYER_NAME_ROUTE), "memory")
        layer.setCrs(crs)

        if not layer.isValid():
            log(f"Errore: impossibile creare layer '{LAYER_NAME_ROUTE}'", Qgis.Critical)
            return None

        # Stile linea route: blu, spessore 2
        from qgis.core import QgsLineSymbol
        symbol = QgsLineSymbol.createSimple({
            'color': '#2563EB',
            'width': '0.8',
            'capstyle': 'round',
            'joinstyle': 'round',
        })
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)

        adopt_layer(layer, LAYER_NAME_ROUTE)
        project.addMapLayer(layer)
        log(f"Creato layer sorgente '{layer.name()}'")
        return layer
