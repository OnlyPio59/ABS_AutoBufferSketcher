"""Product identity and backwards-compatible discovery of managed QGIS layers."""
PLUGIN_NAME = 'ABS - AutoBufferSketcher'

# These keys are persisted identifiers used by existing projects, not display names.
LAYER_TITLES = {
    'ABC Route Line': 'ABS - Rotta',
    'ABC Segments': 'ABS - Segmenti',
    'ABC Pregeocage Buffer': 'ABS - Pregeocage',
    'ABC Geocage Buffer': 'ABS - Geocage',
    'ABC Ground Buffer': 'ABS - Ground Buffer',
    'ABC Adjacent Area Buffer': 'ABS - Adjacent Area',
}
_TITLE_ROLES = {title: role for role, title in LAYER_TITLES.items()}


def layer_title(role):
    return LAYER_TITLES.get(role, role)


def layer_role(layer):
    """Recognize stored roles and both old/new titles, including a bare GPKG."""
    stored = str(layer.customProperty('abs/role', '') or '')
    if stored:
        return _TITLE_ROLES.get(stored, stored)
    name = layer.name()
    return _TITLE_ROLES.get(name, name)


def adopt_layer(layer, role):
    """Tag in place and rename default legacy titles; preserve user custom titles.

    Setting a display name never changes the provider URI or on-disk table name.
    """
    layer.setCustomProperty('abs/role', role)
    if layer.name() == role:
        layer.setName(layer_title(role))
    return layer
