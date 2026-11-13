"""Validated, staged output: a failed write never replaces the destination."""

from .i18n import tr
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from qgis.core import QgsVectorFileWriter, QgsVectorLayer


def write_json(path, value):
    destination = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.abs-', suffix='.json', dir=str(destination.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=4, allow_nan=False)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_geopackage(layers, path, project):
    destination = Path(path).resolve()
    # Replacing an open SQLite datasource would leave providers bound to its old inode.
    for layer in project.mapLayers().values():
        if layer.providerType() == 'ogr' and Path(layer.source().split('|')[0]).resolve() == destination:
            raise ValueError(tr('GeoPackage già aperto nel progetto: scegliere un altro file di destinazione.'))
    fd, temporary = tempfile.mkstemp(prefix='.abs-', suffix='.gpkg', dir=str(destination.parent))
    os.close(fd)
    os.unlink(temporary)
    try:
        if destination.exists():
            # SQLite backup also includes changes committed to a WAL sidecar.
            with sqlite3.connect(destination.as_uri()+'?mode=ro', uri=True) as source:
                if source.execute('PRAGMA application_id').fetchone()[0] != 1196444487:
                    raise ValueError(tr('Il file esistente non è un GeoPackage valido.'))
                with sqlite3.connect(temporary) as target:
                    source.backup(target)
        for layer in layers:
            if not layer.isValid():
                raise ValueError(tr('Layer non valido: {value}').format(value=layer.name()))
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = 'GPKG'
            options.layerName = layer.name()
            options.forceMulti = layer.geometryType() == 2
            options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                if os.path.exists(temporary) else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
            result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, temporary, project.transformContext(), options)
            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                raise ValueError(tr("Errore scrittura '{value}': {value2}").format(value=layer.name(), value2=result[1]))
            check = QgsVectorLayer(f'{temporary}|layername={layer.name()}', layer.name(), 'ogr')
            if not check.isValid() or check.featureCount() != layer.featureCount():
                raise ValueError(tr("Verifica del layer '{value}' non riuscita.").format(value=layer.name()))
            check = None
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
