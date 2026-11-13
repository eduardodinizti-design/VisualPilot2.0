"""Avaliação pós-flop pura: textura/estrutura do board e força da mão do hero.

Sem captura e sem clique. Reaproveita o avaliador exato de 7 cartas (`eval7`) e o
parser de cartas do motor de equity. A classificação de board segue o vocabulário
de estudo (skill poker-fundamentos-posflop): textura (monotone/two-tone/rainbow,
pareado, trinca), estrutura por famílias A/H/M/L (A=Á, H=K-T, M=9-6, L=5-2) e
"straightness" (quantas cartas do board entram numa janela de 5 ranks). A força da
mão combina o rótulo relativo ao board (set, overpair, top pair, dois pares...) com
as GAVETAS clássicas de draws e suas contagens de outs (flush=9, OESD=8, gutshot=4,
combo≤15). Nada aqui decide a jogada — isso é do postflop_advisor.
"""
from collections import Counter

from preflop_equity import parse_card, eval7, SUITS

CATEGORY_NAMES = {8: 'straight_flush', 7: 'quads', 6: 'full_house', 5: 'flush',
                  4: 'straight', 3: 'trips', 2: 'two_pair', 1: 'pair', 0: 'high_card'}


def _cards(seq):
    """Normaliza strings/tuplas em tuplas (rank:int, naipe:str). Levanta ValueError."""
    return [parse_card(c) if isinstance(c, str) else (int(c[0]), c[1]) for c in seq]


def _family(rank):
    """Família estrutural de um rank: A / H (K-T) / M (9-6) / L (5-2)."""
    if rank == 14:
        return 'A'
    if rank >= 10:
        return 'H'
    if rank >= 6:
        return 'M'
    return 'L'


def _has_straight(rank_set):
    """Há uma sequência de 5 ranks consecutivos no conjunto? (Á conta como 1 e 14.)"""
    rs = set(rank_set)
    if 14 in rs:
        rs.add(1)
    for top in range(14, 4, -1):
        if all(x in rs for x in range(top, top - 5, -1)):
            return True
    return False


def classify_board(board):
    """Descreve o board (3 a 5 cartas) por textura e estrutura. Dict com:

    - `texture`: 'monotone'/'two_tone'/'rainbow' no flop; 'flush_N' no turn/river
      (N = maior naipe presente).
    - `paired`/`trips`/`quads`: multiplicidade máxima de rank no board.
    - `flush_count`: maior nº de cartas de um mesmo naipe (3 já = flush possível).
    - `flush_possible`/`straight_on_board`: o board já completa flush/sequência.
    - `straightish`: máximo de ranks do board dentro de uma janela de 5 (3 = board
      coordenado; 4 = muito molhado). Indica potencial de sequência.
    - `structure`: famílias A/H/M/L dos ranks distintos, do mais alto ao mais baixo.
    - `high_rank`: rank mais alto do board.
    """
    cards = _cards(board)
    if not 3 <= len(cards) <= 5:
        raise ValueError('board precisa de 3 a 5 cartas: %r' % (board,))
    ranks = [r for r, _ in cards]
    suits = [s for _, s in cards]
    rc, sc = Counter(ranks), Counter(suits)
    flush_count = max(sc.values())
    mult = sorted(rc.values(), reverse=True)
    n = len(cards)
    if n == 3:
        texture = {3: 'monotone', 2: 'two_tone', 1: 'rainbow'}[flush_count]
    else:
        texture = 'flush_%d' % flush_count
    rset = set(ranks)
    straightish = 0
    probe = rset | ({1} if 14 in rset else set())
    for top in range(14, 4, -1):
        straightish = max(straightish, sum(1 for r in range(top, top - 5, -1) if r in probe))
    distinct_desc = sorted(set(ranks), reverse=True)
    return dict(
        cards=list(board), n=n, flush_count=flush_count,
        paired=mult[0] >= 2, trips=mult[0] >= 3, quads=mult[0] >= 4,
        texture=texture, flush_possible=flush_count >= 3,
        straight_on_board=_has_straight(rset), straightish=straightish,
        structure=[_family(r) for r in distinct_desc], high_rank=max(ranks),
    )


# Regra dos outs descontados ("outs sujos"): um out que pode fazer o VILÃO a melhor
# mão não é um out limpo. Convenção de estudo (conservadora): cada out suspeito vale
# meio out; um out com duas ameaças sobrepostas é limitado a totalmente morto (1).
DIRTY_OUT_WEIGHT = 0.5


