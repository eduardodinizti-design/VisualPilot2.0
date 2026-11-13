"""Offline preflop state and source-backed study. No capture or system input."""
import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


POSITIONS = ('UTG', 'UTG+1', 'UTG+2', 'LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB')
RANKS = 'AKQJT98765432'


class Blocked(ValueError):
    pass


def amount(value):
    if value is None or isinstance(value, bool):
        raise Blocked('AMOUNT_UNKNOWN')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise Blocked('INVALID_AMOUNT') from exc
    if not result.is_finite() or result < 0:
        raise Blocked('INVALID_AMOUNT')
    return result


def hand_key(cards):
    if not isinstance(cards, list) or len(cards) != 2 or any(
        not isinstance(c, str) or not re.fullmatch(r'[AKQJT2-9][cdhs]', c) for c in cards
    ) or cards[0] == cards[1]:
        raise Blocked('HERO_CARDS_UNKNOWN_OR_INVALID')
    a, b = sorted(cards, key=lambda c: RANKS.index(c[0]))
    return a[0] + b[0] + ('' if a[0] == b[0] else 's' if a[1] == b[1] else 'o')


def positions(seats, dealer):
    """Seat numbers increase clockwise; empty seats are omitted, never folded seats."""
    if len(seats) != len(set(seats)) or not 2 <= len(seats) <= 9:
        raise Blocked('PARTICIPANTS_UNKNOWN_OR_INVALID')
    if any(type(s) is not int or not 0 <= s <= 8 for s in seats) or type(dealer) is not int or dealer not in seats:
        raise Blocked('DEALER_OR_SEATS_INVALID')
    clockwise = sorted(seats)
    i = clockwise.index(dealer)
    # SB and BB follow dealer; heads-up dealer is SB and acts first preflop.
    order = (clockwise[i:] + clockwise[:i]) if len(seats) == 2 else (clockwise[i+1:] + clockwise[:i+1])
    labels = ('SB', 'BB') if len(seats) == 2 else ('SB', 'BB') + POSITIONS[-len(seats):-2]
    return dict(zip(order, labels))


