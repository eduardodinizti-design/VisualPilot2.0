"""End-to-end: read one PPPoker table crop and produce an exploratory read-out.

Ties together the readers (hero cards, table state, hand id, board) and the
PreflopAdvisor so that, for one frame, the bot prints what it sees and what it
would do. Observation only: no capture, no clicks, execution never allowed.
Preflop advice comes from the PreflopAdvisor (spot inferred from the bets); from
the flop on, the postflop_advisor attaches a founded-heuristic read (phase
'postflop'). Both are exploratory and never executable (the armed operator plays
preflop only and skips anything marked postflop).
"""
import argparse
import json

import cv2

from table_reading.pipeline import configure_ocr
from table_reading.ocr_runtime import ocr_frame
from table_reading.table_state import read_table_state
from table_reading.community_cards import read_board
from table_reading.hand_tracking import read_hand_id
from table_reading.tournament import read_tournament, tournament_context
from preflop_advisor import PreflopAdvisor, infer_spread
from postflop_advisor import advise_postflop
from preflop_context import villain_postflop_range


def read_hero_cards(crop):
    """Hero's two face-up cards, or None when not readable/duplicate."""
    from table_reading.inspect_cards import inspect
    reading = inspect(crop, (0, 0, crop.shape[1], crop.shape[0]))
    cards = [c.get('card_candidate') for c in reading.get('hero_rank_candidates', [])]
    if len(cards) != 2 or not all(cards) or cards[0] == cards[1]:
        return None
    return cards


def _pot_type_from_context(ctx):
    """Tipo de pote a partir do contexto do rastreador, p/ o gating honesto do
    pós-flop: sem contexto/sem raise -> 'unknown'; não-HU -> 'multiway'; >=2 níveis de
    raise -> 'three_bet'; 1 nível -> 'single_raised' (pote de um raise só)."""
    if ctx is None:
        return 'unknown'
    if not ctx['heads_up']:
        return 'multiway'
    if ctx['raises'] >= 2:
        return 'three_bet'
    if ctx['raises'] == 1:
        return 'single_raised'
    return 'unknown'


def _postflop_in_context(advisor, tracker, state, hero, board, *, mode, stage, table_key):
    """Recalcula o conselho pós-flop usando o CONTEXTO rastreado entre frames: deriva
    pot_type (gating), aggressor (iniciativa) e o range do vilão (equity no HU, pote de
    um raise só) e rechama advise_postflop. Espelha o que o operador armado já fazia,
    agora disponível a qualquer observador contínuo que passe um `tracker`."""
    ctx = tracker.context(table_key)
    seats = state.get('seats') or {}
    spread = (infer_spread({p: (seats.get(s) or {}).get('stack_bb')
                            for s, p in (state.get('positions') or {}).items()})
              if mode in ('icm', 'pko_icm') else None)
    ptype = _pot_type_from_context(ctx)
    combos, meta = villain_postflop_range(advisor, ctx, mode=mode, stage=stage, spread=spread,
                                          hero_stack_bb=(seats.get('hero') or {}).get('stack_bb'))
    # Exploit do HUD: stats do VILÃO (lidos por advise_table em state['hud']). HU = o
    # agressor rastreado, ou o único vilão com HUD lido.
    vstats = None
    hud = state.get('hud') or {}
    if hud:
        positions = state.get('positions') or {}
        aggr = (ctx or {}).get('aggressor')
        vseat = next((s for s, p in positions.items() if p == aggr), None) if aggr and aggr != 'hero' else None
        if vseat is None and len(hud) == 1:
            vseat = next(iter(hud))
        ventry = hud.get(vseat) if vseat else None
        # Só exploita com leitura CONFIÁVEL (8/8 high); 'partial' pode ter campo mal-lido
        # ou linha trocada num skin/escala não calibrado -> não alimenta o exploit.
        vstats = ventry['stats'] if (ventry and ventry.get('confidence') == 'high') else None
    advice = advise_postflop(state, hero, board['cards'], street=board.get('street'),
                             mode=mode, stage=stage, aggressor=(ctx or {}).get('aggressor'),
                             villain_range=(combos or None), pot_type=ptype, narrow_range=True,
                             villain_stats=vstats)
    if isinstance(advice, dict):
        # Observabilidade: qual range foi usado (ou o motivo de ter ficado na Fase 1).
        advice['villain_range_source'] = meta if combos else {'reason': meta}
    return advice


