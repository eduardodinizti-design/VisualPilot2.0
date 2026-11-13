"""Coordenador de ação em DRY-RUN (passo 1 da execução).

Pega a recomendação do conselheiro e a resolve no BOTÃO de ação na tela
(Fold/Check/Call/Bet/Raise), devolvendo a coordenada do clique PRETENDIDO —
**sem enviar nada**. Serve para conferir, em várias mãos, que o bot miraria o
botão certo antes de armar o clique real.

- Só planeja quando é a vez do hero (linha de botões EXPERIMENTAL_BUTTON_ROW); se
  for painel de preseleção (F/C) ou não houver botões, abstém (não inventa turno).
- Bet/Raise com valor é MULTI-ETAPA (abre painel → valor → confirma); o plano
  marca `REQUIRES_SIZING_MULTISTEP` — não é um clique só.
- `DryRunInput` implementa a interface do adaptador do cursor mas REGISTRA o
  clique em vez de enviar; permite rodar o fluxo do coordenador de cursor ponta a
  ponta com zero input real.
"""
import time

from table_reading.action_buttons import read_action_buttons
from screen_coords import frame_to_screen, rect_frame_to_screen

# Recomendação do advisor -> rótulo do botão de ação.
_ACTION_MAP = {
    'fold': 'FOLD', 'check': 'CHECK', 'call': 'CALL', 'limp': 'CALL',
    'bet': 'BET', 'raise': 'RAISE', 'open_raise': 'RAISE', '3bet': 'RAISE',
    '4bet': 'RAISE', 'three_bet': 'RAISE', 'four_bet': 'RAISE',
    'isolate': 'RAISE', 'iso': 'RAISE',
    'all_in': 'RAISE', 'allin': 'RAISE', 'open_shove': 'RAISE', 'shove': 'RAISE',
    '3bet_shove': 'RAISE', '4bet_shove': 'RAISE',
    'three_bet_shove': 'RAISE', 'four_bet_shove': 'RAISE',
}
# Qualquer agressão com valor é MULTI-ETAPA (nunca clique único), mesmo sob outro
# nome; os *shove também são ALL_IN. Nomes das fontes estratégicas normalizados
# aqui sem mudar a semântica (não vira clique único).
_SIZING = {'bet', 'raise', 'open_raise', '3bet', '4bet', 'three_bet', 'four_bet',
           'isolate', 'iso', 'all_in', 'allin', 'open_shove', 'shove',
           '3bet_shove', '4bet_shove', 'three_bet_shove', 'four_bet_shove'}
_ALL_IN = {'all_in', 'allin', 'open_shove', 'shove',
           '3bet_shove', '4bet_shove', 'three_bet_shove', 'four_bet_shove'}


def _norm_amount(amount):
    """Valor normalizado p/ comparação (float arredondado, ou str, ou None)."""
    if isinstance(amount, (int, float)):
        return round(float(amount), 2)
    if amount is None:
        return None
    try:
        return round(float(str(amount).replace(',', '.')), 2)
    except (ValueError, TypeError):
        return str(amount)


def decision_identity(table_key, hand, action, amount, unit):
    """Assinatura observável de UMA decisão: mesa + mão + ação + valor + unidade.

    Usada igual pelo executor (como `source_key` da intenção) e pelo validator ao
    vivo (como `identity` devolvido). Se QUALQUER parte mudar — inclusive o valor
    do Call com o botão na mesma coordenada — a revalidação na chegada detecta
    IDENTITY_CHANGED e cancela o clique."""
    return (table_key, hand, action, _norm_amount(amount), unit)


def map_advice_to_action(recommended):
    """(ação, caveats) do rótulo recomendado, ou (None, []) se não mapear."""
    if not recommended:
        return None, []
    key = str(recommended).strip().lower().replace('-', '_').replace(' ', '_')
    action = _ACTION_MAP.get(key)
    caveats = []
    if key in _SIZING:
        caveats.append('REQUIRES_SIZING_MULTISTEP')   # não é clique único
    if key in _ALL_IN:
        caveats.append('ALL_IN')
    return action, caveats


