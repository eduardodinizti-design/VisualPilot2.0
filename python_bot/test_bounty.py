"""Testes do parser do valor do bounty e da abstenção do leitor (ROI não calibrada).

O parser é puro (strings sintéticas); o ROI do valor no skin só será calibrado com
uma amostra REAL de mesa PKO/MKO-no-ITM (ver table_reading/bounty.py)."""
import os
import unittest

import cv2
import numpy as np

from table_reading.bounty import parse_bounty, read_bounty, read_seat_bounties, _to_float


class ToFloatTests(unittest.TestCase):
    def test_decimal_comma_and_dot(self):
        self.assertEqual(_to_float('2,5'), 2.5)
        self.assertEqual(_to_float('2.5'), 2.5)
        self.assertEqual(_to_float('48,8'), 48.8)

    def test_thousands_vs_decimal(self):
        self.assertEqual(_to_float('1.200,50'), 1200.5)   # ponto milhar, vírgula decimal
        self.assertEqual(_to_float('1,200.50'), 1200.5)   # vírgula milhar, ponto decimal
        self.assertEqual(_to_float('1.200'), 1200.0)      # ponto de milhar (3 dígitos)
        self.assertEqual(_to_float('1200'), 1200.0)

    def test_invalid(self):
        self.assertIsNone(_to_float('abc'))


class ParseBountyTests(unittest.TestCase):
    def test_bb_unit(self):
        r = parse_bounty('8,0 BB')
        self.assertEqual(r['value'], 8.0)
        self.assertEqual(r['unit'], 'bb')
        self.assertEqual(r['confidence'], 'high')

    def test_currency_unit(self):
        r = parse_bounty('$ 2,50')
        self.assertEqual(r['value'], 2.5)
        self.assertEqual(r['unit'], 'currency')
        self.assertEqual(r['confidence'], 'high')

    def test_unknown_unit_is_not_assumed_bb(self):
        r = parse_bounty('15')
        self.assertEqual(r['value'], 15.0)
        self.assertEqual(r['unit'], 'unknown')        # sem BB/moeda -> não assume BB
        self.assertEqual(r['confidence'], 'medium')

    def test_k_suffix(self):
        self.assertEqual(parse_bounty('1,2k')['value'], 1200.0)

    def test_coin_icon_noise_ignored(self):
        # lixo de ícone/estrela ao redor do número não impede a leitura do valor+unidade
        r = parse_bounty('* 3,0 BB')
        self.assertEqual(r['value'], 3.0)
        self.assertEqual(r['unit'], 'bb')

    def test_empty_and_no_digits_abstain(self):
        for t in ('', None, 'MKO', '---'):
            r = parse_bounty(t)
            self.assertIsNone(r['value'])
            self.assertEqual(r['confidence'], 'abstain')


class ReadBountyAbstainTests(unittest.TestCase):
    def test_no_calibrated_roi_abstains(self):
        crop = np.zeros((1334, 750, 3), np.uint8)
        r = read_bounty(crop)                          # sem roi -> não adivinha posição
        self.assertIsNone(r['bounty_bb'])
        self.assertEqual(r['confidence'], 'abstain')
        self.assertEqual(r['source'], 'no_calibrated_roi')

    def test_calibrated_roi_on_blank_abstains(self):
        # Com ROI calibrada mas sem texto (crop vazio), o OCR não lê nada -> abstém,
        # nunca inventa. Exercita o caminho OCR do leitor sem fixture real.
        try:
            from table_reading.pipeline import configure_ocr
            configure_ocr()
        except Exception:                               # noqa: BLE001
            self.skipTest('OCR indisponivel neste ambiente')
        crop = np.zeros((1334, 750, 3), np.uint8)
        r = read_bounty(crop, roi=(0.83, 0.11, 1.0, 0.20))
        self.assertIsNone(r['bounty_bb'])
        self.assertEqual(r['confidence'], 'abstain')

    def test_currency_reading_is_not_bb(self):
        # Regra: unidade não-BB não vira bounty_bb (precisa de fator de conversão).
        self.assertEqual(parse_bounty('$ 5,00')['unit'], 'currency')


class RealPkoFixtureTests(unittest.TestCase):
    """Pixels REAIS: MACHINE PKO (bounty 135 por jogador, pill acima do avatar). O ROI
    por-assento do skin ainda não está calibrado (captura de janela cheia + layout de
    skin diferente do SEAT_ANCHORS); aqui travamos a leitura do VALOR em 3 pills reais
    com ground truth 135, provando OCR+parse em pixels de PKO de verdade."""
    PATH = os.path.join('tests', 'fixtures', 'bounty_live', 'machine-pko-bounty-135.png')
    ROIS = [(0.42, 0.10, 0.58, 0.135), (0.03, 0.265, 0.20, 0.30), (0.02, 0.485, 0.17, 0.515)]

    def test_reads_135_from_real_pills(self):
        try:
            from table_reading.pipeline import configure_ocr
            configure_ocr()
        except Exception:                               # noqa: BLE001
            self.skipTest('OCR indisponivel neste ambiente')
        crop = cv2.imread(self.PATH)
        self.assertIsNotNone(crop, 'fixture ausente: %s' % self.PATH)
        for roi in self.ROIS:
            r = read_bounty(crop, roi=roi)
            self.assertEqual(r['value'], 135.0)
            self.assertIsNone(r['bounty_bb'])           # 135 nao e BB -> nao vira bounty_bb

    def test_read_seat_bounties_with_profile(self):
        try:
            from table_reading.pipeline import configure_ocr
            configure_ocr()
        except Exception:                               # noqa: BLE001
            self.skipTest('OCR indisponivel neste ambiente')
        crop = cv2.imread(self.PATH)
        self.assertIsNotNone(crop)
        # perfil explícito (outro skin) com 3 assentos confirmados.
        profile = {'topC': (0.42, 0.10, 0.58, 0.135),
                   'TL': (0.03, 0.265, 0.20, 0.30),
                   'RL': (0.81, 0.66, 0.98, 0.695)}
        b = read_seat_bounties(crop, profile=profile)
        self.assertEqual({s: v['value'] for s, v in b.items()},
                         {'topC': 135.0, 'TL': 135.0, 'RL': 135.0})

    def test_read_seat_bounties_voting_never_confident_wrong(self):
        # Caminho automático (bounty_box + votação): no fixture todos valem 135. Exige
        # que leia a MAIORIA e que NENHUM valor emitido esteja errado (abstém na dúvida).
        try:
            from table_reading.pipeline import configure_ocr
            configure_ocr()
        except Exception:                               # noqa: BLE001
            self.skipTest('OCR indisponivel neste ambiente')
        crop = cv2.imread(self.PATH)
        occ = ['hero', 'bot_right', 'right_low', 'right_up', 'top_center',
               'left_up', 'left_low', 'bot_left']
        b = read_seat_bounties(crop, seats=occ)
        read = [v['value'] for v in b.values() if v['value'] is not None]
        self.assertGreaterEqual(len(read), 4)             # lê a maioria dos assentos
        self.assertTrue(all(v == 135.0 for v in read))    # nunca confiante-errado


if __name__ == '__main__':
    unittest.main()
