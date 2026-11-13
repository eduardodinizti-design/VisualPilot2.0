"""Exact per-frame OCR memo contract; mocked OCR, not accuracy benchmarks."""
import unittest
from unittest.mock import patch
import numpy as np
from table_reading import ocr_runtime as runtime


def setUpModule():
    # These tests pin the subprocess cache/counting path; keep them deterministic
    # even if an earlier module left the in-process backend enabled.
    runtime.disable_inprocess_ocr()


class OCRFrameTests(unittest.TestCase):
    def setUp(self):
        self.image=np.arange(24,dtype=np.uint8).reshape(4,6)
        self.patch=patch.object(runtime.pytesseract,'image_to_string',return_value='A')
        self.ocr=self.patch.start()
        self.addCleanup(self.patch.stop)

    def call(self,image=None,**kwargs):
        return runtime.image_to_string(self.image if image is None else image,**kwargs)

    def test_identical_copy_reuses_result(self):
        with runtime.ocr_frame():
            self.assertEqual(self.call(config='--psm 7',timeout=3),'A')
            self.assertEqual(self.call(self.image.copy(),config='--psm 7',timeout=3),'A')
        self.assertEqual(self.ocr.call_count,1)

    def test_pixel_mutation_invalidates(self):
        with runtime.ocr_frame():
            self.call();self.image[0,0]+=1;self.call()
        self.assertEqual(self.ocr.call_count,2)

    def test_shape_dtype_and_configuration_are_part_of_identity(self):
        with runtime.ocr_frame():
            self.call()
            self.call(self.image.reshape(6,4))
            self.call(self.image.view(np.int8))
            self.call(config='--psm 7')
            self.call(config='--psm 10')
            self.call(timeout=2)
            self.call(timeout=3)
            self.call(lang='eng')
        self.assertEqual(self.ocr.call_count,8)

    def test_frames_never_share_results(self):
        for _ in range(2):
            with runtime.ocr_frame():self.call();self.call()
        self.assertEqual(self.ocr.call_count,2)

    def test_no_frame_is_passthrough(self):
        self.call();self.call()
        self.assertEqual(self.ocr.call_count,2)

    def test_exception_not_cached_and_frame_cleanup(self):
        self.ocr.side_effect=[RuntimeError('timeout'),'A','A']
        with self.assertRaises(RuntimeError):
            with runtime.ocr_frame():self.call()
        with runtime.ocr_frame():self.call();self.call()
        self.call()
        self.assertEqual(self.ocr.call_count,3)

    def test_exception_retry_within_frame(self):
        self.ocr.side_effect=[RuntimeError('timeout'),'A']
        with runtime.ocr_frame():
            with self.assertRaises(RuntimeError):self.call()
            self.assertEqual(self.call(),'A')
            self.assertEqual(self.call(),'A')
        self.assertEqual(self.ocr.call_count,2)

    def test_outer_disabled_cannot_be_enabled_by_nested_frame(self):
        with runtime.ocr_frame(enabled=False):
            self.call()
            with runtime.ocr_frame(enabled=True):self.call();self.call()
            self.call()
        self.assertEqual(self.ocr.call_count,4)

    def test_enabled_nested_context_reuses_same_frame(self):
        with runtime.ocr_frame():
            self.call()
            with runtime.ocr_frame():self.call()
            self.call()
        self.assertEqual(self.ocr.call_count,1)

    def test_statistics_count_requests_and_real_calls(self):
        with runtime.ocr_frame() as stats:
            self.call();self.call()
        self.assertEqual(stats['requests'],2)
        self.assertEqual(stats['calls'],1)
        self.assertEqual(stats['hits'],1)
        self.assertEqual(stats['bytes'],self.image.nbytes+1)

    def test_entry_limit_is_bounded_and_uncached_values_still_work(self):
        with patch.object(runtime,'MAX_ENTRIES',1):
            with runtime.ocr_frame() as stats:
                self.call(config='one');self.call(config='two');self.call(config='two')
                self.call(config='one')
        self.assertEqual(self.ocr.call_count,3)
        self.assertEqual(stats['hits'],1)

    def test_payload_limit_includes_output_and_preserves_results(self):
        with patch.object(runtime,'MAX_BYTES',self.image.nbytes):
            with runtime.ocr_frame() as stats:self.call();self.call()
        self.assertEqual(self.ocr.call_count,2)
        self.assertEqual(stats['bytes'],0)

    def test_unsupported_objects_options_and_mutable_output_bypass(self):
        with runtime.ocr_frame():
            self.call('image.png');self.call('image.png')
            self.call(options=[]);self.call(options=[])
            self.ocr.return_value={'text':'A'}
            self.call();self.call()
        self.assertEqual(self.ocr.call_count,6)

    def test_backend_path_change_invalidates(self):
        with runtime.ocr_frame():
            self.call()
            with patch.object(runtime.pytesseract.pytesseract,'tesseract_cmd','other'):
                self.call()
        self.assertEqual(self.ocr.call_count,2)

    def test_noncontiguous_view_matches_identical_pixels(self):
        view=self.image[:,::2]
        with runtime.ocr_frame():self.call(view);self.call(view.copy())
        self.assertEqual(self.ocr.call_count,1)

    def test_threads_have_independent_frames(self):
        from concurrent.futures import ThreadPoolExecutor
        def task():
            with runtime.ocr_frame() as stats:
                self.call();self.call()
                return stats.copy()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:task(),range(2)))
        self.assertEqual(self.ocr.call_count,2)
        self.assertEqual([s['hits'] for s in results],[1,1])

    def test_empty_string_is_valid_cached_output(self):
        self.ocr.return_value=''
        with runtime.ocr_frame():self.call();self.call()
        self.assertEqual(self.ocr.call_count,1)

if __name__=='__main__':unittest.main()
