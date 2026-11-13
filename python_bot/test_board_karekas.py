"""Regressão da leitura do BOARD no skin Karekas (gabarito ao vivo com ground truth).

Causa raiz (09/11, captura ao vivo): as faces BRANCAS de carta (val>150) não eram
mascaradas na detecção de candidatos do `read_board` (só a máscara neutra/escura,
limitada a val<150). Resultado: num board real (7♦ J♥ 9♦ A♠ J♦) só a carta CINZA
(7♦) virava candidato -> BOARD_NOT_CONFIRMED. Fix: máscara `white=(sat<60)&(val>=150)`
somada à detecção. Aditivo; não regride os skins validados (test_community_cards OK).

Gated em tesserocr + gabarito; pula no lab sem OCR.
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, 'tests', 'fixtures', 'board_live',
                     'karekas-board-river-7d-jh-9d-as-jd.png')


def _ocr_available():
    try:
        import tesserocr  # noqa: F401
        import cv2  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(os.path.exists(BOARD) and _ocr_available(), 'OCR/gabarito board ausente')
class BoardKarekasTest(unittest.TestCase):
    def setUp(self):
        import cv2
        from table_reading.pipeline import configure_ocr
        from table_reading import ocr_runtime
        configure_ocr()
        self.addCleanup(ocr_runtime.disable_inprocess_ocr)   # isola o backend OCR
        self.cv2 = cv2

    def test_reads_full_river_board(self):
        from table_reading.community_cards import read_board
        r = read_board(self.cv2.imread(BOARD))
        self.assertEqual(r['status'], 'EXPERIMENTAL_BOARD')
        self.assertEqual(r['street'], 'RIVER')
        self.assertEqual(r['cards'], ['7d', 'Jh', '9d', 'As', 'Jd'])


if __name__ == '__main__':
    unittest.main()
