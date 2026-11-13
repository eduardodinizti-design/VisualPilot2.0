"""Temporal identity: link frames to the right table and hand over time.

Two pieces, kept separate so the tracker is testable without OCR:

- read_hand_id(crop): reads the on-table hand ID (e.g.
  "ID: 261108055446-14126629-0000426-8"); the third segment is the hand number,
  which increases every hand, so it detects a new hand exactly instead of
  guessing from stack changes. A covered/animated ID reads as abstain.

- HandTracker: pure, framework-free. Fed (table_id, hand_number, ...) per frame
  it reports new_table / new_hand / same_hand / pending_id, keeps the current
  hand's frame count and last observation, and never switches hands on an
  unreadable or a regressing (misread) id. Periodic sampling can miss actions
  between frames, so this tracks hand identity and state, not every action.
"""
import re
from collections import deque

import cv2

from .ocr_runtime import image_to_string

# Full id, and a fallback for the hand number (7-ish digits) before the final seat digit.
_HAND_ID = re.compile(r'(\d{6,})-(\d{4,})-(\d{3,8})-(\d+)')
# O nº da mão é o penúltimo segmento (antes do assento). Ancorar no par
# nº-assento e pegar o da DIREITA evita capturar um trecho do timestamp/tableref.
_HAND_NUM = re.compile(r'(\d{3,7})-(\d{1,2})(?!\d)')


def read_hand_id(crop):
    """{hand_id, table_ref, hand_number, confidence, raw}. hand_number is the key
    temporal signal; hand_id/table_ref come only from a clean full read."""
    h, w = crop.shape[:2]
    # The ID line sits at different heights per skin: NVT ~0.665, Evolution
    # (Karekas/Veneza) ~0.72. Try each band with psm 7; the first full match wins,
    # so NVT keeps reading exactly as before and the lower skin is also covered.
    raws, partial_hit = [], None
    for y0, y1 in ((0.645, 0.685), (0.70, 0.74)):
        region = crop[int(y0 * h):int(y1 * h), int(0.22 * w):int(0.78 * w)]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        raw = ' '.join(image_to_string(gray, config='--psm 7').split())
        raws.append(raw)
        compact = raw.replace(' ', '')
        full = _HAND_ID.search(compact)
        if full:
            return dict(hand_id=full.group(0), table_ref='%s-%s' % (full.group(1), full.group(2)),
                        hand_number=int(full.group(3)), confidence='high', raw=raw)
        matches = _HAND_NUM.findall(compact)
        if matches and partial_hit is None:
            partial_hit = (int(matches[-1][0]), raw)   # o par mais à direita = nº-assento
    if partial_hit:
        return dict(hand_id=None, table_ref=None, hand_number=partial_hit[0],
                    confidence='medium', raw=partial_hit[1])
    return dict(hand_id=None, table_ref=None, hand_number=None, confidence='abstain', raw=' | '.join(raws))


class HandTracker:
    """Links frames to tables and hands over time. One instance per observer."""

    def __init__(self, max_history=50, max_jump=100000):
        self._max_history = max_history
        self._max_jump = max_jump   # salto p/ frente implausível = misread (nº ~+1/mão)
        self.tables = {}

    def _state(self, table_id):
        if table_id not in self.tables:
            self.tables[table_id] = dict(hand_id=None, hand_number=None, frames=0,
                                         last_obs=None, history=deque(maxlen=self._max_history), seen=False)
        return self.tables[table_id]

    def observe(self, table_id, hand_number, hand_id=None, observation=None):
        """Record one frame. Returns an event dict:
        event in {new_table, new_hand, same_hand, pending_id, suspect_id}."""
        state = self._state(table_id)
        new_table = not state['seen']
        state['seen'] = True

        if hand_number is None:                      # id unreadable this frame
            state['frames'] += 1
            if observation is not None:
                state['last_obs'] = observation
            return self._event('new_table' if new_table and state['hand_number'] is None else 'pending_id',
                               table_id, state)

        if state['hand_number'] is not None and hand_number < state['hand_number']:
            return self._event('suspect_id', table_id, state, reported=hand_number)  # ids only grow
        if (state['hand_number'] is not None
                and hand_number > state['hand_number'] + self._max_jump):
            # Salto absurdo p/ frente (ex.: trecho do timestamp lido como nº da mão)
            # = misread; NÃO adotar como nova mão, senão envenena o rastreamento.
            return self._event('suspect_id', table_id, state, reported=hand_number)

        if state['hand_number'] is None or hand_number != state['hand_number']:
            previous = dict(hand_number=state['hand_number'], frames=state['frames'])
            if state['hand_number'] is not None:
                state['history'].append(previous)
            state.update(hand_id=hand_id, hand_number=hand_number, frames=1,
                         last_obs=observation if observation is not None else state['last_obs'])
            event = 'new_table' if new_table else 'new_hand'
            return self._event(event, table_id, state, previous=previous)

        state['frames'] += 1
        if hand_id and not state['hand_id']:
            state['hand_id'] = hand_id
        if observation is not None:
            state['last_obs'] = observation
        return self._event('same_hand', table_id, state)

    def _event(self, event, table_id, state, **extra):
        return dict(event=event, table_id=table_id, hand_id=state['hand_id'],
                    hand_number=state['hand_number'], frame=state['frames'], **extra)

    def current(self, table_id):
        """The current hand state for a table, or None if unseen."""
        return self.tables.get(table_id)
