import unittest
from observation_metrics import ObservationMetrics
from test_window_capture_engine import Backend
from window_capture_engine import WindowCaptureEngine
from continuous_observer import observe

class LabTests(unittest.TestCase):
    def test_idle_zeros_do_not_dilute_ocr(self):
        m=ObservationMetrics()
        for _ in range(99):m.add({},dict(attempts={'card_reading':0},timings_ms={'card_reading':0}),100)
        m.add({},dict(attempts={'card_reading':1},timings_ms={'card_reading':700}),900)
        self.assertEqual(m.summary()['card_reading']['n'],1)
        self.assertEqual(m.summary()['card_reading']['median_ms'],700)
        self.assertEqual(m.summary()['cycle_with_ocr']['median_ms'],900)
        self.assertEqual(m.counts()['cycles_with_card_reader'],1)
    def test_failures_and_rejections_bounded(self):
        m=ObservationMetrics(limit=3)
        for _ in range(50):m.failure('WINDOW_MINIMIZED')
        m.add({},dict(tables=[dict(status='UNCERTAIN',reasons=['FULL_BOUNDARY_NOT_ESTABLISHED'])]),100)
        self.assertEqual(m.counts()['window'],3)
        self.assertEqual(m.counts()['statuses']['WINDOW_MINIMIZED'],2)
        self.assertEqual(m.counts()['rejection_reasons']['FULL_BOUNDARY_NOT_ESTABLISHED'],1)
    def test_geometry_change_rejected_then_next_capture_recovers(self):
        backend=Backend();backend.after=lambda s:s.update(client_rect=(0,0,20,30))
        engine=WindowCaptureEngine(_backend=backend)
        self.assertIsNone(engine.capture_frame(hwnd=1)[0])
        backend.after=None
        frame,meta=engine.capture_frame(hwnd=1)
        self.assertEqual(frame.shape,(30,20,3));self.assertEqual(meta['status'],'SUCCESS')
    def test_long_failure_run_has_no_reader_calls(self):
        class Engine:
            def capture_frame(self,hwnd):return None,{'status':'WINDOW_MINIMIZED'}
        def forbidden(*a,**k):raise AssertionError('reader called')
        self.assertEqual(observe(Engine(),1,max_cycles=1000,analyze=forbidden,emit=lambda _:None,sleep=lambda _:None),0)

class OCRWorkTests(unittest.TestCase):
    def test_ocr_counts_are_bounded_and_not_reported_as_milliseconds(self):
        m=ObservationMetrics(limit=2)
        for _ in range(3):m.add({},dict(ocr_work=dict(requests=10,calls=6,hits=4)),100)
        self.assertEqual(m.counts()['ocr_work'],dict(requests=20,calls=12,hits=8))
        self.assertNotIn('hits',m.summary())
        m.failure('WINDOW_MINIMIZED')
        self.assertEqual(m.counts()['ocr_work'],dict(requests=10,calls=6,hits=4))