def advise_table(crop, advisor, *, mode=None, stage=None, stabilizer=None, table_key='default',
                 villain_range=None, hero_override=None, tracker=None, bounty_bb=None,
                 enable_hud=False, read_cache=None):
    """Read the table and attach an exploratory recommendation. The tournament
    phase chooses chip EV vs ICM unless mode/stage are forced. Pure read; the
    caller wraps it in an ocr_frame so one snapshot reuses OCR.

    `stabilizer` (opcional, PositionStabilizer): suaviza as POSIÇÕES ao longo dos
    frames — o leitor é stateless e os rótulos oscilam quando a ocupação/dealer
    pisca; o estabilizador trava o dealer (debounce) e usa ocupação por maioria.
    `table_key` identifica a mesa p/ o estado por-mesa do estabilizador."""
    state = read_table_state(crop)
    hand = read_hand_id(crop)
    if stabilizer is not None:
        occ = [s for s, d in (state.get('seats') or {}).items() if d.get('occupied')]
        hkey = (hand or {}).get('hand_id') or (hand or {}).get('hand_number')
        sdealer, spos = stabilizer.update(table_key=table_key, hand_key=hkey,
                                          dealer_seat=state['dealer'].get('seat'),
                                          occupied_seats=occ)
        # As posições do estabilizador são AUTORITATIVAS: {} (pendente/sem dealer)
        # força abstenção em vez de cair na leitura crua que oscila. Mantém o dealer
        # original quando o estável é None (não enfraquece o is_table).
        new_dealer = dict(state['dealer'], stabilized=True)
        if sdealer is not None:
            new_dealer['seat'] = sdealer
        state = dict(state, positions=spos, dealer=new_dealer)
    hero = read_hero_cards(crop)
    # As cartas do hero são imutáveis na mão: se este frame não leu mas o chamador
    # tem uma leitura confiável da MESMA mão (hero_override), reusa — evita abster
    # (HERO_CARDS_UNKNOWN) por falha pontual de leitura/animação num frame.
    if hero is None and hero_override and len(hero_override) == 2:
        hero = list(hero_override)
    board = read_board(crop, hero_cards=hero or [None, None])
    tourney = read_tournament(crop)
    auto_mode, auto_stage = tournament_context(tourney)
    use_mode, use_stage = mode or auto_mode, stage or auto_stage
    # Reject a crop that carries no table field at all (a lobby/tournament list the
    # detector picked up as a false-positive blue table).
    is_table = (state['pot'].get('pot_bb') is not None or state['dealer'].get('seat') is not None
                or tourney.get('paid') is not None or hero is not None
                or any(s['stack_bb'] is not None for s in state['seats'].values()))
    if not is_table:
        return dict(hand=hand, hero_cards=hero, board=board, table_state=state, tournament=tourney,
                    context=dict(mode=use_mode, stage=use_stage), is_table=False,
                    advice=dict(status='SKIP', reason='NAO_PARECE_MESA_LOBBY', exploratory=True, execution_allowed=False))
    # PKO: lê o bounty por assento e anexa ao estado (p/ o call-off escalar a caça pelo
    # bounty do vilão). Só com o overlay armado (bounty_bb) e torneio PKO, p/ não pagar o
    # custo de OCR fora disso. Best-effort: assentos ilegíveis simplesmente não entram.
    if bounty_bb and use_mode in ('pko', 'pko_icm'):
        occ = [s for s, d in (state.get('seats') or {}).items() if d.get('occupied')]
        if read_cache is not None:          # cache: relê só a cada N frames (latência)
            state = dict(state, bounties=read_cache.bounties(crop, table_key, occ))
        else:
            from table_reading.bounty import read_seat_bounties
            bread = read_seat_bounties(crop, seats=occ)
            state = dict(state, bounties={s: v['value'] for s, v in bread.items() if v['value'] is not None})
    # HUD VIP (opcional): lê os 8 stats por vilão e anexa a state['hud'] (p/ o exploit
    # no pós-flop). Custo ALTO (~1s/8 assentos) -> com read_cache, relê só a cada N frames.
    if enable_hud:
        occ = [s for s, d in (state.get('seats') or {}).items() if d.get('occupied')]
        if read_cache is not None:
            state = dict(state, hud=read_cache.huds(crop, table_key, occ))
        else:
            from table_reading.hud_reader import read_seat_huds
            state = dict(state, hud=read_seat_huds(crop, occ))
    # Postflop guard. A read board (cards) is clearly postflop. A board that was
    # DETECTED but not fully read (incomplete, duplicate, or obstructed with the
    # anchor found) is also postflop and must abstain, not be treated as preflop.
    # Preflop itself has no board, which reads as 'anchor missing' -> advise.
    board_status, board_reason = board.get('status'), board.get('reason')
    board_present_unread = (board_status in ('BOARD_INCOMPLETE', 'BOARD_DUPLICATE_REJECTED')
                            or (board_status == 'BOARD_PARTIAL_OR_OBSTRUCTED'
                                and board_reason != 'FIRST_CARD_ANCHOR_MISSING'))
    if board.get('cards'):
        if hero is None:
            advice = dict(status='ABSTAIN', reason='HERO_CARDS_UNKNOWN', phase='postflop',
                          exploratory=True, execution_allowed=False)
        else:
            advice = advise_postflop(state, hero, board['cards'], street=board.get('street'),
                                     mode=use_mode, stage=use_stage, villain_range=villain_range)
    elif board_present_unread:
        advice = dict(status='ABSTAIN', reason='BOARD_PRESENT_BUT_UNREADABLE', exploratory=True, execution_allowed=False)
    elif hero is None:
        advice = dict(status='ABSTAIN', reason='HERO_CARDS_UNKNOWN', exploratory=True, execution_allowed=False)
    else:
        # `bounty_bb` (PKO, opcional): só o call-off o usa, e só engata se o torneio
        # ler como PKO (use_mode pko/pko_icm) e o hero cobrir o shove.
        advice = advisor.advise_from_reading(state, hero, mode=use_mode, stage=use_stage,
                                             bounty_bb=bounty_bb)
        if isinstance(advice, dict):
            advice.setdefault('caveats', []).append('SPOT_INFERRED_FROM_BETS')
    # Contexto ENTRE frames (opcional): atualiza o rastreador do agressor pré-flop e,
    # no pós-flop, recalcula o conselho com pot_type/iniciativa/range do vilão. Só é
    # útil a observadores CONTÍNUOS (um frame único não tem histórico pré-flop).
    if tracker is not None:
        hkey = (hand or {}).get('hand_id') or (hand or {}).get('hand_number')
        has_board = bool(board.get('cards'))
        tracker.update(table_key=table_key, hand_key=hkey, table_state=state, has_board=has_board)
        if has_board and hero is not None and isinstance(advice, dict) and advice.get('phase') == 'postflop':
            advice = _postflop_in_context(advisor, tracker, state, hero, board,
                                          mode=use_mode, stage=use_stage, table_key=table_key)
    return dict(hand=hand, hero_cards=hero, board=board, table_state=state, is_table=True,
                tournament=tourney, context=dict(mode=use_mode, stage=use_stage), advice=advice)


