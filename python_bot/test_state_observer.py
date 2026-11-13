"""Testes do observador de estado integrado (Camada A)."""
import unittest

from state_observer import StateObserver, render


def _result(hand_number=1771, table_ref='T1', hero=('8s', '3c'), pot=4.5,
            to_call=None, dealer='left_up', hero_pos='BB', seats=None,
            advice=None, is_table=True, board=None, bets=None):
    hid = ('261108-14146017-%07d-11' % hand_number) if hand_number else None
    state = dict(
        pot=dict(pot_bb=pot, confidence='medium', source='ocr'),
        to_call=dict(to_call_bb=to_call,
                     confidence='abstain' if to_call is None else 'high',
                     source='buttons'),
        dealer=dict(seat=dealer, confidence='high', source='template'),
        positions=({'hero': hero_pos} if hero_pos else {}),
        seats=(seats if seats is not None else {'hero': dict(occupied=True, stack_bb=35.5)}),
        bets=(bets or []),
    )
    return dict(is_table=is_table,
                hand=dict(hand_number=hand_number, hand_id=hid, table_ref=table_ref),
                hero_cards=list(hero) if hero else None, board=(board or []),
                table_state=state, context=dict(mode='chip_ev', stage='mid'),
                tournament={}, advice=(advice or dict(status='ADVICE', recommended='RAISE', reason='')))


class StateObserverTest(unittest.TestCase):
    def test_new_table_then_same_hand(self):
        obs = StateObserver()
        v1 = obs.observe(_result(hand_number=1771), table_key='t#1')
        self.assertEqual(v1['hand']['event'], 'new_table')
        self.assertIn('MESA_NOVA', v1['changed'])
        v2 = obs.observe(_result(hand_number=1771), table_key='t#1')
        self.assertEqual(v2['hand']['event'], 'same_hand')
        self.assertFalse(any('MAO_NOVA' in c for c in v2['changed']))

    def test_new_hand_on_increment(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=1771), table_key='t#1')
        v = obs.observe(_result(hand_number=1772), table_key='t#1')
        self.assertEqual(v['hand']['event'], 'new_hand')
        self.assertIn('MAO_NOVA #1772', v['changed'])

    def test_illegible_id_holds_hand_pending(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=1771), table_key='t#1')
        v = obs.observe(_result(hand_number=None, table_ref=None), table_key='t#1')
        self.assertEqual(v['hand']['event'], 'pending_id')
        self.assertEqual(v['hand']['number'], 1771)          # mantém a mão
        self.assertTrue(any('HAND_ID_PENDING' in p for p in v['pending']))

    def test_regressed_id_is_suspect(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=1771), table_key='t#1')
        v = obs.observe(_result(hand_number=1700), table_key='t#1')
        self.assertEqual(v['hand']['event'], 'suspect_id')
        self.assertTrue(any('REGREDIU' in p for p in v['pending']))

    def test_table_ref_change_flagged(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=1771, table_ref='T1'), table_key='t#1')
        v = obs.observe(_result(hand_number=1772, table_ref='T2'), table_key='t#1')
        self.assertTrue(any('TABLE_REF_MUDOU' in p for p in v['pending']))

    def test_absence_not_invented_tocall_and_stacks(self):
        obs = StateObserver()
        seats = {'hero': dict(occupied=True, stack_bb=35.5),
                 'left_up': dict(occupied=True, stack_bb=None)}
        v = obs.observe(_result(to_call=None, seats=seats), table_key='t#1')
        self.assertTrue(any('TO_CALL_PENDENTE' in p for p in v['pending']))
        self.assertTrue(any('STACKS_PENDENTES' in p and 'left_up' in p for p in v['pending']))
        # o to_call NÃO vira 0 nem a aposta vira "ninguém apostou"
        tc = next(f for f in v['fields'] if f['name'] == 'to_call')
        self.assertIsNone(tc['value'])
        self.assertFalse(tc['confirmed'])

    def test_confirmed_fields_present(self):
        obs = StateObserver()
        v = obs.observe(_result(to_call=2.5), table_key='t#1')
        names = {f['name']: f for f in v['fields']}
        self.assertTrue(names['hero_cards']['confirmed'])
        self.assertTrue(names['pot']['confirmed'])
        self.assertTrue(names['to_call']['confirmed'])
        self.assertTrue(names['dealer']['confirmed'])

    def test_advice_abstain_is_pending(self):
        obs = StateObserver()
        v = obs.observe(_result(advice=dict(status='ABSTAIN', reason='NO_VALIDATED_NODE')),
                        table_key='t#1')
        self.assertTrue(any('CONSELHO_ABSTAIN' in p for p in v['pending']))

    def test_not_a_table(self):
        obs = StateObserver()
        v = obs.observe(dict(is_table=False, advice=dict(status='SKIP')), table_key='lobby')
        self.assertFalse(v['is_table'])
        self.assertIn('NOT_A_TABLE', v['pending'])

    def test_render_is_string(self):
        obs = StateObserver()
        v = obs.observe(_result(), table_key='t#1')
        out = render(v)
        self.assertIn('MESA t#1', out)
        self.assertIn('MAO #1771', out)

    def test_multi_table_independent(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=10, table_ref='A'), table_key='a')
        obs.observe(_result(hand_number=20, table_ref='B'), table_key='b')
        va = obs.observe(_result(hand_number=11, table_ref='A'), table_key='a')
        self.assertEqual(va['hand']['event'], 'new_hand')   # 'a' independente de 'b'
        self.assertEqual(va['hand']['number'], 11)


