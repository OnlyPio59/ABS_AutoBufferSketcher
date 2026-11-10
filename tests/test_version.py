"""Loaded-version snapshots, independent of QGIS and the live user's profile."""
import configparser
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auto_buffer_sketcher.version import PLUGIN_VERSION


class VersionTests(unittest.TestCase):
    def test_loaded_version_matches_packaged_metadata(self):
        metadata = configparser.ConfigParser(interpolation=None)
        metadata.read(ROOT / 'auto_buffer_sketcher/metadata.txt', encoding='utf-8')
        self.assertEqual(PLUGIN_VERSION, metadata['general']['version'])

    def test_snapshot_survives_disk_update_and_new_load_reads_new_version(self):
        with tempfile.TemporaryDirectory(prefix='abs-loaded-version-') as folder:
            root = Path(folder)
            source = root / 'version.py'
            shutil.copyfile(ROOT / 'auto_buffer_sketcher/version.py', source)
            metadata = root / 'metadata.txt'
            metadata.write_text('[general]\nversion=1.2.3\n')
            spec = importlib.util.spec_from_file_location('abs_version_fixture', source)
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            self.assertEqual(loaded.PLUGIN_VERSION, '1.2.3')
            metadata.write_text('[general]\nversion=2.0.0\n')
            self.assertEqual(loaded.PLUGIN_VERSION, '1.2.3')
            fresh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fresh)
            self.assertEqual(fresh.PLUGIN_VERSION, '2.0.0')
            self.assertEqual(loaded.PLUGIN_VERSION, '1.2.3')


if __name__ == '__main__':
    unittest.main(verbosity=2)
