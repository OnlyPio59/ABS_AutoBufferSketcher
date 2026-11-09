"""
ABS - AutoBufferSketcher — QGIS Plugin
Entry point per il caricamento del plugin in QGIS.
"""


def classFactory(iface):
    """Chiamata da QGIS al caricamento del plugin.

    Args:
        iface: QgisInterface — riferimento all'interfaccia QGIS.

    Returns:
        Istanza della classe principale del plugin.
    """
    from .plugin import AutoBufferPlugin
    return AutoBufferPlugin(iface)
