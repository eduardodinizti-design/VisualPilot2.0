"""Dealer button: badge->seat mapping and position derivation.

Synthetic green badge and pure position logic (lab-safe). The real button->seat
accuracy is validated live on gabaritos; these pin the geometry and naming."""
import unittest
import numpy as np

from table_reading import dealer_button, seat_layout


class BadgeTests(unittest.TestCase):
    def _crop_with_badge(self, fx, fy, w=750, h=1334):
        crop = np.zeros((h, w, 3), np.uint8)
        cx, cy = int(fx * w), int(fy * h)
        crop[cy - 16:cy + 16, cx - 15:cx + 15] = (40, 200, 40)  # bright green blob (BGR)
        return crop

    def test_badge_maps_to_nearest_seat(self):
        for seat, (fx, fy) in seat_layout.SEAT_ANCHORS.items():
            if fy > 0.80 or fy < 0.12:   # badge detector ignores the very top/bottom bands
                continue
            found = dealer_button.find_dealer_seat(self._crop_with_badge(fx, fy))
            self.assertEqual(found['seat'], seat)
            self.assertEqual(found['confidence'], 'high')

    def test_no_badge_abstains(self):
        found = dealer_button.find_dealer_seat(np.zeros((1334, 750, 3), np.uint8))
        self.assertIsNone(found['seat'])
        self.assertEqual(found['confidence'], 'abstain')


class PositionTests(unittest.TestCase):
    def test_full_ring_naming_from_button(self):
        # Mesa 9-max cheia (topo = top_left/top_right, sem top_center).
        occupied = [s for s in seat_layout.CLOCKWISE if s != 'top_center']
        pos = dealer_button.derive_positions('hero', occupied)
        self.assertEqual(pos['hero'], 'BTN')
        self.assertEqual(pos['bot_left'], 'SB')    # horário IMEDIATO após o BTN
        self.assertEqual(pos['left_low'], 'BB')
        self.assertEqual(pos['bot_right'], 'CO')   # último antes do botão
        self.assertEqual(len(pos), 9)

    def test_8max_ring_with_top_center(self):
        # Mesa 8-max PPPoker (topo = top_center; top_left/top_right vazios). O
        # top_center entra na ordem horária entre left_up e right_up.
        occupied = [s for s in seat_layout.CLOCKWISE if s not in ('top_left', 'top_right')]
        self.assertEqual(len(occupied), 8)
        self.assertIn('top_center', occupied)
        pos = dealer_button.derive_positions('hero', occupied)
        self.assertEqual(pos['hero'], 'BTN')
        self.assertEqual(pos['bot_left'], 'SB')
        self.assertEqual(pos['left_low'], 'BB')
        self.assertEqual(pos['bot_right'], 'CO')   # último antes do botão
        # left_up -> top_center -> right_up na ordem de ação
        order = [p for p in ('left_up', 'top_center', 'right_up')]
        idx = [list(seat_layout.CLOCKWISE).index(s) for s in order]
        self.assertEqual(idx, sorted(idx))
        self.assertEqual(len(pos), 8)

    def test_detected_button_is_added_to_occupancy(self):
        # The button is always on a seated player, so a dealer the occupancy
        # missed is still counted and positions derive.
        pos = dealer_button.derive_positions('hero', ['bot_right', 'right_low'])
        self.assertEqual(pos['hero'], 'BTN')
        self.assertEqual(len(pos), 3)

    def test_no_dealer_returns_empty(self):
        self.assertEqual(dealer_button.derive_positions(None, ['bot_right', 'right_low']), {})

    def test_short_ring_names_blinds(self):
        pos = dealer_button.derive_positions('hero', ['hero', 'bot_right', 'right_low'])
        self.assertEqual(pos, {'hero': 'BTN', 'right_low': 'SB', 'bot_right': 'BB'})


if __name__ == '__main__':
    unittest.main()