def reconstruct(scene):
    """Replay a complete supplied preflop history, reconcile observed chips and turn.

    This initial contract accepts simulation evidence only. Confirming a field here
    is a fixture assertion, not an OCR confidence or Windows validation claim.
    """
    if scene.get('evidence') != 'SIMULATION':
        raise Blocked('LIVE_STATE_RECOGNITION_NOT_VALIDATED')
    required = {'participants', 'dealer', 'stacks', 'pot', 'bets', 'history', 'turn', 'hero', 'board'}
    if not required.issubset(set(scene.get('confirmed_fields', []))):
        raise Blocked('UNCONFIRMED_FIELDS')
    if scene.get('history_complete') is not True:
        raise Blocked('INCOMPLETE_ACTION_HISTORY')
    for k in ('source_key', 'table_id', 'snapshot_id', 'hand_id'):
        if not isinstance(scene.get(k), str) or not scene[k]:
            raise Blocked('MISSING_IDENTITY:' + k)
    if scene.get('street') != 'preflop' or scene.get('board') != []:
        raise Blocked('NOT_UNOPENED_PREFLOP')
    key = hand_key(scene.get('hero_cards'))
    players = scene.get('players')
    if not isinstance(players, list) or not all(isinstance(p, dict) for p in players):
        raise Blocked('PARTICIPANTS_UNKNOWN_OR_INVALID')
    seats = [p.get('seat') for p in players]
    pos = positions(seats, scene.get('dealer_seat'))
    hero = scene.get('hero_seat')
    if type(hero) is not int or hero not in pos:
        raise Blocked('HERO_UNKNOWN')
    start = {p['seat']: amount(p.get('start_stack_bb')) for p in players}
    if any(v <= 0 for v in start.values()):
        raise Blocked('INVALID_START_STACK')
    stacks = dict(start)
    bets = {s: Decimal(0) for s in seats}
    folded = set()
    posted = set()
    forced = []
    pot = Decimal(0)
    high = Decimal(0)
    opened = False
    voluntary_started = False
    order = sorted(seats, key=lambda s: POSITIONS.index(pos[s]))
    pending = list(order)
    min_raise = Decimal(1)
    history = scene.get('actions')
    if not isinstance(history, list):
        raise Blocked('INCOMPLETE_ACTION_HISTORY')
    for index, event in enumerate(history):
        if not isinstance(event, dict) or event.get('seq') != index + 1:
            raise Blocked('ACTION_SEQUENCE_GAP')
        s, action = event.get('seat'), event.get('type')
        if type(s) is not int or s not in pos or s in folded:
            raise Blocked('INVALID_ACTION_PARTICIPANT')
        # Every amount is the additional chips paid, never a raise-to total.
        paid = amount(event.get('amount_bb'))
        if action in ('post_sb', 'post_bb', 'post_ante'):
            if voluntary_started or (s, action) in posted or paid <= 0:
                raise Blocked('INVALID_FORCED_BET')
            if action == 'post_sb' and (pos[s] != 'SB' or paid != Decimal('.5')):
                raise Blocked('UNSUPPORTED_BLIND_STRUCTURE')
            if action == 'post_bb' and (pos[s] != 'BB' or paid != 1):
                raise Blocked('UNSUPPORTED_BLIND_STRUCTURE')
            posted.add((s, action))
            forced.append({'position': pos[s], 'type': action, 'amount': float(paid)})
        else:
            voluntary_started = True
            if not {('SB', 'post_sb'), ('BB', 'post_bb')}.issubset({(pos[x], a) for x, a in posted}):
                raise Blocked('BLINDS_MISSING')
            pending = [x for x in pending if x not in folded and stacks[x] > 0]
            if not pending or pending[0] != s:
                raise Blocked('ACTION_OUT_OF_TURN')
            pending.pop(0)
            owed = max(Decimal(0), high - bets[s])
            if action == 'fold':
                if paid:
                    raise Blocked('FOLD_WITH_PAYMENT')
                folded.add(s)
            elif action == 'check':
                if owed or paid:
                    raise Blocked('ILLEGAL_CHECK')
            elif action == 'call':
                if owed <= 0 or paid != min(owed, stacks[s]):
                    raise Blocked('CALL_AMOUNT_MISMATCH')
                opened = True  # Includes a limp: the pot is no longer unopened.
            elif action == 'raise':
                target = bets[s] + paid
                if target <= high or target - high < min_raise:
                    raise Blocked('UNSUPPORTED_OR_INVALID_RAISE')
                min_raise = target - high
                clockwise_order = order[order.index(s)+1:] + order[:order.index(s)]
                pending = [x for x in clockwise_order if x not in folded and stacks[x] > 0]
                opened = True
            else:
                raise Blocked('UNSUPPORTED_ACTION')
        if paid > stacks[s]:
            raise Blocked('STACK_OVERDRAW')
        stacks[s] -= paid
        pot += paid
        if action != 'post_ante':
            bets[s] += paid
            high = max(high, bets[s])
    if not {('SB', 'post_sb'), ('BB', 'post_bb')}.issubset({(pos[x], a) for x, a in posted}):
        raise Blocked('BLINDS_MISSING')
    pending = [x for x in pending if x not in folded and stacks[x] > 0]
    active = [s for s in seats if s not in folded]
    if len(active) < 2 or not pending or pending[0] != hero or scene.get('turn_seat') != hero:
        raise Blocked('NOT_HERO_TURN')
    for p in players:
        s = p['seat']
        if amount(p.get('stack_bb')) != stacks[s] or amount(p.get('bet_bb')) != bets[s]:
            raise Blocked('STACK_OR_BET_MISMATCH')
        if type(p.get('in_hand')) is not bool or p['in_hand'] != (s not in folded):
            raise Blocked('PARTICIPANT_STATE_MISMATCH')
    owed = min(stacks[hero], max(Decimal(0), high - bets[hero]))
    if amount(scene.get('pot_bb')) != pot or amount(scene.get('to_call_bb')) != owed:
        raise Blocked('POT_OR_CALL_MISMATCH')
    return dict(positions=pos, hero_position=pos[hero], hand_key=key,
                start_stacks={pos[s]: float(start[s]) for s in seats},
                stack_bb=float(stacks[hero]), pot_bb=float(pot), to_call_bb=float(owed),
                unopened=not opened, forced=forced, next_actor=hero,
                chip_conservation=sum(stacks.values()) + pot == sum(start.values()))


