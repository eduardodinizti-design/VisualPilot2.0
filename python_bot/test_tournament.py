"""Tournament phase: parsing the on-table info and mapping to an ICM stage."""
import unittest
from unittest.mock import patch
import numpy as np

from table_reading import tournament
from table_reading.tournament import tournament_stage, tournament_context, is_pko, is_mystery


class StageTests(unittest.TestCase):
    def test_stages_from_remaining_and_paid(self):
        self.assertEqual(tournament_stage(8, 20), 'ft')          # final table
        self.assertEqual(tournament_stage(22, 20), 'bubble')     # just above the money
        self.assertEqual(tournament_stage(30, 20), 'pre_itm')    # approaching
        self.assertEqual(tournament_stage(55, 20), 'far')        # deep, chip EV
        self.assertIsNone(tournament_stage(15, 20))              # in the money, pre-FT: no pack stage
        self.assertIsNone(tournament_stage(None, 20))

    def test_context_maps_mode(self):
        self.assertEqual(tournament_context(dict(players_left=22, paid=20)), ('icm', 'bubble'))
        self.assertEqual(tournament_context(dict(players_left=55, paid=20)), ('chip_ev', 'mid'))
        self.assertEqual(tournament_context(dict(players_left=None, paid=None)), ('chip_ev', 'mid'))

    def test_bounty_detection(self):
        self.assertFalse(is_pko('MINI FREEZE'))
        self.assertTrue(is_pko('OMAHA 5 PKO'))
        self.assertFalse(is_mystery('OMAHA 5 PKO'))
        self.assertTrue(is_mystery('BOX MISTERY'))
        self.assertTrue(is_mystery('MYSTERY BOUNTY'))
        self.assertFalse(is_pko('BOX MISTERY'))   # mystery is not a regular PKO

    def test_context_pko_vs_mystery_timing(self):
        self.assertEqual(tournament_context(dict(players_left=55, paid=20, is_pko=True)), ('pko', 'mid'))
        self.assertEqual(tournament_context(dict(players_left=22, paid=20, is_pko=True)), ('pko_icm', 'bubble'))
        # mystery is vanilla until the money
        self.assertEqual(tournament_context(dict(players_left=55, paid=20, is_mystery=True)), ('chip_ev', 'mid'))
        self.assertEqual(tournament_context(dict(players_left=22, paid=20, is_mystery=True)), ('icm', 'bubble'))
        # mystery in the money: bounty active
        self.assertEqual(tournament_context(dict(players_left=8, paid=20, is_mystery=True)), ('pko_icm', 'ft'))


class ReadTests(unittest.TestCase):
    def _read(self, text):
        with patch('table_reading.tournament.image_to_string', return_value=text):
            return tournament.read_tournament(np.zeros((1334, 750, 3), np.uint8))

    def test_reads_paid_and_remaining(self):
        r = self._read('MINI FREEZE Blinds: 600/1,200(200) Lugares pagos: 20 Minha posigao: 40/55')
        self.assertEqual((r['paid'], r['players_left'], r['hero_rank']), (20, 55, 40))
        self.assertEqual(r['confidence'], 'high')

    def test_final_table_engages_without_paid_in_the_money(self):
        # In the money the table shows "Premio atual" instead of "Lugares pagos",
        # so paid stops reading. The final table is still knowable from the seats,
        # and the prize line flags in-the-money (so a Mystery KO's bounty counts).
        r = self._read('KOMBAT MISTERY Blinds: 20K/40K(5,000) Premio atual: 27.85 Minha posicao: 3/8')
        self.assertTrue(r['in_money'])
        self.assertIsNone(r['paid'])
        self.assertEqual(r['players_left'], 8)
        self.assertEqual(tournament.tournament_context(r), ('pko_icm', 'ft'))

    def test_deep_itm_without_paid_stays_chip_ev(self):
        # Deep in the money, far from the final table, no paid: chip EV (low ICM
        # pressure), but the bounty still activates for a Mystery KO.
        r = self._read('CRAZY REBUY ... Premio atual: 27.85 Minha posicao: 10/22')
        self.assertTrue(r['in_money'])
        self.assertEqual(tournament.tournament_context(r), ('chip_ev', 'mid'))

    def test_reads_paid_through_noise_keeps_icm_engaged(self):
        # On the bubble, paid dropping to None would fall back to chip_ev; tolerate
        # OCR noise between "pagos" and the number so the ICM stage stays engaged.
        r = self._read('CRAZY REBUY ... Lugares pagos:. 35 Minha posig&o: 7/36')
        self.assertEqual((r['paid'], r['players_left']), (35, 36))

    def test_reads_remaining_through_cedilla_noise(self):
        # Evolution OCR mangles "posicao" to "posig&o"; the rank/left must still
        # read, and the blinds' own slash ("5,000/10K") must not be matched.
        r = self._read('CRAZY REBUY Blinds: 5,000/10K(1,500) Lugares pagos: 35 Minha posig&o: 23/60')
        self.assertEqual((r['paid'], r['players_left'], r['hero_rank']), (35, 60, 23))

    def test_unread_abstains(self):
        r = self._read('MINI FREEZE Blinds: 600/1,200')
        self.assertIsNone(r['players_left'])
        self.assertEqual(r['confidence'], 'abstain')


if __name__ == '__main__':
    unittest.main()
