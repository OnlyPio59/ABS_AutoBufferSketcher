"""
event_handler.py — Real-time buffer update via QGIS signals with debounce.
"""

from .i18n import tr

from .branding import PLUGIN_NAME
from qgis.core import QgsMessageLog, Qgis
from qgis.PyQt.QtCore import QTimer, QObject

TAG = PLUGIN_NAME


def log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, TAG, level=level)
    print(f"[{TAG}] {msg}")


class EventHandler(QObject):
    """Connects layer edit signals to BufferEngine with 300ms debounce."""

    DEBOUNCE_MS = 300

    def __init__(self, buffer_engine, get_distances_fn, parent=None, update_fn=None):
        super().__init__(parent)
        self._engine = buffer_engine
        self._get_distances = get_distances_fn
        self._update_fn = update_fn
        self._source_layer = None
        self._connected = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._execute_update)

    def _is_layer_alive(self, layer):
        """Verifica che il layer Python wrapper punti ancora a un oggetto C++ valido."""
        if layer is None:
            return False
        try:
            # Se l'oggetto C++ è distrutto, qualsiasi chiamata genera RuntimeError
            layer.id()
            return True
        except RuntimeError:
            return False

    def connect_to_layer(self, layer):
        self.disconnect()
        if layer is None:
            return
        self._source_layer = layer
        layer.geometryChanged.connect(self._on_change)
        layer.featureAdded.connect(self._on_change)
        layer.featureDeleted.connect(self._on_change)
        layer.committedGeometriesChanges.connect(self._on_committed)
        layer.committedFeaturesAdded.connect(self._on_committed)
        layer.committedFeaturesRemoved.connect(self._on_committed)
        self._connected = True
        log(tr("EventHandler connesso a '{value}'").format(value=layer.name()))

    def disconnect(self):
        """Disconnette tutti i segnali. Crash-proof: gestisce oggetti C++ già distrutti."""
        try:
            if self._connected and self._is_layer_alive(self._source_layer):
                try:
                    lyr = self._source_layer
                    lyr.geometryChanged.disconnect(self._on_change)
                    lyr.featureAdded.disconnect(self._on_change)
                    lyr.featureDeleted.disconnect(self._on_change)
                    lyr.committedGeometriesChanges.disconnect(self._on_committed)
                    lyr.committedFeaturesAdded.disconnect(self._on_committed)
                    lyr.committedFeaturesRemoved.disconnect(self._on_committed)
                except (TypeError, RuntimeError):
                    pass
        except (TypeError, RuntimeError):
            pass
        finally:
            self._connected = False
            self._source_layer = None
            self._timer.stop()

    @property
    def is_connected(self):
        return self._connected

    def _on_change(self, *args):
        self._timer.start(self.DEBOUNCE_MS)

    def _on_committed(self, *args):
        self._timer.stop()
        self._execute_update()

    def _execute_update(self):
        if self._update_fn is not None:
            self._update_fn()
            return
        if not self._is_layer_alive(self._source_layer):
            log(tr('Layer sorgente non più valido, skip ricalcolo.'))
            self._connected = False
            self._source_layer = None
            return
        try:
            if not self._source_layer.isValid():
                return
            from qgis.core import QgsProject
            project = QgsProject.instance()
            distances = self._get_distances()
            log(tr('Ricalcolo buffer: pre={value}m, geo={value2}m, gnd={value3}m').format(value=distances.get('pregeocage'), value2=distances.get('geocage'), value3=distances.get('ground')))
            dissolved = self._engine.build_all_buffers(self._source_layer, distances)
            self._engine.update_output_layers(project, dissolved, self._source_layer.crs())
            log(tr('Buffer aggiornati.'))
        except (RuntimeError, Exception) as e:
            log(tr('Errore ricalcolo: {e}').format(e=e), Qgis.Critical)

    def force_update(self):
        self._timer.stop()
        self._execute_update()