class RangeBook:
    """Strict exact-context lookup; no grading, nearest-stack fallback or sizing."""
    def __init__(self, path):
        raw = Path(path).read_bytes()
        b = json.loads(raw)
        if b.get('format') != 'nvt-range-export' or b.get('version') != 1:
            raise Blocked('UNSUPPORTED_RANGE_FORMAT')
        self.hands = b['hands']
        canonical = {r+r for r in RANKS}
        canonical |= {a+b+s for i,a in enumerate(RANKS) for b in RANKS[i+1:] for s in ('s','o')}
        if len(self.hands) != 169 or set(self.hands) != canonical:
            raise Blocked('INVALID_HAND_INDEX')
        self.provenance = dict(sha256=hashlib.sha256(raw).hexdigest(),
                               engine_commit=b.get('engineCommit'), generated_at=b.get('generatedAt'))
        self.nodes = [n for n in b['nodes'] if n.get('validated') is True]
        if len({n['id'] for n in self.nodes}) != len(self.nodes):
            raise Blocked('DUPLICATE_NODE_ID')

    def consult(self, scene, state):
        if not state['unopened']:
            raise Blocked('POT_ALREADY_OPENED')
        ctx = scene.get('strategy_context')
        if not isinstance(ctx, dict) or set(ctx) != {'mode', 'format', 'stage', 'players', 'stack'}:
            raise Blocked('STRATEGY_CONTEXT_UNKNOWN')
        # ICM/PKO need tournament inputs and independent validation beyond this block.
        if ctx['mode'] != 'chip_ev' or ctx['format'] != 'regular' or ctx['stage'] != 'mid':
            raise Blocked('CONTEXT_NOT_SUPPORTED_IN_INITIAL_STUDY')
        if ctx['players'] != len(scene['players']) or amount(ctx['stack']) != amount(state['start_stacks'][state['hero_position']]):
            raise Blocked('STRATEGY_CONTEXT_MISMATCH')
        candidates = [n for n in self.nodes if n['context'] == ctx and n['spot'] == 'open_raise'
                      and n['hero'] == state['hero_position'] and n['vs'] == [] and not n.get('spread')]
        if len(candidates) != 1:
            raise Blocked('NO_UNIQUE_VALIDATED_NODE')
        n = candidates[0]
        # Use only the exported controlled scenario, not arbitrary real stacks.
        expected = n['table']
        if set(expected['stacks']) != set(state['start_stacks']) or any(
            amount(v) != amount(state['start_stacks'][p]) for p,v in expected['stacks'].items()
        ) or expected['actions'] != state['forced'] or amount(expected['potBb']) != amount(state['pot_bb']):
            raise Blocked('EXPORTED_SCENARIO_MISMATCH')
        i = self.hands.index(state['hand_key'])
        if i in n.get('outOfRange', []):
            raise Blocked('HAND_OUT_OF_RANGE')
        mix, ev = [], {}
        actions = n['actions']
        if not actions or len(set(actions)) != len(actions):
            raise Blocked('INVALID_SOURCE_ACTIONS')
        for act in actions:
            if act not in n['legalActions'] or len(n['freq'][act]) != 169:
                raise Blocked('INVALID_SOURCE_ACTIONS')
            freq = n['freq'][act][i]
            if type(freq) not in (int, float) or not math.isfinite(freq) or not 0 <= freq <= 1:
                raise Blocked('INVALID_SOURCE_FREQUENCY')
            if freq > 0:
                mix.append(dict(action=act, frequency=freq))
            values = (n.get('ev') or {}).get(act)
            v = values[i] if values is not None and len(values) == 169 else None
            if v is not None and (type(v) not in (int,float) or not math.isfinite(v)):
                raise Blocked('INVALID_SOURCE_EV')
            ev[act] = None if act != 'fold' and freq == 0 and v == 0 else v
        if abs(sum(m['frequency'] for m in mix)-1) > .002:
            raise Blocked('INVALID_SOURCE_MIX_SUM')
        return dict(status='STUDY_ONLY', node_id=n['id'], source=n['source'],
                    source_validated=True, independently_validated=False,
                    provenance=self.provenance, mix=mix, ev=ev, ev_unit=n['evUnit'],
                    sizing=None, execution_allowed=False,
                    execution_blockers=['SIMULATION_ONLY', 'STRATEGY_NOT_INDEPENDENTLY_VALIDATED',
                                        'STRATEGIC_SIZING_NOT_EXPORTED'])


