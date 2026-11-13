"""Executor de ação — arma o clique real com TRAVAS (passo 3).

Default DRY-RUN (DryRunInput): só clica de verdade quando `armed=True` E o
`BotControl` está RUNNING. Garantias:
- Gate `BotControl` (RUNNING); pausa/takeover por hotkey desarma na hora.
- Só FOLD/CALL/CHECK (clique único). RAISE/BET/all-in ficam de fora (precisam do
  fluxo de sizing multi-etapa) → abstém.
- UMA ação por mão (não reaperta a mesma mão).
- Revalidação na chegada + clique único + verificação de efeito ficam no
  `CursorController` (validator/verifier injetados pelo chamador ao vivo).

Este módulo é o núcleo testável; a captura/revalidação ao vivo entram no CLI.
"""
import time

from action_coordinator import plan_from_buttons, decision_identity
from cursor_controller import CursorController, Intent

SINGLE_CLICK_ACTIONS = ('FOLD', 'CALL', 'CHECK')


class ActionExecutor:
    def __init__(self, *, window_rect, bot_control=None, armed=False,
                 arrival_tol=10.0, clock=time.monotonic, call_margin=0.04):
        self.window_rect = window_rect
        self.bot_control = bot_control
        self.armed = bool(armed)
        self.arrival_tol = float(arrival_tol)
        self._clock = clock
        self.call_margin = float(call_margin)   # folga mínima de equity p/ auto-CALL de call-off
        self._sent = set()               # ASSINATURAS de decisão já enviadas

    def plan(self, result, buttons_result, *, origin, frame_size):
        """Plano de ação com as travas de alçada: só clique único (Fold/Call/Check)."""
        p = plan_from_buttons(buttons_result, result.get('advice') or {},
                              origin=origin, window_rect=self.window_rect,
                              frame_size=frame_size)
        if not p['ok']:
            return p
        action = p['plan']['action']
        if action not in SINGLE_CLICK_ACTIONS:
            return dict(ok=False, plan=None,
                        reason='ACAO_MULTI_ETAPA_NAO_ARMADA:%s' % action)
        return p

    def _eligible(self, advice, action):
        """AUTORIZAÇÃO estratégica única p/ auto-clique (só no armado): status ADVICE
        sozinho NÃO basta. FOLD/CHECK não arriscam fichas -> sempre elegíveis. Ações
        que comprometem fichas (CALL) exigem: ou nó VALIDADO, ou um call-off
        sintetizado com folga de equity suficiente. Conselho de referência/não
        validado NÃO auto-clica (só estuda em dry-run)."""
        if action in ('FOLD', 'CHECK'):
            return True, None
        advice = advice or {}
        spot = str(advice.get('spot') or '')
        if spot.startswith('call_off_'):
            # Call-off é validated=False por construção (equity/ICM aproximados):
            # elegível só com folga sobre a equity exigida (borda ruidosa de MC).
            eq = advice.get('equity')
            req = advice.get('required_equity_icm', advice.get('required_equity'))
            if not isinstance(eq, (int, float)) or not isinstance(req, (int, float)):
                return False, 'CALLOFF_SEM_MARGEM'
            if eq - req < self.call_margin:
                return False, 'CALLOFF_NA_FRONTEIRA'
            return True, None
        # Demais CALL/agressões: exige nó validado (não auto-clica referência/deep).
        if not advice.get('validated'):
            return False, 'NAO_VALIDADO'
        return True, None

    def execute(self, result, buttons_result, *, origin, frame_size, input_adapter,
                validator, verifier=None, hand_id=None, table_key=None):
        """Decide e (se armado + gated) executa UM clique via o CursorController.

        Retorna {acted, state?, reasons?, reason?, plan?, dry_run}. `acted` = o
        clique foi disparado (DONE ou UNKNOWN); CANCELLED = não clicou.

        Dedup por ASSINATURA de decisão (mesa+mão+ação+valor): uma decisão nova e
        legítima na mesma mão é distinguível de uma repetição; a mesma assinatura
        não é reenviada. Identidade desconhecida (hand_id None) BLOQUEIA o armado.
        """
        plan_res = self.plan(result, buttons_result, origin=origin, frame_size=frame_size)
        if not plan_res['ok']:
            return dict(acted=False, reason=plan_res['reason'], dry_run=not self.armed)
        plan = plan_res['plan']
        action = plan['action']
        value = (plan.get('amount'), plan.get('unit'))
        sig = (table_key, hand_id, action, value)
        if sig in self._sent:
            return dict(acted=False, reason='JA_AGIU_NESTA_DECISAO', dry_run=not self.armed)
        if self.armed and self.bot_control is not None \
                and not self.bot_control.execution_allowed():
            return dict(acted=False, reason='BOT_PAUSADO', dry_run=False)
        # #5: identidade desconhecida bloqueia a execução real (dry-run só estuda).
        if self.armed and hand_id is None:
            return dict(acted=False, reason='IDENTIDADE_DESCONHECIDA_BLOQUEIA', dry_run=False)
        # #6-exec: gate de elegibilidade estratégica no armado.
        if self.armed:
            ok_elig, why = self._eligible(result.get('advice') or {}, action)
            if not ok_elig:
                return dict(acted=False, reason='NAO_ELEGIVEL:%s' % why, dry_run=False)

        identity = decision_identity(table_key, hand_id, action, value[0], value[1])
        intent = Intent(id='act-%s-%s-%s' % (table_key, hand_id, action),
                        action=action, source_key=identity,
                        target_rect=plan['screen_rect'], deadline=self._clock() + 5.0,
                        hand=hand_id,
                        expected=dict(action=action, amount=value[0], unit=value[1],
                                      table_key=table_key, hand=hand_id))
        ctrl = CursorController(
            input_adapter=input_adapter, validator=validator, verifier=verifier,
            bot_control=(self.bot_control if self.armed else None),
            clock=self._clock, arrival_tol=self.arrival_tol)
        out = ctrl.execute(intent)
        clicked = out['state'] != 'CANCELLED'      # chegou a clicar?
        if clicked:
            self._sent.add(sig)
        return dict(acted=clicked, state=out['state'], reasons=out['reasons'],
                    plan=plan, intent_id=intent.id, dry_run=not self.armed)
