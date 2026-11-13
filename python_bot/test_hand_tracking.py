"""Temporal identity: hand-id parsing and the hand tracker.

read_hand_id is tested with mocked OCR; HandTracker is pure logic. These pin new
hand detection, the pending/suspect guards and per-table isolation."""
import unittest
from unittest.mock import patch
import numpy as np

from table_reading import hand_tracking
from table_reading.hand_tracking import HandTracker


class HandIdTests(unittest.TestCase):
    def setUp(self):
        self.crop = np.zeros((1334, 750, 3), np.uint8)

    def _read(self, text):
        with patch('table_reading.hand_tracking.image_to_string', return_value=text):
            return hand_tracking.read_hand_id(self.crop)

    def test_full_id(self):
        r = self._read('ID: 261108055446-14126629-0000426-8')
        self.assertEqual(r['hand_number'], 426)
        self.assertEqual(r['hand_id'], '261108055446-14126629-0000426-8')
        self.assertEqual(r['table_ref'], '261108055446-14126629')
        self.assertEqual(r['confidence'], 'high')

    def test_partial_recovers_hand_number(self):
        r = self._read('ID: 2611 osos adeiat 26629-0000297-6')
        self.assertEqual(r['hand_number'], 297)
        self.assertIsNone(r['hand_id'])
        self.assertEqual(r['confidence'], 'medium')

    def test_unreadable_abstains(self):
        r = self._read('pore')
        self.assertIsNone(r['hand_number'])
        self.assertEqual(r['confidence'], 'abstain')


class TrackerTests(unittest.TestCase):
    def test_new_table_then_same_then_new_hand(self):
        t = HandTracker()
        self.assertEqual(t.observe('A', 100)['event'], 'new_table')
        e = t.observe('A', 100)
        self.assertEqual((e['event'], e['frame']), ('same_hand', 2))
        e = t.observe('A', 101)
        self.assertEqual((e['event'], e['frame'], e['previous']['hand_number']), ('new_hand', 1, 100))

    def test_unreadable_id_keeps_current_hand(self):
        t = HandTracker()
        t.observe('A', 100)
        e = t.observe('A', None)
        self.assertEqual(e['event'], 'pending_id')
        self.assertEqual(e['hand_number'], 100)  # did not drop the hand

    def test_regressing_id_is_suspect_not_a_new_hand(self):
        t = HandTracker()
        t.observe('A', 101)
        e = t.observe('A', 99)
        self.assertEqual(e['event'], 'suspect_id')
        self.assertEqual(e['hand_number'], 101)  # kept the real hand

    def test_implausible_jump_is_suspect_not_poisoning(self):
        # Achado ao vivo 09/11: um trecho do timestamp lido como nº da mao (ex.
        # 9133624) NAO pode virar nova mao e travar o rastreamento em suspect.
        t = HandTracker()
        t.observe('A', 596)
        e = t.observe('A', 9133624)
        self.assertEqual(e['event'], 'suspect_id')
        self.assertEqual(e['hand_number'], 596)                 # manteve a mao real
        self.assertEqual(t.observe('A', 597)['event'], 'new_hand')  # segue normal

    def test_first_frame_without_id_is_new_table(self):
        self.assertEqual(HandTracker().observe('A', None)['event'], 'new_table')

    def test_tables_are_independent(self):
        t = HandTracker()
        t.observe('A', 100)
        self.assertEqual(t.observe('B', 500)['event'], 'new_table')
        self.assertEqual(t.observe('A', 100)['event'], 'same_hand')
        self.assertEqual(t.current('A')['hand_number'], 100)
        self.assertEqual(t.current('B')['hand_number'], 500)


if __name__ == '__main__':
    unittest.main()
