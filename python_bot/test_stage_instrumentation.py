"""Per-stage instrumentation: OCR wall time, CPU/memory budget, aggregation.

These are lab/unit measurements of the timing plumbing, not Windows capture or
accuracy benchmarks."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np

from table_reading import ocr_runtime as runtime
from observation_metrics import ObservationMetrics
import stage_metrics
from coletar_sessao import run_session


class OCRWallTests(unittest.TestCase):
    def setUp(self):
        self.image = np.arange(24, dtype=np.uint8).reshape(4, 6)
        self.patch = patch.object(runtime.pytesseract, 'image_to_string', return_value='A')
        self.ocr = self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_wall_ms_counts_only_real_calls(self):
        # Two identical reads: one real tesseract call (timed) + one cache hit (not timed).
        with patch.object(runtime.time, 'perf_counter', side_effect=[10.0, 10.003]):
            with runtime.ocr_frame() as stats:
                runtime.image_to_string(self.image, config='--psm 7')
                runtime.image_to_string(self.image.copy(), config='--psm 7')
        self.assertEqual(self.ocr.call_count, 1)
        self.assertEqual(stats['calls'], 1)
        self.assertEqual(stats['hits'], 1)
        self.assertAlmostEqual(stats['wall_ms'], 3.0, places=6)

    def test_wall_ms_present_even_without_calls(self):
        with runtime.ocr_frame() as stats:
            pass
        self.assertEqual(stats['wall_ms'], 0.0)


class MetricsTests(unittest.TestCase):
    def test_ocr_wall_is_surfaced_as_a_stage(self):
        m = ObservationMetrics()
        m.add({}, dict(attempts={'card_reading': 1}, timings_ms={'card_reading': 5},
                       ocr_work=dict(requests=2, calls=1, hits=1, wall_ms=12)), 100)
        self.assertEqual(m.summary()['ocr_wall']['median_ms'], 12)

    def test_ocr_wall_dropped_when_no_reader_ran(self):
        m = ObservationMetrics()
        m.add({}, dict(attempts={'card_reading': 0}, timings_ms={'card_reading': 0},
                       ocr_work=dict(requests=0, calls=0, hits=0, wall_ms=0.0)), 100)
        self.assertNotIn('ocr_wall', m.summary())

    def test_cpu_and_memory_budget(self):
        m = ObservationMetrics()
        for rss in (40.0, 60.0, 50.0):
            m.add({}, dict(attempts={'card_reading': 1}, timings_ms={'card_reading': 5}),
                  100, resources={'cpu_ms': 7, 'rss_mb': rss})
        self.assertEqual(m.summary()['cpu']['median_ms'], 7)
        self.assertEqual(m.memory_mb(), {'n': 3, 'median_mb': 50.0, 'peak_mb': 60.0})

    def test_resources_optional_and_bad_values_ignored(self):
        m = ObservationMetrics()
        m.add({}, dict(attempts={}), 100)  # no resources at all
        m.add({}, dict(attempts={}), 100, resources={'cpu_ms': float('nan'), 'rss_mb': -1})
        self.assertIsNone(m.memory_mb())
        self.assertNotIn('cpu', m.summary())


class StageMetricsTests(unittest.TestCase):
    def _record(self):
        return dict(duration_ms=120.0, cpu_ms=80.0, rss_mb=55.0,
                    capture=dict(duration_ms=20.0),
                    report=dict(duration_ms=95.0,
                                timings_ms=dict(detection=10.0, ocr_setup=2.0, card_reading=30.0,
                                                button_reading=15.0, board_reading=0.0),
                                ocr_work=dict(calls=3, wall_ms=40.0),
                                attempts=dict(card_reading=1, button_reading=1, board_reading=0)))

    def test_row_applies_idle_zero_rule(self):
        row = stage_metrics.row_from_record(self._record())
        self.assertEqual(row['capture'], 20.0)
        self.assertEqual(row['card_reading'], 30.0)
        self.assertEqual(row['ocr_wall'], 40.0)
        self.assertEqual(row['analyze_total'], 95.0)
        self.assertEqual(row['cycle'], 120.0)
        self.assertEqual(row['cpu'], 80.0)
        self.assertEqual(row['rss_mb'], 55.0)
        self.assertNotIn('board_reading', row)  # zero attempts dropped

    def test_failed_record_yields_only_available_stages(self):
        row = stage_metrics.row_from_record(dict(status='CAPTURE_FAILED', duration_ms=5.0, cpu_ms=1.0))
        self.assertEqual(set(row), {'cycle', 'cpu'})

    def test_summarize_orders_and_computes_memory(self):
        rows = [stage_metrics.row_from_record(self._record()) for _ in range(4)]
        profile = stage_metrics.summarize(rows)
        self.assertEqual(profile['stages']['cycle']['median_ms'], 120.0)
        self.assertEqual(profile['memory'], {'n': 4, 'median_mb': 55.0, 'peak_mb': 55.0})
        order = profile['stage_order']
        self.assertLess(order.index('capture'), order.index('detection'))
        self.assertLess(order.index('card_reading'), order.index('cycle'))
        self.assertIn('Etapa', stage_metrics.format_table(profile))


class _Clock:
    def __init__(self): self.t = 0
    def __call__(self): return self.t
    def sleep(self, n): self.t += n


class _Engine:
    def __init__(self, clock): self.clock = clock; self.n = 0
    def capture_frame(self, hwnd):
        self.clock.t += 15; self.n += 1
        return np.zeros((20, 30, 3), np.uint8), dict(status='SUCCESS', hwnd=hwnd, pid=2,
                                                     process_created=1, executable='PPPoker.exe', duration_ms=8.0)


class SessionProfileTests(unittest.TestCase):
    def test_session_summary_has_stage_profile_and_records_carry_cpu(self):
        import json
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); clock = _Clock()
        folder, summary = run_session(
            _Engine(clock), [1], minutes=1, output=Path(tmp.name), clock=clock, sleep=clock.sleep,
            analyze=lambda *a, **k: dict(tables=[], duration_ms=5.0, attempts={'card_reading': 0},
                                         timings_ms={'detection': 3.0}))
        profile = summary['stage_profile']
        self.assertIn('cycle', profile['stages'])
        self.assertIn('detection', profile['stages'])
        self.assertIsNotNone(profile['memory'])
        rows = [json.loads(l) for l in (folder / 'leituras.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertIn('cpu_ms', rows[0])
        self.assertIn('rss_mb', rows[0])


if __name__ == '__main__':
    unittest.main()
