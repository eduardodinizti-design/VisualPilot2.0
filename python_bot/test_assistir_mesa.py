"""Live advisor loop glue: advise_frame detects tables and advises each.

detect_table_crops and advise_table are mocked; this checks only the frame glue
(complete tables only, indexing, boxes). The readers/advisor are tested
elsewhere, the capture loop live."""
import unittest
from unittest.mock import patch
import numpy as np

import assistir_mesa


class _Prop:
    def __init__(self, box, status):
        self.box = box
        self.status = status


class AdviseFrameTests(unittest.TestCase):
    def test_only_complete_tables_are_advised(self):
        frame = np.zeros((200, 300, 3), np.uint8)
        props = [_Prop((0, 0, 100, 100), 'COMPLETE_CANDIDATE'),
                 _Prop((120, 0, 100, 100), 'UNCERTAIN'),
                 _Prop((0, 110, 100, 80), 'COMPLETE_CANDIDATE')]
        with patch('assistir_mesa.detect_table_crops', return_value=props), \
             patch('assistir_mesa.advise_table', return_value={'is_table': True, 'ok': True}) as adv:
            out = assistir_mesa.advise_frame(frame, {}, advisor=object(), max_tables=6)
        self.assertEqual([r['table_index'] for r in out], [1, 2])     # only the two COMPLETE ones
        self.assertEqual(out[0]['box'], [0, 0, 100, 100])
        self.assertEqual(adv.call_count, 2)

    def test_no_complete_tables_returns_empty(self):
        with patch('assistir_mesa.detect_table_crops', return_value=[_Prop((0, 0, 10, 10), 'UNCERTAIN')]), \
             patch('assistir_mesa.advise_table') as adv:
            out = assistir_mesa.advise_frame(np.zeros((50, 50, 3), np.uint8), {}, advisor=object())
        self.assertEqual(out, [])
        adv.assert_not_called()


if __name__ == '__main__':
    unittest.main()
