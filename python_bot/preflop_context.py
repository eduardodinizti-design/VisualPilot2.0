"""Rastreador do AGRESSOR pré-flop por mão (estado ENTRE frames).

Um frame pós-flop sozinho não carrega a ação pré-flop; para saber o range do vilão
num pote de UM raise só é preciso LEMBRAR quem abriu. Este rastreador observa os
frames PRÉ-FLOP (sem board) de cada mão, anota o último agressor, quantos níveis de
aposta houve e o stack do vilão, e CONGELA isso quando o board aparece. É
best-effort: se nenhum frame pré-flop capturar a aposta do abridor (OCR/cadência),
o agressor fica desconhecido e o pós-flop cai na Fase 1. Puro: não captura; recebe
`table_state` já lido.

`villain_open_range` monta o range do vilão (combos do open do pack validado) SÓ no
caso HU, pote de um raise só, com o vilão como agressor — senão devolve (None, motivo)
e o conselho pós-flop segue sem equity (Fase 1).
"""
from preflop_advisor import infer_live_spot, RAISE_FLOOR_BB


class PreflopAggressorTracker:
    """Estado por mesa (chaveado por `table_key`), reiniciado a cada nova mão."""

    def __init__(self):
        self._by_table = {}

    @staticmethod
    def _fresh(hand_key):
        return dict(hand_key=hand_key, aggressor=None, raises=0, hero_aggressor=False,
                    villain_stack=None, villain_position=None, hero_position=None,
                    villain_in_hand=0, frozen=False)

    def update(self, *, table_key, hand_key, table_state, has_board):
        """Processa um frame. Só muta no PRÉ-FLOP (sem board); ao ver o board,
        CONGELA — o contexto resolvido não muda mais (stack/posição pós-flop não o
        substituem, #4). ID ilegível (hand_key None) SUSPENDE, não apaga (#2/#4).
        Devolve o contexto atual (ver `context`)."""
        if hand_key is None:
            return self.context(table_key)
        st = self._by_table.get(table_key)
        if st is None or st['hand_key'] != hand_key:
            st = self._fresh(hand_key)
            self._by_table[table_key] = st
        if has_board or st['frozen']:
            st['frozen'] = True
            return self.context(table_key)

        seats = table_state.get('seats') or {}
        positions = table_state.get('positions') or {}
        bets = {b.get('seat'): b.get('bet_bb') for b in (table_state.get('bets') or [])}
        if positions.get('hero'):
            st['hero_position'] = positions['hero']
        # Participantes vilões NA MÃO (não ocupação da mesa, #3): não-hero com aposta
        # acima da BB (abertura ou call da abertura). Define o HU e identifica o vilão
        # e seu stack mesmo numa mesa cheia após folds (não dá p/ usar "único sentado").
        vparts = [(s, p) for s, p in positions.items()
                  if s != 'hero' and p and isinstance(bets.get(s), (int, float))
                  and bets[s] > RAISE_FLOOR_BB]
        st['villain_in_hand'] = max(st['villain_in_hand'], len(vparts))
        if len(vparts) == 1:
            vseat, vpos = vparts[0]
            st['villain_position'] = vpos
            vstk = (seats.get(vseat) or {}).get('stack_bb')
            if isinstance(vstk, (int, float)) and vstk > (st['villain_stack'] or 0):
                st['villain_stack'] = vstk          # maior leitura pré-flop ~ stack inicial

        spot = infer_live_spot(table_state)
        s = spot.get('spot')
        if s in ('vs_open', 'vs_open_shove'):
            st['aggressor'] = spot['opener']
            st['hero_aggressor'] = False
            st['raises'] = max(st['raises'], 1)
        elif s == 'vs_3bet':
            st['raises'] = max(st['raises'], 2)         # reraise: não é um raise só
        elif s == 'abstain' and spot.get('reason') == 'HERO_OPENED_NO_RERAISE':
            st['aggressor'] = 'hero'
            st['hero_aggressor'] = True
            st['raises'] = max(st['raises'], 1)
        elif s == 'abstain':
            st['raises'] = max(st['raises'], 2)         # 4bet/multiway: desqualifica
        # first_in: ninguém abriu ainda
        return self.context(table_key)

    def context(self, table_key):
        """Snapshot: aggressor (posição ou 'hero'/None), raises, hero_aggressor,
        villain_stack/position, hero_position, heads_up (UM vilão NA MÃO),
        single_raised (um nível de raise)."""
        st = self._by_table.get(table_key)
        if st is None:
            return None
        return dict(aggressor=st['aggressor'], raises=st['raises'],
                    hero_aggressor=st['hero_aggressor'], villain_stack=st['villain_stack'],
                    villain_position=st['villain_position'], hero_position=st['hero_position'],
                    heads_up=st['villain_in_hand'] == 1, single_raised=st['raises'] == 1,
                    hand_key=st['hand_key'])


