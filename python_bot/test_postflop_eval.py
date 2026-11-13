"""Testes do núcleo de avaliação pós-flop (board + força da mão). Casos conhecidos."""
import unittest

from postflop_eval import (classify_board, hand_strength, narrow_to_continuation,
                           _continuation_multiplier)


class BoardTests(unittest.TestCase):
    def test_rainbow_structure(self):
        b = classify_board(['As', '9h', '3d'])
        self.assertEqual(b['texture'], 'rainbow')
        self.assertFalse(b['paired'])
        self.assertEqual(b['structure'], ['A', 'M', 'L'])
        self.assertEqual(b['flush_count'], 1)
        self.assertFalse(b['flush_possible'])
        self.assertEqual(b['high_rank'], 14)

    def test_monotone_flush_possible(self):
        b = classify_board(['As', '9s', '3s'])
        self.assertEqual(b['texture'], 'monotone')
        self.assertTrue(b['flush_possible'])
        self.assertEqual(b['flush_count'], 3)

    def test_two_tone(self):
        b = classify_board(['Qs', '7s', '2d'])
        self.assertEqual(b['texture'], 'two_tone')
        self.assertFalse(b['flush_possible'])

    def test_paired_low(self):
        b = classify_board(['7h', '7c', '2d'])
        self.assertTrue(b['paired'])
        self.assertFalse(b['trips'])
        self.assertEqual(b['structure'], ['M', 'L'])

    def test_connected_straightish(self):
        b = classify_board(['9h', '8c', '7d'])
        self.assertEqual(b['straightish'], 3)      # 9-8-7 em janela de 5
        self.assertFalse(b['straight_on_board'])

    def test_straight_on_board(self):
        b = classify_board(['9h', '8c', '7d', '6s', '5h'])
        self.assertTrue(b['straight_on_board'])
        self.assertEqual(b['texture'], 'flush_2')

    def test_wheel_uses_ace_low(self):
        b = classify_board(['Ah', '2c', '3d', '4s', '5h'])
        self.assertTrue(b['straight_on_board'])

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            classify_board(['As', 'Kd'])


