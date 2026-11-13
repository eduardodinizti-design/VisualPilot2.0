"""Testes do leitor do painel de aumento + mapeamento de sizing."""
import os
import unittest

from raise_panel import map_multiplier_to_preset, parse_multiplier

HERE = os.path.dirname(os.path.abspath(__file__))
GAB = os.path.join(HERE, 'tests', 'fixtures', 'raise_panel',
                   'karekas-raise-panel-2x-2.5x-3x-4x.png')


def _ocr_ok():
    try:
        import tesserocr  # noqa: F401
        import cv2  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _presets(*mults):
    return [dict(box=[i, 0, 1, 1], label='%sx' % m, mult=m)
            for i, m in enumerate(mults)]


class MultiplierTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_multiplier('2.5x'), 2.5)
        self.assertEqual(parse_multiplier('2x'), 2.0)
        self.assertEqual(parse_multiplier('3×'), 3.0)
        self.assertIsNone(parse_multiplier('abc'))

    def test_map_nearest(self):
        ps = _presets(2.0, 2.5, 3.0, 4.0)
        self.assertEqual(map_multiplier_to_preset(2.5, ps)['mult'], 2.5)   # open 2.5
        self.assertEqual(map_multiplier_to_preset(2.0, ps)['mult'], 2.0)   # open 2.0
        self.assertEqual(map_multiplier_to_preset(3.4, ps)['mult'], 3.0)   # 3bet BB~3.4
        self.assertEqual(map_multiplier_to_preset(2.9, ps)['mult'], 3.0)   # 3bet SB~2.9

    def test_map_tie_prefers_smaller(self):
        ps = _presets(2.0, 3.0)
        self.assertEqual(map_multiplier_to_preset(2.5, ps)['mult'], 2.0)   # empate -> menor

    def test_map_none_when_no_readable(self):
        self.assertIsNone(map_multiplier_to_preset(2.5, [dict(mult=None)]))
        self.assertIsNone(map_multiplier_to_preset(None, _presets(2.0)))

    def test_large_target_has_no_compatible_preset(self):
        # #4 do feedback: alvo 25x (all-in) NAO vira 4x; sem preset compativel -> None
        ps = _presets(2.0, 2.5, 3.0, 4.0)
        self.assertIsNone(map_multiplier_to_preset(25.0, ps))
        self.assertIsNone(map_multiplier_to_preset(6.0, ps))     # 6x tambem fora
        self.assertEqual(map_multiplier_to_preset(3.4, ps)['mult'], 3.0)  # 3bet ok


@unittest.skipUnless(os.path.exists(GAB) and _ocr_ok(), 'OCR/gabarito ausente')
class RealPanelTest(unittest.TestCase):
    def setUp(self):
        import cv2
        from table_reading.pipeline import configure_ocr
        from table_reading import ocr_runtime
        configure_ocr()
        self.addCleanup(ocr_runtime.disable_inprocess_ocr)
        self.cv2 = cv2

    def test_reads_four_presets_and_confirm(self):
        from raise_panel import read_raise_panel
        r = read_raise_panel(self.cv2.imread(GAB))
        self.assertEqual(r['status'], 'EXPERIMENTAL_RAISE_PANEL')
        self.assertIsNotNone(r['confirm'])
        mults = sorted(p['mult'] for p in r['presets'] if p['mult'] is not None)
        self.assertEqual(mults, [2.0, 2.5, 3.0, 4.0])


if __name__ == '__main__':
    unittest.main()
