"""Reconcile the state trajectory within one hand from periodic snapshots.

Periodic sampling can miss actions between frames, so this never reconstructs the
exact fold/call/raise sequence. It reports only what the delta between two
consecutive snapshots of the SAME hand proves:

- street_advanced: the board grew (preflop -> flop -> turn -> river). Reliable.
- seat_committed: a seat's stack dropped, so it put that many chips in. Reliable
  magnitude, even if the exact action (call/bet/raise/blind) is unknown.
- pot_increased / pot_regressed: pot change; a drop flags a missed hand boundary.
- reconciled vs gap: whether the chips that left stacks match the pot+bets growth
  within tolerance. A gap means actions happened between frames that the numbers
  cannot fully explain; it is flagged, not invented.

Pure and framework-free. A HandTracker starts a fresh reconciler per hand.
"""

STREETS = ('preflop', 'flop', 'turn', 'river')
_BY_CARDS = {0: 'preflop', 3: 'flop', 4: 'turn', 5: 'river'}
_TOL = 0.2  # bb; OCR rounding and unread fields make exact conservation impossible


def street_from_board(n_cards):
    """Street name from the community card count, or None if not a known count."""
    return _BY_CARDS.get(n_cards)


def _num(value):
    return value if isinstance(value, (int, float)) else None


class HandReconciler:
    """Accumulates snapshots of one hand and reports evidence-backed events.

    A snapshot is a dict: {pot_bb, street, stacks:{seat:bb}, bets_bb (optional
    total of chips in front)}. Missing fields are tolerated (then that check is
    skipped), never guessed."""

    def __init__(self):
        self.snapshots = []
        self.events = []

    def add(self, snapshot):
        """Record one same-hand snapshot. Returns the list of events for this step."""
        step = []
        if self.snapshots:
            step = self._diff(self.snapshots[-1], snapshot)
        self.snapshots.append(snapshot)
        self.events.extend(step)
        return step

    def _diff(self, prev, curr):
        step = []
        ps, cs = prev.get('street'), curr.get('street')
        if ps in STREETS and cs in STREETS and STREETS.index(cs) > STREETS.index(ps):
            step.append(dict(event='street_advanced', **{'from': ps, 'to': cs}))

        pot_delta = None
        pp, cp = _num(prev.get('pot_bb')), _num(curr.get('pot_bb'))
        if pp is not None and cp is not None:
            pot_delta = round(cp - pp, 2)
            if pot_delta < -_TOL:
                step.append(dict(event='pot_regressed', delta=pot_delta))  # likely a missed hand boundary
            elif pot_delta > _TOL:
                step.append(dict(event='pot_increased', delta=pot_delta))

        committed = 0.0
        measured = False
        for seat, cur_bb in curr.get('stacks', {}).items():
            prev_bb, cur_bb = _num(prev.get('stacks', {}).get(seat)), _num(cur_bb)
            if prev_bb is not None and cur_bb is not None:
                measured = True
                drop = round(prev_bb - cur_bb, 2)
                if drop > _TOL:
                    committed += drop
                    step.append(dict(event='seat_committed', seat=seat, amount=drop))

        # Chip conservation: chips that left stacks should match pot + front-bet growth.
        pb, cb = _num(prev.get('bets_bb')), _num(curr.get('bets_bb'))
        if measured and pot_delta is not None and committed > _TOL:
            expected = pot_delta + ((cb - pb) if (pb is not None and cb is not None) else 0.0)
            status = 'reconciled' if abs(committed - expected) <= max(_TOL, 0.1 * committed) else 'gap'
            step.append(dict(event='reconciliation', status=status,
                             committed=round(committed, 2), expected=round(expected, 2)))
        return step

    def street(self):
        """The latest known street, or None."""
        for snap in reversed(self.snapshots):
            if snap.get('street') in STREETS:
                return snap['street']
        return None