class HandStrengthTests(unittest.TestCase):
    def test_top_pair(self):
        r = hand_strength(['As', 'Qc'], ['Ah', '9h', '3d'])
        self.assertEqual(r['category_name'], 'pair')
        self.assertEqual(r['made'], 'top_pair')

    def test_overpair(self):
        r = hand_strength(['Ks', 'Kc'], ['9h', '3d', '2c'])
        self.assertEqual(r['made'], 'overpair')

    def test_underpair(self):
        r = hand_strength(['5s', '5c'], ['Ah', 'Qd', '2c'])
        self.assertEqual(r['made'], 'underpair')

    def test_set_from_pocket(self):
        r = hand_strength(['3c', '3h'], ['As', '9h', '3d'])
        self.assertEqual(r['category_name'], 'trips')
        self.assertEqual(r['made'], 'set')

    def test_trips_from_one_card(self):
        r = hand_strength(['3c', 'Kh'], ['3s', '3h', '9d'])
        self.assertEqual(r['made'], 'trips')

    def test_board_pair_only(self):
        r = hand_strength(['Ks', 'Qc'], ['7h', '7c', '2d'])
        self.assertEqual(r['category_name'], 'pair')
        self.assertEqual(r['made'], 'board_pair_only')

    def test_two_pair(self):
        r = hand_strength(['As', '9c'], ['Ah', '9h', '3d'])
        self.assertEqual(r['made'], 'two_pair')

    def test_flush_draw_nine_outs(self):
        r = hand_strength(['As', 'Ks'], ['Qs', '7s', '2d'])
        self.assertTrue(r['draws']['flush_draw'])
        self.assertEqual(r['draws']['flush_outs'], 9)
        self.assertEqual(r['outs'], 9)

    def test_oesd_eight_outs(self):
        r = hand_strength(['9s', '8d'], ['7h', '6c', '2s'])
        self.assertTrue(r['draws']['oesd'])
        self.assertEqual(r['draws']['straight_outs'], 8)

    def test_gutshot_four_outs(self):
        r = hand_strength(['9s', '5d'], ['7h', '6c', '2s'])
        self.assertTrue(r['draws']['gutshot'])
        self.assertEqual(r['draws']['straight_outs'], 4)

    def test_combo_draw_capped(self):
        # flush draw (spades: 9s8s7s6s=4) + OESD (T/5); total descontando overlap, cap 15
        r = hand_strength(['9s', '8s'], ['7s', '6s', '2d'])
        self.assertTrue(r['draws']['combo'])
        self.assertLessEqual(r['outs'], 15)
        self.assertGreaterEqual(r['outs'], 12)

    def test_made_straight_no_draw_outs(self):
        r = hand_strength(['9s', '8d'], ['7h', '6c', '5s'])
        self.assertEqual(r['category_name'], 'straight')
        self.assertEqual(r['draws']['straight_outs'], 0)

    def test_made_flush(self):
        r = hand_strength(['As', '7s'], ['Ks', '9s', '2s'])
        self.assertEqual(r['category_name'], 'flush')

    def test_overcards(self):
        r = hand_strength(['As', 'Kd'], ['9h', '7c', '2s'])
        self.assertEqual(r['made'], 'overcards')

    def test_air(self):
        r = hand_strength(['7s', '4d'], ['Ah', 'Kc', '9s'])
        self.assertEqual(r['made'], 'air')

    def test_board_two_pair_is_not_hero_value(self):
        # #5: dois pares no board; hero so tem kicker -> NAO e two_pair forte do hero
        r = hand_strength(['Ah', 'Kd'], ['2h', '2d', '3s', '3c', '5h'])
        self.assertEqual(r['category_name'], 'two_pair')
        self.assertEqual(r['made'], 'board_two_pair')

    def test_board_trips_is_not_hero_set(self):
        r = hand_strength(['Ah', 'Kd'], ['9h', '9d', '9s', '3c'])
        self.assertEqual(r['made'], 'board_trips')

    def test_plays_the_board_straight(self):
        r = hand_strength(['2c', '7d'], ['4h', '5d', '6s', '7h', '8c'])
        self.assertEqual(r['category_name'], 'straight')
        self.assertEqual(r['made'], 'plays_board')

    def test_hero_extends_straight_is_real(self):
        r = hand_strength(['9c', '2d'], ['4h', '5d', '6s', '7h', '8c'])
        self.assertEqual(r['made'], 'straight')          # hero 9 estende: 5-9 bate 4-8

    def test_no_draws_on_river(self):
        # #6: 4 na sequencia no board, mas e river -> sem outs
        r = hand_strength(['Kh', 'Qd'], ['2h', '3d', '4s', '5c', '9h'])
        self.assertEqual(r['outs'], 0)
        self.assertFalse(r['draws']['oesd'])
        self.assertFalse(r['draws']['flush_draw'])

    def test_duplicate_card_returns_none(self):
        self.assertIsNone(hand_strength(['As', 'Kd'], ['As', '9h', '3d']))

    def test_turn_and_river_sizes(self):
        self.assertIsNotNone(hand_strength(['As', 'Qc'], ['Ah', '9h', '3d', '5c']))
        self.assertIsNotNone(hand_strength(['As', 'Qc'], ['Ah', '9h', '3d', '5c', 'Jd']))


