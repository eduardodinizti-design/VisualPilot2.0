"""Session config + eligibility selector (decision only, no clicks)."""
import unittest

from session_config import SessionConfig, SessionState, evaluate_card, select_from_grade


def _card(name='MINI FREEZE', buyin=5, modality='freezeout', state='reg_open'):
    return dict(name=name, buyin=buyin, modality=modality,
                status=dict(state=state, closes_in_min=20, starts_at=None))


def _ready_cfg(**kw):
    base = dict(currency='FICHA', max_entry_buyin=50, daily_budget=200, bankroll_bi=200,
                max_tournaments_day=10, max_simultaneous=4,
                allowed_modalities=('freezeout', 'mko', 'pko'))
    base.update(kw)
    return SessionConfig(**base)


class EvaluateTests(unittest.TestCase):
    def test_eligible_happy_path(self):
        d = evaluate_card(_card(), _ready_cfg(), club='Karekas')
        self.assertEqual(d['decision'], 'ELIGIBLE')
        self.assertFalse(d['execution_allowed'])

    def test_missing_financial_config_blocks(self):
        d = evaluate_card(_card(), SessionConfig(), club='Karekas')  # no currency/caps
        self.assertIn('MISSING_FINANCIAL_CONFIG', d['reasons'])

    def test_club_not_authorized(self):
        d = evaluate_card(_card(), _ready_cfg(), club='OutroClube')
        self.assertIn('CLUB_NOT_AUTHORIZED', d['reasons'])

    def test_preset_grade_filters(self):
        d = evaluate_card(_card('MINI FREEZE'), _ready_cfg(grade_preset=('SUPER DEEP',)), club='Karekas')
        self.assertIn('NOT_IN_PRESET_GRADE', d['reasons'])

    def test_unknown_modality_needs_confirmation(self):
        d = evaluate_card(_card(modality='unknown'), _ready_cfg(), club='Karekas')
        self.assertIn('MODALITY_UNKNOWN_NEEDS_CONFIRMATION', d['reasons'])

    def test_rebuy_only_in_pko(self):
        d = evaluate_card(_card('CRAZY REBUY', modality='rebuy'), _ready_cfg(), club='Karekas')
        self.assertIn('REBUY_ONLY_IN_PKO', d['reasons'])

    def test_pko_allowed_when_in_list(self):
        # Non-turbo PKO at a 200-BI roll (>=150) is eligible.
        d = evaluate_card(_card('PKO NIGHT', buyin=50, modality='pko'), _ready_cfg(), club='Karekas')
        self.assertEqual(d['decision'], 'ELIGIBLE')

    def test_buyin_above_cap(self):
        d = evaluate_card(_card(buyin=80), _ready_cfg(max_entry_buyin=50), club='Karekas')
        self.assertIn('BUYIN_ABOVE_CAP', d['reasons'])

    def test_insufficient_bankroll_for_pko(self):
        # PKO needs >=150 buy-ins; a 120-BI roll blocks it but still allows MKO (120).
        cfg = _ready_cfg(bankroll_bi=120)
        pko = evaluate_card(_card('HYPER PKO', 50, 'pko'), cfg, club='Karekas')
        self.assertIn('INSUFFICIENT_BANKROLL_FOR_FORMAT', pko['reasons'])
        mko = evaluate_card(_card('KOMBAT MISTERY', 50, 'mko'), cfg, club='Karekas')
        self.assertNotIn('INSUFFICIENT_BANKROLL_FOR_FORMAT', mko['reasons'])

    def test_turbo_raises_the_bankroll_requirement(self):
        # Turbo PKO needs 150*1.5=225 BI; a 200-BI roll is enough for non-turbo PKO
        # but not for the turbo one.
        cfg = _ready_cfg(bankroll_bi=200)
        turbo = evaluate_card(_card('TURBO PKO', 50, 'pko'), cfg, club='Karekas')
        self.assertIn('INSUFFICIENT_BANKROLL_FOR_FORMAT', turbo['reasons'])
        normal = evaluate_card(_card('PKO NIGHT', 50, 'pko'), cfg, club='Karekas')
        self.assertNotIn('INSUFFICIENT_BANKROLL_FOR_FORMAT', normal['reasons'])

    def test_registration_not_open(self):
        d = evaluate_card(_card(state='not_started'), _ready_cfg(), club='Karekas')
        self.assertIn('REGISTRATION_NOT_OPEN', d['reasons'])

    def test_past_cutoff(self):
        d = evaluate_card(_card(), _ready_cfg(registration_cutoff='22:00'), club='Karekas', now_hhmm='23:15')
        self.assertIn('PAST_REGISTRATION_CUTOFF', d['reasons'])
        d2 = evaluate_card(_card(), _ready_cfg(registration_cutoff='22:00'), club='Karekas', now_hhmm='21:30')
        self.assertNotIn('PAST_REGISTRATION_CUTOFF', d2['reasons'])

    def test_duplicate_and_limits(self):
        st = SessionState(committed=[{'name': 'MINI FREEZE', 'buyin': 5}])
        d = evaluate_card(_card('MINI FREEZE'), _ready_cfg(), st, club='Karekas')
        self.assertIn('ALREADY_COMMITTED', d['reasons'])

    def test_max_simultaneous(self):
        st = SessionState(committed=[{'name': 'A', 'buyin': 5}, {'name': 'B', 'buyin': 5},
                                     {'name': 'C', 'buyin': 5}, {'name': 'D', 'buyin': 5}])
        d = evaluate_card(_card('E'), _ready_cfg(max_simultaneous=4), st, club='Karekas')
        self.assertIn('MAX_SIMULTANEOUS_REACHED', d['reasons'])

    def test_daily_budget_exceeded(self):
        st = SessionState(confirmed_spend=198)
        d = evaluate_card(_card(buyin=5), _ready_cfg(daily_budget=200), st, club='Karekas')
        self.assertIn('DAILY_BUDGET_EXCEEDED', d['reasons'])


