import tempfile
import unittest
from pathlib import Path
from diagnostic_storage import store_bundle

class StorageTests(unittest.TestCase):
    def test_shared_rotation_and_protection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            store_bundle(root,{'diagnostics/capture-1.json':b'{}','diagnostics/capture-1.png':b'x'*30},100)
            store_bundle(root,{'leitura/leitura-a/resultado.json':b'{}','leitura/leitura-a/mesa.png':b'x'*30},100)
            (root/'leitura/leitura-a/.keep').touch()
            store_bundle(root,{'diagnostics/capture-2.json':b'{}','diagnostics/capture-2.png':b'x'*40},100)
            self.assertFalse((root/'diagnostics/capture-1.json').exists())
            self.assertTrue((root/'leitura/leitura-a/mesa.png').exists())
            self.assertLessEqual(sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),100)
    def test_oversized_does_not_delete(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);store_bundle(root,{'diagnostics/capture-1.json':b'{}'},100)
            with self.assertRaises(RuntimeError):store_bundle(root,{'big':b'x'*101},100)
            self.assertTrue((root/'diagnostics/capture-1.json').exists())
    def test_unknown_files_not_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'important.txt').write_bytes(b'x'*90)
            with self.assertRaises(RuntimeError):store_bundle(root,{'new':b'x'*20},100)
            self.assertEqual((root/'important.txt').stat().st_size,90)
    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):store_bundle(Path(d),{'../outside':b'x'})
