"""Table-state reader: amount parsing, seat geometry, abstention.

Pure logic plus OCR-mocked reads (lab-safe). The 9/9 accuracy on a real gabarito
is validated live, not here; these tests pin the parsing rules and structure."""
import unittest
from unittest.mock import patch
import numpy as np

from table_reading import seat_layout, table_state


class ParseAmountTests(unittest.TestCase):
    def test_comma_is_high_confidence(self):
        self.assertEqual(table_state.parse_amount('buzZzylay 291,8 BB'), (291.8, 'high'))

    def test_dropped_comma_restored_as_one_decimal_medium(self):
        self.assertEqual(table_state.parse_amount('pp108ae | 1431BB'), (143.1, 'medium'))
        self.assertEqual(table_state.parse_amount('Mr.Tomate 1229BR'), (122.9, 'medium'))

    def test_pot_with_dropped_comma(self):
        self.assertEqual(table_state.parse_amount('Pot: 257 BB'), (25.7, 'medium'))

    def test_comma_rendered_as_space(self):
        # Evolution skin: "35,5 BB" read as "35 5BR"
        self.assertEqual(table_state.parse_amount('Just do it 35 5BR'), (35.5, 'medium'))

    def test_unreadable_abstains(self):
        self.assertEqual(table_state.parse_amount(''), (None, 'abstain'))
        self.assertEqual(table_state.parse_amount('----'), (None, 'abstain'))

    def test_five_digit_run_is_noise_and_abstains(self):
        # "15,3" misread as "15232": abstain rather than invent 1523.2
        self.assertEqual(table_state.parse_amount('AlfaCentau 15232BB'), (None, 'abstain'))

    def test_letter_glued_digits_are_rejected_not_misread(self):
        # A bet chip / stats grid overlapping a nameplate yields garbage where the
        # digit run is glued to a letter ("alecaixeta R20RB"). Reading that as 2.0
        # is a dangerous misread, so abstain; a space-separated stack still reads.
        self.assertEqual(table_state.parse_amount('alecaixeta R20RB'), (None, 'abstain'))
        self.assertEqual(table_state.parse_amount('alecaixeta 830 BB'), (83.0, 'medium'))


class SeatLayoutTests(unittest.TestCase):
    def test_ten_unique_seats_hero_first(self):
        # 10 âncoras = 8 fixas + os dois topos possíveis (top_center 8-max XOR
        # top_left/top_right 9-max); nunca todas ocupadas juntas numa mesa real.
        self.assertEqual(len(seat_layout.SEAT_ANCHORS), 10)
        self.assertEqual(set(seat_layout.CLOCKWISE), set(seat_layout.SEAT_ANCHORS))
        self.assertEqual(seat_layout.CLOCKWISE[0], 'hero')

    def test_nameplate_box_within_bounds_and_centered(self):
        x0, y0, x1, y1 = seat_layout.nameplate_box(750, 1334, 'hero')
        self.assertTrue(0 <= x0 < x1 <= 750 and 0 <= y0 < y1 <= 1334)
        self.assertAlmostEqual((x0 + x1) / 2, 375, delta=2)   # hero fx=0.50
        self.assertAlmostEqual((y0 + y1) / 2, int(0.90 * 1334), delta=2)


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.crop = np.zeros((1334, 750, 3), np.uint8)

    def test_read_seat_stacks_covers_all_seats(self):
        with patch('table_reading.table_state.image_to_string', return_value='Hero 63,1 BB'):
            seats = table_state.read_seat_stacks(self.crop)
        self.assertEqual(set(seats), set(seat_layout.SEAT_ANCHORS))
        self.assertTrue(all(s['stack_bb'] == 63.1 for s in seats.values()))

    def test_unreadable_stack_abstains(self):
        with patch('table_reading.table_state.image_to_string', return_value=''):
            seats = table_state.read_seat_stacks(self.crop)
        self.assertTrue(all(s['stack_bb'] is None for s in seats.values()))

    def test_table_state_structure_is_labelled(self):
        with patch('table_reading.table_state.image_to_string', return_value=''):
            state = table_state.read_table_state(self.crop)
        self.assertTrue(state['experimental'])
        self.assertEqual(len(state['seats']), 10)
        self.assertIn('pot_bb', state['pot'])
        self.assertIn('seat', state['dealer'])
        self.assertEqual(state['positions'], {})  # no dealer badge -> no positions
        self.assertIn('to_call_bb', state['to_call'])
        self.assertEqual(state['bets'], [])  # blank crop: no chips, no bets

    def test_bad_crop_rejected(self):
        with self.assertRaises(ValueError):
            table_state.read_table_state(np.zeros((10, 10), np.uint8))


