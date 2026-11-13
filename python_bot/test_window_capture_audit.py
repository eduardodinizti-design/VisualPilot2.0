import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from window_capture_engine import WindowCaptureEngine
from test_window_capture_engine import Backend
import windows_capture_diagnostics as diagnostics
import window_stream
from vision_pipeline import PPPokerObserverPipeline

class IntegrationContracts(unittest.TestCase):
    def test_diagnostic_saves_linux_failure_without_image(self):
        with tempfile.TemporaryDirectory() as folder, patch('platform.system',return_value='Linux'), contextlib.redirect_stdout(io.StringIO()):
            folder=Path(folder)/"diagnostics"
            result=diagnostics.run_diagnostics(output_dir=folder)
            self.assertFalse(result['capture_success'])
            self.assertEqual(result['status'],'ENVIRONMENT_NOT_WINDOWS')
            files=list(Path(folder).glob('*.json'));self.assertEqual(len(files),1)
            self.assertEqual(json.loads(files[0].read_text())['status'],'ENVIRONMENT_NOT_WINDOWS')
            self.assertFalse(list(Path(folder).glob('*.png')))
    def test_diagnostic_forwards_selected_hwnd(self):
        b=Backend();b.windows[2]=dict(b.windows[1],hwnd=2)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            folder=Path(folder)/"diagnostics"
            r=diagnostics.run_diagnostics(2,folder,_engine=WindowCaptureEngine(_backend=b))
            self.assertEqual(r['hwnd'],2);self.assertTrue(r['capture_success'])
            self.assertTrue(Path(r['image_path']).exists())
        self.assertEqual(b.captured,[(2,16,24)])
    def test_standalone_routes_to_engine(self):
        b=Backend()
        with patch.object(window_stream,'_engine',WindowCaptureEngine(_backend=b)):
            self.assertIsNotNone(window_stream.capture_pppoker_window(1))
        self.assertEqual(b.captured,[(1,16,24)])
    def test_observer_routes_to_engine(self):
        b=Backend()
        with patch('vision_pipeline.WindowCaptureEngine',return_value=WindowCaptureEngine(_backend=b)):
            frame,status=PPPokerObserverPipeline.capture_window(1)
        self.assertEqual(status,'SUCCESS');self.assertEqual(b.captured,[(1,16,24)])

if __name__=='__main__':unittest.main()
