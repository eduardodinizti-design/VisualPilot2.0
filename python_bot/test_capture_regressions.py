import sys
import unittest
from unittest.mock import MagicMock, patch
import window_capture_engine as engine

class OriginalRegressionTests(unittest.TestCase):
    def test_linux_cannot_report_success(self):
        with patch('platform.system', return_value='Linux'):
            frame, meta = engine.WindowCaptureEngine().capture_frame()
        self.assertIsNone(frame)
        self.assertEqual(meta['status'], 'ENVIRONMENT_NOT_WINDOWS')

    def test_process_access_denied_is_rejected(self):
        proc = MagicMock()
        proc.Process.side_effect = PermissionError('denied')
        with patch.dict(sys.modules, {'psutil': proc}):
            valid, _, _ = engine.WindowCaptureEngine()._validate_process(12345)
        self.assertFalse(valid)

    def test_arbitrary_executable_is_rejected(self):
        proc = MagicMock()
        proc.Process.return_value.name.return_value = 'unrelated_app.exe'
        with patch.dict(sys.modules, {'psutil': proc}):
            valid, _, _ = engine.WindowCaptureEngine()._validate_process(12345)
        self.assertFalse(valid)

if __name__ == '__main__': unittest.main()
