"""Conselho pós-flop EXPLORATÓRIO (observação, nunca executa).

Motor de heurística fundamentada — NÃO é um solver. Decide sobre primitivas
verificáveis: força da mão feita (postflop_eval), outs/draws pela regra do 2 e do
4, pot odds, MDF e SPR (fundamentos da skill poker-fundamentos-posflop). Onde a
decisão depende de ler o vilão (bluffcatch marginal contra aposta grande), ABSTÉM
em vez de inventar um range — o projeto não fabrica números de solver. Toda saída
carrega `execution_allowed=False`; a execução pós-flop é uma etapa futura separada,
validada à parte (igual ao pré-flop, que só clicou depois de aconselhar).

`advise_postflop(table_state, hero, board, ...)` devolve o mesmo formato de
contrato do pré-flop: status ADVICE/ABSTAIN, `recommended`, métricas e `caveats`.
"""
from postflop_eval import classify_board, hand_strength, narrow_to_continuation
from preflop_equity import required_equity, equity_vs_range, hand_to_combos
from hud_exploit import classify_villain, exploit_caveats

BASE_CAVEATS = ('EXPLORATORY_NOT_FOR_EXECUTION', 'POSTFLOP_HEURISTIC_NO_SOLVER',
                'SINGLE_FRAME_NO_VILLAIN_MODEL')

# Famílias de força da mão feita.
_STRONG = ('set', 'trips', 'two_pair', 'overpair', 'straight', 'flush',
           'full_house', 'quads', 'straight_flush')
_MARGINAL = ('second_pair', 'third_pair', 'low_pair', 'underpair')

# Deságio aplicado ao decidir um CALL pela equity vs o range PRÉ-FLOP do vilão: o
# range pré-flop é mais largo que o range que realmente aposta/continua pós-flop,
# então a equity crua até o showdown SUPERESTIMA a do hero. Exigir folga extra evita
# pagar demais. Aposta grande/overbet (pot_odds>0.40) tem range polarizado — o
# pré-flop erra demais lá, então continua abstendo mesmo com range.
_CALL_HAIRCUT = 0.05
_BIG_BET_POT_ODDS = 0.40
# Equity mínima (vs range) para AUMENTAR por valor com uma mão de categoria forte.
# Abaixo disso (mas acima das pot odds) paga; se nem as pot odds bater, folda — a
# categoria não manda sozinha quando a equity contra o range diz o contrário.
_VALUE_RAISE_MIN_EQUITY = 0.60
# 3bet pot HU: abaixo deste SPR, mãos feitas fortes (até top pair) COMETEM (pote já
# grande, pouco atrás). Acima, top pair enfrenta um range polarizado e vira bluffcatch.
SPR_COMMIT_3BET = 4.0


def _normalize_range(villain_range):
    """Aceita lista de (combo, peso) OU de strings de mão ('AA','AKs','72o'); devolve
    [(frozenset, peso)] p/ o equity_vs_range (peso 1.0 p/ strings). None se vazio."""
    if not villain_range:
        return None
    out = []
    for item in villain_range:
        if isinstance(item, str):
            h = item.strip()
            # 'AK' (2 chars, ranks distintos) = suited + offsuit; 'AKs'/'AKo'/'AA' literais.
            variants = ([h + 's', h + 'o'] if len(h) == 2 and h[0].upper() != h[1].upper()
                        else [h])
            for v in variants:
                out.extend((c, 1.0) for c in hand_to_combos(v))
        else:
            combo, weight = item
            out.append((combo, weight))
    return out or None


def _abstain(reason, **extra):
    return dict(status='ABSTAIN', reason=reason, phase='postflop', exploratory=True,
                execution_allowed=False, caveats=list(BASE_CAVEATS), **extra)


def _uncovered_pot(reason, info, caveats, pot, to_call):
    """ABSTENÇÃO explícita p/ tipo de pote fora da cobertura (3bet/multiway): mantém
    a LEITURA (mão, board, outs, SPR, pote) mas não recomenda — a dinâmica difere do
    pote de um raise só e o pack não resolve esses nós, então não damos heurística."""
    read = {k: info[k] for k in ('street', 'made', 'category', 'board_texture',
                                 'structure', 'outs', 'spr', 'pot_bb', 'to_call_bb')}
    po = required_equity(to_call, pot) if isinstance(to_call, (int, float)) and to_call > 0 else None
    return dict(status='ABSTAIN', phase='postflop', reason=reason, recommended=None,
                pot_odds=round(po, 4) if po is not None else None,
                exploratory=True, execution_allowed=False,
                caveats=caveats + ['POSTFLOP_POT_TYPE_UNCOVERED'], **read)


