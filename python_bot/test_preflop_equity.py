"""Testes do motor de equity pré-flop: avaliador de 7 cartas (categorias) e
equity mão-vs-range contra valores de poker conhecidos (tolerância de Monte Carlo)."""
import unittest

from preflop_equity import (eval7, parse_card, hand_to_combos, equity_vs_range,
                            required_equity)


def C(*cards):
    return [parse_card(c) for c in cards]


def single_hand_range(hand):
    return [(combo, 1.0) for combo in hand_to_combos(hand)]


class EvaluatorTest(unittest.TestCase):
    def test_straight_flush_beats_quads(self):
        sf = eval7(C('As', 'Ks', 'Qs', 'Js', 'Ts', '2d', '3c'))
        quads = eval7(C('Ah', 'Ad', 'Ac', 'As', 'Kd', 'Kc', '2h'))
        self.assertEqual(sf[0], 8)
        self.assertEqual(quads[0], 7)
        self.assertGreater(sf, quads)

    def test_wheel_straight(self):
        s = eval7(C('Ah', '2d', '3c', '4s', '5h', 'Kd', 'Qc'))
        self.assertEqual(s[0], 4)
        self.assertEqual(s[1], 5)                      # A-baixo: topo é o 5

    def test_full_house_over_flush(self):
        fh = eval7(C('Kh', 'Kd', 'Kc', '2s', '2h', '9d', '4c'))
        fl = eval7(C('Ah', '9h', '7h', '4h', '2h', 'Ks', 'Qd'))
        self.assertEqual(fh[0], 6)
        self.assertEqual(fl[0], 5)
        self.assertGreater(fh, fl)

    def test_two_pair_kicker(self):
        hi = eval7(C('Ah', 'Ad', 'Ks', 'Kc', 'Qd', '3h', '2c'))
        lo = eval7(C('Ah', 'Ad', 'Ks', 'Kc', 'Jd', '3h', '2c'))
        self.assertEqual(hi[0], 2)
        self.assertGreater(hi, lo)                     # Q kicker > J kicker

    def test_best_five_of_seven(self):
        # trinca de ases com dois kickers altos, não deixa par virar o resultado
        r = eval7(C('As', 'Ah', 'Ad', 'Kh', 'Qc', '7d', '2s'))
        self.assertEqual(r[0], 3)
        self.assertEqual(r[1], 14)


class EquityTest(unittest.TestCase):
    ITERS = 12000

    def eq(self, hero, hand, **kw):
        return equity_vs_range(hero, single_hand_range(hand), iters=self.ITERS,
                               seed=42, **kw)

    def test_aa_vs_kk(self):
        e = self.eq(['As', 'Ah'], 'KK')
        self.assertAlmostEqual(e, 0.82, delta=0.03)

    def test_aks_vs_qq_is_near_coinflip(self):
        e = self.eq(['As', 'Ks'], 'QQ')               # ~46% (AK levemente dog)
        self.assertAlmostEqual(e, 0.46, delta=0.03)

    def test_aa_vs_suited_connector(self):
        e = self.eq(['As', 'Ah'], '76s')              # ~0.77
        self.assertAlmostEqual(e, 0.77, delta=0.03)

    def test_pair_vs_two_overcards(self):
        e = self.eq(['2c', '2d'], 'AKo')              # 22 ~52.5% vs AKo
        self.assertAlmostEqual(e, 0.525, delta=0.03)

    def test_blockers_removed_from_range(self):
        # hero tem Ks: combos de KK que usam Ks saem; range ainda tem combos -> roda
        e = equity_vs_range(['As', 'Ks'], single_hand_range('KK'),
                            iters=2000, seed=1)
        self.assertIsNotNone(e)
        self.assertTrue(0.0 <= e <= 1.0)

    def test_empty_range_returns_none(self):
        self.assertIsNone(equity_vs_range(['As', 'Ah'], [], iters=500))

    def test_all_combos_blocked_returns_none(self):
        # range só com combos que usam as cartas do hero -> todos filtrados -> None
        blocked = [(frozenset({(14, 's'), (13, 'h')}), 1.0),   # AsKh (usa As do hero)
                   (frozenset({(14, 'h'), (12, 'd')}), 1.0)]   # AhQd (usa Ah do hero)
        self.assertIsNone(equity_vs_range(['As', 'Ah'], blocked, iters=500))


class PotOddsTest(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(required_equity(6, 12), 6 / 18)

    def test_half_pot_shove(self):
        self.assertAlmostEqual(required_equity(10, 10), 0.5)

    def test_invalid(self):
        self.assertIsNone(required_equity(0, 10))
        self.assertIsNone(required_equity(None, 10))


if __name__ == '__main__':
    unittest.main()