class DirtyOutsTests(unittest.TestCase):
    """Outs sujos (regra do meio-out): outs que podem dar a melhor mão ao vilão são
    descontados em `clean_outs`; `outs` cru é preservado para os rótulos de draw."""

    def test_clean_straight_rainbow_unchanged(self):
        # OESD limpo em board rainbow despareado: nada a descontar.
        d = hand_strength(['9h', '8c'], ['7h', '6c', '2d'])['draws']
        self.assertEqual(d['straight_outs'], 8)
        self.assertEqual(d['outs'], 8)
        self.assertEqual(d['tainted_outs'], 0.0)
        self.assertEqual(d['clean_outs'], 8)

    def test_straight_into_a_flush_discounted(self):
        # Mesmo OESD, mas duas cartas do board são do mesmo naipe: as cartas de
        # sequência DESSE naipe (Th, 5h) colocam a 3a do naipe no board -> meio-out.
        d = hand_strength(['9h', '8c'], ['7h', '6h', '2d'])['draws']
        self.assertEqual(d['straight_outs'], 8)
        self.assertEqual(d['outs'], 8)
        self.assertEqual(d['tainted_outs'], 1.0)      # Th + 5h, meio cada
        self.assertEqual(d['clean_outs'], 7.0)

    def test_paired_board_halves_flush_draw(self):
        # Flush draw num board PAREADO: full house vivo p/ o vilão -> cada out vale meio.
        d = hand_strength(['As', 'Ks'], ['7s', '7h', '2s'])['draws']
        self.assertTrue(d['flush_draw'])
        self.assertEqual(d['flush_outs'], 9)
        self.assertEqual(d['outs'], 9)
        self.assertEqual(d['tainted_outs'], 4.5)
        self.assertEqual(d['clean_outs'], 4.5)

    def test_flush_out_that_pairs_board_discounted(self):
        # Board despareado, mas 1 out de flush (2s) tem rank que já está no board (2d):
        # fechar o flush PAREIA o board -> meio-out; os outros 8 ficam limpos.
        d = hand_strength(['As', 'Ks'], ['Qs', '7s', '2d'])['draws']
        self.assertEqual(d['flush_outs'], 9)
        self.assertEqual(d['outs'], 9)
        self.assertEqual(d['tainted_outs'], 0.5)
        self.assertEqual(d['clean_outs'], 8.5)

    def test_clean_combo_draw_barely_discounted(self):
        # Combo monstro (FD + OESD) em board two-tone SECO: quase nada sujo (só o 2s,
        # que pareia o board). Garante que NÃO super-descontamos draws limpos.
        d = hand_strength(['9s', '8s'], ['7s', '6s', '2d'])['draws']
        self.assertTrue(d['combo'])
        self.assertEqual(d['outs'], 15)
        self.assertEqual(d['tainted_outs'], 0.5)
        self.assertEqual(d['clean_outs'], 14.5)

    def test_river_has_no_clean_outs(self):
        d = hand_strength(['Kh', 'Qd'], ['2h', '3d', '4s', '5c', '9h'])['draws']
        self.assertEqual(d['outs'], 0)
        self.assertEqual(d['clean_outs'], 0)
        self.assertEqual(d['tainted_outs'], 0.0)


class NutFlushDrawTests(unittest.TestCase):
    def test_ace_high_is_nut(self):
        d = hand_strength(['As', 'Ks'], ['9s', '7s', '2d'])['draws']
        self.assertTrue(d['flush_draw'])
        self.assertTrue(d['nut_flush_draw'])

    def test_king_high_not_nut_ace_live(self):
        d = hand_strength(['Ks', 'Qs'], ['9s', '7s', '2d'])['draws']
        self.assertTrue(d['flush_draw'])
        self.assertFalse(d['nut_flush_draw'])          # Ás ainda pode estar com o vilão

    def test_board_ace_makes_king_high_nut(self):
        d = hand_strength(['Ks', 'Qs'], ['As', '7s', '2d'])['draws']
        self.assertTrue(d['flush_draw'])
        self.assertTrue(d['nut_flush_draw'])           # Á no board joga p/ todos -> K é nut