class CamadaBReconcileTest(unittest.TestCase):
    """Reconciliação de ações ao longo da mão (deltas provados; gap sinalizado)."""

    def test_street_advanced(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=5, board=[], pot=1.5), table_key='t')
        v = obs.observe(_result(hand_number=5, board=['Ah', 'Kd', '2c'], pot=3.0),
                        table_key='t')
        self.assertEqual(v['reconcile']['street'], 'flop')
        self.assertTrue(any('STREET: preflop->flop' in c for c in v['changed']))

    def test_seat_committed_reconciles(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=5, seats={'hero': dict(occupied=True, stack_bb=40)}, pot=1.0),
                    table_key='t')
        v = obs.observe(_result(hand_number=5, seats={'hero': dict(occupied=True, stack_bb=35)}, pot=6.0),
                        table_key='t')
        self.assertTrue(any('hero comprometeu 5' in c for c in v['changed']))
        # committed 5 == pot delta 5 -> reconciliado, sem gap
        self.assertFalse(any('RECONCILIACAO_GAP' in p for p in v['pending']))

    def test_gap_flagged_not_invented(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=5, seats={'hero': dict(occupied=True, stack_bb=40)}, pot=1.0),
                    table_key='t')
        v = obs.observe(_result(hand_number=5, seats={'hero': dict(occupied=True, stack_bb=30)}, pot=3.0),
                        table_key='t')
        # saiu 10 do stack, pote so subiu 2 -> gap (ações entre frames)
        self.assertTrue(any('RECONCILIACAO_GAP' in p for p in v['pending']))

    def test_pot_regressed_flags_missed_boundary(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=5, pot=10.0), table_key='t')
        v = obs.observe(_result(hand_number=5, pot=2.0), table_key='t')
        self.assertTrue(any('POTE_REGREDIU' in p for p in v['pending']))

    def test_reconciler_resets_on_new_hand(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=5, board=['Ah', 'Kd', '2c']), table_key='t')
        v = obs.observe(_result(hand_number=6, board=[]), table_key='t')
        self.assertEqual(v['hand']['event'], 'new_hand')
        self.assertEqual(v['reconcile']['street'], 'preflop')   # reconciler novo
        self.assertEqual(v['reconcile']['total_events'], 0)

    def test_board_dict_empty_center_is_preflop(self):
        # Achado ao vivo 09/11: all-in pré-flop (centro vazio, sem candidatos) ->
        # street 'preflop', NUNCA 'river' (que era o bug de len(dict)=5).
        obs = StateObserver()
        board = {'status': 'BOARD_NOT_CONFIRMED', 'street': None, 'cards': [],
                 'candidates': []}
        v = obs.observe(_result(board=board), table_key='t')
        self.assertEqual(v['reconcile']['street'], 'preflop')
        bf = next(f for f in v['fields'] if f['name'] == 'board')
        self.assertFalse(bf['confirmed'])

    def test_board_dict_candidates_unreadable_is_pending(self):
        # Board com candidatos mas não confirmado = ilegível -> street pendente.
        obs = StateObserver()
        board = {'status': 'BOARD_NOT_CONFIRMED', 'street': None, 'cards': [],
                 'candidates': [[151, 505, 84, 124]]}
        v = obs.observe(_result(board=board), table_key='t')
        self.assertIsNone(v['reconcile']['street'])
        self.assertTrue(any('BOARD_ILEGIVEL' in p for p in v['pending']))

    def test_board_dict_confirmed_sets_street(self):
        obs = StateObserver()
        # O reader real usa MAIÚSCULA (FLOP/TURN/RIVER); o observador normaliza.
        board = {'status': 'EXPERIMENTAL_BOARD', 'street': 'RIVER',
                 'cards': ['7d', 'Jh', '9d', 'As', 'Jd']}
        v = obs.observe(_result(board=board), table_key='t')
        self.assertEqual(v['reconcile']['street'], 'river')
        bf = next(f for f in v['fields'] if f['name'] == 'board')
        self.assertTrue(bf['confirmed'])

    def test_suspect_id_not_reconciled(self):
        obs = StateObserver()
        obs.observe(_result(hand_number=5, pot=5.0), table_key='t')
        v = obs.observe(_result(hand_number=4, pot=99.0), table_key='t')  # id regride
        self.assertEqual(v['hand']['event'], 'suspect_id')
        self.assertEqual(v['reconcile']['step'], [])             # frame suspeito ignorado


if __name__ == '__main__':
    unittest.main()
