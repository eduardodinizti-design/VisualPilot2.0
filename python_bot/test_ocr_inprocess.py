"""In-process OCR backend: config parsing, dispatch, fallback, cache.

Uses a fake in-process runner (no tesserocr/engine needed), so it runs in the
lab. The backend is a performance swap; these tests pin that it never changes
what reaches the readers and that pytesseract stays the default and fallback."""
import unittest
from unittest.mock import patch
import numpy as np

from table_reading import ocr_runtime as runtime


class ConfigParseTests(unittest.TestCase):
    def test_psm_and_whitelist(self):
        self.assertEqual(runtime._parse_config('--psm 10 -c tessedit_char_whitelist=AKQJT1098765432'),
                         (10, 'AKQJT1098765432'))

    def test_psm_only_and_defaults(self):
        self.assertEqual(runtime._parse_config('--psm 7'), (7, ''))
        self.assertEqual(runtime._parse_config(''), (3, ''))
        self.assertEqual(runtime._parse_config(None), (3, ''))


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((4, 6), np.uint8)
        self.addCleanup(runtime.disable_inprocess_ocr)
        self.py = patch.object(runtime.pytesseract, 'image_to_string', return_value='SUB')
        self.ocr = self.py.start()
        self.addCleanup(self.py.stop)

    def test_disabled_uses_pytesseract(self):
        self.assertFalse(runtime.inprocess_enabled())
        with runtime.ocr_frame():
            self.assertEqual(runtime.image_to_string(self.image, config='--psm 7'), 'SUB')
        self.assertEqual(self.ocr.call_count, 1)

    def test_enabled_uses_inprocess_and_skips_subprocess(self):
        runtime.use_inprocess_ocr('C:/fake/tessdata')
        with patch.object(runtime, '_inproc_ocr', return_value='INPROC') as inproc:
            with runtime.ocr_frame() as stats:
                self.assertEqual(runtime.image_to_string(self.image, config='--psm 7'), 'INPROC')
        inproc.assert_called_once()
        self.assertEqual(self.ocr.call_count, 0)
        self.assertEqual(stats['calls'], 1)

    def test_inprocess_failure_falls_back_to_subprocess(self):
        runtime.use_inprocess_ocr('C:/fake/tessdata')
        with patch.object(runtime, '_inproc_ocr', side_effect=RuntimeError('no engine')):
            with runtime.ocr_frame():
                self.assertEqual(runtime.image_to_string(self.image, config='--psm 7'), 'SUB')
        self.assertEqual(self.ocr.call_count, 1)

    def test_cache_still_dedups_with_inprocess(self):
        runtime.use_inprocess_ocr('C:/fake/tessdata')
        with patch.object(runtime, '_inproc_ocr', return_value='X') as inproc:
            with runtime.ocr_frame() as stats:
                runtime.image_to_string(self.image, config='--psm 7')
                runtime.image_to_string(self.image.copy(), config='--psm 7')
        self.assertEqual(inproc.call_count, 1)  # second identical crop is a cache hit
        self.assertEqual(stats['hits'], 1)


if __name__ == '__main__':
    unittest.main()