def plan_from_buttons(buttons_result, advice, *, origin=(0, 0),
                      window_rect=None, frame_size=None):
    """Plano de ação PURO a partir dos botões já lidos + o conselho.

    `origin` = canto (x,y) do crop no FRAME. Com `window_rect` (lógico) +
    `frame_size` (físico), também devolve `screen_rect`/`screen_center` na
    coordenada do cursor (via screen_coords), prontos para o SendInput."""
    status = (advice or {}).get('status')
    rec = (advice or {}).get('recommended')
    if status != 'ADVICE' or not rec:
        return dict(ok=False, plan=None, reason='SEM_ACAO_RECOMENDADA:%s' % status)
    brow = (buttons_result or {}).get('status')
    if brow != 'EXPERIMENTAL_BUTTON_ROW':
        return dict(ok=False, plan=None, reason='NAO_E_VEZ_DO_HERO_OU_SEM_BOTOES:%s' % brow)
    action, caveats = map_advice_to_action(rec)
    if action is None:
        return dict(ok=False, plan=None, reason='CONSELHO_NAO_MAPEADO:%s' % rec)

    buttons = buttons_result.get('buttons') or []

    def find(a):
        return next((b for b in buttons if b.get('action') == a), None)

    # Equivalências SÓ nas direções seguras:
    # - CALL -> CHECK: se o rótulo é CHECK (e não CALL), a UI prova que não há
    #   aposta a pagar (to_call=0); checar é grátis e correto.
    # - RAISE -> BET: ambas são agressão com sizing (multi-etapa, já sinalizado).
    # NUNCA CHECK -> CALL: um botão CALL significa que HÁ aposta; clicar CALL quando
    # se queria CHECK paga um valor desconhecido (bug reproduzido: CHECK + CALL 50BB).
    btn = find(action)
    if btn is None and action == 'CALL':
        btn = find('CHECK')
    elif btn is None and action == 'RAISE':
        btn = find('BET')
    if btn is None:
        return dict(ok=False, plan=None,
                    reason='SEM_BOTAO_PARA:%s' % action,
                    disponiveis=[b.get('action') for b in buttons])

    ox, oy = origin
    x, y, bw, bh = btn['box']
    rect = (ox + x, oy + y, bw, bh)                      # no FRAME
    center = (ox + x + bw / 2.0, oy + y + bh / 2.0)
    plan = dict(action=btn.get('action'), button_label=btn.get('label'),
                amount=btn.get('amount'), unit=btn.get('unit'),
                recommended=rec, rect=rect, center=center, caveats=caveats)
    if window_rect is not None and frame_size is not None:
        plan['screen_rect'] = rect_frame_to_screen(rect, window_rect=window_rect,
                                                    frame_size=frame_size)
        plan['screen_center'] = frame_to_screen(center, window_rect=window_rect,
                                                 frame_size=frame_size)
    return dict(ok=True, plan=plan, reason='DRY_RUN_PLANO')


def plan_action(crop, advice, *, origin=(0, 0), window_rect=None, frame_size=None,
                _reader=None):
    """Lê os botões do crop e planeja a ação (dry-run)."""
    reader = _reader or read_action_buttons
    return plan_from_buttons(reader(crop), advice, origin=origin,
                             window_rect=window_rect, frame_size=frame_size)


def describe_plan(result):
    """Linha humana do plano (ou da abstenção). Deixa explícito: NÃO enviado."""
    if not result.get('ok'):
        return 'INTENCAO: (nenhuma) - %s' % result.get('reason')
    p = result['plan']
    cav = (' [%s]' % ', '.join(p['caveats'])) if p['caveats'] else ''
    coord = p.get('screen_center') or p['center']      # tela se houver, senão frame
    onde = 'tela' if p.get('screen_center') else 'frame'
    return ('INTENCAO: %s (conselho=%s) -> clicaria em %s=%s%s  [DRY-RUN, NAO enviado]'
            % (p['action'], p['recommended'], onde,
               tuple(round(c) for c in coord), cav))


class DryRunInput:
    """Adaptador do cursor em DRY-RUN: registra move/click, NUNCA envia input."""

    def __init__(self, bounds=(-100000, -100000, 200000, 200000), pos=(0, 0)):
        self._bounds = bounds
        self.pos = pos
        self.moves = []
        self.clicks = []

    def virtual_bounds(self):
        return self._bounds

    def cursor_pos(self):
        return self.pos

    def move_to(self, x, y, bounds=None):
        self.moves.append((x, y))
        self.pos = (x, y)
        return dict(requested=1, accepted=1, norm=(0, 0))

    def click_once(self, x=None, y=None, bounds=None, hold_s=None):
        if x is not None and y is not None:
            self.pos = (x, y)
        self.clicks.append((x, y))
        return dict(released=True, down_accepted=1, up_accepted=1,
                    moved=dict(requested=1, accepted=1), dry_run=True)
