"""Testes do rastreador de agressor pré-flop e do builder de range do vilão (HU)."""
import unittest

from preflop_study import RANKS
from preflop_advisor import PreflopAdvisor
from preflop_context import (PreflopAggressorTracker, villain_open_range,
                             villain_postflop_range)

HANDS = [r + r for r in RANKS] + [a + b + s for i, a in enumerate(RANKS)
                                  for b in RANKS[i + 1:] for s in ('s', 'o')]


def _vec(hands):
    idx = set(hands)
    return [1.0 if HANDS[k] in idx else 0.0 for k in range(169)]


def pack_open_and_call(open_hands, call_hands, opener='BTN', caller='BB', stack=25):
    """Pack com um nó de open (opener) e um vs_open (caller vs opener, ação 'call')."""
    ctx = dict(mode='chip_ev', format='regular', stage='mid', players=9, stack=stack)
    z = [0.0] * 169
    open_node = dict(id='op', context=ctx, spot='open_raise', hero=opener, vs=[], validated=True,
                     evUnit='bb', legalActions=['fold', 'raise'], actions=['raise', 'fold'],
                     freq={'raise': _vec(open_hands), 'fold': z}, ev={}, outOfRange=[], source='t')
    vs_node = dict(id='vo', context=ctx, spot='vs_open', hero=caller, vs=[opener], validated=True,
                   evUnit='bb', legalActions=['fold', 'call', 'three_bet', 'all_in'],
                   actions=['all_in', 'three_bet', 'call', 'fold'],
                   freq={'all_in': z, 'three_bet': z, 'call': _vec(call_hands), 'fold': z},
                   ev={}, outOfRange=[], source='t')
    return dict(format='nvt-range-export', version=1, engineCommit='t', hands=HANDS,
                nodes=[open_node, vs_node])


def open_pack(hands, pos='BTN', stack=25):
    idx = set(hands)
    raise_ = [1.0 if HANDS[k] in idx else 0.0 for k in range(169)]
    fold = [0.0 if HANDS[k] in idx else 1.0 for k in range(169)]
    node = dict(id='o1', context=dict(mode='chip_ev', format='regular', stage='mid', players=9, stack=stack),
                spot='open_raise', hero=pos, vs=[], validated=True, evUnit='bb',
                legalActions=['fold', 'raise'], actions=['raise', 'fold'],
                freq={'raise': raise_, 'fold': fold},
                ev={'raise': [0.0] * 169, 'fold': [0.0] * 169}, outOfRange=[], source='test')
    return dict(format='nvt-range-export', version=1, engineCommit='test', hands=HANDS, nodes=[node])


def mk(positions, bets, occupied, stacks=None):
    seats = {s: dict(occupied=(s in occupied), stack_bb=(stacks or {}).get(s)) for s in positions}
    return dict(positions=positions, bets=bets, seats=seats,
                pot=dict(pot_bb=5), to_call=dict(to_call_bb=0), dealer=dict(seat=None))


HU_VS_OPEN = mk({'hero': 'BB', 'v': 'BTN'}, [{'seat': 'v', 'bet_bb': 2.5}],
                {'hero', 'v'}, {'v': 25.0, 'hero': 25.0})


