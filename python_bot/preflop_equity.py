"""Motor próprio de equity pré-flop (mão vs range, all-in até o showdown).

Usado para SINTETIZAR o call-off quando o pack não tem o nó `vs_3bet` no stack
curto: o hero abriu, o vilão deu re-shove, e a decisão é pagar/foldar. A regra é
a da teoria de push/fold (skill poker-preflop-mtt): *pago se a minha equity contra
o range de shove do vilão for maior que as pot odds*. O range do vilão vem do nó
`3bet_shove` validado (Nash) do próprio pack — não inventamos números.

Avaliador de 7 cartas exato (categorias de poker), equity por Monte Carlo com
semente fixa (determinístico para teste). Tudo chip-EV: ICM não é aplicado aqui
(quem usa sinaliza). Sem captura, sem clique.
"""
from collections import Counter
import random

RANK_CHARS = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
              'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
SUITS = ('s', 'h', 'd', 'c')
FULL_DECK = tuple((r, s) for r in range(2, 15) for s in SUITS)


def parse_card(text):
    """'As' -> (14, 's'). Aceita só rank+naipe de uma carta. Levanta ValueError."""
    t = (text or '').strip()
    if len(t) != 2 or t[0].upper() not in RANK_CHARS or t[1].lower() not in SUITS:
        raise ValueError('carta invalida: %r' % (text,))
    return (RANK_CHARS[t[0].upper()], t[1].lower())


def hand_to_combos(hand):
    """'AKs'->4 combos suited; 'AKo'->12 offsuit; 'AA'->6 pares. combo=frozenset."""
    h = hand.strip()
    r1 = RANK_CHARS[h[0].upper()]
    if len(h) == 2:                                   # par
        if h[0].upper() != h[1].upper():
            raise ValueError('par invalido: %r' % (hand,))
        return [frozenset({(r1, a), (r1, b)})
                for i, a in enumerate(SUITS) for b in SUITS[i + 1:]]
    r2 = RANK_CHARS[h[1].upper()]
    kind = h[2].lower()
    if kind == 's':
        return [frozenset({(r1, s), (r2, s)}) for s in SUITS]
    if kind == 'o':
        return [frozenset({(r1, a), (r2, b)}) for a in SUITS for b in SUITS if a != b]
    raise ValueError('mao invalida: %r' % (hand,))


def _straight_high(ranks):
    """Carta mais alta de uma sequência de 5 (A conta como 1 e 14), ou None."""
    rs = set(ranks)
    if 14 in rs:
        rs.add(1)
    for top in range(14, 4, -1):
        if all(r in rs for r in range(top, top - 5, -1)):
            return top
    return None


def eval7(cards):
    """Score comparável (maior = melhor) da melhor mão de 5 entre 7 cartas.

    Tupla (categoria, desempates...). Categorias: 8 straight flush, 7 quadra,
    6 full house, 5 flush, 4 sequência, 3 trinca, 2 dois pares, 1 par, 0 carta alta.
    """
    ranks = [c[0] for c in cards]
    by_suit = {}
    for r, s in cards:
        by_suit.setdefault(s, []).append(r)

    flush_suit = next((s for s, rs in by_suit.items() if len(rs) >= 5), None)
    if flush_suit is not None:
        sf = _straight_high(by_suit[flush_suit])
        if sf is not None:
            return (8, sf)

    counts = Counter(ranks)
    # ordena por (quantidade, rank) desc -> grupos dominantes primeiro
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    quads = [r for r, c in counts.items() if c == 4]
    trips = sorted((r for r, c in counts.items() if c == 3), reverse=True)
    pairs = sorted((r for r, c in counts.items() if c == 2), reverse=True)

    if quads:
        q = quads[0]
        kicker = max(r for r in ranks if r != q)
        return (7, q, kicker)
    if trips and (len(trips) >= 2 or pairs):          # full house
        t = trips[0]
        pair = trips[1] if len(trips) >= 2 else pairs[0]
        return (6, t, pair)
    if flush_suit is not None:
        top5 = sorted(by_suit[flush_suit], reverse=True)[:5]
        return (5, tuple(top5))
    st = _straight_high(ranks)
    if st is not None:
        return (4, st)
    if trips:
        t = trips[0]
        kick = sorted((r for r in ranks if r != t), reverse=True)[:2]
        return (3, t, tuple(kick))
    if len(pairs) >= 2:
        hi, lo = pairs[0], pairs[1]
        kicker = max(r for r in ranks if r != hi and r != lo)
        return (2, hi, lo, kicker)
    if pairs:
        p = pairs[0]
        kick = sorted((r for r in ranks if r != p), reverse=True)[:3]
        return (1, p, tuple(kick))
    return (0, tuple(sorted(ranks, reverse=True)[:5]))


