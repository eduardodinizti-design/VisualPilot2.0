"""Testes do conselho pós-flop (heurística fundamentada, exploratória)."""
import unittest

from postflop_advisor import advise_postflop, _implied_bb


def state(pot, to_call, stack=40.0):
    return dict(pot=dict(pot_bb=pot), to_call=dict(to_call_bb=to_call),
                seats=dict(hero=dict(stack_bb=stack, occupied=True)),
                positions=dict(hero='BTN'))


class ImpliedOddsTests(unittest.TestCase):
    """Implied odds nos draws: o ganho futuro quando o draw completa baixa a equity
    exigida; limitado pelo stack atrás; draw óbvio (flush) rende menos; river = 0."""
    OESD = dict(oesd=True, flush_draw=False, combo=False, gutshot=False, backdoor_flush=False)
    FD = dict(oesd=False, flush_draw=True, combo=False, gutshot=False, backdoor_flush=False)

    def test_helper_street_and_stack_cap(self):
        self.assertEqual(_implied_bb('FLOP', 10, 40, 5, self.OESD), 5.0)   # 0.5*10, teto 35
        self.assertEqual(_implied_bb('TURN', 10, 40, 5, self.OESD), 2.5)   # 0.25*10
        self.assertEqual(_implied_bb('FLOP', 10, 7, 5, self.OESD), 2.0)    # teto = 7-5 atrás
        self.assertEqual(_implied_bb('RIVER', 10, 40, 5, self.OESD), 0.0)  # river sem implied

    def test_obvious_flush_draw_gets_less_implied(self):
        self.assertLess(_implied_bb('FLOP', 10, 40, 5, self.FD),          # flush (óbvio)
                        _implied_bb('FLOP', 10, 40, 5, self.OESD))        # sequência (escondida)

    def test_deep_stack_implied_turns_fold_into_call(self):
        # OESD (8 outs limpos) em pot odds que SEM implied foldaria; deep -> implied paga.
        r = advise_postflop(state(10, 5, 40), ['9h', '8c'], ['7h', '6c', '2d'])
        self.assertEqual(r['recommended'], 'call')
        self.assertEqual(r['implied_bb'], 5.0)
        self.assertLess(r['draw_equity'], r['pot_odds'])        # sem implied seria fold
        self.assertLess(r['pot_odds_implied'], r['pot_odds'])

    def test_short_stack_no_implied_folds(self):
        # Mesmo draw/pote, mas sem fichas atrás (stack=to_call) -> implied 0 -> fold.
        r = advise_postflop(state(10, 5, 5), ['9h', '8c'], ['7h', '6c', '2d'])
        self.assertEqual(r['recommended'], 'fold')
        self.assertEqual(r['implied_bb'], 0.0)

    def test_reverse_implied_nonnut_flush_folds_borderline(self):
        # Mesmo board/pote: nut flush draw (As Ks) paga; não-nut (Ks Qs, Ás na roda) tem
        # implied menor (reverse implied) e folda o borderline.
        board = ['9s', '7s', '2d']
        nut = advise_postflop(state(10, 6), ['As', 'Ks'], board)
        non = advise_postflop(state(10, 6), ['Ks', 'Qs'], board)
        self.assertEqual(nut['recommended'], 'call')
        self.assertEqual(non['recommended'], 'fold')
        self.assertLess(non['implied_bb'], nut['implied_bb'])
        self.assertIn('REVERSE_IMPLIED_NONNUT_FLUSH', non['caveats'])


