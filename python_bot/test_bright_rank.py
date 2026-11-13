"""Regressão do leitor de rank CLARO em tile ESCURO (skin Karekas).

Causa raiz (09/11): o '8' cinza em carta de espada no skin Karekas MKO tem baixo
contraste; o OCR por OTSU/segmentação do read_rank abstinha mesmo com a carta
bem localizada. `read_bright_rank` (threshold alto relativo ao brilho + voto
entre thresholds) resgata o dígito, só quando o primário e o fallback nativo já
abstiveram — aditivo, sem regressão nos skins validados.

Gated em tesserocr + imagens reais (pula no lab sem OCR).
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KAREKAS = os.path.join(HERE, 'logs', 'sessoes', 'sessao-20261108-200315-f2b0d315')
F1 = os.path.join(KAREKAS, 'sample-000001-mesa-2.png')   # ground truth 8s 3c
F2 = os.path.join(KAREKAS, 'sample-000032-mesa-2.png')   # ground truth 2h 4d


def _ocr_available():
    # NÃO configura o OCR aqui (skipUnless roda na import): só checa disponibilidade,
    # para não poluir o backend global de outros testes.
    try:
        import tesserocr  # noqa: F401
        import cv2  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(os.path.exists(F1) and _ocr_available(), 'OCR/gabarito Karekas ausente')
class BrightRankTest(unittest.TestCase):
    def setUp(self):
        import cv2
        from table_reading.pipeline import configure_ocr
        from table_reading import ocr_runtime
        configure_ocr()
        self.addCleanup(ocr_runtime.disable_inprocess_ocr)   # restaura o backend
        self.cv2 = cv2

    def test_bright_rank_reads_low_contrast_8(self):
        from table_reading.inspect_cards import read_bright_rank
        table = self.cv2.resize(self.cv2.imread(F1), (720, 1280))
        self.assertEqual(read_bright_rank(table[1010:1070, 402:444]), '8')

    def test_hero_cards_8s_3c(self):
        from table_advisor import read_hero_cards
        self.assertEqual(read_hero_cards(self.cv2.imread(F1)), ['8s', '3c'])

    @unittest.skipUnless(os.path.exists(F2), 'gabarito 000032 ausente')
    def test_hero_cards_2h_4d(self):
        from table_advisor import read_hero_cards
        self.assertEqual(read_hero_cards(self.cv2.imread(F2)), ['2h', '4d'])

    def test_bright_rank_abstains_on_blank(self):
        import numpy as np
        from table_reading.inspect_cards import read_bright_rank
        self.assertIsNone(read_bright_rank(np.zeros((60, 42, 3), np.uint8)))


if __name__ == '__main__':
    unittest.main()
