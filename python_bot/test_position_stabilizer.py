"""Estabilizador de posições: ignora blips de 1 frame (ocupação e dealer) e só
troca de epoch quando o botão do dealer persiste (mão nova)."""
import unittest

from position_stabilizer import PositionStabilizer
from table_reading.dealer_button import derive_positions
from table_reading.seat_layout import CLOCKWISE

FULL = [s for s in CLOCKWISE if s != 'top_center']   # 9-max cheio (topo = top_left/top_right)
DEALER = 'hero'


def raw(dealer, occ):
    return derive_positions(dealer, occ)


class PositionStabilizerTest(unittest.TestCase):
    def feed(self, stab, n, dealer, occ, key='t', hand=None):
        out = None
        for _ in range(n):
            out = stab.update(table_key=key, dealer_seat=dealer, occupied_seats=occ, hand_key=hand)
        return out

    def test_steady_state_matches_raw(self):
        stab = PositionStabilizer()
        d, pos = self.feed(stab, 4, DEALER, FULL)
        self.assertEqual(d, DEALER)
        self.assertEqual(pos, raw(DEALER, FULL))

    def test_single_frame_occupancy_blip_is_ignored(self):
        stab = PositionStabilizer()
        self.feed(stab, 4, DEALER, FULL)
        blip = [s for s in FULL if s != 'top_left']          # cai 1 assento (não-dealer)
        self.assertNotEqual(raw(DEALER, blip), raw(DEALER, FULL))   # o cru MUDARIA
        d, pos = stab.update(table_key='t', dealer_seat=DEALER, occupied_seats=blip)
        self.assertEqual(pos, raw(DEALER, FULL))             # estabilizado = maioria
        self.assertNotIn(pos, (raw(DEALER, blip),))

    def test_same_hand_dealer_blip_is_held(self):
        # dentro da MESMA mão (hand_key estável) um blip de dealer é misread -> segura
        stab = PositionStabilizer()
        self.feed(stab, 4, DEALER, FULL, hand='H1')
        d, pos = stab.update(table_key='t', dealer_seat='top_right', occupied_seats=FULL, hand_key='H1')
        self.assertEqual(d, DEALER)
        self.assertEqual(pos, raw(DEALER, FULL))

    def test_unknown_hand_dealer_conflict_is_pending(self):
        # sem info de mão, conflito não confirmado NÃO emite a posição antiga
        stab = PositionStabilizer()
        self.feed(stab, 4, DEALER, FULL)
        d, pos = stab.update(table_key='t', dealer_seat='top_right', occupied_seats=FULL)
        self.assertEqual(pos, {})                            # pendente -> abstém
        self.assertEqual(d, DEALER)

    def test_persistent_dealer_move_starts_new_epoch(self):
        stab = PositionStabilizer(debounce=2)
        self.feed(stab, 4, DEALER, FULL)
        stab.update(table_key='t', dealer_seat='bot_left', occupied_seats=FULL)   # pendente
        d, pos = stab.update(table_key='t', dealer_seat='bot_left', occupied_seats=FULL)
        self.assertEqual(d, 'bot_left')
        self.assertEqual(pos, raw('bot_left', FULL))

    def test_new_hand_switches_immediately_no_debounce(self):
        stab = PositionStabilizer()
        self.feed(stab, 4, DEALER, FULL, hand='H1')
        # mão nova com novo dealer -> adota JÁ no 1º frame (sem debounce)
        d, pos = stab.update(table_key='t', dealer_seat='bot_left', occupied_seats=FULL, hand_key='H2')
        self.assertEqual(d, 'bot_left')
        self.assertEqual(pos, raw('bot_left', FULL))

    def test_new_hand_does_not_inherit_previous_position(self):
        # #7: mão A com dealer D1; mão B (nova) com dealer D2 -> 1º frame da mão B
        # emite a posição NOVA, nunca a herdada da mão A.
        stab = PositionStabilizer()
        self.feed(stab, 4, 'hero', FULL, hand='A')           # hero = BTN nesta config
        old = raw('hero', FULL)
        d, pos = stab.update(table_key='t', dealer_seat='bot_left', occupied_seats=FULL, hand_key='B')
        self.assertEqual(pos, raw('bot_left', FULL))
        self.assertNotEqual(pos['hero'], old['hero'])        # rótulo do hero mudou

    def test_no_dealer_yet_returns_empty(self):
        stab = PositionStabilizer()
        d, pos = stab.update(table_key='t', dealer_seat=None, occupied_seats=FULL)
        self.assertIsNone(d)
        self.assertEqual(pos, {})

    def test_recovers_locked_dealer_when_badge_missing(self):
        stab = PositionStabilizer()
        self.feed(stab, 3, DEALER, FULL)
        d, pos = stab.update(table_key='t', dealer_seat=None, occupied_seats=FULL)
        self.assertEqual(d, DEALER)                          # mantém o travado
        self.assertEqual(pos, raw(DEALER, FULL))

    def test_tables_are_independent(self):
        stab = PositionStabilizer()
        self.feed(stab, 3, 'hero', FULL, key='A')
        self.feed(stab, 3, 'bot_left', FULL, key='B')
        _, pa = stab.update(table_key='A', dealer_seat='hero', occupied_seats=FULL)
        _, pb = stab.update(table_key='B', dealer_seat='bot_left', occupied_seats=FULL)
        self.assertEqual(pa, raw('hero', FULL))
        self.assertEqual(pb, raw('bot_left', FULL))


if __name__ == '__main__':
    unittest.main()
