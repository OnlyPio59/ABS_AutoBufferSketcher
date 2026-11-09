"""
plugin.py — Classe principale del plugin ABS - AutoBufferSketcher.

Responsabilità:
- Registrazione nel menu e toolbar di QGIS
- Creazione e gestione del dock panel, sketcher tool, buffer engine, event handler
- Ciclo di vita completo: initGui → run → unload
- Esportazione in GeoPackage
"""

import os
import json

from qgis.PyQt.QtWidgets import QAction, QFileDialog
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.PyQt import sip
from qgis.core import (
    QgsProject,
    QgsVectorFileWriter,
    QgsMessageLog,
    Qgis,
)

from .buffer_engine import (
    BufferEngine, LAYER_NAME_ROUTE, LAYER_NAME_SEGMENTS,
    SEG_FIELD_ID, SEG_FIELD_PRECAGE, SEG_FIELD_GEOCAGE, SEG_FIELD_GROUND,
    SEG_FIELD_ADJACENT,
)
from .dock_panel import BufferDockPanel
from .sketcher_tool import LineSketcherTool
from .event_handler import EventHandler
from .plan_exporter import PlanExporter
from .geojson_exporter import GeoJSONExporter
from .buffer_engine import (DEFAULT_DISTANCES, LAYER_NAME_PREGEOCAGE, LAYER_NAME_GEOCAGE, LAYER_NAME_GROUND, LAYER_NAME_ADJACENT)
from .branding import PLUGIN_NAME, layer_role, layer_title, adopt_layer
from .segment_sync import synchronize, validate as validate_segments
from .file_io import write_geopackage
from .layer_edits import edit_layer, checked

TAG = PLUGIN_NAME


def log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, TAG, level=level)
    print(f"[{TAG}] {msg}")


