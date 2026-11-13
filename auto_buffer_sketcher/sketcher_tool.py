"""
sketcher_tool.py — Tool di disegno linea interattiva per ABS - AutoBufferSketcher.

Responsabilità:
- Cattura click sulla mappa per costruire una polyline
- Mostra rubber band live durante il disegno
- Al completamento (click destro), crea la feature nel layer sorgente
- Supporta ESC per annullare il disegno corrente
"""

from .i18n import tr

from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from .branding import PLUGIN_NAME
from qgis.core import (
    QgsWkbTypes,
    QgsGeometry,
    QgsFeature,
    QgsPointXY,
    QgsMessageLog,
    Qgis,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor


TAG = PLUGIN_NAME


class LineSketcherTool(QgsMapToolEmitPoint):
    """Map tool per disegnare una polyline interattivamente.

    Signals:
        line_sketched(QgsGeometry): emesso quando l'utente completa una linea (click destro).
    """

    line_sketched = pyqtSignal(QgsGeometry)
    error_occurred = pyqtSignal(str)

    def __init__(self, canvas, target_layer):
        """
        Args:
            canvas: QgsMapCanvas su cui operare.
            target_layer: QgsVectorLayer in cui inserire la feature completata.
        """
        super().__init__(canvas)
        self.canvas = canvas
        self.target_layer = target_layer
        self._vertices = []

        # Rubber band per la linea in costruzione
        self._rubber_band = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self._rubber_band.setColor(QColor("#2563EB"))
        self._rubber_band.setWidth(2)
        self._rubber_band.setLineStyle(Qt.PenStyle.DashLine)

        # Rubber band per i vertici (punti)
        self._vertex_band = QgsRubberBand(canvas, Qgis.GeometryType.Point)
        self._vertex_band.setColor(QColor("#2563EB"))
        self._vertex_band.setIconSize(8)
        self._vertex_band.setIcon(QgsRubberBand.IconType.ICON_CIRCLE)

        self.setCursor(Qt.CursorShape.CrossCursor)

    def canvasPressEvent(self, event):
        """Gestisce i click sulla mappa."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._add_vertex(event)
        elif event.button() == Qt.MouseButton.RightButton:
            self._finalize_line()

    def canvasMoveEvent(self, event):
        """Aggiorna la rubber band live durante il movimento del mouse."""
        if not self._vertices:
            return

        # Mostra linea temporanea dall'ultimo vertice al cursore
        point = self.toMapCoordinates(event.pos())
        self._rubber_band.reset(Qgis.GeometryType.Line)

        for v in self._vertices:
            self._rubber_band.addPoint(v, False)
        self._rubber_band.addPoint(point, True)

    def keyPressEvent(self, event):
        """ESC per annullare il disegno corrente."""
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif event.key() == Qt.Key.Key_Backspace and self._vertices:
            # Rimuovi ultimo vertice
            self._vertices.pop()
            self._refresh_rubber_bands()

    def deactivate(self):
        """Pulisce le rubber bands quando il tool viene disattivato."""
        self._cleanup_rubber_bands()
        super().deactivate()

    # ─────────────────────────────────────────────
    #  Metodi interni
    # ─────────────────────────────────────────────

    def _add_vertex(self, event):
        """Aggiunge un vertice alla polyline corrente."""
        point = self.toMapCoordinates(event.pos())
        self._vertices.append(point)

        # Aggiorna rubber band dei vertici
        self._vertex_band.addPoint(point, True)

        log(tr('Vertice aggiunto: ({value:.2f}, {value2:.2f}) — totale: {value3}').format(value=point.x(), value2=point.y(), value3=len(self._vertices)))

    def _finalize_line(self):
        try:
            self._store_line()
        except Exception as error:
            self.error_occurred.emit(str(error))
            log(str(error), Qgis.MessageLevel.Critical)
            self._cancel()

    def _store_line(self):
        """Completa la linea e crea la feature nel layer sorgente."""
        if len(self._vertices) < 2:
            log(tr('Servono almeno 2 vertici per creare una linea.'), Qgis.MessageLevel.Warning)
            self._cancel()
            return

        # Crea geometria
        layer_points = [self.toLayerCoordinates(self.target_layer, point) for point in self._vertices]
        geom = QgsGeometry.fromPolylineXY(layer_points)

        if geom.isNull() or geom.isEmpty():
            log(tr('Geometria risultante non valida.'), Qgis.MessageLevel.Warning)
            self._cancel()
            return

        # Inserisci la feature nel layer target
        if self.target_layer and self.target_layer.isValid():
            owns_edit = not self.target_layer.isEditable()
            if owns_edit and not self.target_layer.startEditing():
                raise ValueError(tr('Impossibile modificare il layer rotta.'))
            feat = QgsFeature(self.target_layer.fields())
            feat.setGeometry(geom)
            if not self.target_layer.addFeature(feat):
                if owns_edit:
                    self.target_layer.rollBack()
                raise ValueError(tr('Inserimento della rotta non riuscito.'))
            if owns_edit and not self.target_layer.commitChanges():
                self.target_layer.rollBack()
                raise ValueError(tr('Salvataggio della rotta non riuscito.'))
            log(tr('Linea creata con {value} vertici.').format(value=len(self._vertices)))

        # Emetti segnale per notificare il plugin
        self.line_sketched.emit(geom)

        # Reset
        self._vertices.clear()
        self._cleanup_rubber_bands()

    def _cancel(self):
        """Annulla il disegno corrente."""
        self._vertices.clear()
        self._cleanup_rubber_bands()
        log(tr('Disegno annullato.'))

    def _refresh_rubber_bands(self):
        """Ridisegna le rubber bands dopo modifica ai vertici."""
        self._rubber_band.reset(Qgis.GeometryType.Line)
        self._vertex_band.reset(Qgis.GeometryType.Point)

        for v in self._vertices:
            self._rubber_band.addPoint(v, False)
            self._vertex_band.addPoint(v, True)

        if self._vertices:
            self._rubber_band.addPoint(self._vertices[-1], True)

    def _cleanup_rubber_bands(self):
        """Pulisce tutte le rubber bands."""
        self._rubber_band.reset(Qgis.GeometryType.Line)
        self._vertex_band.reset(Qgis.GeometryType.Point)


def log(msg, level=Qgis.MessageLevel.Info):
    """Logging centralizzato."""
    QgsMessageLog.logMessage(msg, TAG, level=level)
    print(f"[{TAG}] {msg}")
