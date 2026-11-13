"""Dealer button detection and position derivation (experimental, observation only).

The PPPoker dealer button is a small bright-green hexagon with a white "D",
placed next to the seat on the button. We find that hexagon by colour+size
(restricted to the felt area so the green action buttons at the bottom and the
corner icons are excluded) and map it to the nearest seat anchor. From the
button, positions follow the table's clockwise order using the RangeLab naming.

Validated on real gabaritos for the button-to-seat mapping (two dealer positions
so far: bot_left and right_up); other positions and the full-ring naming are
derived by the same rule but not yet each seen in a gabarito.
"""
import cv2
import numpy as np
from .seat_layout import SEAT_ANCHORS, CLOCKWISE

# RangeLab position names; with fewer players the earliest (UTG) seats drop,
# exactly as preflop_study.positions does, so the names match the range pack.
_CORE = ('UTG', 'UTG+1', 'UTG+2', 'LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB')


def find_dealer_badge(crop):
    """Return (cx, cy, w, h) of the green 'D' hexagon, or None. Felt area only."""
    h, w = crop.shape[:2]
    b, g, r = crop[:, :, 0].astype(int), crop[:, :, 1].astype(int), crop[:, :, 2].astype(int)
    green = ((g > 120) & (g > r + 40) & (g > b + 20)).astype(np.uint8) * 255
    mask = np.zeros_like(green)
    mask[int(0.10 * h):int(0.80 * h), int(0.03 * w):int(0.97 * w)] = 255
    green = cv2.bitwise_and(green, mask)
    best = None
    for contour in cv2.findContours(green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        if 14 < bw < 48 and 16 < bh < 50 and 0.6 < bw / bh < 1.3 and cv2.contourArea(contour) > 300:
            area = cv2.contourArea(contour)
            if best is None or area > best[0]:
                best = (area, x + bw // 2, y + bh // 2, bw, bh)
    return None if best is None else best[1:]


def find_dealer_seat(crop):
    """{seat, confidence, source, badge} for the dealer, or seat=None (abstain)."""
    badge = find_dealer_badge(crop)
    if badge is None:
        return dict(seat=None, confidence='abstain', source='template', badge=None)
    cx, cy, bw, bh = badge
    h, w = crop.shape[:2]
    seat = min(SEAT_ANCHORS, key=lambda s: (SEAT_ANCHORS[s][0] * w - cx) ** 2 + (SEAT_ANCHORS[s][1] * h - cy) ** 2)
    return dict(seat=seat, confidence='high', source='template', badge=[cx, cy, bw, bh])


def derive_positions(dealer_seat, occupied_seats):
    """Map occupied seats to RangeLab positions from the button, clockwise.

    occupied_seats: iterable of seat names that hold a player (must include the
    dealer). Returns {seat: position} or {} when it cannot be derived. For a full
    9-handed ring the canonical names are used; with fewer players BTN/SB/BB are
    named and the rest are labelled EP/MP by distance from the button."""
    seats = set(occupied_seats)
    if dealer_seat is not None:
        seats.add(dealer_seat)   # the button is always on a seated player
    occupied = [s for s in CLOCKWISE if s in seats]
    if dealer_seat not in occupied or not 2 <= len(occupied) <= 9:
        return {}
    i, n = occupied.index(dealer_seat), len(occupied)
    if n == 2:
        order, labels = occupied[i:] + occupied[:i], ('SB', 'BB')   # heads-up: dealer is SB
    else:
        order = occupied[i + 1:] + occupied[:i + 1]                 # dealer is last (BTN)
        labels = ('SB', 'BB') + _CORE[-n:-2]
    return dict(zip(order, labels))