def _summary(result):
    st = result['table_state']
    occ = [s for s, d in st['seats'].items() if d['occupied']]
    tour = result['tournament']
    lines = ['=== LEITURA DA MESA (observacao, sem cliques) ===',
             'Mao: %s | Dealer: %s | Pote: %s BB | Pagar: %s BB' % (
                 result['hand'].get('hand_number'), st['dealer'].get('seat'),
                 st['pot'].get('pot_bb'), st['to_call'].get('to_call_bb')),
             'Fase: pagos=%s restantes=%s -> %s/%s' % (
                 tour.get('paid'), tour.get('players_left'),
                 result['context']['mode'], result['context']['stage']),
             'Hero: %s' % (result['hero_cards'] or 'nao identificado'),
             'Assentos ocupados: %d' % len(occ)]
    for seat in occ:
        d = st['seats'][seat]
        lines.append('  %-9s pos=%-5s stack=%s BB%s' % (
            seat, st['positions'].get(seat, '-'), d['stack_bb'],
            ' [DEALER]' if st['dealer'].get('seat') == seat else ''))
    bets = [b for b in (st.get('bets') or []) if isinstance(b.get('bet_bb'), (int, float))]
    if bets:   # per-seat bets drive the spot inference; log them to diagnose it
        lines.append('Bets: ' + ', '.join(
            '%s=%sbb(%s)' % (b['seat'], b['bet_bb'], st['positions'].get(b['seat'], '-')) for b in bets))
    adv = result['advice']
    lines.append('=== RECOMENDACAO (exploratoria, nao-executar) ===')
    if adv.get('phase') == 'postflop' and adv.get('status') == 'ADVICE':
        sz = adv.get('sizing') or {}
        size_txt = ' %.1fbb (%s)' % (sz['size_bb'], sz.get('basis', '')) if sz.get('size_bb') else ''
        extra = []
        if adv.get('pot_odds') is not None:
            extra.append('pot odds %.0f%%' % (adv['pot_odds'] * 100))
        if adv.get('draw_equity') is not None:
            extra.append('eq draw ~%.0f%%' % (adv['draw_equity'] * 100))
        if adv.get('spr') is not None:
            extra.append('SPR %.1f' % adv['spr'])
        lines.append('POSFLOP %s: %s%s | mao: %s (%s) | outs: %s%s' % (
            adv.get('street'), str(adv['recommended']).upper(), size_txt,
            adv.get('made'), adv.get('category'), adv.get('outs'),
            (' | ' + ', '.join(extra)) if extra else ''))
    elif adv.get('status') == 'ADVICE':
        mix = ', '.join('%s %d%%' % (m['action'], round(m['frequency'] * 100)) for m in adv['mix'])
        sz = adv.get('sizing') or {}
        size_txt = ''
        if sz.get('size_bb') is not None:
            size_txt = ' -> %s BB (%s%s)' % (sz['size_bb'], sz.get('basis', ''),
                                             '; heuristica' if sz.get('heuristic') else '')
        caveats = adv.get('caveats') or []
        deep = ''
        if 'STACK_ABOVE_SOLVED_DEPTH_100BB_REFERENCE' in caveats:
            deep = ' [ref 100bb p/ %sbb deep]' % adv.get('stack_bb')
        mw = next((c for c in caveats if c.startswith('MULTIWAY_') and 'CALLERS' in c), None)
        if mw:
            deep += ' [multiway aprox: %s caller(s) via vs_open]' % mw.split('_')[1]
        lines.append('ACAO: %s%s | mix: %s | stack usado: %sbb%s | no: %s' % (
            adv['recommended'].upper(), size_txt, mix, adv['stack_bucket'], deep, adv['node_id']))
    else:
        lines.append('ABSTEM: %s' % adv.get('reason'))
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ranges', required=True, help='nvt-ranges-validados.json')
    p.add_argument('--deep', default=None, help='Pacote deep 40/100bb opcional (reference, nao validado)')
    p.add_argument('--imagem', required=True, help='Recorte de uma mesa (PNG)')
    p.add_argument('--mode', default=None, help='Forca o modo; padrao: detecta da fase do torneio')
    p.add_argument('--stage', default=None, help='Forca o estagio; padrao: detecta da fase')
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)
    advisor = PreflopAdvisor.from_files(args.ranges, args.deep) if args.deep else PreflopAdvisor.from_file(args.ranges)
    crop = cv2.imread(args.imagem)
    if crop is None:
        raise SystemExit('Nao consegui ler a imagem: ' + args.imagem)
    configure_ocr()
    with ocr_frame():
        result = advise_table(crop, advisor, mode=args.mode, stage=args.stage)
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != 'table_state'}, ensure_ascii=False, indent=2, default=str))
    else:
        print(_summary(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
