"""Testes da revalidação/verificação ao vivo do operador (updates.txt #1 e #2).

Cobrem os bloqueadores de execução: a revalidação RELÊ a mão (não ecoa a esperada)
e a verificação de efeito só confirma com evidência POSITIVA (um read limpo sem a
linha de ação), nunca por erro de OCR/captura.
"""
import unittest
from unittest.mock import patch

import numpy as np

import operar_mesa


class FakeIntent:
    def __init__(self, action, expected):
        self.action = action
        self.expected = expected
        self.source_key = None


class FakeEngine:
    def __init__(self, frame):
        self._frame = frame

    def capture_frame(self, hwnd=None):
        return self._frame, {}


WIN = {'hwnd': 1, 'x': 0, 'y': 0, 'w': 100, 'h': 100}
BTN_ROW = dict(status='EXPERIMENTAL_BUTTON_ROW',
               buttons=[dict(action='FOLD', box=[1, 1, 10, 10], amount=None, unit=None)])


class ValidatorRereadsHand(unittest.TestCase):
    def test_identity_uses_reread_hand_not_expected(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        with patch.object(operar_mesa, 'discover_pppoker', return_value={'windows': [WIN]}), \
                patch.object(operar_mesa, '_find_table_by_key', return_value=(0, 0, 100, 100)), \
                patch.object(operar_mesa, 'read_action_buttons', return_value=BTN_ROW), \
                patch.object(operar_mesa, 'read_hand_id',
                             return_value=dict(hand_id='H2', hand_number=None)):
            v = operar_mesa.make_validator(FakeEngine(frame), 1, 6)
            out = v(FakeIntent('FOLD', dict(table_key='0x0', hand='H1')), 0.0)
        self.assertTrue(out['ok'])
        # identity = (table_key, hand, action, amount, unit): a mão vem do RE-READ (H2),
        # não da esperada (H1) -> uma mão nova faz a identidade divergir e cancela.
        self.assertEqual(out['identity'][1], 'H2')

    def test_button_gone_blocks(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        with patch.object(operar_mesa, 'discover_pppoker', return_value={'windows': [WIN]}), \
                patch.object(operar_mesa, '_find_table_by_key', return_value=(0, 0, 100, 100)), \
                patch.object(operar_mesa, 'read_action_buttons',
                             return_value=dict(status='NO_BUTTON_ROW', buttons=[])):
            v = operar_mesa.make_validator(FakeEngine(frame), 1, 6)
            out = v(FakeIntent('FOLD', dict(table_key='0x0', hand='H1')), 0.0)
        self.assertFalse(out['ok'])
        self.assertIn('NAO_E_VEZ_DO_HERO', out['reasons'])


class VerifierPositiveEvidence(unittest.TestCase):
    def _verify(self, status):
        frame = np.zeros((100, 100, 3), np.uint8)
        with patch.object(operar_mesa.time, 'sleep', lambda *a, **k: None), \
                patch.object(operar_mesa, '_find_table_by_key', return_value=(0, 0, 100, 100)), \
                patch.object(operar_mesa, 'read_action_buttons',
                             return_value=dict(status=status, buttons=[])):
            vf = operar_mesa.make_verifier(FakeEngine(frame), 1, 6)
            return vf(FakeIntent('FOLD', dict(table_key='0x0')), 0.0)['confirmed']

    def test_clean_no_row_confirms(self):
        self.assertTrue(self._verify('NO_BUTTON_ROW'))
        self.assertTrue(self._verify('PRESELECTION_ROW'))

    def test_still_hero_turn_not_confirmed(self):
        self.assertFalse(self._verify('EXPERIMENTAL_BUTTON_ROW'))

    def test_read_error_does_not_confirm(self):
        # #2: erro de leitura NÃO é prova de que a ação ocorreu.
        self.assertFalse(self._verify('INVALID_CROP'))
        self.assertFalse(self._verify('CROP_TOO_SMALL'))


if __name__ == '__main__':
    unittest.main()
