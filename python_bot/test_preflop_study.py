import copy
import json
from pathlib import Path
import tempfile
import unittest

from preflop_study import (Blocked, POSITIONS, RANKS, RangeBook, exported_example,
                           hand_key, positions, reconstruct, study_tables)
from simular_preflop import main
from contextlib import redirect_stdout
from io import StringIO


class PreflopStudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        hands = [r+r for r in RANKS] + [a+b+s for i,a in enumerate(RANKS)
                 for b in RANKS[i+1:] for s in ('s','o')]
        # Deliberately synthetic arithmetic fixture, NOT a poker strategy reference.
        node = dict(id='synthetic-open-btn', context=dict(mode='chip_ev', format='regular',
                    stage='mid', players=9, stack=25), spot='open_raise', hero='BTN', vs=[],
                    table=dict(stacks={p:25 for p in POSITIONS}, potBb=2.5, actions=[
                        dict(position='BB', type='post_ante', amount=1),
                        dict(position='SB', type='post_sb', amount=.5),
                        dict(position='BB', type='post_bb', amount=1)]),
                    source=dict(id='SYNTHETIC_TEST_ONLY'), validated=True,
                    legalActions=['fold','raise'], actions=['raise','fold'],
                    freq={'raise':[.25]*169,'fold':[.75]*169},
                    ev={'raise':[0]*169,'fold':[0]*169}, evUnit='bb')
        self.path = Path(self.tmp.name)/'fixture.json'
        self.bundle = dict(format='nvt-range-export', version=1, hands=hands, nodes=[node],
                           engineCommit='SYNTHETIC', generatedAt='SYNTHETIC')
        self.save()
        self.scene = exported_example(self.book, 'synthetic-open-btn', ['Ah','Kd'])

    def save(self):
        self.path.write_text(json.dumps(self.bundle))
        self.book = RangeBook(self.path)

    def result(self, scene=None):
        return study_tables([self.scene if scene is None else scene], self.book)[0]

    def blocked(self, reason):
        result = self.result()
        self.assertEqual(result['status'], 'ABSTAIN')
        self.assertEqual(result['reason'], reason)
        self.assertFalse(result['execution_allowed'])

    def test_exact_state_and_source_mix_without_execution(self):
        r = self.result()
        self.assertEqual(r['status'], 'STUDY_ONLY')
        self.assertEqual(r['state']['hero_position'], 'BTN')
        self.assertEqual((r['state']['pot_bb'],r['state']['to_call_bb']), (2.5,1))
        self.assertTrue(r['state']['chip_conservation'])
        self.assertEqual(r['strategy']['mix'], [dict(action='raise',frequency=.25),dict(action='fold',frequency=.75)])
        self.assertIsNone(r['strategy']['sizing'])
        self.assertFalse(r['strategy']['execution_allowed'])

    def test_empty_seats_and_rotated_dealer(self):
        self.assertEqual(positions([0,2,3,5,6,8],5), {6:'SB',8:'BB',0:'LJ',2:'HJ',3:'CO',5:'BTN'})
        self.assertEqual(positions([2,8],8), {8:'SB',2:'BB'})
        for dealer in range(9):
            result = positions(list(range(9)),dealer)
            self.assertEqual(result[dealer],'BTN')
            self.assertEqual(result[(dealer+1)%9],'SB')

    def test_card_order_and_suits(self):
        self.assertEqual(hand_key(['Kd','Ah']), 'AKo')
        self.assertEqual(hand_key(['Kh','Ah']), 'AKs')
        self.assertEqual(hand_key(['7d','7h']), '77')
        self.scene['hero_cards'] = ['Ah','Ah']
        self.blocked('HERO_CARDS_UNKNOWN_OR_INVALID')

    def test_missing_or_unconfirmed_data_never_consults(self):
        for field in self.scene['confirmed_fields']:
            s = copy.deepcopy(self.scene)
            s['confirmed_fields'].remove(field)
            self.assertEqual(self.result(s)['reason'],'UNCONFIRMED_FIELDS')
        self.scene['players'][0]['stack_bb'] = None
        self.blocked('AMOUNT_UNKNOWN')

    def test_live_evidence_is_not_promoted(self):
        self.scene['evidence'] = 'OCR'
        self.blocked('LIVE_STATE_RECOGNITION_NOT_VALIDATED')

    def test_pot_call_and_stack_reconciliation(self):
        for key in ('pot_bb','to_call_bb'):
            s = copy.deepcopy(self.scene); s[key] = 99
            self.assertEqual(self.result(s)['reason'],'POT_OR_CALL_MISMATCH')
        self.scene['players'][8]['stack_bb'] = 24
        self.blocked('STACK_OR_BET_MISMATCH')

    def test_nan_negative_and_boolean_amounts_abstain(self):
        for v in ('NaN','Infinity',-1,True):
            s = copy.deepcopy(self.scene); s['pot_bb'] = v
            self.assertEqual(self.result(s)['status'],'ABSTAIN')

    def test_history_gap_out_of_turn_and_missing_start(self):
        self.scene['actions'][3]['seq'] = 5
        self.blocked('ACTION_SEQUENCE_GAP')
        self.scene['actions'][3]['seq'] = 4
        self.scene['actions'][3]['seat'] = 1
        self.blocked('ACTION_OUT_OF_TURN')
        self.scene['history_complete'] = False
        self.blocked('INCOMPLETE_ACTION_HISTORY')

    def test_wrong_supplied_turn_does_not_make_hero_turn(self):
        self.scene['turn_seat'] = 7
        self.blocked('NOT_HERO_TURN')

    def test_limp_is_not_unopened(self):
        self.scene['actions'][3].update(type='call',amount_bb='1')
        self.scene['players'][0].update(stack_bb='24',bet_bb='1',in_hand=True)
        self.scene['pot_bb'] = '3.5'
        self.blocked('POT_ALREADY_OPENED')

    def test_raise_reopens_action_in_order_and_reconciles(self):
        self.scene['actions'][3].update(type='raise',amount_bb='2')
        self.scene['players'][0].update(stack_bb='23',bet_bb='2',in_hand=True)
        self.scene['pot_bb'] = '4.5'
        self.scene['to_call_bb'] = '2'
        state = reconstruct(self.scene)
        self.assertFalse(state['unopened'])
        self.assertEqual(state['to_call_bb'],2)
        self.assertTrue(state['chip_conservation'])
        self.blocked('POT_ALREADY_OPENED')

    def test_no_context_or_stack_approximation(self):
        self.scene['strategy_context'] = dict(self.scene['strategy_context'],stack=24.9)
        self.blocked('STRATEGY_CONTEXT_MISMATCH')
        self.scene['strategy_context']['stack'] = 25
        self.scene['strategy_context']['stage'] = 'early'
        self.blocked('CONTEXT_NOT_SUPPORTED_IN_INITIAL_STUDY')

    def test_no_borrowing_another_players_stack(self):
        self.scene['players'][8]['start_stack_bb'] = '26'
        self.scene['players'][8]['stack_bb'] = '24'
        self.blocked('EXPORTED_SCENARIO_MISMATCH')

    def test_sixmax_cannot_use_ninemax_node(self):
        self.scene['players'] = self.scene['players'][3:]
        self.scene['strategy_context'] = dict(self.scene['strategy_context'],players=6)
        self.scene['actions'] = self.scene['actions'][:3] + self.scene['actions'][6:]
        for i,e in enumerate(self.scene['actions'],1):
            e['seq'] = i
        self.blocked('NO_UNIQUE_VALIDATED_NODE')

    def test_unvalidated_duplicate_and_nonreaching_source(self):
        self.bundle['nodes'][0]['validated'] = False
        self.save(); self.blocked('NO_UNIQUE_VALIDATED_NODE')
        self.bundle['nodes'][0]['validated'] = True
        self.bundle['nodes'][0]['outOfRange'] = [self.book.hands.index('AKo')]
        self.save(); self.blocked('HAND_OUT_OF_RANGE')
        self.bundle['nodes'].append(copy.deepcopy(self.bundle['nodes'][0]))
        with self.assertRaisesRegex(Blocked,'DUPLICATE_NODE_ID'):
            self.save()

    def test_zero_unplayed_ev_becomes_unknown(self):
        self.bundle['nodes'][0]['freq']['raise'] = [0]*169
        self.bundle['nodes'][0]['freq']['fold'] = [1]*169
        self.save()
        self.assertIsNone(self.result()['strategy']['ev']['raise'])

    def test_invalid_frequency_does_not_recommend(self):
        self.bundle['nodes'][0]['freq']['raise'] = [.8]*169
        self.save(); self.blocked('INVALID_SOURCE_MIX_SUM')

    def test_six_tables_isolate_missing_state_and_new_snapshots(self):
        scenes = [copy.deepcopy(self.scene) for _ in range(6)]
        for i,s in enumerate(scenes):
            s['table_id'] = str(i)
        scenes[2]['hero_cards'] = [None,None]
        results = study_tables(scenes,self.book)
        self.assertEqual([r['status'] for r in results],['STUDY_ONLY']*2+['ABSTAIN']+['STUDY_ONLY']*3)
        scenes[2]['hero_cards'] = ['As','Ks']
        scenes[2]['snapshot_id'] = 'new-snapshot'
        self.assertEqual(study_tables(scenes,self.book)[2]['state']['hand_key'],'AKs')
        with self.assertRaisesRegex(Blocked,'TABLE_LIMIT'):
            study_tables(scenes+[copy.deepcopy(scenes[0])],self.book)
        with self.assertRaisesRegex(Blocked,'DUPLICATE_TABLE_IDENTITY'):
            study_tables([scenes[0],scenes[0]],self.book)
        with self.assertRaisesRegex(Blocked,'INVALID_TABLE_SNAPSHOT'):
            study_tables([None],self.book)
        scenes[0]['source_key'] = []
        with self.assertRaisesRegex(Blocked,'INVALID_TABLE_IDENTITY'):
            study_tables(scenes,self.book)

    def test_cli_simulation_and_abstention_exit_codes(self):
        with redirect_stdout(StringIO()) as out:
            code = main(['--ranges',str(self.path),'--exemplo','synthetic-open-btn','--cartas','Ah','Kd'])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out.getvalue())['scope'],'OFFLINE_SIMULATION')
        with redirect_stdout(StringIO()):
            self.assertEqual(main(['--ranges',str(self.path),'--exemplo','synthetic-open-btn']),2)


if __name__ == '__main__':
    unittest.main()