class AutoBufferPlugin:
    """Plugin principale ABS - AutoBufferSketcher."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "&" + PLUGIN_NAME

        # Componenti (creati in initGui)
        self.dock_panel = None
        self.sketcher_tool = None
        self.buffer_engine = None
        self.event_handler = None
        self._route_layer = None
        self._segments_layer = None
        self._selected_seg_id = None
        self._delete_pending = False
        self._global_distances = dict(DEFAULT_DISTANCES)
        self._restored_route_id = None
        self._updating = False
        self._route_hooks = []
        self._route_hook_layer = None
        self._segment_edit_snapshot = None

    # ─────────────────────────────────────────────
    #  Ciclo di vita QGIS
    # ─────────────────────────────────────────────

    def initGui(self):
        """Registra il plugin nell'interfaccia QGIS."""
        icon_path = os.path.join(self.plugin_dir, "resources", "icon.svg")
        if not os.path.exists(icon_path):
            icon_path = ":/images/themes/default/mActionBuffer.svg"

        action = QAction(QIcon(icon_path), PLUGIN_NAME, self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setStatusTip("Disegna linea e genera buffer automatici")
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)

        # Inizializza componenti
        self.buffer_engine = BufferEngine()
        self.dock_panel = BufferDockPanel(self.iface.mainWindow())

        # Event handler con callback alle distanze correnti dalla UI
        self.event_handler = EventHandler(
            self.buffer_engine,
            lambda: dict(self._global_distances),
            update_fn=self._on_recalc,
        )

        # Connetti segnali del dock panel
        self.dock_panel.sketcher_requested.connect(self._on_sketcher_requested)
        self.dock_panel.edit_requested.connect(self._on_edit_requested)
        self.dock_panel.delete_requested.connect(self._on_delete_requested)
        self.dock_panel.recalc_requested.connect(self._on_recalc)
        self.dock_panel.export_requested.connect(self._on_export)
        self.dock_panel.export_plan_requested.connect(self._on_export_plan)
        self.dock_panel.export_geojson_requested.connect(self._on_export_geojson)
        self.dock_panel.make_persistent_requested.connect(self._on_make_persistent)
        self.dock_panel.distances_changed.connect(self._on_distances_changed)
        self.dock_panel.auto_update_toggled.connect(self._on_auto_update_toggled)
        self.dock_panel.diff_buffers_toggled.connect(self._on_diff_buffers_toggled)
        self.dock_panel.apply_to_segment.connect(self._on_apply_to_segment)
        self.dock_panel.apply_to_all_segments.connect(self._on_apply_to_all_segments)

        # Aggiungi dock panel (nascosto inizialmente)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_panel)
        self.dock_panel.hide()

        project = QgsProject.instance()
        project.readProject.connect(self._on_project_read)
        project.cleared.connect(self._on_project_cleared)
        self.dock_panel.spin_alt_flight.valueChanged.connect(self._save_route_state)
        self.dock_panel.spin_alt_pad.valueChanged.connect(self._save_route_state)
        log("Plugin inizializzato.")

    def unload(self):
        """Rimuove il plugin dall'interfaccia QGIS."""
        self._save_route_state()
        self._disconnect_segments()
        self._disconnect_route_hooks()
        project = QgsProject.instance()
        for signal, callback in ((project.readProject, self._on_project_read), (project.cleared, self._on_project_cleared)):
            try:
                signal.disconnect(callback)
            except (TypeError, RuntimeError):
                pass
        # Disconnetti event handler
        if self.event_handler:
            self.event_handler.disconnect()

        # Rimuovi dock panel
        if self.dock_panel:
            self.iface.removeDockWidget(self.dock_panel)
            self.dock_panel.deleteLater()
            self.dock_panel = None

        # Disattiva sketcher tool
        if self.sketcher_tool:
            self.iface.mapCanvas().unsetMapTool(self.sketcher_tool)
            self.sketcher_tool = None

        # Rimuovi azioni
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()

        log("Plugin scaricato.")

    # ─────────────────────────────────────────────
    #  Entry point
    # ─────────────────────────────────────────────

    def run(self):
        """Mostra il pannello dock e prepara il layer sorgente."""
        self.dock_panel.show()
        self.dock_panel.raise_()
        self._ensure_route_layer()
        self.dock_panel.set_status("Pronto. Clicca 'Disegna Linea' per iniziare.")

    # ─────────────────────────────────────────────
    #  Gestione layer sorgente
    # ─────────────────────────────────────────────

    @staticmethod
    def _is_layer_alive(layer):
        """Verifica che il layer Python wrapper punti ancora a un oggetto C++ valido."""
        if layer is None or sip.isdeleted(layer):
            return False
        try:
            layer.id()
            return True
        except RuntimeError:
            return False

    def _ensure_route_layer(self):
        project = QgsProject.instance()
        if not self._is_layer_alive(self._route_layer) or not project.mapLayer(self._route_layer.id()):
            self.event_handler.disconnect()
            self._route_layer = None
        self._route_layer = self.buffer_engine.get_route_layer(project)
        if self._route_layer is None:
            return
        if self._restored_route_id != self._route_layer.id():
            self._disconnect_segments()
            self._segments_layer = None
            self._selected_seg_id = None
            adopt_layer(self._route_layer, LAYER_NAME_ROUTE)
            self._restore_route_state()
            self._connect_route_hooks()
            self._restored_route_id = self._route_layer.id()
        if self.dock_panel.is_auto_update:
            self.event_handler.connect_to_layer(self._route_layer)

    @staticmethod
    def _layers_for_role(role):
        return [layer for layer in QgsProject.instance().mapLayers().values()
            if layer_role(layer) == role]

    def _disconnect_segments(self):
        if self._is_layer_alive(self._segments_layer):
            try:
                self._segments_layer.selectionChanged.disconnect(self._on_segment_selected)
            except (TypeError, RuntimeError):
                pass

    def _disconnect_route_hooks(self):
        # Bound Qt signal objects must never be dereferenced after their C++ owner died.
        if self._is_layer_alive(self._route_hook_layer):
            for signal, callback in self._route_hooks:
                try:
                    signal.disconnect(callback)
                except (TypeError, RuntimeError):
                    pass
        self._route_hooks = []
        self._route_hook_layer = None
        self._segment_edit_snapshot = None

    def _connect_route_hooks(self):
        self._disconnect_route_hooks()
        self._route_hook_layer = self._route_layer
        for signal, callback in ((self._route_layer.editingStarted,self._on_route_edit_started),
                (self._route_layer.beforeRollBack,self._on_route_rollback),
                (self._route_layer.editingStopped,self._on_route_edit_stopped)):
            signal.connect(callback)
            self._route_hooks.append((signal,callback))

    def _on_route_edit_started(self):
        from qgis.core import QgsFeature
        if self.dock_panel.is_diff_buffers and self._is_layer_alive(self._segments_layer):
            self._segment_edit_snapshot = [QgsFeature(f) for f in self._segments_layer.getFeatures()]

    def _on_route_rollback(self):
        # Restore the pre-edit distances/topology before recalculating the reverted route.
        if self._segment_edit_snapshot is not None and self._is_layer_alive(self._segments_layer):
            try:
                with edit_layer(self._segments_layer, 'Ripristina segmenti prima della modifica'):
                    checked(self._segments_layer.deleteFeatures([f.id() for f in self._segments_layer.getFeatures()]), 'Ripristino segmenti non riuscito.')
                    for original in self._segment_edit_snapshot:
                        from qgis.core import QgsFeature
                        f=QgsFeature(original)
                        f.setId(-1)
                        checked(self._segments_layer.addFeature(f), 'Segmento non ripristinato.')
            except Exception as error:
                self.dock_panel.set_status(f'Ripristino segmenti interrotto: {error}')
                log(str(error), Qgis.Critical)

    def _on_route_edit_stopped(self):
        self._segment_edit_snapshot = None
        if not self._updating:
            self._on_recalc()

    def _save_route_state(self, *args):
        if not self.dock_panel or not self._is_layer_alive(self._route_layer):
            return
        state = {'version': 1, 'distances': self._global_distances,
            'diff': self.dock_panel.is_diff_buffers, 'auto': self.dock_panel.is_auto_update,
            'mission': self.dock_panel.get_mission_config()}
        self._route_layer.setCustomProperty('abs/state', json.dumps(state))

    def _restore_route_state(self):
        raw = self._route_layer.customProperty('abs/state', '')
        try:
            state = json.loads(raw) if raw else {}
            values = {k: float(state.get('distances', {}).get(k, v)) for k,v in DEFAULT_DISTANCES.items()}
            if any(not 0 <= v <= 50000 for v in values.values()):
                raise ValueError('Distanze salvate non valide.')
        except (TypeError, ValueError):
            self.dock_panel.set_status('Stato salvato non valido: aggiornamento automatico disabilitato.')
            state = {'auto': False};values = dict(DEFAULT_DISTANCES)
        self._global_distances = values
        candidates = self._layers_for_role(LAYER_NAME_SEGMENTS)
        diff = bool(state.get('diff', bool(candidates)))
        panel = self.dock_panel
        panel.blockSignals(True)
        try:
            panel.set_distances(values)
            panel.chk_diff_buffers.setChecked(diff)
            panel.chk_auto_update.setChecked(state.get('auto', True))
            mission = state.get('mission', {})
            panel.spin_alt_flight.setValue(mission.get('alt_flight', 120.0))
            panel.spin_alt_pad.setValue(mission.get('alt_pad', 40.0))
        finally:
            panel.blockSignals(False)
        if diff and len(candidates) == 1:
            self._segments_layer = adopt_layer(candidates[0], LAYER_NAME_SEGMENTS)
            self._segments_layer.selectionChanged.connect(self._on_segment_selected)
        self._save_route_state()

    def _on_project_cleared(self, *args):
        self.event_handler.disconnect()
        self._disconnect_route_hooks()
        self._disconnect_segments()
        self._route_layer = None
        self._segments_layer = None
        self._restored_route_id = None
        self._selected_seg_id = None
        self._delete_pending = False
        self.buffer_engine._output_layers.clear()

    def _on_project_read(self, *args):
        self._on_project_cleared()
        if self._layers_for_role(LAYER_NAME_ROUTE):
            self._ensure_route_layer()

    def _on_sketcher_requested(self):
        """Attiva il tool di disegno linea."""
        self._ensure_route_layer()

        if self._route_layer is None:
            self.dock_panel.set_status("Errore: impossibile creare il layer sorgente.")
            return

        canvas = self.iface.mapCanvas()

        # Crea il sketcher tool
        self.sketcher_tool = LineSketcherTool(canvas, self._route_layer)
        self.sketcher_tool.line_sketched.connect(self._on_line_sketched)
        self.sketcher_tool.error_occurred.connect(self.dock_panel.set_status)

        canvas.setMapTool(self.sketcher_tool)
        self.dock_panel.set_status(
            "Modalità disegno: Click SX = vertice, Click DX = fine, ESC = annulla"
        )
        log("Sketcher tool attivato.")

    def _on_line_sketched(self, geometry):
        """Callback quando una linea viene completata dal sketcher."""
        self.dock_panel.set_status("Linea creata. Generazione buffer...")

        # Disattiva il sketcher tool dopo il completamento della linea
        canvas = self.iface.mapCanvas()
        if self.sketcher_tool:
            canvas.unsetMapTool(self.sketcher_tool)
            self.sketcher_tool = None

        # Genera buffer immediatamente
        if self._on_recalc():
            self.dock_panel.set_status("Buffer generati. Modifica la linea per aggiornamento real-time.")

        # Connetti event handler per aggiornamenti futuri
        if self.dock_panel.is_auto_update and self._route_layer:
            self.event_handler.connect_to_layer(self._route_layer)

    def _on_edit_requested(self):
        """Attiva/disattiva la modalità editing con il vertex tool nativo di QGIS."""
        self._ensure_route_layer()

        if self._route_layer is None:
            self.dock_panel.set_status("Errore: nessun layer rotta trovato.")
            return

        if self._route_layer.isEditable():
            # Già in editing → salva e esci
            if not self._route_layer.commitChanges():
                self.dock_panel.set_status("Salvataggio non riuscito: " + "; ".join(self._route_layer.commitErrors()))
                return
            self.dock_panel.set_status("Editing terminato. Modifiche salvate.")
            self.dock_panel.btn_edit.setText("Modifica linea")
            # Ricalcola buffer dopo le modifiche
            self._on_recalc()
            log("Editing disattivato, buffer ricalcolati.")
        else:
            # Entra in editing e attiva il vertex tool
            if not self._route_layer.startEditing():
                self.dock_panel.set_status("Il layer rotta non è modificabile.")
                return
            self.iface.setActiveLayer(self._route_layer)
            self.iface.actionVertexTool().trigger()
            self.dock_panel.set_status(
                "Modalità modifica: sposta/aggiungi/rimuovi vertici. "
                "Clicca di nuovo 'Modifica Linea' per salvare."
            )
            self.dock_panel.btn_edit.setText("Salva modifiche")
            log("Editing attivato con vertex tool.")

    def _on_delete_requested(self):
        """Gestisce eliminazione linee: seleziona → conferma eliminazione."""
        self._ensure_route_layer()

        if self._route_layer is None:
            self.dock_panel.set_status("Errore: nessun layer rotta trovato.")
            return

        # Conta features nel layer
        feat_count = self._route_layer.featureCount()
        if feat_count == 0:
            self.dock_panel.set_status("Nessuna linea da eliminare.")
            return

        if not self._delete_pending:
            # FASE 1: Attiva selezione sul layer
            self.iface.setActiveLayer(self._route_layer)

            if feat_count == 1:
                # Una sola feature → selezionala automaticamente
                fid = next(self._route_layer.getFeatures()).id()
                self._route_layer.selectByIds([fid])
                self._delete_pending = True
                self.dock_panel.btn_delete.setText("Conferma eliminazione")
                self.dock_panel.set_status(
                    f"1 linea selezionata. Clicca 'Conferma Eliminazione' per rimuoverla."
                )
            else:
                # Più features → attiva il tool di selezione
                self.iface.actionSelect().trigger()
                self._delete_pending = True
                self.dock_panel.btn_delete.setText("Conferma eliminazione")
                self.dock_panel.set_status(
                    f"{feat_count} linee presenti. Seleziona quelle da eliminare, "
                    "poi clicca 'Conferma Eliminazione'."
                )
            log(f"Delete: fase selezione ({feat_count} features).")
        else:
            # FASE 2: Elimina le feature selezionate
            selected_ids = self._route_layer.selectedFeatureIds()

            if not selected_ids:
                self.dock_panel.set_status("Nessuna linea selezionata. Seleziona prima.")
                return

            try:
                with edit_layer(self._route_layer, 'Elimina rotte selezionate'):
                    checked(self._route_layer.deleteFeatures(selected_ids), 'Cancellazione non riuscita.')
            except Exception as error:
                self.dock_panel.set_status(str(error))
                return

            deleted_count = len(selected_ids)
            self._delete_pending = False
            self.dock_panel.btn_delete.setText("Elimina linea")
            self.dock_panel.set_status(f"{deleted_count} linea/e eliminata/e.")
            log(f"Eliminate {deleted_count} features.")

            # Ricalcola buffer (o puliscili se non ci sono più linee)
            self._on_recalc()

    def _on_recalc(self):
        if self._updating:
            return False
        self._updating = True
        try:
            if not self._is_layer_alive(self._route_layer):
                self._ensure_route_layer()
            if self._route_layer is None or not self._route_layer.isValid():
                raise ValueError('Nessun layer rotta valido.')
            seg_layer = None
            if self.dock_panel.is_diff_buffers:
                if not self._is_layer_alive(self._segments_layer):
                    candidates = self._layers_for_role(LAYER_NAME_SEGMENTS)
                    if len(candidates) != 1:
                        raise ValueError('Layer segmenti mancante o ambiguo: ripristinarlo prima del ricalcolo.')
                    self._segments_layer = candidates[0]
                    self._segments_layer.selectionChanged.connect(self._on_segment_selected)
                synchronize(self._route_layer, self._segments_layer, self._global_distances)
                seg_layer = self._segments_layer
            else:
                self._global_distances = self.dock_panel.get_distances()
            dissolved = self.buffer_engine.build_all_buffers(self._route_layer,
                self._global_distances, segments_layer=seg_layer)
            self.buffer_engine.update_output_layers(QgsProject.instance(), dissolved, self._route_layer.crs())
            self._save_route_state()
            self.dock_panel.set_status('Buffer aggiornati.')
            return True
        except Exception as error:
            self.dock_panel.set_status(f'Ricalcolo interrotto: {error}')
            log(str(error), Qgis.Critical)
            return False
        finally:
            self._updating = False

    def _on_distances_changed(self):
        if not self.dock_panel.is_diff_buffers:
            self._global_distances = self.dock_panel.get_distances()
            self._save_route_state()
            if self.dock_panel.is_auto_update and self._is_layer_alive(self._route_layer):
                self._on_recalc()

    def _on_auto_update_toggled(self, enabled):
        """Connette/disconnette l'event handler."""
        if enabled and self._route_layer:
            self.event_handler.connect_to_layer(self._route_layer)
            self.dock_panel.set_status("Auto-update attivato.")
        else:
            self.event_handler.disconnect()
            self.dock_panel.set_status("Auto-update disattivato.")
        self._save_route_state()

    # ─────────────────────────────────────────────
    #  Buffer differenziati per segmento
    # ─────────────────────────────────────────────

    def _on_diff_buffers_toggled(self, enabled):
        """Crea/rimuove il layer segmenti quando la checkbox viene attivata/disattivata."""
        project = QgsProject.instance()

        if enabled:
            if not self._is_layer_alive(self._route_layer):
                self._ensure_route_layer()

            if self._route_layer is None or self._route_layer.featureCount() == 0:
                self.dock_panel.set_status(
                    "Disegna prima una linea, poi attiva i buffer differenziati."
                )
                self.dock_panel.chk_diff_buffers.blockSignals(True)
                self.dock_panel.chk_diff_buffers.setChecked(False)
                self.dock_panel.chk_diff_buffers.blockSignals(False)
                return

            # Cerca se esiste già un layer segmenti nel progetto
            found_seg_layer = None
            for lyr in project.mapLayers().values():
                try:
                    if layer_role(lyr) == LAYER_NAME_SEGMENTS and lyr.type() == Qgis.LayerType.Vector:
                        found_seg_layer = lyr
                        break
                except RuntimeError:
                    continue

            if found_seg_layer:
                self._segments_layer = found_seg_layer
                log("Trovato layer segmenti esistente nel progetto. Riuso.")
            else:
                # Crea il layer segmenti
                distances = dict(self._global_distances)
                self._segments_layer = self.buffer_engine.create_segments_layer(
                    self._route_layer, distances, project
                )

            try:
                synchronize(self._route_layer, self._segments_layer, self._global_distances)
            except Exception as error:
                self.dock_panel.set_status(f'Modalità segmenti: {error}')
                self.dock_panel.chk_auto_update.setChecked(False)
                return
            self._save_route_state()
            adopt_layer(self._segments_layer, LAYER_NAME_SEGMENTS)
            # Connetti selezione del layer segmenti
            try:
                self._segments_layer.selectionChanged.disconnect(self._on_segment_selected)
            except (TypeError, RuntimeError):
                pass
            self._segments_layer.selectionChanged.connect(self._on_segment_selected)
            self.iface.setActiveLayer(self._segments_layer)

            # IMPORTANTE: disattiva il sketcher tool e attiva il tool di selezione
            canvas = self.iface.mapCanvas()
            if self.sketcher_tool:
                canvas.unsetMapTool(self.sketcher_tool)
                self.sketcher_tool = None
            self.iface.actionSelect().trigger()

            seg_count = self._segments_layer.featureCount()
            self.dock_panel.set_status(
                f"Modalità segmenti attiva: {seg_count} segmenti. "
                "Clicca su un segmento per modificarne le distanze."
            )
            log(f"Modalità differenziata attivata: {seg_count} segmenti.")
        else:
            # Rimuovi il layer segmenti
            if self._is_layer_alive(self._segments_layer):
                try:
                    self._segments_layer.selectionChanged.disconnect(self._on_segment_selected)
                except (TypeError, RuntimeError):
                    pass
                project.removeMapLayer(self._segments_layer.id())
            self._segments_layer = None
            self._selected_seg_id = None
            self.dock_panel.set_segment_info(None)
            self.dock_panel.set_distances(self._global_distances)
            self._save_route_state()
            self.dock_panel.set_status("Modalità buffer uniforme.")
            # Ricalcola buffer con distanze globali
            self._on_recalc()

    def _on_segment_selected(self, *args):
        if not self.dock_panel:
            return
        try:
            if self._is_layer_alive(self._segments_layer):
                validate_segments(self._segments_layer)
            self._update_segment_selection()
        except Exception as error:
            self.dock_panel.set_status(str(error))
            self.dock_panel.set_segment_info(None)

    def _update_segment_selection(self):
        """Callback quando l'utente seleziona un segmento sulla mappa."""
        if not self.dock_panel or not self._is_layer_alive(self._segments_layer):
            return

        sel_ids = self._segments_layer.selectedFeatureIds()
        log(f"Selezione segmenti cambiata: {len(sel_ids)} selezionati, ids={list(sel_ids)}")

        if not sel_ids:
            self._selected_seg_id = None
            self.dock_panel.set_segment_info(None)
            return

        # Prendi il primo segmento selezionato
        feat = self._segments_layer.getFeature(sel_ids[0])
        seg_id = feat[SEG_FIELD_ID]
        self._selected_seg_id = seg_id

        # Carica le distanze del segmento negli spinbox
        distances = {
            'pregeocage': feat[SEG_FIELD_PRECAGE],
            'geocage': feat[SEG_FIELD_GEOCAGE],
            'ground': feat[SEG_FIELD_GROUND],
            'adjacent': feat[SEG_FIELD_ADJACENT],
        }
        self.dock_panel.set_segment_info(seg_id, distances)
        log(f"Segmento {seg_id} selezionato: pre={distances['pregeocage']}m, "
            f"geo={distances['geocage']}m, gnd={distances['ground']}m")

    def _on_apply_to_segment(self):
        self._apply_segment_values(False)

    def _on_apply_to_all_segments(self):
        self._apply_segment_values(True)

    def _apply_segment_values(self, all_segments):
        try:
            if not self._is_layer_alive(self._segments_layer):
                raise ValueError('Layer segmenti non valido.')
            validate_segments(self._segments_layer)
            features = list(self._segments_layer.getFeatures()) if all_segments else self._segments_layer.selectedFeatures()
            if not features:
                raise ValueError('Nessun segmento selezionato.')
            if not all_segments:
                features = features[:1]
            distances = self.dock_panel.get_distances()
            fields = (('pregeocage',SEG_FIELD_PRECAGE),('geocage',SEG_FIELD_GEOCAGE),
                ('ground',SEG_FIELD_GROUND),('adjacent',SEG_FIELD_ADJACENT))
            with edit_layer(self._segments_layer, 'Modifica distanze dei segmenti'):
                for feat in features:
                    for key,field in fields:
                        checked(self._segments_layer.changeAttributeValue(feat.id(),
                            self._segments_layer.fields().indexFromName(field), distances[key]), 'Distanza non salvata.')
            recalculated = self._on_recalc()
            self.dock_panel.mark_segment_saved()
            target = 'Tutti i segmenti' if all_segments else f'Segmento {features[0][SEG_FIELD_ID]}'
            if recalculated:
                self.dock_panel.set_status(f'{target}: distanze salvate nel layer. Puoi selezionare un altro segmento.')
            else:
                detail = self.dock_panel.status_label.text()
                self.dock_panel.set_status(f'{target}: distanze salvate, ma {detail}')
            return True
        except Exception as error:
            self.dock_panel.set_status(f'Salvataggio distanze non riuscito: {error}')
            return False

    def _on_export(self):
        """Esporta tutti i layer in un GeoPackage."""
        project = QgsProject.instance()

        # Raccogli layer da esportare
        export_names = [LAYER_NAME_ROUTE, LAYER_NAME_PREGEOCAGE,
            LAYER_NAME_GEOCAGE, LAYER_NAME_GROUND, LAYER_NAME_ADJACENT]
        layers = []
        for lyr in project.mapLayers().values():
            if layer_role(lyr) in export_names:
                layers.append(lyr)

        if not layers:
            self.dock_panel.set_status("Nessun layer da esportare.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self.dock_panel,
            "Esporta Buffer in GeoPackage",
            os.path.expanduser("~/abs_results.gpkg"),
            "GeoPackage (*.gpkg)",
        )

        if not file_path:
            return

        self.dock_panel.set_status("Esportazione in corso...")
        try:
            if not self._on_recalc():
                return
            layers = [l for l in project.mapLayers().values() if layer_role(l) in export_names]
            write_geopackage(layers, file_path, project)
            self.dock_panel.set_status(f"Risultati esportati in {os.path.basename(file_path)} (rotta e buffer; per i segmenti usare Rendi Layer Persistenti).")
            log(f"Esportazione completata: {file_path}")
        except Exception as e:
            self.dock_panel.set_status(f"Errore esportazione: {e}")
            log(f"Errore esportazione: {e}", Qgis.Critical)

    def _buffer_layer_dict(self):
        from .buffer_engine import (LAYER_NAME_PREGEOCAGE,LAYER_NAME_GEOCAGE,LAYER_NAME_GROUND,LAYER_NAME_ADJACENT)
        return {key:layers[0] for key,role in (('pregeocage',LAYER_NAME_PREGEOCAGE),('geocage',LAYER_NAME_GEOCAGE),
            ('ground',LAYER_NAME_GROUND),('adjacent',LAYER_NAME_ADJACENT)) if (layers := self._layers_for_role(role))}

    def _plan_export_layers(self):
        from qgis.core import QgsFeatureRequest, QgsVectorLayer, QgsFeature
        route = self._route_layer
        if route.featureCount() > 1:
            if route.selectedFeatureCount() != 1:
                raise ValueError('Più rotte presenti: selezionare una sola rotta sulla mappa per esportare il .plan.')
            route = route.materialize(QgsFeatureRequest().setFilterFids(route.selectedFeatureIds()))
        dissolved = self.buffer_engine.build_all_buffers(route, self._global_distances,
            self._segments_layer if self.dock_panel.is_diff_buffers else None)
        from .buffer_engine import (LAYER_NAME_PREGEOCAGE,LAYER_NAME_GEOCAGE,LAYER_NAME_GROUND,LAYER_NAME_ADJACENT)
        buffers = {}
        for key,role in (('pregeocage',LAYER_NAME_PREGEOCAGE),('geocage',LAYER_NAME_GEOCAGE),
                ('ground',LAYER_NAME_GROUND),('adjacent',LAYER_NAME_ADJACENT)):
            layer = QgsVectorLayer('MultiPolygon',layer_title(role),'memory')
            layer.setCrs(route.crs())
            g = dissolved[role]
            if not g.isEmpty():
                g.convertToMultiType()
                f=QgsFeature();f.setGeometry(g)
                checked(layer.dataProvider().addFeatures([f])[0], 'Buffer di esportazione non creato.')
            buffers[key]=layer
        return route,buffers

    def _on_export_plan(self):
        """Esporta la rotta e i buffer in un file .plan per Rigicloud."""
        project = QgsProject.instance()

        # Verifica che il layer rotta sia valido e presente
        if not self._is_layer_alive(self._route_layer) or not self._route_layer.isValid():
            # Cerca di ritrovarlo nel progetto se il riferimento è perso
            self._route_layer = None
            for lyr in project.mapLayers().values():
                if layer_role(lyr) == LAYER_NAME_ROUTE:
                    self._route_layer = lyr
                    break

        if not self._route_layer:
            self.dock_panel.set_status("Nessun layer rotta trovato.")
            return

        # Cerca i layer buffer nel progetto
        from .buffer_engine import (
            LAYER_NAME_PREGEOCAGE, LAYER_NAME_GEOCAGE,
            LAYER_NAME_GROUND, LAYER_NAME_ADJACENT
        )
        buffer_layers_dict = {}
        for lyr in project.mapLayers().values():
            name = layer_role(lyr)
            if name == LAYER_NAME_PREGEOCAGE:
                buffer_layers_dict["pregeocage"] = lyr
            elif name == LAYER_NAME_GEOCAGE:
                buffer_layers_dict["geocage"] = lyr
            elif name == LAYER_NAME_GROUND:
                buffer_layers_dict["ground"] = lyr
            elif name == LAYER_NAME_ADJACENT:
                buffer_layers_dict["adjacent"] = lyr

        file_path, _ = QFileDialog.getSaveFileName(
            self.dock_panel,
            "Esporta Piano di Volo (.plan)",
            os.path.expanduser("~/abs_mission.plan"),
            "Rigicloud Plan (*.plan)",
        )

        if not file_path:
            return

        self.dock_panel.set_status("Generazione file .plan in corso...")
        try:
            distances = self.dock_panel.get_distances()
            config = self.dock_panel.get_mission_config()

            if not self._on_recalc():
                return
            export_route, buffer_layers_dict = self._plan_export_layers()
            distances = dict(self._global_distances)
            exporter = PlanExporter()
            success = exporter.export(
                export_route,
                buffer_layers_dict,
                distances,
                config,
                file_path
            )

            if success:
                self.dock_panel.set_status(f"Piano esportato in {os.path.basename(file_path)}")
            else:
                self.dock_panel.set_status(exporter.last_error)
        except Exception as e:
            self.dock_panel.set_status(f"Errore esportazione piano: {e}")
            log(f"Errore esportazione piano: {e}", Qgis.Critical)

    def _on_export_geojson(self):
        """Esporta la rotta, i waypoint e i buffer in un file GeoJSON."""
        project = QgsProject.instance()

        # Verifica che il layer rotta sia valido e presente
        if not self._is_layer_alive(self._route_layer) or not self._route_layer.isValid():
            # Cerca di ritrovarlo nel progetto se il riferimento è perso
            self._route_layer = None
            for lyr in project.mapLayers().values():
                if layer_role(lyr) == LAYER_NAME_ROUTE:
                    self._route_layer = lyr
                    break

        if not self._route_layer:
            self.dock_panel.set_status("Nessun layer rotta trovato.")
            return

        # Cerca i layer buffer nel progetto
        from .buffer_engine import (
            LAYER_NAME_PREGEOCAGE, LAYER_NAME_GEOCAGE,
            LAYER_NAME_GROUND, LAYER_NAME_ADJACENT
        )
        buffer_layers_dict = {}
        for lyr in project.mapLayers().values():
            name = layer_role(lyr)
            if name == LAYER_NAME_PREGEOCAGE:
                buffer_layers_dict["pregeocage"] = lyr
            elif name == LAYER_NAME_GEOCAGE:
                buffer_layers_dict["geocage"] = lyr
            elif name == LAYER_NAME_GROUND:
                buffer_layers_dict["ground"] = lyr
            elif name == LAYER_NAME_ADJACENT:
                buffer_layers_dict["adjacent"] = lyr

        file_path, _ = QFileDialog.getSaveFileName(
            self.dock_panel,
            "Esporta in GeoJSON",
            os.path.expanduser("~/abs_mission.geojson"),
            "GeoJSON Files (*.geojson)",
        )

        if not file_path:
            return

        self.dock_panel.set_status("Generazione file GeoJSON in corso...")
        try:
            if not self._on_recalc():
                return
            buffer_layers_dict = self._buffer_layer_dict()
            exporter = GeoJSONExporter()
            success = exporter.export(
                self._route_layer,
                buffer_layers_dict,
                file_path
            )

            if success:
                self.dock_panel.set_status(f"GeoJSON esportato in {os.path.basename(file_path)}")
            else:
                self.dock_panel.set_status(exporter.last_error)
        except Exception as e:
            self.dock_panel.set_status(f"Errore esportazione GeoJSON: {e}")
            log(f"Errore esportazione GeoJSON: {e}", Qgis.Critical)

    def _on_make_persistent(self):
        from qgis.core import QgsVectorLayer
        from .buffer_engine import (LAYER_NAME_PREGEOCAGE, LAYER_NAME_GEOCAGE,
            LAYER_NAME_GROUND, LAYER_NAME_ADJACENT)
        project = QgsProject.instance()
        names = (LAYER_NAME_ROUTE,LAYER_NAME_SEGMENTS,LAYER_NAME_PREGEOCAGE,
            LAYER_NAME_GEOCAGE,LAYER_NAME_GROUND,LAYER_NAME_ADJACENT)
        layers = [l for l in project.mapLayers().values() if layer_role(l) in names]
        if not layers:
            self.dock_panel.set_status('Nessun layer da salvare.')
            return
        if any(l.isEditable() for l in layers):
            self.dock_panel.set_status('Salvare o annullare le modifiche dei layer prima di renderli persistenti.')
            return
        if all(l.providerType() != 'memory' for l in layers):
            self.dock_panel.set_status('I layer sono già persistenti.')
            return
        file_path, _ = QFileDialog.getSaveFileName(self.dock_panel,
            'Salva Layer del Plugin in GeoPackage', os.path.expanduser('~/abs_data.gpkg'), 'GeoPackage (*.gpkg)')
        if not file_path:
            return
        try:
            if not self._on_recalc():
                return
            self._save_route_state()
            layers = [l for l in project.mapLayers().values() if layer_role(l) in names]
            write_geopackage(layers, file_path, project)
            replacements = []
            for old in layers:
                new = QgsVectorLayer(f'{file_path}|layername={old.name()}', old.name(), 'ogr')
                if not new.isValid():
                    raise ValueError(f'Riapertura non riuscita: {old.name()}; i layer originali sono ancora nel progetto.')
                new.setRenderer(old.renderer().clone())
                for key in old.customPropertyKeys():
                    new.setCustomProperty(key, old.customProperty(key))
                replacements.append((old,new))
            self.event_handler.disconnect()
            self._disconnect_segments()
            self._disconnect_route_hooks()
            for old,new in replacements:
                project.addMapLayer(new)
                role = layer_role(old)
                if role == LAYER_NAME_ROUTE:
                    self._route_layer = new
                    self._restored_route_id = new.id()
                elif role == LAYER_NAME_SEGMENTS:
                    self._segments_layer = new
                else:
                    self.buffer_engine._output_layers[role] = new
                project.removeMapLayer(old.id())
            self.buffer_engine._reorder_layers(project)
            self._connect_route_hooks()
            if self.dock_panel.is_auto_update:
                self.event_handler.connect_to_layer(self._route_layer)
            if self.dock_panel.is_diff_buffers and self._is_layer_alive(self._segments_layer):
                self._segments_layer.selectionChanged.connect(self._on_segment_selected)
            self.dock_panel.set_status('Layer persistenti salvati; le altre tabelle del GeoPackage sono state conservate.')
        except Exception as error:
            self.dock_panel.set_status(f'Salvataggio interrotto: {error}')
            log(str(error), Qgis.Critical)