class NarrowRangeTests(unittest.TestCase):
    """C: estreitar o range do vilão para o range de continuação no board (equity
    robusta vs não-robusta) é mais preciso que o deságio fixo sobre o range pré-flop."""
    RNG = ['AK', 'AQ', 'AJ', 'AT', 'A9', 'KQ', 'KJ', 'QJ', 'JT', 'T9', 'TT', '99', '88']

    def test_narrowing_strengthens_range_and_flips_to_fold(self):
        # 22 (terceiro par) em J-9-5 two-tone (MOLHADO/polarizado). Contra o range
        # PRÉ-FLOP (muito ar) a equity basta p/ pagar; contra o range de CONTINUAÇÃO
        # (valor + draws, pouco ar num board molhado) despenca e vira fold — o leak que
        # o deságio fixo deixava.
        s = state(10, 3.7)
        hero, board = ['2s', '2d'], ['Js', '9s', '5h']
        wide = advise_postflop(s, hero, board, villain_range=self.RNG, narrow_range=False, seed=1)
        narr = advise_postflop(s, hero, board, villain_range=self.RNG, narrow_range=True, seed=1)
        self.assertEqual(wide['recommended'], 'call')
        self.assertIn('RANGE_NOT_NARROWED_POSTFLOP', wide['caveats'])
        self.assertEqual(narr['recommended'], 'fold')
        self.assertIn('RANGE_NARROWED_TO_BOARD', narr['caveats'])
        self.assertLess(narr['equity'], wide['equity'])

    def test_narrow_only_applies_when_facing_a_bet(self):
        # Passaram a vez (to_call==0): a decisão é por tiers, sem equity de call, então
        # o estreitamento não se aplica (o range de aposta do vilão nem existe aqui).
        s = state(10, 0)
        r = advise_postflop(s, ['6s', '6d'], ['As', '7h', '2c'],
                            villain_range=self.RNG, narrow_range=True)
        self.assertNotIn('RANGE_NARROWED_TO_BOARD', r.get('caveats', []))


class ExploitHudTests(unittest.TestCase):
    """Exploit do HUD: a leitura do vilão decide o bluffcatch de aposta grande e
    nudgeia o limiar das mãos feitas."""
    FISH = {'vpip': 45, 'pfr': 12, 'cbet': 40, 'foldcbet': 30, 'threebet': 2, 'fold3bet': 70, 'steal': 20, 'cr': 5}
    LAG = {'vpip': 30, 'pfr': 26, 'cbet': 70, 'foldcbet': 40, 'threebet': 11, 'fold3bet': 40, 'steal': 45, 'cr': 8}

    def test_big_bet_abstains_without_hud(self):
        r = advise_postflop(state(10, 8), ['As', 'Kc'], ['Ad', '9h', '3d'])   # top pair, pot_odds 0.44
        self.assertEqual(r['reason'], 'BLUFFCATCH_VS_BIG_BET_NEEDS_READS')

    def test_big_bet_calls_vs_aggressive(self):
        r = advise_postflop(state(10, 8), ['As', 'Kc'], ['Ad', '9h', '3d'], villain_stats=self.LAG)
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('EXPLOIT_HUD_LAG', r['caveats'])
        self.assertTrue(any('BLUFFCATCH_BIG_BET_EXPLOIT_AGGRO' in c for c in r['caveats']))

    def test_big_bet_folds_vs_passive(self):
        r = advise_postflop(state(10, 8), ['As', 'Kc'], ['Ad', '9h', '3d'], villain_stats=self.FISH)
        self.assertEqual(r['recommended'], 'fold')
        self.assertIn('EXPLOIT_HUD_FISH', r['caveats'])

    FOLDCBET = {'vpip': 22, 'pfr': 18, 'cbet': 55, 'foldcbet': 65, 'threebet': 5, 'fold3bet': 55, 'steal': 30, 'cr': 5}

    def test_cbet_bluff_air_vs_folds_to_cbet(self):
        # Passaram a vez com AR: sem HUD dá check; vs vilão que foge de c-bet, blefa.
        board = ['Ah', 'Kc', '9s']
        self.assertEqual(advise_postflop(state(10, 0), ['7s', '4d'], board)['recommended'], 'check')
        r = advise_postflop(state(10, 0), ['7s', '4d'], board, villain_stats=self.FOLDCBET)
        self.assertEqual(r['recommended'], 'bet')
        self.assertIn('EXPLOIT_CBET_BLUFF_VS_FOLDCBET', r['caveats'])

    def test_no_cbet_bluff_with_showdown_value(self):
        # Mão média (segundo par) vs folds_to_cbet NÃO vira blefe (tem showdown value).
        r = advise_postflop(state(10, 0), ['9s', '8d'], ['Ah', '9h', '3d'], villain_stats=self.FOLDCBET)
        self.assertEqual(r['recommended'], 'check')


