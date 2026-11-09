"""Packaging invariants, without a QGIS installation."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_plugin import build_plugin
ROOT=Path(__file__).resolve().parents[1]

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='abs-package-')
        self.root=Path(self.temp.name)/'source';self.root.mkdir()
        shutil.copytree(ROOT/'auto_buffer_sketcher',self.root/'auto_buffer_sketcher',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name in ('LICENSE','NOTICE'):shutil.copyfile(ROOT/name,self.root/name)
    def tearDown(self):self.temp.cleanup()
    def test_reproducible_and_only_plugin_files(self):
        package=self.root/'auto_buffer_sketcher'
        (package/'private.plan').write_text('must not ship')
        (package/'.env').write_text('must not ship')
        first=build_plugin(self.root,Path(self.temp.name)/'one',True)
        second=build_plugin(self.root,Path(self.temp.name)/'two',True)
        self.assertEqual(first[0].read_bytes(),second[0].read_bytes())
        with zipfile.ZipFile(first[0]) as z:
            names=z.namelist()
            self.assertTrue(all(n.startswith('auto_buffer_sketcher/') for n in names))
            self.assertNotIn('auto_buffer_sketcher/private.plan',names)
            self.assertNotIn('auto_buffer_sketcher/.env',names)
            self.assertIn('auto_buffer_sketcher/LICENSE',names)
            self.assertIn('auto_buffer_sketcher/README.md',names)
            self.assertIn('auto_buffer_sketcher/resources/icon.png',names)
    def test_release_requires_real_contact(self):
        path=self.root/'auto_buffer_sketcher/metadata.txt'
        for value in ('','dev@example.com'):
            text=path.read_text();text='\n'.join('email='+value if line.startswith('email=') else line for line in text.splitlines())+'\n';path.write_text(text)
            with self.assertRaisesRegex(ValueError,'email'):build_plugin(self.root,Path(self.temp.name)/'release')
        self.assertFalse((Path(self.temp.name)/'release').exists())
    def test_release_path_with_synthetic_contact_fixture(self):
        # Fixture exercises validation only; no real contact is selected for the project.
        path=self.root/'auto_buffer_sketcher/metadata.txt'
        path.write_text('\n'.join('email=fixture@abs.test' if line.startswith('email=') else line for line in path.read_text().splitlines())+'\n')
        archive,_,_,valid=build_plugin(self.root,Path(self.temp.name)/'release')
        self.assertTrue(valid);self.assertFalse(archive.name.endswith('-dev.zip'))
    def test_license_mirror_must_match(self):
        (self.root/'auto_buffer_sketcher/LICENSE').write_text('different license')
        with self.assertRaisesRegex(ValueError,'LICENSE differs'):build_plugin(self.root,Path(self.temp.name)/'out',True)
    def test_symlinks_are_rejected(self):
        (self.root/'auto_buffer_sketcher/resources/escape.svg').symlink_to(self.root/'LICENSE')
        with self.assertRaisesRegex(ValueError,'Symlinks'):build_plugin(self.root,Path(self.temp.name)/'out',True)
    def test_version_cannot_escape_output_path(self):
        path=self.root/'auto_buffer_sketcher/metadata.txt'
        path.write_text('\n'.join('version=../../escape' if line.startswith('version=') else line for line in path.read_text().splitlines())+'\n')
        with self.assertRaisesRegex(ValueError,'Version'):build_plugin(self.root,Path(self.temp.name)/'out',True)

if __name__=='__main__':unittest.main(verbosity=2)
