"""End-to-end glue: advise_table gates street/hero and calls the advisor.

The individual readers are tested elsewhere; here they are mocked so the glue is
checked without OCR."""
import unittest
from unittest.mock import patch
import numpy as np

import table_advisor


class FakeAdvisor:
    def advise_from_reading(self, state, hero, **kw):
        return dict(status='ADVICE', recommended='raise', mix=[{'action': 'raise', 'frequency': 1.0}],
                    stack_bucket=25, node_id='n1', caveats=[], execution_allowed=False)


def _patch(hero, board_cards):
    return [
        patch('table_advisor.read_table_state', return_value=dict(
            positions={'hero': 'BTN'}, seats={'hero': {'stack_bb': 25.0, 'occupied': True}},
            pot={'pot_bb': 2.5}, to_call={'to_call_bb': 1.0}, dealer={'seat': 'bot_left'})),
        patch('table_advisor.read_hand_id', return_value=dict(hand_number=10)),
        patch('table_advisor.read_board', return_value=dict(cards=board_cards)),
        patch('table_advisor.read_hero_cards', return_value=hero),
        patch('table_advisor.read_tournament', return_value=dict(paid=20, players_left=55, confidence='high')),
    ]


class AdviseTableTests(unittest.TestCase):
    crop = np.zeros((1334, 750, 3), np.uint8)

    def _run(self, hero, board_cards):
        patches = _patch(hero, board_cards)
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return table_advisor.advise_table(self.crop, FakeAdvisor())

    def test_preflop_with_hero_gets_advice(self):
        r = self._run(['As', 'Ks'], [])
        self.assertEqual(r['advice']['status'], 'ADVICE')
        self.assertIn('SPOT_INFERRED_FROM_BETS', r['advice']['caveats'])
        self.assertFalse(r['advice']['execution_allowed'])

    def test_postflop_gets_heuristic_advice(self):
        # Antes abstinha (POSTFLOP_NOT_COVERED); agora o postflop_advisor dá um
        # conselho exploratório. Top pair contra aposta pequena = bluffcatch (call).
        r = self._run(['As', 'Ks'], ['Kh', 'Qd', '2c'])
        self.assertEqual(r['advice']['phase'], 'postflop')
        self.assertEqual(r['advice']['status'], 'ADVICE')
        self.assertEqual(r['advice']['made'], 'top_pair')
        self.assertEqual(r['advice']['recommended'], 'call')
        self.assertFalse(r['advice']['execution_allowed'])

    def test_bounty_bb_threaded_to_advisor(self):
        # O --bounty-bb do operador chega ao advise_from_reading (p/ o overlay de call-off).
        captured = {}

        class RecAdvisor(FakeAdvisor):
            def advise_from_reading(self, state, hero, **kw):
                captured['bounty_bb'] = kw.get('bounty_bb')
                return super().advise_from_reading(state, hero, **kw)

        patches = _patch(['As', 'Ks'], [])
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        table_advisor.advise_table(self.crop, RecAdvisor(), bounty_bb=9.0)
        self.assertEqual(captured['bounty_bb'], 9.0)

    def test_mode_override_forces_tournament_mode(self):
        # --mode/--stage sobrepoem a deteccao por nome (ex. forcar PKO onde o skin nao
        # mostra bounty no nome do torneio).
        captured = {}

        class RecAdvisor(FakeAdvisor):
            def advise_from_reading(self, state, hero, **kw):
                captured.update(mode=kw.get('mode'), stage=kw.get('stage'))
                return super().advise_from_reading(state, hero, **kw)

        patches = _patch(['As', 'Ks'], [])
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        table_advisor.advise_table(self.crop, RecAdvisor(), mode='pko', stage='bubble')
        self.assertEqual(captured['mode'], 'pko')
        self.assertEqual(captured['stage'], 'bubble')

    def test_no_hero_cards_abstains(self):
        r = self._run(None, [])
        self.assertEqual(r['advice']['reason'], 'HERO_CARDS_UNKNOWN')

    def test_hero_override_used_when_read_fails(self):
        # Leitura do hero falha neste frame, mas o cache da mão fornece as cartas:
        # usa o override em vez de abster por HERO_CARDS_UNKNOWN.
        patches = _patch(None, [])
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        r = table_advisor.advise_table(self.crop, FakeAdvisor(), hero_override=['As', 'Ks'])
        self.assertEqual(r['hero_cards'], ['As', 'Ks'])
        self.assertEqual(r['advice']['status'], 'ADVICE')

    def _run_board(self, board):
        patches = [
            patch('table_advisor.read_table_state', return_value=dict(
                positions={'hero': 'BTN'}, seats={'hero': {'stack_bb': 25.0, 'occupied': True}},
                pot={'pot_bb': 2.5}, to_call={'to_call_bb': 1.0}, dealer={'seat': 'bot_left'})),
            patch('table_advisor.read_hand_id', return_value=dict(hand_number=10)),
            patch('table_advisor.read_board', return_value=board),
            patch('table_advisor.read_hero_cards', return_value=['As', 'Ks']),
            patch('table_advisor.read_tournament', return_value=dict(paid=20, players_left=55, confidence='high')),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return table_advisor.advise_table(self.crop, FakeAdvisor())

    def test_board_detected_but_unreadable_abstains(self):
        # A board that was detected but not fully read must not be treated as preflop.
        for board in (dict(cards=[], status='BOARD_INCOMPLETE'),
                      dict(cards=[], status='BOARD_DUPLICATE_REJECTED'),
                      dict(cards=[], status='BOARD_PARTIAL_OR_OBSTRUCTED')):
            r = self._run_board(board)
            self.assertEqual(r['advice']['reason'], 'BOARD_PRESENT_BUT_UNREADABLE')

    def test_anchor_missing_is_preflop_and_advises(self):
        # No board = the first-card anchor is missing; that is preflop, advise.
        r = self._run_board(dict(cards=[], status='BOARD_PARTIAL_OR_OBSTRUCTED', reason='FIRST_CARD_ANCHOR_MISSING'))
        self.assertEqual(r['advice']['status'], 'ADVICE')

    def test_tracker_makes_postflop_context_aware(self):
        # A: com um `tracker`, o pós-flop usa o CONTEXTO entre frames. Aqui o pré-flop
        # foi MULTIWAY (dois vilões apostando); no flop, o mesmo frame que isolado daria
        # conselho (top pair call) passa a ABSTER rotulado como pote multiway não coberto.
        from preflop_context import PreflopAggressorTracker
        pre_state = dict(
            positions={'hero': 'BTN', 'sa': 'HJ', 'sb': 'CO'},
            seats={'hero': {'stack_bb': 25.0, 'occupied': True},
                   'sa': {'stack_bb': 25.0, 'occupied': True},
                   'sb': {'stack_bb': 25.0, 'occupied': True}},
            pot={'pot_bb': 6.5}, to_call={'to_call_bb': 2.5},
            bets=[{'seat': 'sa', 'bet_bb': 2.5}, {'seat': 'sb', 'bet_bb': 2.5}],
            dealer={'seat': 'bot_left'})
        post_state = dict(
            positions={'hero': 'BTN', 'sa': 'HJ', 'sb': 'CO'},
            seats={'hero': {'stack_bb': 23.0, 'occupied': True}},
            pot={'pot_bb': 8.0}, to_call={'to_call_bb': 2.0}, bets=[],
            dealer={'seat': 'bot_left'})
        tracker = PreflopAggressorTracker()
        with patch('table_advisor.read_hand_id', return_value=dict(hand_number=10)), \
             patch('table_advisor.read_hero_cards', return_value=['As', 'Ks']), \
             patch('table_advisor.read_tournament', return_value=dict(paid=20, players_left=55, confidence='high')):
            with patch('table_advisor.read_table_state', return_value=pre_state), \
                 patch('table_advisor.read_board', return_value=dict(cards=[])):
                table_advisor.advise_table(self.crop, FakeAdvisor(), table_key='t1', tracker=tracker)
            with patch('table_advisor.read_table_state', return_value=post_state), \
                 patch('table_advisor.read_board', return_value=dict(cards=['Kh', 'Qd', '2c'], street='FLOP')):
                withctx = table_advisor.advise_table(self.crop, FakeAdvisor(), table_key='t1', tracker=tracker)
                noctx = table_advisor.advise_table(self.crop, FakeAdvisor(), table_key='t2')
        self.assertEqual(noctx['advice']['status'], 'ADVICE')          # frame isolado: aconselha
        self.assertEqual(withctx['advice']['phase'], 'postflop')
        self.assertEqual(withctx['advice']['reason'], 'POSTFLOP_MULTIWAY_NOT_COVERED')
        self.assertEqual(withctx['advice']['villain_range_source'], {'reason': 'NOT_HEADS_UP'})

    def test_enable_hud_attaches_villain_stats(self):
        # No crop REAL (MINI FREEZE), enable_hud lê os 8 stats por vilão e anexa a
        # state['hud'] (ponte do exploit). Sem mocks (leitores reais).
        import os
        import cv2
        try:
            from table_reading.pipeline import configure_ocr
            configure_ocr()                      # os leitores de stack/pote usam OCR
        except Exception:                        # noqa: BLE001
            self.skipTest('OCR indisponivel')
        path = os.path.join('tests', 'fixtures', 'hud_live', 'minifreeze-9max-huds.png')
        crop = cv2.imread(path)
        if crop is None:
            self.skipTest('fixture ausente')
        r = table_advisor.advise_table(crop, FakeAdvisor(), enable_hud=True)
        hud = r['table_state'].get('hud', {})
        self.assertTrue(hud, 'nenhum HUD lido')
        self.assertEqual(hud.get('left_up', {}).get('stats', {}).get('vpip'), 25)  # balmeidar

    def test_lobby_crop_is_skipped(self):
        patches = [
            patch('table_advisor.read_table_state', return_value=dict(
                positions={}, seats={'hero': {'stack_bb': None, 'occupied': True}},
                pot={'pot_bb': None}, to_call={'to_call_bb': None}, dealer={'seat': None})),
            patch('table_advisor.read_hand_id', return_value=dict(hand_number=None)),
            patch('table_advisor.read_board', return_value=dict(cards=[])),
            patch('table_advisor.read_hero_cards', return_value=None),
            patch('table_advisor.read_tournament', return_value=dict(paid=None, players_left=None, confidence='abstain')),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        r = table_advisor.advise_table(self.crop, FakeAdvisor())
        self.assertFalse(r['is_table'])
        self.assertEqual(r['advice']['status'], 'SKIP')


if __name__ == '__main__':
    unittest.main()
