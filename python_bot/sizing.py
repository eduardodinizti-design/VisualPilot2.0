"""Raise-sizing for the preflop advice, matched to the solver's betting tree.

Sizes are NOT taken from the button label or the pack's historical bets (the
handoff and the cursor spec forbid that). They mirror the sizes the HRC ranges
were solved against: open 2bb (2.5bb at 100bb), 3bet to 2.5x the open in
position / 2.9x from the SB / 3.4x from the BB, 4bet all-in. Isolating limpers
is not in the solved tree, so that add stays a flagged heuristic. Folds, checks,
calls, limps and all-ins are exact.
"""
# Solver betting-tree sizes, in big blinds.
OPEN_RAISE_BB = 2.0           # first-in open at <=40bb
OPEN_RAISE_DEEP_BB = 2.5      # first-in open at 100bb
OPEN_DEEP_THRESHOLD_BB = 40   # above this, use the deep open size
ISO_ADD_PER_LIMPER_BB = 1.0   # heuristic add per limper (iso is not in the solved tree)
THREEBET_IP_MULT = 2.5        # 3bet-to as a multiple of the open, in position
THREEBET_SB_MULT = 2.9        # from the SB
THREEBET_BB_MULT = 3.4        # from the BB


def open_size_bb(hero_stack_bb):
    """Solver open size: 2.0bb normally, 2.5bb at 100bb-deep."""
    if isinstance(hero_stack_bb, (int, float)) and hero_stack_bb > OPEN_DEEP_THRESHOLD_BB:
        return OPEN_RAISE_DEEP_BB
    return OPEN_RAISE_BB


def three_bet_mult(hero_position, ip):
    """3bet-to multiple of the open: BB 3.4x, SB 2.9x, else 2.5x (in position)."""
    if hero_position == 'BB':
        return THREEBET_BB_MULT
    if hero_position == 'SB':
        return THREEBET_SB_MULT
    return THREEBET_IP_MULT

# Postflop action order (SB first, BTN last = in position).
_POSTFLOP_ORDER = ('SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'LJ', 'HJ', 'CO', 'BTN')


def count_limpers(table_state):
    """Non-hero, non-blind seats that just called the BB (bet ~1bb)."""
    positions = table_state.get('positions') or {}
    n = 0
    for bet in (table_state.get('bets') or []):
        seat, amount = bet.get('seat'), bet.get('bet_bb')
        if seat == 'hero' or not isinstance(amount, (int, float)):
            continue
        if 0.9 <= amount <= 1.1 and positions.get(seat) not in ('BB', 'SB'):
            n += 1
    return n


def opener_raise_bb(table_state):
    """The largest non-hero bet above the BB = the opener's raise-to size, or None."""
    best = None
    for bet in (table_state.get('bets') or []):
        seat, amount = bet.get('seat'), bet.get('bet_bb')
        if seat == 'hero' or not isinstance(amount, (int, float)):
            continue
        if amount > 1.5 and (best is None or amount > best):
            best = amount
    return best


def in_position(hero_position, opener_position):
    """Will the hero act after the opener post-flop? (BTN last, blinds first.)"""
    if hero_position not in _POSTFLOP_ORDER or opener_position not in _POSTFLOP_ORDER:
        return True
    return _POSTFLOP_ORDER.index(hero_position) > _POSTFLOP_ORDER.index(opener_position)


def recommend_size(action, *, hero_stack_bb=None, to_call_bb=None, limpers=0,
                   opener_bb=None, ip=True, hero_position=None):
    """{action, size_bb, basis, heuristic} for one action, or None for fold.

    Open/3bet/4bet sizes come from the solver betting tree; isolating limpers is a
    flagged heuristic; call/limp/all-in/check are exact amounts."""
    cap = hero_stack_bb if isinstance(hero_stack_bb, (int, float)) else None

    def capped(size):
        return round(min(size, cap), 1) if cap is not None else round(size, 1)

    if action == 'fold':
        return None
    if action == 'check':
        return dict(action='check', size_bb=0.0, basis='check', heuristic=False)
    if action == 'call':
        return dict(action='call', size_bb=to_call_bb, basis='to_call', heuristic=False)
    if action == 'limp':
        return dict(action='limp', size_bb=capped(1.0), basis='bb', heuristic=False)
    if action in ('all_in', 'open_shove', 'vs_open_shove', 'three_bet_shove', 'four_bet_shove'):
        return dict(action=action, size_bb=cap, basis='all-in', heuristic=False)
    if action in ('raise', 'open_raise'):
        open_bb = open_size_bb(hero_stack_bb)
        size = open_bb + ISO_ADD_PER_LIMPER_BB * limpers
        basis = 'open %.1fbb (solver)' % open_bb
        if limpers:
            basis += ' + %d limper(s) (heuristica)' % limpers
        return dict(action='raise', size_bb=capped(size), heuristic=bool(limpers), basis=basis)
    if action == 'three_bet':
        base = opener_bb if isinstance(opener_bb, (int, float)) else open_size_bb(hero_stack_bb)
        mult = three_bet_mult(hero_position, ip)
        pos = hero_position if hero_position in ('BB', 'SB') else ('IP' if ip else 'OOP')
        return dict(action='three_bet', size_bb=capped(base * mult), heuristic=False,
                    basis='3bet %.1fx open (%s, solver)' % (mult, pos))
    if action == 'four_bet':
        return dict(action='four_bet', size_bb=cap, basis='4bet all-in (solver)', heuristic=False)
    return None


def size_from_reading(action, table_state, hero_position, opener_position=None):
    """Convenience: build the context from a read_table_state result and size the action."""
    hero = (table_state.get('seats') or {}).get('hero', {})
    return recommend_size(action, hero_stack_bb=hero.get('stack_bb'),
                          to_call_bb=(table_state.get('to_call') or {}).get('to_call_bb'),
                          limpers=count_limpers(table_state),
                          opener_bb=opener_raise_bb(table_state), hero_position=hero_position,
                          ip=in_position(hero_position, opener_position) if opener_position else True)
