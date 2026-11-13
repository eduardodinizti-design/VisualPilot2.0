"""Observador de estado integrado (Camada A, sem cliques).

Amarra as leituras de UM frame à MESMA mesa, MESMA mão e ao momento atual,
usando o `HandTracker`. Produz uma visão estruturada e HONESTA:

  mesa identificada → mão identificada → campos confirmados
  → contexto reconhecido → consulta de estratégia OU abstenção

...explicando o que SABE, o que MUDOU e por que ficou PENDENTE. Ausência nunca é
inventada: ID ilegível mantém a mão (pendente), campo None fica pendente, e uma
troca de `table_ref` na mesma tela é sinalizada (possível troca de mesa/torneio).

É PURO em relação à visão: recebe o resultado de `table_advisor.advise_table`
(mais uma chave de mesa estável) e devolve a visão. Não captura, não lê tela,
não clica.
"""
from table_reading.hand_tracking import HandTracker
from table_reading.hand_reconcile import HandReconciler, street_from_board, STREETS

_ABSTAIN = ('abstain', None)


def _board_cards(board):
    """Cartas confirmadas do board, tratando o formato dict (de advise_table) ou
    lista. Vazio quando não confirmado — nunca conta chaves do dict como cartas."""
    if isinstance(board, dict):
        return board.get('cards') or []
    return list(board) if board else []


def _board_street(board):
    """Street HONESTA (nunca inventa 'river' de len(dict)):
    - dict com `street` confirmada → usa.
    - não confirmada + centro VAZIO (sem candidatos de carta) → 'preflop' (não há
      board = pré-flop; ex.: all-in pré-flop). Mesma evidência que o advisor usa.
    - não confirmada + candidatos presentes (board ilegível) → None (pendente).
    - lista → pela contagem de cartas.
    """
    if isinstance(board, dict):
        s = board.get('street')
        s = s.lower() if isinstance(s, str) else s   # reader usa FLOP/TURN/RIVER
        if s in STREETS:
            return s
        return 'preflop' if not board.get('candidates') else None
    return street_from_board(len(board or []))


def _confirmed(value, confidence):
    return value is not None and confidence not in _ABSTAIN


def _field(name, value, confidence=None, source=None):
    return dict(name=name, value=value, confidence=confidence, source=source,
                confirmed=_confirmed(value, confidence))