class ContinuationMultiplierTests(unittest.TestCase):
    """Pesos-base por tier/rua (fatores de textura NEUTROS), travados na função pura."""
    NODRAW = dict(combo=False, flush_draw=False, oesd=False, gutshot=False, backdoor_flush=False)

    def test_value_tier_full(self):
        self.assertEqual(_continuation_multiplier('top_pair', self.NODRAW, 'FLOP'), 1.0)
        self.assertEqual(_continuation_multiplier('set', self.NODRAW, 'RIVER'), 1.0)

    def test_medium_tier_half(self):
        self.assertEqual(_continuation_multiplier('second_pair', self.NODRAW, 'FLOP'), 0.5)

    def test_air_bluff_falls_by_street(self):
        self.assertEqual(_continuation_multiplier('air', self.NODRAW, 'FLOP'), 0.25)
        self.assertEqual(_continuation_multiplier('air', self.NODRAW, 'TURN'), 0.15)
        self.assertEqual(_continuation_multiplier('air', self.NODRAW, 'RIVER'), 0.10)

    def test_strong_draw_full_weak_draw_small(self):
        self.assertEqual(_continuation_multiplier('air', dict(self.NODRAW, flush_draw=True), 'FLOP'), 1.0)
        self.assertEqual(_continuation_multiplier('air', dict(self.NODRAW, gutshot=True), 'FLOP'), 0.4)


class NarrowContinuationTests(unittest.TestCase):
    """Estreitamento do range pré-flop do vilão para o range de continuação no board
    (reponderação por tier + textura + card removal)."""

    @staticmethod
    def _combo(a, b):
        from preflop_equity import parse_card
        return frozenset({parse_card(a), parse_card(b)})

    def _w(self, narrowed, a, b):
        c = self._combo(a, b)
        return next((round(w, 3) for cc, w in narrowed if cc == c), None)

    def test_dry_board_value_medium_air(self):
        # K-9-2 rainbow desconexo = SECO: ar e média sobem (fatores 1.30/1.15).
        board = ['Ks', '9h', '2c']
        rng = [(self._combo('Kh', 'Qd'), 1.0),   # top pair -> valor 1.0
               (self._combo('9c', '8d'), 1.0),   # segundo par -> 0.5*1.15
               (self._combo('7c', '4d'), 1.0)]   # ar -> 0.25*1.30
        out = narrow_to_continuation(rng, board)
        self.assertEqual(self._w(out, 'Kh', 'Qd'), 1.0)
        self.assertEqual(self._w(out, '9c', '8d'), 0.575)
        self.assertEqual(self._w(out, '7c', '4d'), 0.325)

    def test_dry_widens_bluffs_wet_narrows(self):
        # MESMO ar: board seco deixa mais ar na range de aposta (hero defende largo);
        # board molhado polariza e tira ar puro (hero folda mais).
        air = [(self._combo('4d', '3d'), 1.0)]
        dry = narrow_to_continuation(air, ['Ks', '9h', '2c'])    # rainbow desconexo
        wet = narrow_to_continuation(air, ['Ks', '9s', '8s'])    # monotone conectado
        self.assertEqual(self._w(dry, '4d', '3d'), 0.325)        # 0.25 * 1.30
        self.assertEqual(self._w(wet, '4d', '3d'), 0.15)         # 0.25 * 0.60
        self.assertGreater(self._w(dry, '4d', '3d'), self._w(wet, '4d', '3d'))

    def test_strong_draw_keeps_full_weight(self):
        board = ['Ks', '9s', '2c']          # two-tone spades (molhado)
        rng = [(self._combo('Qs', 'Js'), 1.0)]   # flush draw -> segue cheio (textura não mexe)
        out = narrow_to_continuation(rng, board)
        self.assertEqual(self._w(out, 'Qs', 'Js'), 1.0)

    def test_board_blocked_combo_dropped(self):
        board = ['Ks', '9h', '2c']
        rng = [(self._combo('Ks', 'Qd'), 1.0),   # usa o Ks do board -> impossível
               (self._combo('Ah', 'Ad'), 1.0)]   # overpair -> fica (valor, textura não mexe)
        out = narrow_to_continuation(rng, board)
        self.assertIsNone(self._w(out, 'Ks', 'Qd'))
        self.assertEqual(self._w(out, 'Ah', 'Ad'), 1.0)


if __name__ == '__main__':
    unittest.main()