def _straight_out_cardset(hero_cards, board_cards):
    """Conjunto de CARTAS (rank, naipe) que completam uma sequência (vazio se já é
    sequência). OESD => 8 cartas, gutshot => 4."""
    present = hero_cards + board_cards
    ranks = {r for r, _ in present}
    if _has_straight(ranks):
        return set()
    seen = set(present)
    cards = set()
    for r in range(2, 15):
        if r in ranks:
            continue
        if _has_straight(ranks | {r}):
            cards |= {(r, s) for s in SUITS if (r, s) not in seen}
    return cards


def _dirty_outs(out_cards, flush_out_cards, board_cards, flush_suit):
    """Outs 'sujos' entre as cartas de out (peso somado, meio-out por ameaça, teto 1
    por carta). Gatilhos, cada um porque a carta pode dar a MELHOR mão ao vilão:

    - board já PAREADO: ao fechar flush/sequência, o vilão ainda pode ter full house
      (qualquer par/ trinca no board) — toda carta de out vira meio-out;
    - out de FLUSH cujo rank já aparece no board: fechar o flush PAREIA o board,
      abrindo full house para o vilão;
    - out de SEQUÊNCIA que coloca a 3ª carta de um naipe no board (sequência "dentro
      de um flush"): o vilão pode ter o flush. Não vale para o próprio naipe de flush
      do hero (aí ELE fecha o flush, não é sujo).

    Devolve (peso_total_float, lista_ordenada_das_cartas_sujas)."""
    board_ranks = {r for r, _ in board_cards}
    board_paired = max(Counter(r for r, _ in board_cards).values(), default=0) >= 2
    board_suits = Counter(s for _, s in board_cards)
    total = 0.0
    dirty = []
    for card in out_cards:
        r, s = card
        w = 0.0
        if board_paired:
            w += DIRTY_OUT_WEIGHT
        if card in flush_out_cards and r in board_ranks:      # flush que pareia o board
            w += DIRTY_OUT_WEIGHT
        if card not in flush_out_cards and s != flush_suit \
                and board_suits.get(s, 0) + 1 >= 3:           # sequência dentro de um flush
            w += DIRTY_OUT_WEIGHT
        w = min(w, 1.0)
        if w > 0:
            total += w
            dirty.append(card)
    return total, sorted(dirty)


def _nut_flush_draw(hero_cards, board_cards, flush_suit):
    """Hero está no draw do FLUSH NUT? True se NÃO há carta do naipe mais alta que a do
    hero fora do que já é visível (ninguém pode ter um flush maior). Trata o Á no board
    (flush compartilhado -> a carta de hole mais alta do naipe decide)."""
    if flush_suit is None:
        return False
    visible = {r for (r, s) in (hero_cards + board_cards) if s == flush_suit}
    hero_max = max((r for (r, s) in hero_cards if s == flush_suit), default=0)
    higher_available = [r for r in range(hero_max + 1, 15) if r not in visible]
    return hero_max > 0 and not higher_available


def _draws(hero_cards, board_cards):
    """Gavetas de draw do hero e contagem de outs (cartas), com contribuição do hero.

    Só conta flush/sequência em que o hero PARTICIPA (não draw que é só do board). O
    combo (FD + straight) é limitado a 15 outs; a interseção (carta que fecha os dois)
    é naturalmente deduplicada pela união de conjuntos. No RIVER (board com 5 cartas)
    NÃO há draw: não vem mais carta -> tudo zero.

    Além do `outs` CRU (estrutural), devolve `clean_outs` = outs menos os outs sujos
    (regra do meio-out; ver `_dirty_outs`) e `tainted_outs` (quanto foi descontado).
    O `outs` cru é preservado para os rótulos de draw; quem estima equity de draw sem
    range do vilão deve usar `clean_outs`."""
    if len(board_cards) >= 5:
        return dict(flush_draw=False, backdoor_flush=False, flush_outs=0,
                    straight_outs=0, oesd=False, gutshot=False, combo=False,
                    outs=0, clean_outs=0, tainted_outs=0.0, nut_flush_draw=False)
    present = hero_cards + board_cards
    suits = Counter(s for _, s in present)
    hero_suits = Counter(s for _, s in hero_cards)
    flush_draw = False
    backdoor_flush = False
    flush_suit = None
    for s, ct in suits.items():
        if ct == 4 and hero_suits.get(s, 0) >= 1:
            flush_draw, flush_suit = True, s
        elif ct == 3 and hero_suits.get(s, 0) >= 1 and len(board_cards) == 3:
            backdoor_flush = True
    made_flush = any(ct >= 5 for ct in suits.values())
    seen = set(present)
    flush_out_cards = set()
    if flush_draw and not made_flush:
        flush_out_cards = {(r, flush_suit) for r in range(2, 15) if (r, flush_suit) not in seen}
    straight_out_cards = _straight_out_cardset(hero_cards, board_cards)
    # A união deduplica a interseção (carta do naipe do flush que também fecha a
    # sequência conta uma vez só no total do combo).
    out_cards = flush_out_cards | straight_out_cards
    straight_cnt = len(straight_out_cards)
    oesd = straight_cnt >= 8
    gutshot = straight_cnt == 4
    outs = min(len(out_cards), 15)
    tainted, _dirty = _dirty_outs(out_cards, flush_out_cards, board_cards, flush_suit)
    tainted = min(tainted, outs)
    clean_outs = round(outs - tainted, 1)
    return dict(flush_draw=flush_draw, backdoor_flush=backdoor_flush,
                flush_outs=len(flush_out_cards), straight_outs=straight_cnt,
                oesd=oesd, gutshot=gutshot,
                combo=bool(flush_draw and straight_cnt >= 4),
                outs=outs, clean_outs=clean_outs, tainted_outs=round(tainted, 1),
                nut_flush_draw=_nut_flush_draw(hero_cards, board_cards, flush_suit))