class StateObserver:
    """Mantém o estado temporal por mesa e monta a visão por frame."""

    def __init__(self):
        self.tracker = HandTracker()
        self._prev = {}          # table_key -> visão anterior
        self._last_ref = {}      # table_key -> ultimo table_ref visto
        self._recon = {}         # table_key -> HandReconciler da mão atual (Camada B)

    def observe(self, result, *, table_key):
        """`result` = saída de advise_table. `table_key` = identidade ESTÁVEL da
        mesa (ex.: source_key do HWND + índice do crop). Retorna a StateView."""
        if not result.get('is_table', True):
            return dict(is_table=False, table=dict(key=table_key),
                        advice=result.get('advice', {}),
                        pending=['NOT_A_TABLE'], changed=[])

        hand = result.get('hand') or {}
        state = result.get('table_state') or {}
        ref = hand.get('table_ref')

        event = self.tracker.observe(
            table_key, hand.get('hand_number'), hand_id=hand.get('hand_id'),
            observation=result)
        cur = self.tracker.current(table_key) or {}

        # Camada B: reconciliação de ações ao longo da MÃO. Mão nova = reconciler
        # novo; frame suspeito (id regredido) não entra. Nunca reconstrói a
        # sequência exata — só o que os números provam, e marca GAP quando não
        # fecham (ações entre frames que a amostragem perdeu).
        ev = event['event']
        if ev in ('new_table', 'new_hand') or table_key not in self._recon:
            self._recon[table_key] = HandReconciler()
        recon = self._recon[table_key]
        step = recon.add(self._snapshot(result, state)) if ev != 'suspect_id' else []
        reconcile = dict(street=recon.street(), step=step,
                         total_events=len(recon.events))

        fields = self._fields(result, state)
        pending = self._pending(event, result, state, fields, table_key, ref, step)
        view = dict(
            is_table=True,
            table=dict(key=table_key, ref=ref,
                       ref_confirmed=ref is not None,
                       number=cur.get('hand_number')),
            hand=dict(event=event['event'], number=event.get('hand_number'),
                      id=event.get('hand_id'), frame=event.get('frame')),
            fields=fields,
            context=dict(context=result.get('context'),
                         tournament=result.get('tournament')),
            reconcile=reconcile,
            advice=result.get('advice', {}),
            pending=pending,
        )
        view['changed'] = self._changed(table_key, view)
        self._prev[table_key] = view
        if ref is not None:
            self._last_ref[table_key] = ref
        return view

    # ---- montagem dos campos (proveniência por campo) -------------------
    def _fields(self, result, state):
        f = []
        hero = result.get('hero_cards')
        f.append(_field('hero_cards', hero if hero and all(hero) else None,
                        'high' if hero and all(hero) else 'abstain', 'cards'))
        cards = _board_cards(result.get('board'))
        f.append(_field('board', cards or None,
                        'high' if cards else 'abstain', 'cards'))
        for key, sub in (('pot', 'pot_bb'), ('to_call', 'to_call_bb')):
            d = state.get(key) or {}
            f.append(_field(key, d.get(sub), d.get('confidence'), d.get('source')))
        dealer = state.get('dealer') or {}
        f.append(_field('dealer', dealer.get('seat'), dealer.get('confidence'),
                        dealer.get('source')))
        positions = state.get('positions') or {}
        f.append(_field('hero_position', positions.get('hero'),
                        'high' if positions.get('hero') else 'abstain', 'positions'))
        # Stacks: resumo ocupado vs legível, com os assentos pendentes nomeados.
        seats = state.get('seats') or {}
        occ = [n for n, s in seats.items() if s.get('occupied')]
        none_stacks = [n for n in occ if (seats[n].get('stack_bb') is None)]
        f.append(dict(name='stacks', value='%d/%d legiveis' % (len(occ) - len(none_stacks), len(occ)),
                      confidence='high' if not none_stacks else 'partial',
                      source='ocr', confirmed=(len(occ) > 0 and not none_stacks),
                      pending_seats=none_stacks))
        return f

    # ---- snapshot para a reconciliação (só campos legíveis) -------------
    def _snapshot(self, result, state):
        seats = state.get('seats') or {}
        # Apenas stacks LEGÍVEIS entram; assento ocluído fica de fora (não chuta).
        stacks = {n: s.get('stack_bb') for n, s in seats.items()
                  if s.get('occupied') and s.get('stack_bb') is not None}
        vals = [b.get('bet_bb') for b in (state.get('bets') or [])
                if isinstance(b.get('bet_bb'), (int, float))]
        return dict(pot_bb=(state.get('pot') or {}).get('pot_bb'),
                    street=_board_street(result.get('board')),   # None quando não confirma
                    stacks=stacks,
                    bets_bb=(round(sum(vals), 2) if vals else None))

    # ---- por que pendente (ausência NUNCA inventada) --------------------
    def _pending(self, event, result, state, fields, table_key, ref, step=()):
        pending = []
        ev = event['event']
        if ev == 'pending_id':
            pending.append('HAND_ID_PENDING: ID ilegivel; mantida a mao atual')
        elif ev == 'suspect_id':
            pending.append('HAND_ID_REGREDIU: ignorado (ids so crescem)')
        last_ref = self._last_ref.get(table_key)
        if ref is not None and last_ref is not None and ref != last_ref:
            pending.append('TABLE_REF_MUDOU: possivel troca de mesa/torneio (%s->%s)'
                           % (last_ref, ref))
        # Board com candidatos de carta mas não confirmado = ilegível (pendente);
        # centro vazio é pré-flop (não pendente).
        board = result.get('board')
        if (isinstance(board, dict) and board.get('street') not in STREETS
                and board.get('candidates') and not board.get('cards')):
            pending.append('BOARD_ILEGIVEL: %d candidato(s) de carta nao confirmados'
                           % len(board['candidates']))
        adv = result.get('advice') or {}
        if adv.get('status') in ('ABSTAIN', 'SKIP'):
            pending.append('CONSELHO_%s: %s' % (adv.get('status'), adv.get('reason')))
        for fld in fields:
            if not fld['confirmed'] and fld['name'] in ('hero_cards', 'to_call'):
                pending.append('%s_PENDENTE' % fld['name'].upper())
            if fld['name'] == 'stacks' and fld.get('pending_seats'):
                pending.append('STACKS_PENDENTES: %s' % ','.join(fld['pending_seats']))
        # Reconciliação (Camada B): gap = ações entre frames não explicadas pelos
        # números; pote regredido = possível fronteira de mão perdida.
        for e in step:
            if e.get('event') == 'reconciliation' and e.get('status') == 'gap':
                pending.append('RECONCILIACAO_GAP: acoes entre frames nao explicadas '
                               '(saiu %s vs esperado %s)' % (e['committed'], e['expected']))
            elif e.get('event') == 'pot_regressed':
                pending.append('POTE_REGREDIU %s: possivel fronteira de mao perdida'
                               % e['delta'])
        return pending

    # ---- o que mudou vs o frame anterior --------------------------------
    def _changed(self, table_key, view):
        prev = self._prev.get(table_key)
        changed = []
        if prev is None:
            changed.append('MESA_NOVA')
            return changed
        if view['hand']['event'] in ('new_hand', 'new_table'):
            changed.append('MAO_NOVA #%s' % view['hand']['number'])
        pv = {f['name']: f['value'] for f in prev['fields']}
        for f in view['fields']:
            if f['value'] != pv.get(f['name']):
                changed.append('%s: %r -> %r' % (f['name'], pv.get(f['name']), f['value']))
        pa = (prev.get('advice') or {}).get('recommended')
        na = (view.get('advice') or {}).get('recommended')
        if pa != na:
            changed.append('CONSELHO: %r -> %r' % (pa, na))
        # Eventos da reconciliação (provados pelos números): street e commits.
        for e in (view.get('reconcile') or {}).get('step', ()):
            if e.get('event') == 'street_advanced':
                changed.append('STREET: %s->%s' % (e['from'], e['to']))
            elif e.get('event') == 'seat_committed':
                changed.append('%s comprometeu %sbb' % (e['seat'], e['amount']))
        return changed


def render(view):
    """Texto humano da visão (mesa→mão→campos→contexto→conselho, com mudou/pendente)."""
    if not view.get('is_table', True):
        return 'NAO-MESA (%s)' % view['table'].get('key')
    t, h = view['table'], view['hand']
    lines = ['MESA %s%s | MAO #%s [%s] frame %s' % (
        t.get('key'), (' ref=%s' % t['ref']) if t.get('ref') else ' (ref pendente)',
        h.get('number'), h.get('event'), h.get('frame'))]
    rec = view.get('reconcile') or {}
    if rec.get('street'):
        lines[-1] += ' | street %s' % rec['street']
    conf = [f for f in view['fields'] if f['confirmed']]
    lines.append('  confirmados: ' + (', '.join(
        '%s=%s' % (f['name'], f['value']) for f in conf) or '(nenhum)'))
    adv = view.get('advice') or {}
    lines.append('  conselho: %s %s' % (adv.get('status'),
                 adv.get('recommended') or adv.get('reason') or ''))
    if view.get('changed'):
        lines.append('  mudou: ' + '; '.join(view['changed']))
    if view.get('pending'):
        lines.append('  pendente: ' + '; '.join(view['pending']))
    return '\n'.join(lines)
