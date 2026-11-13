import unittest
from test_window_capture_engine import Backend
from window_capture_engine import WindowCaptureEngine
from observation_metrics import ObservationMetrics

class ReviewTests(unittest.TestCase):
    def test_diagnostics_copy_and_failure_replaces_success(self):
        engine=WindowCaptureEngine(_backend=Backend())
        self.assertEqual(engine.get_diagnostic_info()['status'],'CAPTURE_NOT_STARTED')
        engine.capture_frame(hwnd=1)
        result=engine.get_diagnostic_info();result['image_shape'][0]=999
        self.assertEqual(engine.get_diagnostic_info()['image_shape'][0],24)
        engine.capture_frame(hwnd=99)
        self.assertEqual(engine.get_diagnostic_info()['status'],'WINDOW_INVALID_HWND')
        self.assertNotIn('image_shape',engine.get_diagnostic_info())
    def test_metrics_bounded_and_percentiles(self):
        metrics=ObservationMetrics(limit=20)
        for n in range(30):metrics.add({'duration_ms':n},{'timings_ms':{'detection':n}},n)
        summary=metrics.summary()['cycle']
        self.assertEqual(summary,{'n':20,'median_ms':19.5,'p95_ms':28.0})
    def test_missing_timing_not_reported_as_zero(self):
        metrics=ObservationMetrics();metrics.add({}, {}, 100)
        self.assertEqual(set(metrics.summary()),{'cycle','cycle_without_ocr'})