class TrackerTests(unittest.TestCase):
    def test_hu_single_raise_villain_opened(self):
        t = PreflopAggressorTracker()
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        ctx = t.update(table_key='t', hand_key=1,
                       table_state=mk({'hero': 'BB', 'v': 'BTN'}, [], {'hero', 'v'}),
                       has_board=True)   # flop chega
        self.assertEqual(ctx['aggressor'], 'BTN')
        self.assertTrue(ctx['heads_up'])
        self.assertTrue(ctx['single_raised'])
        self.assertFalse(ctx['hero_aggressor'])
        self.assertEqual(ctx['villain_stack'], 25.0)

    def test_board_freezes_aggressor(self):
        t = PreflopAggressorTracker()
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=True)
        # um frame posterior que "pareceria" first_in não pode apagar o agressor
        ctx = t.update(table_key='t', hand_key=1,
                       table_state=mk({'hero': 'BB', 'v': 'BTN'}, [], {'hero', 'v'}),
                       has_board=True)
        self.assertEqual(ctx['aggressor'], 'BTN')

    def test_new_hand_resets(self):
        t = PreflopAggressorTracker()
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        ctx = t.update(table_key='t', hand_key=2,
                       table_state=mk({'hero': 'BB', 'v': 'BTN'}, [], {'hero', 'v'}),
                       has_board=False)
        self.assertIsNone(ctx['aggressor'])

    def test_multiway_detected_as_not_heads_up(self):
        t = PreflopAggressorTracker()
        state = mk({'hero': 'BB', 'v': 'BTN', 'c': 'CO'},
                   [{'seat': 'v', 'bet_bb': 2.5}, {'seat': 'c', 'bet_bb': 2.5}],
                   {'hero', 'v', 'c'}, {'v': 25, 'c': 25, 'hero': 25})
        ctx = t.update(table_key='t', hand_key=1, table_state=state, has_board=False)
        self.assertFalse(ctx['heads_up'])          # dois vilaos na mao -> multiway

    def test_heads_up_at_full_table_after_folds(self):
        # #3: mesa de 9 ocupada, mas so o BTN abriu (resto foldou) -> HU na mao
        t = PreflopAggressorTracker()
        pos = {'hero': 'BB', 'v': 'BTN', 'a': 'UTG', 'b': 'UTG+1', 'c': 'CO', 'd': 'HJ'}
        state = mk(pos, [{'seat': 'v', 'bet_bb': 2.5}], set(pos), {k: 25 for k in pos})
        ctx = t.update(table_key='t', hand_key=1, table_state=state, has_board=False)
        self.assertTrue(ctx['heads_up'])
        self.assertEqual(ctx['aggressor'], 'BTN')

    def test_frozen_stack_not_overwritten_postflop(self):
        # #4: stack pre-flop de 25 nao e substituido pela leitura pos-flop de 18
        t = PreflopAggressorTracker()
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        post = mk({'hero': 'BB', 'v': 'BTN'}, [], {'hero', 'v'}, {'v': 18.0, 'hero': 18.0})
        ctx = t.update(table_key='t', hand_key=1, table_state=post, has_board=True)
        self.assertEqual(ctx['villain_stack'], 25.0)

    def test_unreadable_id_suspends_context(self):
        # #2/#4: hand_key ilegivel (None) nao apaga o contexto da mao em curso
        t = PreflopAggressorTracker()
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        ctx = t.update(table_key='t', hand_key=None,
                       table_state=mk({'hero': 'BB'}, [], {'hero'}), has_board=True)
        self.assertEqual(ctx['aggressor'], 'BTN')

    def test_new_hand_first_frame_postflop_has_no_stale_context(self):
        # #2: 1o frame legivel da nova mao ja no flop -> contexto da mao anterior some
        t = PreflopAggressorTracker()
        t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        ctx = t.update(table_key='t', hand_key=2,
                       table_state=mk({'hero': 'BB', 'v': 'BTN'}, [], {'hero', 'v'}),
                       has_board=True)
        self.assertIsNone(ctx['aggressor'])

    def test_three_bet_not_single_raised(self):
        t = PreflopAggressorTracker()
        state = mk({'hero': 'CO', 'v': 'BTN'},
                   [{'seat': 'hero', 'bet_bb': 2.5}, {'seat': 'v', 'bet_bb': 7.0}],
                   {'hero', 'v'}, {'v': 25, 'hero': 25})
        ctx = t.update(table_key='t', hand_key=1, table_state=state, has_board=False)
        self.assertFalse(ctx['single_raised'])

    def test_hero_opened_marks_hero_aggressor(self):
        t = PreflopAggressorTracker()
        state = mk({'hero': 'BTN', 'v': 'BB'}, [{'seat': 'hero', 'bet_bb': 2.5}],
                   {'hero', 'v'}, {'v': 25, 'hero': 25})
        ctx = t.update(table_key='t', hand_key=1, table_state=state, has_board=False)
        self.assertTrue(ctx['hero_aggressor'])
        self.assertEqual(ctx['aggressor'], 'hero')

    def test_records_hero_and_villain_positions(self):
        t = PreflopAggressorTracker()
        ctx = t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        self.assertEqual(ctx['hero_position'], 'BB')
        self.assertEqual(ctx['villain_position'], 'BTN')