def _relative_label(hero_cards, board_cards, category):
    """Rótulo da força relativa ao board, SEMPRE exigindo contribuição do hero.

    Quando a categoria vem SÓ do board (dois pares/trinca/sequência/flush no próprio
    board, ou o hero não supera o que o board já faz), o rótulo é fraco
    ('board_two_pair', 'board_trips', 'plays_board', 'board_pair_only') — o hero não
    tem a mão forte, só valor de showdown. Caso contrário distingue set/trinca,
    overpair/underpair, top/second/third pair e nomeia straight+ de fato do hero.
    """
    c = category[0]
    board_desc = sorted({r for r, _ in board_cards}, reverse=True)
    board_counts = Counter(r for r, _ in board_cards)
    hero_ranks = sorted((r for r, _ in hero_cards), reverse=True)
    hero_set = set(hero_ranks)
    pocket_pair = hero_ranks[0] == hero_ranks[1]
    top = board_desc[0] if board_desc else 0
    board_best = eval7(board_cards)
    hero_improves = category > board_best       # o hero supera o que o board já faz?

    if c >= 4:
        # sequência / flush / full house / quadra / straight flush: se o hero não
        # supera o board (todo mundo "joga o board"), é só valor de showdown.
        return CATEGORY_NAMES[c] if hero_improves else 'plays_board'
    if c == 3:
        trip_rank = next((r for r, ct in board_counts.items() if ct >= 3), None)
        if trip_rank is not None:
            return 'board_trips'                # trinca no próprio board
        return 'set' if pocket_pair else 'trips'
    if c == 2:
        board_pairs = [r for r, ct in board_counts.items() if ct >= 2]
        if len(board_pairs) >= 2:
            return 'board_two_pair'             # dois pares no próprio board (hero só kicker)
        return 'two_pair'
    if c == 1:
        if pocket_pair:
            return 'overpair' if hero_ranks[0] > top else 'underpair'
        matched = [r for r in board_desc if r in hero_set and board_counts[r] >= 1]
        if not matched:
            return 'board_pair_only'            # par só do board; hero não pareou
        m = max(matched)
        if m == board_desc[0]:
            return 'top_pair'
        if len(board_desc) >= 2 and m == board_desc[1]:
            return 'second_pair'
        if len(board_desc) >= 3 and m == board_desc[2]:
            return 'third_pair'
        return 'low_pair'
    # carta alta
    if board_desc and all(h > top for h in hero_ranks):
        return 'overcards'
    return 'air'


def hand_strength(hero, board):
    """Força da mão do hero no board. hero: 2 strings; board: 3-5 strings.

    Dict: `category`/`category_name`/`score` (do eval7), `made` (rótulo relativo),
    `draws` (gavetas + outs) e `outs`. Levanta ValueError para entrada inválida e
    retorna None se houver carta repetida entre hero e board (leitura inconsistente).
    """
    hc, bc = _cards(hero), _cards(board)
    if len(hc) != 2 or not 3 <= len(bc) <= 5:
        raise ValueError('hero precisa de 2 cartas e board de 3-5')
    if len(set(hc) | set(bc)) != len(hc) + len(bc):
        return None
    score = eval7(hc + bc)
    draws = _draws(hc, bc)
    return dict(category=score[0], category_name=CATEGORY_NAMES[score[0]], score=score,
                made=_relative_label(hc, bc, score), draws=draws, outs=draws['outs'])