def villain_open_range(advisor, ctx, *, mode='chip_ev', stage='mid', players=9,
                       spread=None, hero_stack_bb=None):
    """Range do vilão p/ a equity pós-flop, SÓ no HU, pote de um raise só, vilão
    agressor. Usa o stack do vilão rastreado (ou o do hero como proxy, sinalizado).
    `mode/stage/spread` devem casar com o contexto do hero (o pack só tem open em
    15/25bb; chip_ev só no stage 'mid'; ICM exige spread) — fora disso devolve motivo
    e o pós-flop fica na Fase 1. Devolve (combos, meta) ou (None, motivo)."""
    if ctx is None:
        return None, 'NO_CONTEXT'
    if not ctx['heads_up']:
        return None, 'NOT_HEADS_UP'
    if not ctx['single_raised']:
        return None, 'NOT_SINGLE_RAISED'
    if ctx['hero_aggressor']:
        return None, 'HERO_WAS_AGGRESSOR'       # vilão deu flat: range de call, não de open
    pos = ctx['aggressor']
    if not pos or pos == 'hero':
        return None, 'AGGRESSOR_UNKNOWN'
    vstack = ctx.get('villain_stack')
    proxy = False
    if not isinstance(vstack, (int, float)):
        if not isinstance(hero_stack_bb, (int, float)):
            return None, 'VILLAIN_STACK_UNKNOWN'
        vstack, proxy = hero_stack_bb, True
    combos, node = advisor.open_range_combos(pos, vstack, mode=mode, stage=stage,
                                             players=players, spread=spread)
    if combos is None:
        return None, node                        # motivo (NO_OPEN_NODE_FOR_CONTEXT / STACK_UNKNOWN)
    meta = dict(kind='open', aggressor=pos, villain_stack_bb=vstack, stack_proxy=proxy,
                node=node['id'], combos=len(combos))
    return combos, meta


def _villain_stack(ctx, hero_stack_bb):
    """Stack do vilão rastreado, ou o do hero como proxy. (stack, é_proxy) | (None, _)."""
    vstack = ctx.get('villain_stack')
    if isinstance(vstack, (int, float)):
        return vstack, False
    if isinstance(hero_stack_bb, (int, float)):
        return hero_stack_bb, True
    return None, False


def villain_postflop_range(advisor, ctx, *, mode='chip_ev', stage='mid', players=9,
                           spread=None, hero_stack_bb=None):
    """Range do vilão p/ a equity pós-flop no HU, pote de um raise só, escolhendo:

    - vilão ABRIU (hero deu flat): range de OPEN da posição do vilão.
    - hero ABRIU (vilão deu flat): range de FLAT do vilão vs o open do hero (vs_open).

    Devolve (combos, meta{kind}) ou (None, motivo). Fora do HU single-raised, ou sem
    posições/nó no pack, devolve motivo e o pós-flop fica na Fase 1."""
    if ctx is None:
        return None, 'NO_CONTEXT'
    if not ctx['heads_up']:
        return None, 'NOT_HEADS_UP'
    if not ctx['single_raised']:
        return None, 'NOT_SINGLE_RAISED'
    vstack, proxy = _villain_stack(ctx, hero_stack_bb)
    if vstack is None:
        return None, 'VILLAIN_STACK_UNKNOWN'
    if not ctx['hero_aggressor']:
        return villain_open_range(advisor, ctx, mode=mode, stage=stage,
                                  players=players, spread=spread, hero_stack_bb=hero_stack_bb)
    # Hero abriu, vilão pagou: range de flat do vilão vs o open do hero.
    vpos, hpos = ctx.get('villain_position'), ctx.get('hero_position')
    if not vpos or not hpos:
        return None, 'POSITIONS_UNKNOWN'
    combos, node = advisor.call_range_combos(vpos, hpos, vstack, mode=mode, stage=stage,
                                             players=players, spread=spread)
    if combos is None:
        return None, node
    meta = dict(kind='call', villain_position=vpos, opener_position=hpos,
                villain_stack_bb=vstack, stack_proxy=proxy, node=node['id'], combos=len(combos))
    return combos, meta