class VillainRangeTests(unittest.TestCase):
    def setUp(self):
        self.a = PreflopAdvisor(open_pack(['AA', 'KK'], pos='BTN', stack=25))
        self.t = PreflopAggressorTracker()

    def _ctx_hu(self):
        self.t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=False)
        return self.t.update(table_key='t', hand_key=1, table_state=HU_VS_OPEN, has_board=True)

    def test_builds_open_range_hu(self):
        combos, meta = villain_open_range(self.a, self._ctx_hu())
        self.assertIsNotNone(combos)
        self.assertEqual(len(combos), 12)         # AA + KK = 12 combos
        self.assertEqual(meta['aggressor'], 'BTN')
        self.assertFalse(meta['stack_proxy'])

    def test_not_heads_up(self):
        ctx = dict(aggressor='BTN', raises=1, hero_aggressor=False, villain_stack=25,
                   heads_up=False, single_raised=True, hand_key=1)
        self.assertEqual(villain_open_range(self.a, ctx)[1], 'NOT_HEADS_UP')

    def test_hero_was_aggressor_blocks(self):
        ctx = dict(aggressor='hero', raises=1, hero_aggressor=True, villain_stack=25,
                   heads_up=True, single_raised=True, hand_key=1)
        self.assertEqual(villain_open_range(self.a, ctx)[1], 'HERO_WAS_AGGRESSOR')

    def test_aggressor_unknown(self):
        ctx = dict(aggressor=None, raises=0, hero_aggressor=False, villain_stack=None,
                   heads_up=True, single_raised=False, hand_key=1)
        self.assertEqual(villain_open_range(self.a, ctx)[1], 'NOT_SINGLE_RAISED')

    def test_stack_proxy_when_villain_stack_unknown(self):
        ctx = dict(aggressor='BTN', raises=1, hero_aggressor=False, villain_stack=None,
                   heads_up=True, single_raised=True, hand_key=1)
        combos, meta = villain_open_range(self.a, ctx, hero_stack_bb=25.0)
        self.assertIsNotNone(combos)
        self.assertTrue(meta['stack_proxy'])

    def test_no_open_node_reason(self):
        a = PreflopAdvisor(open_pack(['AA'], pos='CO', stack=25))   # só CO tem nó
        ctx = dict(aggressor='BTN', raises=1, hero_aggressor=False, villain_stack=25,
                   heads_up=True, single_raised=True, hand_key=1)
        self.assertEqual(villain_open_range(a, ctx)[1], 'NO_OPEN_NODE_FOR_CONTEXT')


class DispatcherTests(unittest.TestCase):
    """villain_postflop_range escolhe open range (vilão abriu) x call range (hero abriu)."""

    def setUp(self):
        self.a = PreflopAdvisor(pack_open_and_call(['AA', 'KK'], ['AKs', 'QQ'],
                                                   opener='BTN', caller='BB'))

    def test_villain_opened_uses_open_range(self):
        ctx = dict(aggressor='BTN', raises=1, hero_aggressor=False, villain_stack=25,
                   villain_position='BTN', hero_position='BB', heads_up=True,
                   single_raised=True, hand_key=1)
        combos, meta = villain_postflop_range(self.a, ctx)
        self.assertEqual(meta['kind'], 'open')
        self.assertEqual(len(combos), 12)         # AA + KK

    def test_hero_opened_uses_call_range(self):
        ctx = dict(aggressor='hero', raises=1, hero_aggressor=True, villain_stack=25,
                   villain_position='BB', hero_position='BTN', heads_up=True,
                   single_raised=True, hand_key=1)
        combos, meta = villain_postflop_range(self.a, ctx)
        self.assertEqual(meta['kind'], 'call')
        self.assertEqual(len(combos), 10)         # AKs (4) + QQ (6)
        self.assertEqual(meta['opener_position'], 'BTN')

    def test_call_range_needs_both_positions(self):
        ctx = dict(aggressor='hero', raises=1, hero_aggressor=True, villain_stack=25,
                   villain_position=None, hero_position='BTN', heads_up=True,
                   single_raised=True, hand_key=1)
        self.assertEqual(villain_postflop_range(self.a, ctx)[1], 'POSITIONS_UNKNOWN')

    def test_not_single_raised_blocks(self):
        ctx = dict(aggressor='BTN', raises=2, hero_aggressor=False, villain_stack=25,
                   villain_position='BTN', hero_position='BB', heads_up=True,
                   single_raised=False, hand_key=1)
        self.assertEqual(villain_postflop_range(self.a, ctx)[1], 'NOT_SINGLE_RAISED')


if __name__ == '__main__':
    unittest.main()