class AbstentionTests(unittest.TestCase):
    def test_no_board(self):
        r = advise_postflop(state(10, 0), ['As', 'Kd'], [])
        self.assertEqual(r['status'], 'ABSTAIN')
        self.assertEqual(r['reason'], 'NO_BOARD')

    def test_pot_unknown(self):
        r = advise_postflop(state(None, 0), ['As', 'Kd'], ['Ah', '9h', '3d'])
        self.assertEqual(r['reason'], 'POT_UNKNOWN')

    def test_to_call_unknown(self):
        r = advise_postflop(dict(pot=dict(pot_bb=10), to_call=dict(to_call_bb=None),
                                 seats=dict(hero=dict(stack_bb=40))),
                            ['As', 'Kd'], ['Ah', '9h', '3d'])
        self.assertEqual(r['reason'], 'TO_CALL_UNKNOWN')

    def test_card_conflict(self):
        r = advise_postflop(state(10, 0), ['As', 'Kd'], ['As', '9h', '3d'])
        self.assertEqual(r['reason'], 'HERO_BOARD_CARD_CONFLICT')


class FacingBetTests(unittest.TestCase):
    def test_strong_dry_board_raises(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'])  # set
        self.assertEqual(r['recommended'], 'raise')
        self.assertIn('size_bb', r['sizing'])
        self.assertFalse(r['execution_allowed'])

    def test_strong_but_board_makes_flush_calls_only(self):
        r = advise_postflop(state(10, 4), ['Ks', 'Kc'], ['9s', '7s', '2s'])  # overpair, monotone
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('BOARD_MAY_BEAT_ONE_PAIR_CALL_ONLY', r['caveats'])

    def test_flush_draw_good_odds_calls(self):
        r = advise_postflop(state(6, 1), ['As', 'Ks'], ['Qs', '7s', '2d'])
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('DRAW_EQUITY_RULE_OF_2_AND_4', r['caveats'])
        self.assertGreater(r['draw_equity'], r['pot_odds'])

    def test_flush_draw_bad_odds_folds(self):
        r = advise_postflop(state(2, 6), ['As', 'Ks'], ['Qs', '7s', '2d'])
        self.assertEqual(r['recommended'], 'fold')
        self.assertLess(r['draw_equity'], r['pot_odds'])

    def test_dirty_outs_flip_draw_call_to_fold(self):
        # Mesmo OESD (8 outs crus), mesma pot odds (3 p/ pagar num pote de 7 = 30%):
        # board rainbow LIMPO (clean=8 -> 32%) paga; board com 2 do mesmo naipe suja
        # 2 outs (Th,5h -> clean=7 -> 28%) e deve FOLDAR. Sem range do vilao.
        # stack=3 (=to_call) -> sem fichas atrás -> implied odds 0, isolando o efeito
        # dos outs sujos (senão o implied tornaria o draw pagável mesmo sujo).
        clean = advise_postflop(state(7, 3, 3), ['9h', '8c'], ['7h', '6c', '2d'])
        self.assertEqual(clean['recommended'], 'call')
        self.assertEqual(clean['clean_outs'], 8)
        dirty = advise_postflop(state(7, 3, 3), ['9h', '8c'], ['7h', '6h', '2d'])
        self.assertEqual(dirty['recommended'], 'fold')
        self.assertEqual(dirty['clean_outs'], 7.0)
        self.assertTrue(any(c.startswith('DIRTY_OUTS_DISCOUNTED') for c in dirty['caveats']))

    def test_top_pair_small_bet_calls(self):
        r = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'])
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('BLUFFCATCH_DEFEND_TO_MDF', r['caveats'])

    def test_top_pair_big_bet_abstains(self):
        r = advise_postflop(state(10, 20), ['As', 'Qc'], ['Ah', '9h', '3d'])
        self.assertEqual(r['status'], 'ABSTAIN')
        self.assertEqual(r['reason'], 'BLUFFCATCH_VS_BIG_BET_NEEDS_READS')

    def test_marginal_pair_folds(self):
        r = advise_postflop(state(10, 5), ['9s', 'Qc'], ['Ah', '9h', '3d'])  # second pair
        self.assertEqual(r['recommended'], 'fold')
        self.assertIn('MARGINAL_BLUFFCATCH_FOLD_DEFAULT_EXPLOITABLE', r['caveats'])

    def test_air_folds(self):
        r = advise_postflop(state(10, 5), ['7s', '4d'], ['Ah', 'Kc', '9s'])
        self.assertEqual(r['recommended'], 'fold')

    def test_mdf_and_pot_odds_reported(self):
        r = advise_postflop(state(10, 5), ['9s', 'Qc'], ['Ah', '9h', '3d'])
        self.assertAlmostEqual(r['pot_odds'], 5 / 15, places=3)
        self.assertAlmostEqual(r['mdf'], 10 / 15, places=3)


class CheckedToTests(unittest.TestCase):
    def test_strong_value_bets(self):
        r = advise_postflop(state(8, 0), ['3c', '3h'], ['As', '9h', '3d'])
        self.assertEqual(r['recommended'], 'bet')
        self.assertGreater(r['sizing']['size_bb'], 0)

    def test_strong_draw_semibluffs(self):
        r = advise_postflop(state(8, 0), ['As', 'Ks'], ['Qs', '7s', '2d'])
        self.assertEqual(r['recommended'], 'bet')
        self.assertIn('SEMI_BLUFF_NEGA_EQUITY_E_CRESCE_POTE', r['caveats'])

    def test_top_pair_dry_bets_thin(self):
        r = advise_postflop(state(8, 0), ['As', 'Qc'], ['Ah', '9c', '3d'])
        self.assertEqual(r['recommended'], 'bet')
        self.assertLess(r['sizing']['fraction'], 0.5)

    def test_air_checks(self):
        r = advise_postflop(state(8, 0), ['7s', '4d'], ['Ah', 'Kc', '9s'])
        self.assertEqual(r['recommended'], 'check')

    def test_marginal_checks(self):
        r = advise_postflop(state(8, 0), ['9s', 'Qc'], ['Ah', '9h', '3d'])
        self.assertEqual(r['recommended'], 'check')


class Phase2EquityTests(unittest.TestCase):
    """Com range do vilão, o CALL passa a ser por equity exata (Monte Carlo, seed fixa)."""

    def test_top_pair_calls_vs_wide_value(self):
        # AQ top pair de ases vs overpairs/AK: hero à frente da maioria -> call.
        r = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['KK', 'QQ', 'JJ', 'AK'], iters=2000)
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('BLUFFCATCH_EQUITY_DRIVEN', r['caveats'])
        self.assertGreater(r['equity'], r['pot_odds'])

    def test_top_pair_folds_vs_sets(self):
        # Mesmo top pair vs um range só de sets: atrás -> fold.
        r = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['AA', '99', '33'], iters=2000)
        self.assertEqual(r['recommended'], 'fold')
        self.assertLess(r['equity'], r['pot_odds'] + 0.05)

    def test_big_bet_still_abstains_with_range(self):
        r = advise_postflop(state(10, 20), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['KK', 'QQ', 'AK'], iters=2000)
        self.assertEqual(r['status'], 'ABSTAIN')
        self.assertEqual(r['reason'], 'BLUFFCATCH_VS_BIG_BET_NEEDS_READS')
        self.assertIsNotNone(r['equity'])      # equity reportada, mas abstém

    def test_draw_equity_exact_overrides_rule(self):
        r = advise_postflop(state(6, 1), ['As', 'Ks'], ['Qs', '7s', '2d'],
                            villain_range=['QQ', '77', '22'], iters=2000)
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('EQUITY_VS_VILLAIN_PREFLOP_RANGE', r['caveats'])
        self.assertNotIn('draw_equity', r)     # usa equity exata, não a regra 2-e-4

    def test_marginal_calls_vs_air_range(self):
        r = advise_postflop(state(10, 5), ['9s', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['KQ', 'KJ', 'QJ', 'JT'], iters=2000)
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('MARGINAL_EQUITY_DRIVEN', r['caveats'])

    def test_marginal_folds_vs_value_range(self):
        r = advise_postflop(state(10, 5), ['9s', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['AA', 'AK', 'AQ', '99'], iters=2000)
        self.assertEqual(r['recommended'], 'fold')

    def test_equity_is_deterministic(self):
        a = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['KK', 'QQ', 'AK'], iters=2000)
        b = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['KK', 'QQ', 'AK'], iters=2000)
        self.assertEqual(a['equity'], b['equity'])

    def test_range_accepts_hand_strings_and_combos(self):
        from preflop_equity import hand_to_combos
        combos = [(c, 1.0) for c in hand_to_combos('KK')] + [(c, 1.0) for c in hand_to_combos('QQ')]
        a = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=['KK', 'QQ'], iters=2000)
        b = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'],
                            villain_range=combos, iters=2000)
        self.assertEqual(a['equity'], b['equity'])

    def test_no_range_keeps_phase1_behavior(self):
        r = advise_postflop(state(10, 3), ['As', 'Qc'], ['Ah', '9h', '3d'])
        self.assertIsNone(r['equity'])
        self.assertEqual(r['recommended'], 'call')     # bluffcatch Fase 1
        self.assertIn('BLUFFCATCH_DEFEND_TO_MDF', r['caveats'])


