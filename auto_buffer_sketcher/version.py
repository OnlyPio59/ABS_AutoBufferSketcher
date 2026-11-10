"""Version of the loaded code, captured once from the package metadata.

Do not read metadata when constructing widgets: it may have been replaced by a
new installation while the current Python modules are still running in QGIS.
"""
import configparser
from pathlib import Path


def _metadata_version():
    metadata = configparser.ConfigParser(interpolation=None)
    with Path(__file__).with_name('metadata.txt').open(encoding='utf-8') as source:
        metadata.read_file(source)
    return metadata['general']['version'].strip()


PLUGIN_VERSION = _metadata_version()
