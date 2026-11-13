"""Testes da ponte lobby real → registrador 3A (plug no lobby).

A lógica da ponte é testada com fakes (sem OCR/Windows). Há também um teste
END-TO-END no crop de lobby REAL do Karekas, com OCR in-process — pulado se o
tesserocr ou a imagem não estiverem disponíveis.
"""
import os
import unittest
from types import SimpleNamespace

import numpy as np

from lobby_runner import (details_from_card, find_lobby_crop, merge_cards,
                          read_lobby, read_lobby_multi, select_lobby,
                          session_state_from_ledger)
from registration_flow import RegistrationRound
from registration_ledger import RegistrationLedger
from session_config import SessionConfig

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_LOBBY = os.path.join(
    HERE, 'logs', 'sessoes', 'sessao-20261108-200315-f2b0d315',
    'sample-000001-mesa-1.png')


def _config(**over):
    base = dict(enabled=True, clubs_authorized=('Karekas',),
                allowed_modalities=('freezeout', 'mko', 'pko'), currency='BRL',
                max_entry_buyin=100.0, daily_budget=500.0, bankroll_bi=200.0,
                max_simultaneous=4)
    base.update(over)
    return SessionConfig(**base)


def _card(name='DEEP FREEZEOUT', buyin=50.0, modality='freezeout', state='reg_open'):
    return dict(name=name, buyin=buyin, modality=modality,
                players_registered=40, players_max=500, level_minutes=8,
                status=dict(state=state, starts_at=None), confidence='high')


