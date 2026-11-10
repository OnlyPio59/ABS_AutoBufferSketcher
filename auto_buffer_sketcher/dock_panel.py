"""Dock UI for ABS - AutoBufferSketcher; calculation and export stay in plugin.py."""

from .i18n import tr
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QEvent, QPointF, pyqtSignal
from qgis.PyQt.QtSvg import QSvgWidget
from qgis.PyQt.QtGui import QIcon, QPainter, QPalette, QPolygonF, QColor
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QPushButton, QCheckBox, QFrame,
    QTabWidget, QScrollArea, QStyle, QStyleOptionSpinBox, QAbstractSpinBox,
)
from .branding import PLUGIN_NAME
from .version import PLUGIN_VERSION


class MeterSpinBox(QDoubleSpinBox):
    """Native stepping/keyboard behaviour with explicit, theme-safe arrow glyphs.

    Qt still owns the hit areas and stepping, including auto-repeat and limits.
    Paint over the native arrows so stylesheet/platform icons cannot disappear.
    """

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for control, enabled, direction in (
            (QStyle.SC_SpinBoxUp, QAbstractSpinBox.StepUpEnabled, -1),
            (QStyle.SC_SpinBoxDown, QAbstractSpinBox.StepDownEnabled, 1),
        ):
            rect = self.style().subControlRect(QStyle.CC_SpinBox, option, control, self)
            active = self.isEnabled() and bool(self.stepEnabled() & enabled)
            group = QPalette.Active if active else QPalette.Disabled
            background = self.palette().color(QPalette.Button)
            if active and option.activeSubControls & control and option.state & QStyle.State_MouseOver:
                background = self.palette().color(QPalette.Highlight)
                foreground = self.palette().color(QPalette.HighlightedText)
            else:
                foreground = self.palette().color(group, QPalette.ButtonText)
            painter.fillRect(rect, background)
            painter.setPen(self.palette().color(QPalette.Mid))
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if direction == 1:
                painter.drawLine(rect.topLeft(), rect.topRight())
            x, y = rect.center().x(), rect.center().y()
            painter.setPen(Qt.NoPen)
            painter.setBrush(foreground)
            painter.drawPolygon(QPolygonF([
                QPointF(x - 4, y - direction * 2),
                QPointF(x + 4, y - direction * 2),
                QPointF(x, y + direction * 3),
            ]))
        painter.end()