# Range de CONTINUAÇÃO: quais mãos do vilão seguem apostando no board. Pesos de
# estudo CONSERVADORES (não é saída de solver): valor sempre segue; mão média segue
# pela metade; draw forte blefa/segue; draw fraco pouco; ar entra só como blefe, numa
# fração que CAI do flop ao river (o range polariza). Ajustáveis num lugar só.
_CONT_VALUE = ('set', 'trips', 'two_pair', 'overpair', 'top_pair',
               'straight', 'flush', 'full_house', 'quads', 'straight_flush')
_CONT_MEDIUM = ('second_pair', 'third_pair', 'low_pair', 'underpair')
CONTINUATION_WEIGHTS = dict(value=1.0, medium=0.5, weak_draw=0.4,
                            bluff_FLOP=0.25, bluff_TURN=0.15, bluff_RIVER=0.10)


# Afinamento por TEXTURA (direção da skill poker-fundamentos-posflop): a textura muda
# QUEM aposta no board, então escala o AR (blefe) e as MÃOS MÉDIAS do range de aposta.
# - SECO (rainbow desconexo): o agressor aposta largo com range MESCLADO -> mais ar e
#   value fino na range de aposta -> hero defende mais largo.
# - MOLHADO (two-tone+/conectado/flush possível): a range POLARIZA e dá mais check ->
#   menos ar PURO apostando (os draws já entram cheios) e média faz pote-controle.
# - PAREADO (e seco): c-bet largo e pequeno, mas valor é mais raro.
# Fatores conservadores e ajustáveis (não são solver); valor e draw forte seguem 1.0.
_TEXTURE_FACTORS = dict(dry=dict(bluff=1.30, medium=1.15),
                        paired=dict(bluff=1.15, medium=0.90),
                        wet=dict(bluff=0.60, medium=0.70),
                        neutral=dict(bluff=1.0, medium=1.0))


def _texture_key(board_class):
    """Classe de textura p/ os fatores: molhado (draw-heavy) domina; depois pareado;
    senão seco."""
    if (board_class['flush_possible'] or board_class['flush_count'] >= 2
            or board_class['straightish'] >= 3):
        return 'wet'
    if board_class['paired']:
        return 'paired'
    return 'dry'


def _continuation_multiplier(made, draws, street, factors=None):
    """Fração do peso do combo que segue no range de APOSTA do vilão (ver pesos acima).
    É o máximo entre o tier da mão feita e o do draw (uma mão feita COM draw segue cheia).
    `factors` (opcional) escala o AR e a MÉDIA por textura; ausente = neutro (1.0)."""
    factors = factors or _TEXTURE_FACTORS['neutral']
    strong_draw = bool(draws['combo'] or draws['flush_draw'] or draws['oesd'])
    weak_draw = bool(draws['gutshot'] or draws['backdoor_flush'])
    if made in _CONT_VALUE:
        cat = CONTINUATION_WEIGHTS['value']
    elif made in _CONT_MEDIUM:
        cat = min(1.0, CONTINUATION_WEIGHTS['medium'] * factors['medium'])
    else:
        cat = min(1.0, CONTINUATION_WEIGHTS.get('bluff_%s' % street, 0.20) * factors['bluff'])
    draw = (CONTINUATION_WEIGHTS['value'] if strong_draw
            else CONTINUATION_WEIGHTS['weak_draw'] if weak_draw else 0.0)
    return max(cat, draw)


def narrow_to_continuation(range_combos, board, *, street=None):
    """Estreita o range PRÉ-FLOP do vilão para o range de CONTINUAÇÃO no board
    (conceito de equity robusta vs não-robusta): reponderação por tier — valor segue
    cheio, mão média pela metade, draws fortes seguem, draws fracos pouco, ar entra só
    como blefe por rua. Os pesos de ar/média são afinados pela TEXTURA (ver
    `_TEXTURE_FACTORS`). Descarta combos BLOQUEADOS pelo board (card removal). Recebe e
    devolve a forma normalizada [(frozenset, peso)]. Devolve lista (talvez vazia)."""
    street = street or {3: 'FLOP', 4: 'TURN', 5: 'RIVER'}.get(len(board))
    try:
        factors = _TEXTURE_FACTORS[_texture_key(classify_board(board))]
    except (ValueError, KeyError, TypeError):
        factors = _TEXTURE_FACTORS['neutral']
    out = []
    for combo, w in range_combos or ():
        if w <= 0:
            continue
        try:
            s = hand_strength(list(combo), board)
        except (ValueError, KeyError, TypeError):
            continue
        if s is None:                      # combo bloqueado pelo board -> impossível
            continue
        m = _continuation_multiplier(s['made'], s['draws'], street, factors)
        if m > 0:
            out.append((combo, w * m))
    return out