def range_from_node(node, hands_index, actions=('all_in', 'call')):
    """Combos (frozenset) + peso do range do nó, somando as frequências das ações
    de continuação (padrão: all_in + call). Retorna lista [(combo, peso)]."""
    out = []
    avail = [a for a in actions if a in node.get('actions', ())]
    if not avail:
        return out
    freq = node['freq']
    for i, hand in enumerate(hands_index):
        w = 0.0
        for a in avail:
            v = freq[a][i]
            if v:
                w += v
        if w > 0:
            for combo in hand_to_combos(hand):
                out.append((combo, w))
    return out


def required_equity(to_call_bb, pot_bb):
    """Pot odds: fração do pote final que o call precisa valer = to_call/(pot+to_call).
    `pot_bb` é o pote já na mesa (inclui o shove do vilão), antes do call do hero."""
    if not isinstance(to_call_bb, (int, float)) or not isinstance(pot_bb, (int, float)):
        return None
    if to_call_bb <= 0 or pot_bb < 0:
        return None
    denom = pot_bb + to_call_bb
    return to_call_bb / denom if denom > 0 else None


def equity_vs_range(hero_cards, range_combos, *, iters=8000, seed=0, board=()):
    """Equity (win+tie/2) do hero all-in até o showdown contra um range ponderado.

    hero_cards: 2 strings ('As','7h'). range_combos: [(frozenset{(r,s),(r,s)}, peso)].
    Combos que colidem com as cartas do hero/board são descartados. Monte Carlo com
    semente fixa (determinístico). Retorna float em [0,1], ou None se range vazio.
    """
    hero = [parse_card(c) if isinstance(c, str) else tuple(c) for c in hero_cards]
    board = [parse_card(c) if isinstance(c, str) else tuple(c) for c in board]
    dead0 = set(hero) | set(board)
    combos, weights = [], []
    for combo, w in range_combos:
        cc = tuple(combo)
        if w > 0 and not (set(cc) & dead0):
            combos.append(cc)
            weights.append(w)
    if not combos:
        return None
    rng = random.Random(seed)
    cum, acc = [], 0.0
    for w in weights:
        acc += w
        cum.append(acc)
    total = acc
    deck_base = [c for c in FULL_DECK if c not in dead0]
    need = 5 - len(board)
    score = 0.0
    for _ in range(iters):
        # amostra ponderada de um combo do vilão
        x = rng.random() * total
        lo, hi = 0, len(cum)
        while lo < hi:
            mid = (lo + hi) // 2
            if x < cum[mid]:
                hi = mid
            else:
                lo = mid + 1
        v = combos[lo]
        vset = set(v)
        # distribui o board a partir do baralho vivo (sem as cartas do vilão)
        deck = [c for c in deck_base if c not in vset]
        drawn = rng.sample(deck, need) if need > 0 else []
        full = list(board) + drawn
        hs = eval7(hero + full)
        vs = eval7(list(v) + full)
        if hs > vs:
            score += 1.0
        elif hs == vs:
            score += 0.5
    return score / iters
