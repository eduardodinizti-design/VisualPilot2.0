import os
import threading
import unittest
from unittest.mock import patch
import numpy as np
from table_reading.concurrent_reads import ordered_board_reads
from table_reading.ocr_runtime import ocr_frame,image_to_string

class ConcurrentTests(unittest.TestCase):
    def test_two_workers_overlap_and_preserve_order(self):
        barrier=threading.Barrier(2)
        def read(n):barrier.wait(timeout=3);return n*2
        with patch.dict(os.environ,VISUALPILOT_PARALLEL_BOARD='1'):
            self.assertEqual(ordered_board_reads(read,[2,1]),[4,2])
    def test_exception_is_propagated(self):
        def read(n):raise ValueError('test')
        with self.assertRaises(ValueError):ordered_board_reads(read,[1,2])
    def test_frame_cache_propagates_but_does_not_survive_snapshot(self):
        im=np.zeros((10,10),np.uint8)
        with patch('table_reading.ocr_runtime.pytesseract.image_to_string',return_value='A') as ocr:
            for _ in range(2):
                with ocr_frame() as stats:
                    image_to_string(im)
                    self.assertEqual(ordered_board_reads(lambda _:image_to_string(im),[1,2,3]),['A']*3)
                    self.assertEqual(stats['hits'],3)
            self.assertEqual(ocr.call_count,2)
    def test_injected_reader_stays_serial(self):
        threads=[]
        ordered_board_reads(lambda _:threads.append(threading.get_ident()),range(5),enabled=False)
        self.assertEqual(threads,[threading.get_ident()]*5)
    def test_shared_cache_memory_limit(self):
        from table_reading import ocr_runtime as runtime
        barrier=threading.Barrier(2)
        def ocr(*a,**k):barrier.wait(timeout=3);return 'A'
        with patch.object(runtime,'MAX_ENTRIES',1),patch.object(runtime.pytesseract,'image_to_string',side_effect=ocr),ocr_frame() as stats:
            ordered_board_reads(lambda n:image_to_string(np.full((10,10),n,np.uint8)),[1,2])
            self.assertEqual(stats['bytes'],101)
