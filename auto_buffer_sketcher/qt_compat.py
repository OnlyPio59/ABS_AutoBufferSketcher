"""Small API bridge for the oldest supported QGIS and current Qt6 builds."""
from qgis.core import Qgis


def field_type(meta_type):
    """QgsField switched from QVariant.Type to QMetaType.Type in QGIS 3.38."""
    if Qgis.QGIS_VERSION_INT < 33800:
        from qgis.PyQt.QtCore import QVariant
        return QVariant.Type(int(meta_type))
    return meta_type
