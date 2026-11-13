"""HandReconciler: evidence-backed state-trajectory events within one hand."""
import unittest
from table_reading.hand_reconcile import HandReconciler, street_from_board


class StreetTests(unittest.TestCase):
    def test_board_count_to_street(self):
        self.assertEqual([street_from_board(n) for n in (0, 3, 4, 5)], ['preflop', 'flop', 'turn', 'river'])
        self.assertIsNone(street_from_board(2))


class ReconcileTests(unittest.TestCase):
    def test_street_advance_and_commit_reconcile(self):
        r = HandReconciler()
        r.add(dict(pot_bb=3.0, street='preflop', stacks={'hero': 100.0, 'btn': 100.0}, bets_bb=0.0))
        events = r.add(dict(pot_bb=3.0, street='flop', stacks={'hero': 94.0, 'btn': 100.0}, bets_bb=6.0))
        kinds = [e['event'] for e in events]
        self.assertIn('street_advanced', kinds)
        self.assertIn('seat_committed', kinds)
        commit = next(e for e in events if e['event'] == 'seat_committed')
        self.assertEqual((commit['seat'], commit['amount']), ('hero', 6.0))
        rec = next(e for e in events if e['event'] == 'reconciliation')
        self.assertEqual(rec['status'], 'reconciled')  # 6 committed = pot 0 + bets +6

    def test_unexplained_change_is_a_gap(self):
        r = HandReconciler()
        r.add(dict(pot_bb=3.0, street='preflop', stacks={'hero': 100.0}, bets_bb=0.0))
        events = r.add(dict(pot_bb=3.0, street='preflop', stacks={'hero': 80.0}, bets_bb=0.0))  # -20 but pot/bets flat
        rec = next(e for e in events if e['event'] == 'reconciliation')
        self.assertEqual(rec['status'], 'gap')

    def test_pot_regressed_flags_missed_boundary(self):
        r = HandReconciler()
        r.add(dict(pot_bb=20.0, street='river', stacks={}))
        events = r.add(dict(pot_bb=3.0, street='preflop', stacks={}))
        self.assertIn('pot_regressed', [e['event'] for e in events])

    def test_missing_fields_are_tolerated(self):
        r = HandReconciler()
        r.add(dict(street=None, stacks={'hero': None}))
        events = r.add(dict(pot_bb=5.0, street='flop', stacks={'hero': 100.0}))
        self.assertEqual([e for e in events if e['event'] == 'reconciliation'], [])  # nothing to reconcile

    def test_street_helper_returns_latest(self):
        r = HandReconciler()
        r.add(dict(street='preflop', stacks={}))
        r.add(dict(street='flop', stacks={}))
        self.assertEqual(r.street(), 'flop')


if __name__ == '__main__':
    unittest.main()