def _street(board):
    return {3: 'FLOP', 4: 'TURN', 5: 'RIVER'}[len(board)]


def _draw_equity(outs, street):
    """Equity aproximada de um draw até o river pela regra do 2 e do 4 (fração).

    Flop (2 cartas): ~outs×4; turn (1 carta): ~outs×2+2; river: 0. Aproximação de
    estudo, NÃO equity exata vs range — por isso vem sempre com caveat e limitada."""
    if street == 'FLOP':
        pct = outs * 4
    elif street == 'TURN':
        pct = outs * 2 + 2
    else:
        return 0.0
    return min(pct / 100.0, 0.90)


# Implied odds (skill poker-fundamentos-posflop): fichas a ganhar nas PRÓXIMAS ruas
# quando o draw completa. Estimativa conservadora = fração do pote por nº de ruas que
# faltam, LIMITADA pelo que há atrás (não se ganha mais do que o stack efetivo). Draw
# ÓBVIO (flush, 3º naipe visível) realiza menos que escondido (sequência). Reverse
# implied (completar p/ a 2ª melhor mão) NÃO é modelado -> caveat.
IMPLIED_POT_FRACTION = {'FLOP': 0.5, 'TURN': 0.25}   # 2 ruas restantes vs 1
OBVIOUS_DRAW_IMPLIED = 0.5                            # desconto p/ flush draw (óbvio)
REVERSE_IMPLIED_NONNUT = 0.5                          # flush NÃO-nut: às vezes perde ao acertar


def _implied_bb(street, pot, hero_stack, to_call, draws):
    """Ganho futuro estimado (BB) quando o draw completa; 0 no river/sem stack atrás.
    Flush não-nut leva REVERSE IMPLIED (perde pro flush maior às vezes)."""
    if street not in IMPLIED_POT_FRACTION or not isinstance(pot, (int, float)) or pot <= 0:
        return 0.0
    frac = IMPLIED_POT_FRACTION[street]
    if draws.get('flush_draw') and not draws.get('combo'):
        frac *= OBVIOUS_DRAW_IMPLIED                  # flush é óbvio -> implied menor
        if not draws.get('nut_flush_draw'):
            frac *= REVERSE_IMPLIED_NONNUT            # reverse implied do flush não-nut
    raw = frac * pot
    if isinstance(hero_stack, (int, float)) and isinstance(to_call, (int, float)):
        raw = min(raw, max(0.0, hero_stack - to_call))   # teto = stack efetivo atrás
    return round(raw, 2)


def _bet_fraction(bclass, made, draws):
    """Fração do pote para apostar, por vantagem de range/nuts (poucos sizes/rua).

    - Valor com vantagem de nuts / board molhado ou pareado -> grande (~0.75).
    - Valor em board seco (vantagem de range, range mesclado) -> pequeno (~0.33).
    - Semi-blefe com draw forte -> médio (~0.5).
    - Top pair fino em board seco -> pequeno (~0.33).
    """
    wet = bclass['flush_possible'] or bclass['straightish'] >= 3 or bclass['paired']
    if made in _STRONG:
        return 0.75 if wet else 0.33
    if draws.get('combo') or draws.get('flush_draw') or draws.get('oesd'):
        return 0.5
    return 0.33


def _size(pot_bb, fraction, cap_bb, basis):
    size = round(min(pot_bb * fraction, cap_bb), 1) if cap_bb is not None else round(pot_bb * fraction, 1)
    return dict(size_bb=size, fraction=round(fraction, 2), basis=basis, heuristic=True)