def study_tables(scenes, book):
    """No persistent table/hand cache; one result per supplied independent snapshot."""
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 6:
        raise Blocked('TABLE_LIMIT_1_TO_6')
    if any(not isinstance(s, dict) for s in scenes):
        raise Blocked('INVALID_TABLE_SNAPSHOT')
    identities = [(s.get('source_key'), s.get('table_id')) for s in scenes]
    if any(not isinstance(v, str) or not v for identity in identities for v in identity):
        raise Blocked('INVALID_TABLE_IDENTITY')
    if len(set(identities)) != len(identities):
        raise Blocked('DUPLICATE_TABLE_IDENTITY')
    output = []
    for scene in scenes:
        row = {k:scene.get(k) for k in ('source_key','table_id','snapshot_id','hand_id')}
        row.update(execution_allowed=False, evidence='SIMULATION')
        try:
            row['state'] = reconstruct(scene)
            row['strategy'] = book.consult(scene, row['state'])
            row['status'] = 'STUDY_ONLY'
        except (Blocked, KeyError, TypeError, IndexError, AttributeError) as exc:
            row.update(status='ABSTAIN', reason=str(exc), strategy=None)
        output.append(row)
    return output


def exported_example(book, node_id, cards):
    """Build an explicitly fictional observation from one exact exported 9-max node."""
    nodes = [n for n in book.nodes if n['id'] == node_id and n['spot'] == 'open_raise'
             and n['context']['players'] == 9 and not n['vs']]
    if len(nodes) != 1:
        raise Blocked('EXAMPLE_NODE_UNAVAILABLE')
    n = nodes[0]
    hand_key(cards)
    hero = POSITIONS.index(n['hero'])
    start = {i: amount(n['table']['stacks'][pos]) for i,pos in enumerate(POSITIONS)}
    stacks, bets, events = dict(start), dict.fromkeys(start, Decimal(0)), []
    for act in n['table']['actions']:
        seat = POSITIONS.index(act['position'])
        paid = amount(act['amount'])
        if act['type'] not in ('post_ante','post_sb','post_bb'):
            raise Blocked('EXAMPLE_HAS_VOLUNTARY_ACTION')
        events.append(dict(seq=len(events)+1, seat=seat, type=act['type'], amount_bb=str(paid)))
        stacks[seat] -= paid
        if act['type'] != 'post_ante':
            bets[seat] += paid
    for seat in range(hero):
        events.append(dict(seq=len(events)+1, seat=seat, type='fold', amount_bb='0'))
    return dict(evidence='SIMULATION', source_key='exported-fixture', table_id='table-1',
                snapshot_id='fixture-1', hand_id='hand-1', street='preflop',
                history_complete=True, confirmed_fields=['participants','dealer','stacks','pot',
                'bets','history','turn','hero','board'], dealer_seat=6, hero_seat=hero,
                turn_seat=hero, hero_cards=cards, board=[], strategy_context=n['context'],
                players=[dict(seat=s, start_stack_bb=str(start[s]), stack_bb=str(stacks[s]),
                              bet_bb=str(bets[s]), in_hand=s>=hero) for s in range(9)],
                actions=events, pot_bb=str(sum(start.values())-sum(stacks.values())),
                to_call_bb=str(min(stacks[hero], max(bets.values())-bets[hero])))