class BufferDockPanel(QDockWidget):
    """Two scrollable workflow pages; public controls/signals remain compatible."""

    sketcher_requested = pyqtSignal()
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    recalc_requested = pyqtSignal()
    export_requested = pyqtSignal()
    export_plan_requested = pyqtSignal()
    export_geojson_requested = pyqtSignal()
    make_persistent_requested = pyqtSignal()
    distances_changed = pyqtSignal()
    auto_update_toggled = pyqtSignal(bool)
    diff_buffers_toggled = pyqtSignal(bool)
    apply_to_segment = pyqtSignal()    # applica distanze al segmento selezionato
    apply_to_all_segments = pyqtSignal()  # applica distanze a tutti i segmenti

    def __init__(self, parent=None):
        super().__init__(PLUGIN_NAME, parent)
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "resources/icon.svg")))
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._segment_id = None
        self._segment_baseline = None
        self.setMinimumWidth(360)
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        self.container = QWidget()
        self.container.setObjectName("absPanel")
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("absBrand")
        row = QHBoxLayout(header)
        row.setContentsMargins(10, 10, 10, 10)
        mark = QSvgWidget(str(Path(__file__).parent / "resources/icon.svg"))
        mark.setFixedSize(44, 44)
        mark.setAccessibleName(tr('Logo ABS'))
        row.addWidget(mark)
        words = QVBoxLayout()
        title = QLabel(PLUGIN_NAME)
        title.setWordWrap(True)
        title.setObjectName("absTitle")
        words.addWidget(title)
        subtitle = QLabel(tr('Rotte, buffer e missioni'))
        subtitle.setObjectName("absSubtitle")
        subtitle.setWordWrap(True)
        details = QHBoxLayout()
        details.addWidget(subtitle, 1)
        self.version_label = QLabel(f'v{PLUGIN_VERSION}')
        self.version_label.setObjectName('absVersion')
        self.version_label.setAlignment(Qt.AlignCenter)
        hint = tr('Versione caricata: {version}').format(version=PLUGIN_VERSION)
        self.version_label.setToolTip(hint)
        self.version_label.setAccessibleName(hint)
        details.addWidget(self.version_label, 0, Qt.AlignVCenter)
        words.addLayout(details)
        row.addLayout(words, 1)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._refresh_segment_actions)
        tab_font = self.tabs.tabBar().font()
        tab_font.setBold(True)
        self.tabs.tabBar().setFont(tab_font)
        self.tabs.tabBar().setDrawBase(False)
        layout.addWidget(self.tabs, 1)
        route = self._page(tr('Rotta e buffer'))
        tools = self._card(route, tr('Rotta'), tr('Disegna la linea sulla mappa o modifica i suoi vertici.'))
        self.btn_sketcher = self._button(tr('Disegna linea'), self.sketcher_requested, tools)
        self.btn_sketcher.setProperty("primary", True)
        row = QHBoxLayout()
        self.btn_edit = self._button(tr('Modifica linea'), self.edit_requested, row,
            tr('Attiva la modalità editing sul layer rotta.\nPuoi spostare, aggiungere o rimuovere vertici.'))
        self.btn_delete = self._button(tr('Elimina linea'), self.delete_requested, row,
            tr('Seleziona una o più linee sulla mappa e clicca di nuovo per eliminarle.'))
        self.btn_delete.setProperty("danger", True)
        tools.addLayout(row)

        distances = self._card(route, tr('Distanze dei buffer'), tr('Valori in metri, applicati alla rotta.'))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        for index, (key, name, value, color) in enumerate((
            ("pregeocage", tr('Pregeocage'), 50.0, "#22C55E"),
            ("geocage", tr('Geocage'), 100.0, "#FFD700"),
            ("ground", tr('Ground Buffer'), 150.0, "#DC143C"),
            ("adjacent", tr('Adjacent Area'), 5000.0, "#6f63c2"),
        )):
            swatch = QLabel("●")
            swatch.setStyleSheet(f"color: {color};")
            grid.addWidget(swatch, index, 0)
            spin = self._spinbox(name, value, 50000.0, decimals=1)
            spin.valueChanged.connect(self._on_distance_input)
            setattr(self, f"spin_{key}", spin)
            label = QLabel(name)
            label.setBuddy(spin)
            grid.addWidget(label, index, 1)
            grid.addWidget(spin, index, 2)
        distances.addLayout(grid)
        self.chk_auto_update = QCheckBox(tr('Aggiornamento automatico'))
        self.chk_auto_update.setChecked(True)
        self.chk_auto_update.toggled.connect(self.auto_update_toggled.emit)
        distances.addWidget(self.chk_auto_update)
        self.chk_diff_buffers = QCheckBox(tr('Distanze diverse per segmento'))
        self.chk_diff_buffers.setToolTip(tr('Assegna distanze diverse ad ogni segmento della linea.'))
        self.chk_diff_buffers.toggled.connect(self._on_diff_toggled)
        distances.addWidget(self.chk_diff_buffers)
        self.btn_recalc = self._button(tr('Ricalcola buffer'), self.recalc_requested, distances)

        self.btn_apply_all = self._button(tr('Applica a tutti i segmenti'), self.apply_to_all_segments,
            distances, tr('Sostituisce le distanze di tutti i segmenti con i valori correnti.'))
        self.btn_apply_all.hide()
        route.addStretch()

        files = self._page(tr('Missione e file'))
        mission = self._card(files, tr('Quote della missione'),
            tr('Quote AMSL: altitudini rispetto al livello medio del mare.'))
        grid = QGridLayout()
        for index, (key, name, value) in enumerate((("flight", tr('Volo'), 120.0), ("pad", tr('Pad'), 40.0))):
            spin = self._spinbox(tr('Altitudine {name} (AMSL)').format(name=name), value, 5000.0)
            setattr(self, f"spin_alt_{key}", spin)
            label = QLabel(name)
            label.setBuddy(spin)
            grid.addWidget(label, index, 0)
            grid.addWidget(spin, index, 1)
        mission.addLayout(grid)
        exports = self._card(files, tr('Esporta'), tr('Scegli il formato per il passaggio successivo.'))
        for attr, text, signal, description in (
            ("btn_export_plan", tr('Esporta .plan per RigiCloud'), self.export_plan_requested, tr('Profilo missione dedicato a RigiCloud')),
            ("btn_export_geojson", tr('Esporta GeoJSON'), self.export_geojson_requested, tr('Dati geografici in formato JSON')),
            ("btn_export", tr('Esporta GeoPackage'), self.export_requested, tr('Rotta e buffer in un file .gpkg')),
        ):
            setattr(self, attr, self._button(text, signal, exports))
            self._description(exports, description)
        persistence = self._card(files, tr('Salva i layer'), tr('Conserva su disco i layer temporanei del plugin.'))
        self.btn_make_persistent = self._button(tr('Rendi layer persistenti'), self.make_persistent_requested,
            persistence, tr('Converte i layer temporanei del plugin in layer permanenti salvandoli su disco.'))
        files.addStretch()

        footer = QFrame()
        footer.setObjectName("absStatus")
        status_layout = QVBoxLayout(footer)
        status_layout.setContentsMargins(10, 9, 10, 9)
        self.seg_group = QFrame()
        self.seg_group.setObjectName("absSegmentSave")
        segment = QVBoxLayout(self.seg_group)
        segment.setContentsMargins(0, 0, 0, 6)
        segment.setSpacing(6)
        self.seg_info_label = QLabel(tr('Nessun segmento selezionato.'))
        self.seg_info_label.setWordWrap(True)
        segment.addWidget(self.seg_info_label)
        self.btn_apply_segment = self._button(tr('Salva distanze del segmento'), self.apply_to_segment,
            segment, tr('Memorizza i quattro valori solo nel segmento selezionato.\nPoi puoi selezionare un altro segmento. Per conservarli dopo la chiusura,\nrendi persistenti i layer e salva il progetto QGIS.'))
        self.btn_apply_segment.setProperty("primary", True)
        self.btn_apply_segment.setEnabled(False)
        self.seg_group.hide()
        status_layout.addWidget(self.seg_group)
        self.status_label = QLabel(tr('Pronto.'))
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        status_layout.addWidget(self.status_label)
        layout.addWidget(footer)
        self.setWidget(self.container)

    def _page(self, title):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("absPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 8)
        layout.setSpacing(12)
        area.setWidget(page)
        self.tabs.addTab(area, title)
        return layout

    @staticmethod
    def _description(layout, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("muted", True)
        layout.addWidget(label)

    def _card(self, parent_layout, title, description=None):
        frame = QFrame()
        frame.setObjectName("absCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        heading = QLabel(title)
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        if description:
            self._description(layout, description)
        parent_layout.addWidget(frame)
        return layout

    @staticmethod
    def _button(text, signal, layout, tooltip=None):
        button = QPushButton(text)
        button.setMinimumHeight(34)
        button.clicked.connect(signal.emit)
        if tooltip:
            button.setToolTip(tooltip)
        layout.addWidget(button)
        return button

    @staticmethod
    def _spinbox(name, value, maximum, decimals=2):
        spin = MeterSpinBox()
        spin.setAccessibleName(name)
        spin.setRange(0.0, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSuffix(" m")
        spin.setMinimumHeight(40)
        spin.setMinimumWidth(spin.fontMetrics().horizontalAdvance(f"{maximum:.{decimals}f} m") + 40)
        return spin

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            if hasattr(self, "container"):
                self._apply_theme()

    def _apply_theme(self):
        # Read the host palette; style only this panel, never the QGIS application.
        dark = self.palette().color(QPalette.Window).lightness() < 128
        bg = "#111827" if dark else "#F3F5F8"
        surface = "#1E293B" if dark else "#FFFFFF"
        text = "#E5EAF2" if dark else "#172033"
        muted = "#A9B6C9" if dark else "#58677C"
        border = "#3B4A60" if dark else "#CFD7E3"
        field = "#111C2D" if dark else "#FFFFFF"
        palette = self.palette()
        for role, color in ((QPalette.Window, bg), (QPalette.WindowText, text),
            (QPalette.Base, field), (QPalette.Text, text), (QPalette.Button, surface),
            (QPalette.ButtonText, text), (QPalette.Mid, border),
            (QPalette.Highlight, "#2563EB"), (QPalette.HighlightedText, "#FFFFFF")):
            palette.setColor(role, QColor(color))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(muted))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(muted))
        self.container.setPalette(palette)
        self.container.setAutoFillBackground(True)
        self.container.setStyleSheet(f"""
            QWidget#absPanel {{background:{bg};}}
            QWidget#absPanel QWidget {{color:{text};}}
            QScrollArea, QWidget#absPage {{background:{bg};}}
            QFrame#absBrand {{background:#18212F;border-radius:10px;}}
            QWidget#absPanel QLabel#absTitle {{color:#F8FAFC;font-size:12pt;font-weight:600;}}
            QWidget#absPanel QLabel#absSubtitle {{color:#CBD5E1;}}
            QWidget#absPanel QLabel#absVersion {{color:#F8FAFC;background:#263449;border-radius:4px;padding:2px 5px;font-weight:600;}}
            QFrame#absCard {{background:{surface};border:1px solid {border};border-radius:9px;}}
            QLabel[heading="true"] {{font-weight:600;}}
            QWidget#absPanel QLabel[muted="true"] {{color:{muted};}}
            QPushButton {{background:{surface};border:1px solid {border};border-radius:6px;padding:5px 9px;}}
            QPushButton:hover {{border-color:#3B82F6;}}
            QPushButton:focus {{border:2px solid #3B82F6;}}
            QWidget#absPanel QPushButton[primary="true"] {{background:#2563EB;color:white;border-color:#2563EB;font-weight:600;}}
            QWidget#absPanel QPushButton[danger="true"] {{color:{'#FDA4AF' if dark else '#B42338'};}}
            QWidget#absPanel QPushButton:disabled {{color:{muted};}}
            QWidget#absPanel QPushButton[primary="true"]:disabled {{color:#FFFFFF;}}
            QDoubleSpinBox {{background:{field};border:1px solid {border};border-radius:5px;padding:2px 2px 2px 7px;}}
            QDoubleSpinBox:focus {{border:1px solid #3B82F6;}}
            QDoubleSpinBox::up-button {{subcontrol-origin:border;subcontrol-position:top right;width:28px;border:0;}}
            QDoubleSpinBox::down-button {{subcontrol-origin:border;subcontrol-position:bottom right;width:28px;border:0;}}
            QTabWidget::pane {{border:0;}}
            QTabBar::tab {{background:{bg};padding:10px 10px;border:0;border-bottom:2px solid transparent;}}
            QTabBar::tab:selected {{border-bottom-color:#3B82F6;}}
            QTabBar::tab:focus {{border-color:#3B82F6;}}
            QFrame#absStatus {{background:{surface};border:1px solid {border};border-radius:6px;}}
            QCheckBox {{spacing:7px;min-height:24px;}}
            QScrollBar:vertical {{background:{bg};width:12px;margin:0;}}
            QScrollBar::handle:vertical {{background:{border};min-height:30px;border-radius:5px;}}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{background:transparent;}}
        """)

    def get_distances(self):
        """Restituisce le distanze correnti come dict."""
        return {
            "pregeocage": self.spin_pregeocage.value(),
            "geocage": self.spin_geocage.value(),
            "ground": self.spin_ground.value(),
            "adjacent": self.spin_adjacent.value(),
        }

    def set_distances(self, distances):
        """Imposta le distanze negli spinbox senza emettere distances_changed."""
        self.spin_pregeocage.blockSignals(True)
        self.spin_geocage.blockSignals(True)
        self.spin_ground.blockSignals(True)
        self.spin_adjacent.blockSignals(True)

        self.spin_pregeocage.setValue(distances.get('pregeocage', 50.0))
        self.spin_geocage.setValue(distances.get('geocage', 100.0))
        self.spin_ground.setValue(distances.get('ground', 150.0))
        self.spin_adjacent.setValue(distances.get('adjacent', 5000.0))

        self.spin_pregeocage.blockSignals(False)
        self.spin_geocage.blockSignals(False)
        self.spin_ground.blockSignals(False)
        self.spin_adjacent.blockSignals(False)
        self._refresh_segment_caption()

    @property
    def has_unsaved_segment_changes(self):
        return (self._segment_id is not None and self._segment_baseline is not None
                and self.get_distances() != self._segment_baseline)

    def _on_distance_input(self, *args):
        self._refresh_segment_caption()
        self.distances_changed.emit()

    def _refresh_segment_caption(self):
        if not hasattr(self, "seg_info_label"):
            return
        if self._segment_id is None:
            text = tr('Seleziona un segmento sulla mappa.')
        elif self.has_unsaved_segment_changes:
            text = tr('Segmento {segment_id}: modifiche da salvare.').format(segment_id=self._segment_id)
        else:
            text = tr('Segmento {segment_id}: distanze memorizzate nel layer.').format(segment_id=self._segment_id)
        self.seg_info_label.setText(text)
        self.btn_apply_segment.setEnabled(self._segment_id is not None)

    def _refresh_segment_actions(self, *args):
        if not hasattr(self, "seg_group"):
            return
        self.seg_group.setVisible(self.is_diff_buffers and self.tabs.currentIndex() == 0)
        self.btn_apply_all.setVisible(self.is_diff_buffers)

    def mark_segment_saved(self):
        if self._segment_id is not None:
            self._segment_baseline = self.get_distances()
        self._refresh_segment_caption()

    def set_segment_info(self, seg_id, distances=None):
        """Load the selected segment and track unsaved values in the input fields."""
        self._segment_id = seg_id
        if seg_id is None:
            self._segment_baseline = None
        else:
            if distances:
                self.set_distances(distances)
            self._segment_baseline = self.get_distances()
        self._refresh_segment_caption()

    def get_mission_config(self):
        """Restituisce i parametri di missione correnti."""
        return {
            "alt_flight": self.spin_alt_flight.value(),
            "alt_pad": self.spin_alt_pad.value(),
            "geoid_offset": 39.27
        }

    def set_status(self, msg):
        """Aggiorna il messaggio di stato."""
        self.status_label.setText(msg)

    def _on_diff_toggled(self, checked):
        """Mostra/nasconde il gruppo segmento e emette il segnale."""
        self._refresh_segment_actions()
        if not checked:
            self.set_segment_info(None)
        self.diff_buffers_toggled.emit(checked)

    @property
    def is_auto_update(self):
        return self.chk_auto_update.isChecked()

    @property
    def is_diff_buffers(self):
        return self.chk_diff_buffers.isChecked()