def _advise_three_bet_pot(info, strength, bclass, caveats, *, pot, to_call,
                          hero_stack, spr, street):
    """Heurística pós-flop para 3bet pot HEADS-UP (antes abstinha). Três ajustes vs o
    pote de um raise só, fundamentados: (1) SPR BAIXO -> mãos fortes (até top pair)
    COMETEM; (2) range do vilão mais FORTE/POLARIZADO -> marginais foldam; (3) implied
    BAIXO -> draws só por odds diretas. Tier + SPR, sem range de 3bet (não temos um;
    usar o range de open seria errado)."""
    made, draws, outs = strength['made'], strength['draws'], strength['outs']
    strong = made in _STRONG
    monster = made in ('set', 'trips', 'two_pair', 'straight', 'flush',
                       'full_house', 'quads', 'straight_flush')
    has_strong_draw = bool(draws['combo'] or draws['flush_draw'] or draws['oesd'])
    caveats = caveats + ['POSTFLOP_THREE_BET_POT_HEURISTIC', 'LOW_SPR_3BET',
                         'VILLAIN_RANGE_STRONGER_POLARIZED']
    cap = hero_stack if isinstance(hero_stack, (int, float)) else None
    board_beats_us = (bclass['straight_on_board']
                      or (bclass['flush_possible'] and made not in
                          ('flush', 'full_house', 'quads', 'straight_flush')))
    low_spr = spr is None or spr <= SPR_COMMIT_3BET
    if to_call > 0:
        pot_odds = required_equity(to_call, pot)
        if pot_odds is None:
            return _abstain('CANNOT_COMPUTE_POT_ODDS', pot_bb=pot, to_call_bb=to_call)
        info.update(pot_odds=round(pot_odds, 4))
        if strong:
            if monster and not board_beats_us:
                raise_to = round(min(to_call * 3, cap), 1) if cap else round(to_call * 3, 1)
                info.update(recommended='raise',
                            sizing=dict(size_bb=raise_to, basis='3bet pot: comete (SPR baixo)',
                                        heuristic=True), caveats=caveats)
                return info
            if board_beats_us:
                caveats.append('BOARD_MAY_BEAT_ONE_PAIR_CALL_ONLY')
            info.update(recommended='call', caveats=caveats)       # overpair/forte comete
            return info
        if made == 'top_pair':
            if low_spr:
                info.update(recommended='call', caveats=caveats + ['TOP_PAIR_COMMITS_LOW_SPR'])
                return info
            info.update(recommended='fold',
                        caveats=caveats + ['TOP_PAIR_DEEP_3BET_POLARIZED_FOLD'])
            return info
        if made in _MARGINAL:
            info.update(recommended='fold', caveats=caveats + ['MARGINAL_FOLD_VS_3BET_RANGE'])
            return info
        if street != 'RIVER' and has_strong_draw:
            clean = draws.get('clean_outs', outs)
            deq = _draw_equity(clean, street)                      # SEM implied (SPR baixo)
            info.update(draw_equity=round(deq, 4), clean_outs=clean,
                        recommended=('call' if deq >= pot_odds else 'fold'),
                        caveats=caveats + ['DRAW_DIRECT_ODDS_NO_IMPLIED_3BET'])
            return info
        info.update(recommended='fold', caveats=caveats)
        return info
    # Passaram a vez (to_call == 0): comete/semi-blefe no SPR baixo.
    if strong:
        info.update(recommended='bet',
                    sizing=_size(pot, 0.66, cap, '3bet pot: valor/comete (size maior)'),
                    caveats=caveats)
        return info
    if has_strong_draw:
        info.update(recommended='bet',
                    sizing=_size(pot, 0.5, cap, '3bet pot: semi-blefe (SPR baixo)'),
                    caveats=caveats + ['SEMI_BLUFF_LOW_SPR'])
        return info
    if made == 'top_pair':
        info.update(recommended='bet',
                    sizing=_size(pot, 0.5, cap, '3bet pot: valor top pair'), caveats=caveats)
        return info
    info.update(recommended='check', sizing=dict(size_bb=0.0, basis='check', heuristic=False),
                caveats=caveats + ['CHECK_SHOWDOWN_OR_GIVEUP'])
    return info


