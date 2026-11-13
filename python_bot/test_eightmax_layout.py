"""Calibração do assento top_center (mesas PPPoker 8-max) contra 2 frames REAIS.

As mesas PPPoker usadas têm UM assento no topo (top_center), não os dois top_left/
top_right do 9-max. O SEAT_ANCHORS perdia esse jogador. Validado aqui com ground truth:
RM6702 26,6 BB (MACHINE PKO) e Dekkii 48,8 BB (CRAZY REBUY)."""
import os
import unittest

import cv2

from table_reading.table_state import read_seat_stacks, read_occupancy

PKO = os.path.join('tests', 'fixtures', 'bounty_live', 'machine-pko-bounty-135.png')
REBUY = os.path.join('tests', 'fixtures', 'seat_live',
                     'pppoker-8max-rebuy-topcenter-dekkii-488.png')


class TopCenterSeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from table_reading.pipeline import configure_ocr
            configure_ocr()
        except Exception as exc:                        # noqa: BLE001
            raise unittest.SkipTest('OCR indisponivel: %s' % exc)

    def test_pko_reads_top_center_stack(self):
        crop = cv2.imread(PKO)
        self.assertIsNotNone(crop, 'fixture ausente: %s' % PKO)
        seats = read_seat_stacks(crop)
        self.assertIn('top_center', seats)
        self.assertEqual(seats['top_center']['stack_bb'], 26.6)   # RM6702
        self.assertTrue(read_occupancy(crop)['top_center']['occupied'])

    def test_rebuy_reads_top_center_stack(self):
        crop = cv2.imread(REBUY)
        self.assertIsNotNone(crop, 'fixture ausente: %s' % REBUY)
        seats = read_seat_stacks(crop)
        self.assertEqual(seats['top_center']['stack_bb'], 48.8)   # Dekkii

    def test_nine_max_top_seats_empty_on_8max(self):
        # Numa mesa 8-max (topo = top_center), os assentos 9-max top_left/top_right
        # ficam em feltro vazio -> não ocupados (sem falso-positivo).
        crop = cv2.imread(PKO)
        occ = read_occupancy(crop)
        self.assertFalse(occ['top_left']['occupied'])
        self.assertFalse(occ['top_right']['occupied'])


if __name__ == '__main__':
    unittest.main()