class ToCallTests(unittest.TestCase):
    def setUp(self):
        self.crop = np.zeros((1334, 750, 3), np.uint8)

    def test_call_amount_is_to_call(self):
        with patch('table_reading.action_buttons.read_action_buttons',
                   return_value={'buttons': [{'action': 'CALL', 'amount': '3.2', 'unit': 'BB', 'label': 'Call 3,2 BB'}]}):
            self.assertEqual(table_state.read_to_call(self.crop)['to_call_bb'], 3.2)

    def test_call_without_bb_unit_abstains(self):
        # An amount with no confirmed BB unit could be chips; do not read it as BB.
        with patch('table_reading.action_buttons.read_action_buttons',
                   return_value={'buttons': [{'action': 'CALL', 'amount': '100', 'unit': None, 'label': 'Call 100'}]}):
            r = table_state.read_to_call(self.crop)
            self.assertIsNone(r['to_call_bb'])
            self.assertEqual(r['confidence'], 'abstain')

    def test_check_means_zero_to_call(self):
        with patch('table_reading.action_buttons.read_action_buttons',
                   return_value={'buttons': [{'action': 'CHECK', 'amount': None}]}):
            tc = table_state.read_to_call(self.crop)
            self.assertEqual(tc['to_call_bb'], 0.0)

    def test_no_button_row_abstains(self):
        with patch('table_reading.action_buttons.read_action_buttons', return_value={'buttons': []}):
            tc = table_state.read_to_call(self.crop)
            self.assertIsNone(tc['to_call_bb'])
            self.assertEqual(tc['confidence'], 'abstain')


class OccupancyTests(unittest.TestCase):
    def test_blue_felt_seat_is_empty_avatar_photo_is_occupied(self):
        felt = np.zeros((1334, 750, 3), np.uint8); felt[:] = (200, 90, 40)   # blue felt (BGR)
        occ = table_state.read_occupancy(felt)
        self.assertTrue(all(not s['occupied'] for s in occ.values()))
        # a non-blue textured avatar over every seat -> occupied
        photo = felt.copy()
        for seat in seat_layout.SEAT_ANCHORS:
            x0, y0, x1, y1 = seat_layout.nameplate_box(750, 1334, seat)
            photo[y0:y1, x0:x1] = np.random.randint(0, 255, (y1 - y0, x1 - x0, 3), np.uint8)
        occ2 = table_state.read_occupancy(photo)
        self.assertTrue(all(s['occupied'] for s in occ2.values()))

    def test_stacks_and_occupancy_are_independent(self):
        crop = np.zeros((1334, 750, 3), np.uint8); crop[:] = (200, 90, 40)
        for seat in seat_layout.SEAT_ANCHORS:
            x0, y0, x1, y1 = seat_layout.nameplate_box(750, 1334, seat)
            crop[y0:y1, x0:x1] = np.random.randint(0, 255, (y1 - y0, x1 - x0, 3), np.uint8)
        with patch('table_reading.table_state.image_to_string', return_value=''):
            state = table_state.read_table_state(crop)
        self.assertTrue(all(s['occupied'] and s['stack_bb'] is None for s in state['seats'].values()))


if __name__ == '__main__':
    unittest.main()