def advise_postflop(table_state, hero, board, *, street=None, mode='chip_ev',
                    stage='mid', aggressor=None, villain_range=None, pot_type=None,
                    narrow_range=False, villain_stats=None, iters=4000, seed=0):
    """Conselho pós-flop para uma leitura. `hero`: 2 strings; `board`: 3-5 strings.

    `aggressor` (opcional): quem teve a iniciativa no pré-flop ('hero'/posição), para
    a lógica de c-bet quando passam a vez. Desconhecido -> flag e postura conservadora.

    `villain_range` (opcional): range do vilão — lista de (combo, peso) ou de strings
    de mão. Quando dado, enfrentando aposta, a decisão de CALL passa a ser por EQUITY
    ESTIMADA por Monte Carlo no board (semente fixa -> determinística, mas é
    estimativa, não valor fechado) vs esse range, em vez da regra do 2-e-4
    / tiers. É o range PRÉ-FLOP (não estreitado pós-flop) -> deságio + caveats; aposta
    grande segue abstendo. Sem range, cai no comportamento da Fase 1.
    """
    if not board or len(board) < 3:
        return _abstain('NO_BOARD')
    try:
        strength = hand_strength(hero, board)
        bclass = classify_board(board)
    except (ValueError, KeyError, TypeError):
        return _abstain('UNREADABLE_CARDS')
    if strength is None:
        return _abstain('HERO_BOARD_CARD_CONFLICT')
    street = street or _street(board)

    pot = (table_state.get('pot') or {}).get('pot_bb')
    to_call = (table_state.get('to_call') or {}).get('to_call_bb')
    hero_seat = (table_state.get('seats') or {}).get('hero', {})
    hero_stack = hero_seat.get('stack_bb')
    if not isinstance(pot, (int, float)) or pot <= 0:
        return _abstain('POT_UNKNOWN', pot_bb=pot)
    if to_call is None:
        return _abstain('TO_CALL_UNKNOWN')

    made = strength['made']
    draws = strength['draws']
    outs = strength['outs']
    spr = round(hero_stack / pot, 2) if isinstance(hero_stack, (int, float)) and pot else None
    strong = made in _STRONG
    marginal = made in _MARGINAL
    has_strong_draw = bool(draws['combo'] or draws['flush_draw'] or draws['oesd'])
    has_weak_draw = bool(draws['gutshot'] or draws['backdoor_flush'])

    caveats = list(BASE_CAVEATS)
    if spr is not None:
        caveats.append('SPR_PROXY_HERO_STACK')
    if aggressor == 'hero':
        caveats.append('HERO_HAS_INITIATIVE')
    elif aggressor:
        caveats.append('VILLAIN_HAS_INITIATIVE')
    else:
        caveats.append('AGGRESSOR_UNKNOWN')
    if mode != 'chip_ev':
        caveats.append('ICM_PKO_NOT_APPLIED_POSTFLOP')

    info = dict(status='ADVICE', phase='postflop', street=street, made=made,
                category=strength['category_name'], board_texture=bclass['texture'],
                structure=bclass['structure'], outs=outs, spr=spr, equity=None,
                pot_bb=pot, to_call_bb=to_call, exploratory=True, execution_allowed=False)

    # Tipos de pote fora da cobertura: ABSTÉM com rótulo ANTES de qualquer Monte
    # Carlo (abstenção conhecida não paga o custo da equity, a cada frame/mesa).
    if pot_type == 'three_bet':      # HU 3bet pot (multiway é pego como 'multiway')
        return _advise_three_bet_pot(info, strength, bclass, caveats, pot=pot, to_call=to_call,
                                     hero_stack=hero_stack, spr=spr, street=street)
    if pot_type == 'multiway':
        return _uncovered_pot('POSTFLOP_MULTIWAY_NOT_COVERED', info, caveats, pot, to_call)

    # Equity ESTIMADA do hero vs o range do vilão (se dado), Monte Carlo no board com
    # semente fixa -> determinística (mas estimativa). É a Fase 2: CALL quantitativo.
    vr = _normalize_range(villain_range)
    # Enfrentando aposta, com `narrow_range`, ESTREITA o range pré-flop do vilão para o
    # range de continuação no board (equity robusta vs não-robusta) ANTES do Monte
    # Carlo — mais preciso que o deságio fixo, que vira dispensável quando estreitamos.
    narrowed = False
    if vr and narrow_range and isinstance(to_call, (int, float)) and to_call > 0:
        vr_cont = narrow_to_continuation(vr, list(board), street=street)
        if vr_cont:
            vr, narrowed = vr_cont, True
    equity = equity_vs_range(hero, vr, board=list(board), iters=iters, seed=seed) if vr else None
    haircut = 0.0 if narrowed else _CALL_HAIRCUT
    # Exploit do HUD (opcional): classifica o vilão e nudgeia o limiar de bluffcatch
    # (foldar mais vs passivo/value-heavy; pagar mais largo vs quem blefa). Bounded e
    # sempre flagado (amostra desconhecida). Só mexe nas mãos FEITAS enfrentando aposta.
    profile = classify_villain(villain_stats) if villain_stats else None
    ex_delta = profile['bluffcatch_delta'] if profile else 0.0
    if profile and profile['category'] != 'unknown':
        caveats = caveats + exploit_caveats(profile)
    if equity is not None:
        if narrowed:
            caveats += ['EQUITY_VS_VILLAIN_CONTINUATION_RANGE', 'RANGE_NARROWED_TO_BOARD']
        else:
            caveats += ['EQUITY_VS_VILLAIN_PREFLOP_RANGE', 'RANGE_NOT_NARROWED_POSTFLOP',
                        'CALL_HAIRCUT_%dPCT' % round(_CALL_HAIRCUT * 100)]
        info['equity'] = round(equity, 4)

    # ---- Enfrentando uma aposta -------------------------------------------------
    if to_call > 0:
        pot_odds = required_equity(to_call, pot)
        if pot_odds is None:
            return _abstain('CANNOT_COMPUTE_POT_ODDS', pot_bb=pot, to_call_bb=to_call)
        mdf = round(pot / (pot + to_call), 4) if (pot + to_call) else None
        info.update(pot_odds=round(pot_odds, 4), mdf=mdf)
        cap = hero_stack if isinstance(hero_stack, (int, float)) else None
        board_beats_us = (bclass['straight_on_board']
                          or (bclass['flush_possible'] and made not in
                              ('flush', 'full_house', 'quads', 'straight_flush')))
        # Mão de categoria forte: a equity (quando há range) manda. Não aumenta —
        # nem paga — contra um range que nos domina, mesmo com categoria boa (#7).
        if strong:
            if equity is not None and equity < pot_odds + haircut + ex_delta:
                info.update(recommended='fold',
                            caveats=caveats + ['STRONG_CATEGORY_BUT_DOMINATED_BY_RANGE'])
                return info
            can_value_raise = (not board_beats_us
                               and (equity is None or equity >= _VALUE_RAISE_MIN_EQUITY))
            if can_value_raise:
                raise_to = round(min(to_call * 3, cap), 1) if cap else round(to_call * 3, 1)
                info.update(recommended='raise',
                            sizing=dict(size_bb=raise_to, basis='raise ~3x aposta (heuristica)',
                                        heuristic=True), caveats=caveats)
                return info
            if board_beats_us:
                caveats.append('BOARD_MAY_BEAT_ONE_PAIR_CALL_ONLY')
            info.update(recommended='call', caveats=caveats)
            return info
        # Mãos FEITAS fracas/médias decidem como bluffcatcher ANTES de qualquer draw
        # (uma mão feita com draw não deve ser foldada como se fosse só draw) (#6).
        if made == 'top_pair':
            if pot_odds > _BIG_BET_POT_ODDS:
                # Aposta grande = bluffcatch que precisa de LEITURA. Com HUD, DECIDE:
                # vilão que blefa (lag/cbet-heavy/3bet-happy) -> paga; passivo/nit (aposta
                # grande = valor) -> folda. Sem HUD, segue abstendo (honesto).
                if profile and profile['category'] != 'unknown':
                    dec = 'call' if profile['aggressive'] else 'fold'
                    info.update(recommended=dec,
                                caveats=caveats + ['BLUFFCATCH_BIG_BET_EXPLOIT_%s'
                                                   % ('AGGRO' if profile['aggressive'] else 'PASSIVE')])
                    return info
                return _abstain('BLUFFCATCH_VS_BIG_BET_NEEDS_READS', pot_bb=pot,
                                to_call_bb=to_call, pot_odds=round(pot_odds, 4), made=made,
                                equity=round(equity, 4) if equity is not None else None)
            if equity is not None:
                caveats.append('BLUFFCATCH_EQUITY_DRIVEN')
                info.update(recommended=('call' if equity >= pot_odds + haircut + ex_delta else 'fold'),
                            caveats=caveats)
                return info
            caveats += ['BLUFFCATCH_DEFEND_TO_MDF', 'EXPLOIT_DEPENDS_ON_VILLAIN']
            info.update(recommended='call', caveats=caveats)
            return info
        if marginal:
            if equity is not None:
                caveats.append('MARGINAL_EQUITY_DRIVEN')
                info.update(recommended=('call' if equity >= pot_odds + haircut + ex_delta else 'fold'),
                            caveats=caveats)
                return info
            caveats.append('MARGINAL_BLUFFCATCH_FOLD_DEFAULT_EXPLOITABLE')
            info.update(recommended='fold', caveats=caveats)
            return info
        # Mão NÃO-feita com draw: só vale fora do river (no river não vem carta) (#6).
        if street != 'RIVER' and (has_strong_draw or has_weak_draw):
            # Implied odds: o ganho futuro quando o draw completa baixa a equity exigida.
            implied = _implied_bb(street, pot, hero_stack, to_call, draws)
            po_imp = required_equity(to_call, pot + implied) if implied > 0 else pot_odds
            if implied > 0:
                caveats.append('IMPLIED_ODDS_APPROX_%gBB' % implied)
                if draws['flush_draw'] and not draws['combo'] and not draws.get('nut_flush_draw'):
                    caveats.append('REVERSE_IMPLIED_NONNUT_FLUSH')      # modelado (implied menor)
                elif not draws['flush_draw']:
                    caveats.append('REVERSE_IMPLIED_STRAIGHT_NOT_MODELED')
            else:
                caveats.append('IMPLIED_ODDS_NONE_NO_STACK_BEHIND')
            if equity is not None:
                info.update(implied_bb=implied, pot_odds_implied=round(po_imp, 4),
                            recommended=('call' if equity >= po_imp + haircut else 'fold'),
                            caveats=caveats)
                return info
            clean = draws.get('clean_outs', outs)
            deq = _draw_equity(clean, street)
            caveats.append('DRAW_EQUITY_RULE_OF_2_AND_4')
            if clean < outs:
                # Outs sujos descontados (board pareado / flush que pareia / sequência
                # dentro de um flush): a equity de draw usa os outs LIMPOS, não os crus.
                caveats.append('DIRTY_OUTS_DISCOUNTED_%g_OF_%d' % (round(outs - clean, 1), outs))
            info.update(draw_equity=round(deq, 4), clean_outs=clean, implied_bb=implied,
                        pot_odds_implied=round(po_imp, 4),
                        recommended=('call' if deq >= po_imp else 'fold'), caveats=caveats)
            return info
        # Ar / joga o board: folda, salvo equity (vs range) acima das pot odds.
        if equity is not None and equity >= pot_odds + haircut + ex_delta:
            info.update(recommended='call', caveats=caveats + ['WEAK_BUT_EQUITY_OK'])
            return info
        info.update(recommended='fold', caveats=caveats)
        return info

    # ---- Passaram a vez (to_call == 0): apostar ou dar check ---------------------
    info.update(pot_odds=None, mdf=None)
    cap = hero_stack if isinstance(hero_stack, (int, float)) else None
    if strong:
        frac = _bet_fraction(bclass, made, draws)
        info.update(recommended='bet', sizing=_size(pot, frac, cap, 'valor por vantagem de range/nuts'),
                    caveats=caveats)
        return info
    if has_strong_draw:
        frac = _bet_fraction(bclass, made, draws)
        caveats.append('SEMI_BLUFF_NEGA_EQUITY_E_CRESCE_POTE')
        info.update(recommended='bet', sizing=_size(pot, frac, cap, 'semi-blefe com draw'),
                    caveats=caveats)
        return info
    if made == 'top_pair' and not (bclass['flush_possible'] or bclass['straightish'] >= 3):
        info.update(recommended='bet', sizing=_size(pot, 0.33, cap, 'valor fino top pair, board seco'),
                    caveats=caveats)
        return info
    # EXPLOIT (HUD): passaram a vez com AR (sem showdown value) -> normalmente check;
    # mas vs vilão que FOGE de c-bet (tag folds_to_cbet), blefa com size pequeno (a fold
    # equity é alta). Só o ar — mão média tem showdown value e segue de check.
    if (profile and 'folds_to_cbet' in profile.get('tags', [])
            and made in ('air', 'overcards')):
        info.update(recommended='bet', sizing=_size(pot, 0.4, cap, 'c-bet blefe vs folds_to_cbet'),
                    caveats=caveats + ['EXPLOIT_CBET_BLUFF_VS_FOLDCBET'])
        return info
    # Mãos médias/marginais/ar com valor de showdown ou sem: check.
    caveats.append('CHECK_SHOWDOWN_OR_GIVEUP')
    info.update(recommended='check',
                sizing=dict(size_bb=0.0, basis='check', heuristic=False), caveats=caveats)
    return info