class LobbyCropTest(unittest.TestCase):
    def test_picks_crop_with_badges(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        props = [SimpleNamespace(box=(0, 0, 40, 40), status='COMPLETE_CANDIDATE'),
                 SimpleNamespace(box=(50, 50, 40, 40), status='COMPLETE_CANDIDATE')]
        # a segunda caixa é o lobby: o badger acha 3 badges nela, 0 na primeira.
        def badger(crop):
            return [1, 2, 3] if crop.shape[0] == 40 and int(crop[0, 0, 0]) == 7 else []
        frame[50:90, 50:90, 0] = 7   # marca a região "lobby"
        crop, box, n = find_lobby_crop(frame, detector=lambda rgb, max_tables: props,
                                       badger=badger)
        self.assertEqual((box, n), ((50, 50, 40, 40), 3))

    def test_picks_crop_regardless_of_table_status(self):
        # O lobby não é mesa: vem UNCERTAIN, não COMPLETE_CANDIDATE. O sinal é o
        # badge, não o status (regressão do achado ao vivo 09/11).
        frame = np.zeros((100, 100, 3), np.uint8)
        props = [SimpleNamespace(box=(50, 50, 40, 40), status='UNCERTAIN')]
        crop, box, n = find_lobby_crop(frame, detector=lambda rgb, max_tables: props,
                                       badger=lambda c: [1, 2, 3, 4])
        self.assertEqual((box, n), ((50, 50, 40, 40), 4))

    def test_merge_prefers_reg_open_either_order(self):
        # A 3ª linha alterna stack<->countdown; em N frames o reg_open deve vencer
        # o unknown, em qualquer ordem. Nunca inventa (só entra se um frame leu).
        unk, opn = [_card(state='unknown')], [_card(state='reg_open')]
        self.assertEqual(merge_cards([unk, opn])[0]['status']['state'], 'reg_open')
        self.assertEqual(merge_cards([opn, unk])[0]['status']['state'], 'reg_open')
        self.assertEqual(merge_cards([unk, unk])[0]['status']['state'], 'unknown')

    def test_read_lobby_multi_merges_toggling_status(self):
        crop = np.zeros((50, 50, 3), np.uint8)
        seq = iter([[_card(state='unknown')], [_card(state='reg_open')]])
        out = read_lobby_multi(lambda: crop, frames=2, delay=0,
                               sleep=lambda d: None, is_crop=True,
                               reader=lambda c: next(seq))
        self.assertTrue(out['ok'])
        self.assertEqual(out['frames'], 2)
        self.assertEqual(out['cards'][0]['status']['state'], 'reg_open')

    def test_no_lobby_crop(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        props = [SimpleNamespace(box=(0, 0, 40, 40), status='COMPLETE_CANDIDATE')]
        out = read_lobby(frame, detector=lambda rgb, max_tables: props,
                         badger=lambda c: [])
        self.assertFalse(out['ok'])
        self.assertEqual(out['reason'], 'NO_LOBBY_CROP_FOUND')

    def test_read_lobby_is_crop_uses_reader(self):
        crop = np.zeros((50, 50, 3), np.uint8)
        out = read_lobby(crop, is_crop=True, reader=lambda c: [_card()])
        self.assertTrue(out['ok'])
        self.assertEqual(out['cards'][0]['name'], 'DEEP FREEZEOUT')


class LedgerStateTest(unittest.TestCase):
    def test_session_state_mirrors_ledger(self):
        led = RegistrationLedger()
        led.reserve(identity='a', cost=50, currency='BRL', name='A', token='ta')
        led.reserve(identity='b', cost=30, currency='BRL', name='B', token='tb')
        led.set_state('ta', 'AWAITING_CONFIRMATION')
        led.set_state('ta', 'CONFIRMATION_SENT')
        led.confirm('ta')
        st = session_state_from_ledger(led)
        self.assertEqual(st.confirmed_spend, 50.0)
        self.assertEqual(len(st.committed), 1)             # só a reserva pendente
        self.assertEqual(st.committed_cost(), 80.0)        # 50 confirmado + 30 pendente

    def test_select_uses_ledger_budget(self):
        led = RegistrationLedger()
        led.reserve(identity='pre', cost=470, currency='BRL', name='PRE', token='pre')
        elig, blocked = select_lobby([_card(buyin=50.0)], _config(daily_budget=500.0),
                                     led, club='Karekas', now_hhmm='20:00')
        # 470 reservado + 50 estoura 500 -> evaluate_card já barra no pré-filtro
        self.assertEqual(elig, [])
        self.assertIn('DAILY_BUDGET_EXCEEDED', blocked[0]['reasons'])


class DetailsTest(unittest.TestCase):
    def test_currency_never_invented(self):
        det = details_from_card(_card(), club='Karekas', currency=None)
        self.assertIsNone(det['currency'])   # fluxo deve bloquear com CURRENCY_UNKNOWN

    def test_flag_present(self):
        det = details_from_card(_card(), club='Karekas', currency='BRL')
        self.assertEqual(det['details_source'], 'lobby+operator')


class GlueEndToEndTest(unittest.TestCase):
    def test_operator_asserted_open_unblocks(self):
        # Cliente sem status no cartão: status unknown -> bloqueado. O operador
        # AFIRMA aberto (flag) -> elegível e o fluxo prossegue. Só o operador
        # pode afirmar; o leitor nunca inventa reg_open.
        led = RegistrationLedger()
        unknown = _card(state='unknown')
        elig, blocked = select_lobby([unknown], _config(), led, club='Karekas',
                                     now_hhmm='20:00')
        self.assertEqual(elig, [])
        self.assertIn('REGISTRATION_NOT_OPEN', blocked[0]['reasons'])
        asserted = dict(unknown, status=dict(state='reg_open', closes_in_min=None,
                                             starts_at=None, operator_asserted=True))
        elig2, _ = select_lobby([asserted], _config(), led, club='Karekas',
                                now_hhmm='20:00')
        self.assertEqual([d['name'] for d in elig2], ['DEEP FREEZEOUT'])

    def test_fake_reader_to_awaiting(self):
        led = RegistrationLedger()
        cards = [_card(), _card(name='CRAZY REBUY', buyin=5.0, modality='rebuy')]
        elig, blocked = select_lobby(cards, _config(), led, club='Karekas',
                                     now_hhmm='20:00')
        self.assertEqual([d['name'] for d in elig], ['DEEP FREEZEOUT'])
        self.assertIn('REBUY_ONLY_IN_PKO', blocked[0]['reasons'])
        from bot_control import BotControl
        ctrl = BotControl(); ctrl.resume()
        card = cards[0]
        r = RegistrationRound(round_id='g', operator='e', target_name='DEEP FREEZEOUT',
                              authorized_cost=50.0, currency='BRL', config=_config(),
                              ledger=led, mode='observation', bot_control=ctrl)
        r.observe(card, club='Karekas', now_hhmm='20:00')
        r.check_details(details_from_card(card, club='Karekas', currency='BRL'),
                        now_hhmm='20:00')
        out = r.reserve()
        self.assertEqual(out['flow_state'], 'AWAITING_CONFIRMATION')
        self.assertEqual(out['summary']['budget_remaining_after_reserve'].__str__(), '450.00')


@unittest.skipUnless(os.path.exists(REAL_LOBBY), 'crop de lobby real ausente')
class RealLobbyOCRTest(unittest.TestCase):
    """End-to-end no lobby REAL do Karekas, OCR in-process (dado real, lab)."""
    @classmethod
    def setUpClass(cls):
        try:
            import cv2
            from table_reading.pipeline import configure_ocr
            configure_ocr()
            cls.cv2 = cv2
        except Exception as e:  # noqa: BLE001
            raise unittest.SkipTest('OCR in-process indisponivel: %s' % e)

    def test_read_grade_scale_invariant(self):
        # O mesmo lobby v228 ampliado 1.34x (escala do painel ao vivo) deve ler
        # os mesmos cartões: valida as ROIs relativas ao pitch (não-regressão em
        # escala). Dado real, determinístico.
        from grade_reader import read_grade
        im = self.cv2.imread(REAL_LOBBY)
        big = self.cv2.resize(im, None, fx=1.34, fy=1.34,
                              interpolation=self.cv2.INTER_CUBIC)
        cards = read_grade(big)
        deep = next((c for c in cards
                     if (c['name'] or '').startswith('DEEP FREEZEOUT')), None)
        self.assertIsNotNone(deep)                       # ROIs seguem o pitch na escala viva
        self.assertEqual(float(deep['buyin']), 50.0)     # nome+buy-in sobrevivem à escala

    def test_reads_real_lobby_and_reaches_awaiting(self):
        im = self.cv2.imread(REAL_LOBBY)
        out = read_lobby(im, is_crop=True)
        self.assertTrue(out['ok'])
        names = {(c['name'] or '').strip(): c for c in out['cards']}
        self.assertIn('DEEP FREEZEOUT', names)
        deep = names['DEEP FREEZEOUT']
        self.assertEqual(float(deep['buyin']), 50.0)
        self.assertEqual(deep['status']['state'], 'reg_open')

        led = RegistrationLedger()
        from bot_control import BotControl
        ctrl = BotControl(); ctrl.resume()
        r = RegistrationRound(round_id='real', operator='eduardo',
                              target_name='DEEP FREEZEOUT', authorized_cost=50.0,
                              currency='BRL', config=_config(), ledger=led,
                              mode='observation', bot_control=ctrl)
        r.observe(deep, club='Karekas', now_hhmm='20:00')
        r.check_details(details_from_card(deep, club='Karekas', currency='BRL'),
                        now_hhmm='20:00')
        res = r.reserve()
        self.assertEqual(res['flow_state'], 'AWAITING_CONFIRMATION')
        self.assertEqual(led.active_count(), 1)


if __name__ == '__main__':
    unittest.main()