class ValidationTests(unittest.TestCase):
    def test_non_finite_buyin_is_blocked(self):
        for bad in (float('nan'), float('inf'), -5):
            d = evaluate_card(_card(buyin=bad), _ready_cfg(), club='Karekas')
            self.assertIn('BUYIN_UNKNOWN', d['reasons'])

    def test_cutoff_without_a_valid_clock_fails_safe(self):
        cfg = _ready_cfg(registration_cutoff='22:00')
        self.assertIn('REGISTRATION_TIME_UNKNOWN', evaluate_card(_card(), cfg, club='Karekas')['reasons'])
        self.assertIn('REGISTRATION_TIME_UNKNOWN',
                      evaluate_card(_card(), cfg, club='Karekas', now_hhmm='99:99')['reasons'])

    def test_unknown_club_is_blocked(self):
        self.assertIn('CLUB_NOT_AUTHORIZED', evaluate_card(_card(), _ready_cfg(), club=None)['reasons'])

    def test_confirm_moves_reserve_without_double_counting(self):
        st = SessionState(committed=[{'name': 'A', 'buyin': 5}])
        self.assertEqual(st.committed_cost(), 5)
        st.confirm('A')
        self.assertEqual(st.confirmed_spend, 5)
        self.assertFalse(st.is_committed('A'))
        self.assertEqual(st.committed_cost(), 5)   # still 5, not 10


class SelectTests(unittest.TestCase):
    def test_split_eligible_blocked(self):
        cards = [_card('MINI FREEZE', 5, 'freezeout'),
                 _card('BIG ONE', 500, 'freezeout'),           # above cap
                 _card('KOMBAT MISTERY', 50, 'mko')]
        elig, blocked = select_from_grade(cards, _ready_cfg(), club='Karekas')
        self.assertEqual({d['name'] for d in elig}, {'MINI FREEZE', 'KOMBAT MISTERY'})
        self.assertEqual([d['name'] for d in blocked], ['BIG ONE'])


if __name__ == '__main__':
    unittest.main()
