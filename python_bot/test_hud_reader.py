"""Leitor do HUD VIP (template matching de dígitos) validado no gabarito ROTULADO.

Sem OCR (puro cv2 + atlas de templates) -> determinístico, roda em qualquer ambiente.
Gabarito: MINI FREEZE 9-max (sessao-164218), 7 HUDs de vilão com valores conhecidos."""
import os
import unittest

import cv2

from table_reading.hud_reader import read_hud, read_seat_huds, STAT_NAMES

FIX = os.path.join('tests', 'fixtures', 'hud_live', 'minifreeze-9max-huds.png')
KNOWN = {
    'left_up':   [25, 19, 34, 0, 7, 77, 81, 100],
    'left_low':  [24, 9, 18, 10, 4, 22, 42, 60],
    'bot_left':  [32, 21, 46, 9, 9, 50, 85, 47],
    'top_left':  [32, 21, 44, 20, 12, 37, 38, 32],
    'top_right': [26, 16, 35, 6, 5, 53, 57, 62],
    'right_up':  [25, 12, 23, 3, 3, 29, 27, 50],
    'right_low': [29, 18, 39, 10, 7, 35, 56, 49],
}


class HudReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.crop = cv2.imread(FIX)
        if cls.crop is None:
            raise unittest.SkipTest('fixture ausente: %s' % FIX)

    def test_reads_all_villain_huds_exactly(self):
        huds = read_seat_huds(self.crop, list(KNOWN))
        for seat, exp in KNOWN.items():
            r = huds.get(seat)
            self.assertIsNotNone(r, '%s sem HUD' % seat)
            self.assertEqual([r['stats'][n] for n in STAT_NAMES], exp, seat)
            self.assertEqual(r['confidence'], 'high')

    def test_stat_names_mapped(self):
        r = read_hud(self.crop, 'left_up')          # 25 19 34 0 / 7 77 81 100
        self.assertEqual(r['stats']['vpip'], 25)
        self.assertEqual(r['stats']['pfr'], 19)
        self.assertEqual(r['stats']['steal'], 34)
        self.assertEqual(r['stats']['threebet'], 7)
        self.assertEqual(r['stats']['foldcbet'], 100)

    def test_hero_and_unknown_seat_have_no_hud(self):
        self.assertEqual(read_seat_huds(self.crop, ['hero']), {})
        self.assertIsNone(read_hud(self.crop, 'nope'))

    def test_blank_crop_abstains(self):
        # Robustez: sem HUD na região (crop vazio) -> None (piso + <4 campos), nunca inventa.
        import numpy as np
        blank = np.zeros((1334, 750, 3), np.uint8)
        for seat in ('left_up', 'top_right', 'right_low'):
            self.assertIsNone(read_hud(blank, seat))


if __name__ == '__main__':
    unittest.main()