class PotTypeGatingTests(unittest.TestCase):
    """3bet pot HU dá HEURÍSTICA (SPR baixo/range mais forte); multiway abstém."""

    def test_three_bet_pot_gives_heuristic(self):
        # Set em 3bet pot (SPR baixo): comete -> raise, com o rótulo de heurística 3bet.
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'], pot_type='three_bet')
        self.assertEqual(r['status'], 'ADVICE')
        self.assertEqual(r['made'], 'set')
        self.assertEqual(r['recommended'], 'raise')
        self.assertIn('POSTFLOP_THREE_BET_POT_HEURISTIC', r['caveats'])
        self.assertFalse(r['execution_allowed'])

    def test_multiway_abstains_labeled(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'], pot_type='multiway')
        self.assertEqual(r['reason'], 'POSTFLOP_MULTIWAY_NOT_COVERED')
        self.assertIsNotNone(r['pot_odds'])         # leitura preservada

    def test_single_raised_still_advises(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'], pot_type='single_raised')
        self.assertEqual(r['status'], 'ADVICE')
        self.assertEqual(r['recommended'], 'raise')

    def test_unknown_pot_type_falls_to_phase1(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'], pot_type='unknown')
        self.assertEqual(r['status'], 'ADVICE')     # não bloqueia: Fase 1

    def test_default_none_unchanged(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'])
        self.assertEqual(r['status'], 'ADVICE')

    def test_three_bet_heuristic_is_tier_based_no_equity(self):
        # A heurística de 3bet é por TIER+SPR (não há range de 3bet) -> não roda Monte
        # Carlo mesmo com um range dado; equity fica None.
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'],
                            villain_range=['AK', 'KQ'], pot_type='three_bet')
        self.assertEqual(r['status'], 'ADVICE')
        self.assertIsNone(r.get('equity'))

    def test_multiway_skips_equity(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'],
                            villain_range=['AK', 'KQ'], pot_type='multiway')
        self.assertEqual(r['status'], 'ABSTAIN')
        self.assertIsNone(r.get('equity'))


class ThreeBetPotTests(unittest.TestCase):
    """Heurística do 3bet pot HU: SPR baixo comete, range mais forte folda marginais,
    draw sem implied (odds diretas)."""

    def test_top_pair_commits_at_low_spr(self):
        r = advise_postflop(state(10, 4, 20), ['As', 'Kc'], ['Ad', '9h', '3d'],
                            pot_type='three_bet')           # spr 2.0
        self.assertEqual(r['made'], 'top_pair')
        self.assertEqual(r['recommended'], 'call')
        self.assertIn('TOP_PAIR_COMMITS_LOW_SPR', r['caveats'])

    def test_top_pair_deep_3bet_folds(self):
        r = advise_postflop(state(10, 4, 100), ['As', 'Kc'], ['Ad', '9h', '3d'],
                            pot_type='three_bet')           # spr 10 -> polarizado
        self.assertEqual(r['recommended'], 'fold')
        self.assertIn('TOP_PAIR_DEEP_3BET_POLARIZED_FOLD', r['caveats'])

    def test_marginal_folds_vs_3bet_range(self):
        r = advise_postflop(state(10, 4, 40), ['9s', '8d'], ['As', '9h', '3d'],
                            pot_type='three_bet')           # segundo par
        self.assertEqual(r['recommended'], 'fold')
        self.assertIn('MARGINAL_FOLD_VS_3BET_RANGE', r['caveats'])

    def test_draw_uses_direct_odds_no_implied(self):
        # OESD deep: no pote de um raise só o implied pagaria; no 3bet pot é só odds
        # diretas -> aqui 0.32 < pot_odds 0.333 -> fold.
        r = advise_postflop(state(10, 5, 100), ['9h', '8c'], ['7h', '6c', '2d'],
                            pot_type='three_bet')
        self.assertEqual(r['recommended'], 'fold')
        self.assertIn('DRAW_DIRECT_ODDS_NO_IMPLIED_3BET', r['caveats'])
        self.assertIsNone(r.get('implied_bb'))              # 3bet nao modela implied


class ReviewFixesTests(unittest.TestCase):
    """Contraexemplos da revisão (updates.txt #5, #6, #7) — não podem regredir."""

    def test_5_board_two_pair_does_not_raise(self):
        r = advise_postflop(state(15, 5), ['Ah', 'Kd'], ['2h', '2d', '3s', '3c', '5h'])
        self.assertEqual(r['made'], 'board_two_pair')
        self.assertNotEqual(r['recommended'], 'raise')
        self.assertEqual(r['recommended'], 'fold')

    def test_6_no_semibluff_on_river(self):
        r = advise_postflop(state(8, 0), ['Kh', 'Qd'], ['2h', '3d', '4s', '5c', '9h'])
        self.assertEqual(r['recommended'], 'check')
        self.assertEqual(r['outs'], 0)

    def test_6_made_pair_with_draw_not_folded_as_draw(self):
        # Top pair de ases + flush draw (4 copas) contra aposta pequena -> paga como
        # mão feita, nao folda como se fosse so draw.
        r = advise_postflop(state(10, 3), ['Ah', 'Qh'], ['Ad', '7h', '2h'])
        self.assertEqual(r['made'], 'top_pair')
        self.assertEqual(r['recommended'], 'call')

    def test_7_strong_category_folds_when_equity_zero(self):
        r = advise_postflop(state(10, 4), ['Qh', 'Qd'], ['Ks', 'Qc', '2d', '7h', 'Ac'],
                            villain_range=['KK'])
        self.assertEqual(r['made'], 'set')
        self.assertEqual(r['equity'], 0.0)
        self.assertEqual(r['recommended'], 'fold')
        self.assertIn('STRONG_CATEGORY_BUT_DOMINATED_BY_RANGE', r['caveats'])

    def test_7_strong_still_raises_with_high_equity(self):
        r = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'],
                            villain_range=['AK', 'AQ', 'KQ', 'JT'])
        self.assertEqual(r['made'], 'set')
        self.assertEqual(r['recommended'], 'raise')


class ContractTests(unittest.TestCase):
    def test_never_allows_execution(self):
        for st, hero, board in [
            (state(10, 4), ['3c', '3h'], ['As', '9h', '3d']),
            (state(6, 1), ['As', 'Ks'], ['Qs', '7s', '2d']),
            (state(8, 0), ['7s', '4d'], ['Ah', 'Kc', '9s']),
            (state(10, 20), ['As', 'Qc'], ['Ah', '9h', '3d']),
        ]:
            r = advise_postflop(st, hero, board)
            self.assertFalse(r['execution_allowed'])
            self.assertTrue(r['exploratory'])
            self.assertIn('POSTFLOP_HEURISTIC_NO_SOLVER', r['caveats'])

    def test_phase_marker_on_advice_and_abstain(self):
        # O marcador phase='postflop' é o que impede o operador armado de executar
        # pós-flop (o executor só olha status/elegibilidade), então deve estar sempre.
        adv = advise_postflop(state(10, 4), ['3c', '3h'], ['As', '9h', '3d'])
        self.assertEqual(adv['phase'], 'postflop')
        ab = advise_postflop(state(None, 0), ['As', 'Kd'], ['Ah', '9h', '3d'])
        self.assertEqual(ab['status'], 'ABSTAIN')
        self.assertEqual(ab['phase'], 'postflop')

    def test_spr_computed(self):
        r = advise_postflop(state(10, 0, stack=40), ['3c', '3h'], ['As', '9h', '3d'])
        self.assertAlmostEqual(r['spr'], 4.0, places=2)

    def test_icm_mode_flagged(self):
        r = advise_postflop(state(10, 0), ['3c', '3h'], ['As', '9h', '3d'], mode='icm')
        self.assertIn('ICM_PKO_NOT_APPLIED_POSTFLOP', r['caveats'])

    def test_street_inferred(self):
        self.assertEqual(advise_postflop(state(8, 0), ['As', 'Qc'], ['Ah', '9c', '3d'])['street'], 'FLOP')
        self.assertEqual(advise_postflop(state(8, 0), ['As', 'Qc'], ['Ah', '9c', '3d', '5s'])['street'], 'TURN')
        self.assertEqual(advise_postflop(state(8, 0), ['As', 'Qc'], ['Ah', '9c', '3d', '5s', 'Jd'])['street'], 'RIVER')


if __name__ == '__main__':
    unittest.main()
