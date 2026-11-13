"""Fluxo supervisionado de inscrição — máquina de estados (Fase 3A).

Coordena UMA rodada de teste sobre UM alvo autorizado, conforme
`ESTRATÉGIA DE INSCRIÇ.txt` §4/§5/§7/§9/§10. É LÓGICA PURA:

- NUNCA envia um clique. `execution_allowed` é sempre False e não há nenhuma
  chamada de input (SetCursorPos/SendInput/mouse_event) neste módulo nem no
  ledger. No piloto, quem clica no cliente é o usuário (spec §2, Etapa F).
- Para em AGUARDANDO CONFIRMAÇÃO e exige autorização explícita do usuário para
  ESTA inscrição; a autorização não se transfere para outro torneio/custo.
- Uma tentativa por rodada; um alvo. Se o alvo ficar inelegível, PARA e explica
  — não troca por outro evento (§4).
- Dinheiro é Decimal exato; as três restrições de custo (§5) são exigidas juntas.

Estados (§7): OBSERVATION → CANDIDATE → DETAILS_CHECKED → RESERVED →
AWAITING_CONFIRMATION → CONFIRMATION_SENT → CONFIRMED.
Saídas: BLOCKED, REJECTED, CANCELLED_BEFORE_SEND, UNKNOWN_RESULT.
"""
import time
from decimal import Decimal

from registration_ledger import (CENT, RegistrationLedger, make_identity,
                                  sum_parcels, to_money)
from session_config import SessionState, evaluate_card

FLOW_STATES = ('OBSERVATION', 'CANDIDATE', 'DETAILS_CHECKED', 'RESERVED',
               'AWAITING_CONFIRMATION', 'CONFIRMATION_SENT', 'CONFIRMED')
FLOW_EXITS = ('BLOCKED', 'REJECTED', 'CANCELLED_BEFORE_SEND', 'UNKNOWN_RESULT')

MODES = ('simulation', 'observation', 'real_supervised')


class RegistrationRound:
    """Uma rodada supervisionada sobre um alvo. Instâncie, depois chame em ordem:
    observe() → check_details() → reserve() → authorize() →
    record_user_action() [real] → reconcile()."""

    def __init__(self, *, round_id, operator, target_name, authorized_cost,
                 currency, config, ledger=None, state=None, bot_control=None,
                 mode='observation', clock=time.monotonic):
        if mode not in MODES:
            raise ValueError('mode inválido: %r' % (mode,))
        self.round_id = round_id
        self.operator = operator
        self.target_name = (target_name or '').strip()
        self.authorized_cost = to_money(authorized_cost)   # a oferta que o usuário autorizou
        self.currency = (currency or '').strip() or None
        self.config = config
        self.ledger = ledger or RegistrationLedger()
        self.state = state or SessionState()
        self.bot_control = bot_control
        self.mode = mode
        self._clock = clock

        self.execution_allowed = False      # invariante: o bot NUNCA clica
        self.flow_state = 'OBSERVATION'
        self.attempts = 0
        self.token = None
        self.identity = None
        self.identity_basis = []
        self.observed = None                 # snapshot do lobby
        self.details = None                  # snapshot dos detalhes
        self.reserve_snapshot = None         # oferta no momento da reserva (p/ revalidar)
        self.authorized = False
        self.history = []                    # trilha de auditoria de transições
        self._log('ROUND_OPEN', mode=mode, target=self.target_name)

    # ---- infra -----------------------------------------------------------
    def _log(self, event, **data):
        self.history.append(dict(event=event, flow_state=self.flow_state,
                                 at_mono=self._clock(), at_wall=time.time(), **data))

    def _block(self, reasons):
        self.flow_state = 'BLOCKED'
        self._log('BLOCKED', reasons=list(reasons))
        return self._result(reasons=list(reasons))

    def _running(self):
        """Gate de segurança (F2): sem RUNNING não se cria nova intenção."""
        if self.bot_control is None:
            return True
        return bool(getattr(self.bot_control, 'execution_allowed', lambda: False)())

    def _result(self, **extra):
        conf, pend, active = self.ledger.committed()
        avail = (self.ledger.available_budget(self.config.daily_budget)
                 if getattr(self.config, 'daily_budget', None) is not None else None)
        base = dict(round_id=self.round_id, flow_state=self.flow_state,
                    execution_allowed=self.execution_allowed, token=self.token,
                    identity=self.identity, identity_basis=list(self.identity_basis),
                    committed_confirmed=str(conf), committed_pending=str(pend),
                    active_commitments=active,
                    available_budget=(str(avail) if avail is not None else None))
        base.update(extra)
        return base

    # ---- ETAPA B: observação / candidato --------------------------------
    def observe(self, card, *, club=None, now_hhmm=None):
        """Lê o cartão do lobby e aplica o filtro de política (evaluate_card).

        Confere que é o ALVO autorizado (um só). BLOQUEIA se a política barrar ou
        se o cartão não for o alvo — sem trocar por evento parecido (§4).
        """
        if self.flow_state != 'OBSERVATION':
            return self._block(['INVALID_FLOW_STATE_FOR_OBSERVE'])
        name = (card.get('name') or '').strip()
        if not self.target_name or name != self.target_name:
            return self._block(['NOT_THE_AUTHORIZED_TARGET'])
        decision = evaluate_card(card, self.config, self.state,
                                 club=club, now_hhmm=now_hhmm)
        self.observed = dict(card=card, club=club, decision=decision)
        if decision['decision'] != 'ELIGIBLE':
            return self._block(decision['reasons'])
        self.flow_state = 'CANDIDATE'
        self._log('CANDIDATE', name=name, buyin=card.get('buyin'))
        return self._result(policy=decision)

    # ---- ETAPA C: detalhes conferidos -----------------------------------
    def check_details(self, details, *, now_hhmm=None):
        """Confere identidade + custo/moeda/modalidade entre lobby e detalhes (§C).

        `details` deve trazer: name, club, modality, buyin OU (parcels[,total]),
        currency, start_time, status. Divergência de custo/identidade bloqueia.
        """
        if self.flow_state != 'CANDIDATE':
            return self._block(['INVALID_FLOW_STATE_FOR_DETAILS'])
        reasons = []
        card = self.observed['card']

        # Identidade verificável (§4): nome + buy-in/horário; nome só não basta.
        ident, basis = make_identity(
            name=details.get('name'), club=details.get('club'),
            modality=details.get('modality'), buyin=details.get('buyin'),
            start_time=details.get('start_time'))
        self.identity, self.identity_basis = ident, basis
        if ident is None:
            reasons.append('IDENTITY_NOT_VERIFIABLE')

        # Moeda explícita e igual à autorizada (§5).
        dcur = (details.get('currency') or '').strip() or None
        if dcur is None:
            reasons.append('CURRENCY_UNKNOWN')
        elif self.currency and dcur != self.currency:
            reasons.append('CURRENCY_MISMATCH')

        # Custo total: aceita buy-in simples OU parcelas conferidas contra o total.
        cost, cost_ok = self._resolve_cost(details)
        if not cost_ok or cost is None:
            reasons.append('COST_UNKNOWN_OR_PARCEL_MISMATCH')
        else:
            # Divergência lobby×detalhes (§C): custo observado no lobby deve bater.
            lobby_cost = to_money(card.get('buyin'))
            if lobby_cost is not None and lobby_cost != cost:
                reasons.append('COST_DIVERGENCE_LOBBY_VS_DETAILS')
            # As TRÊS restrições de §5, exigidas juntas.
            if self.authorized_cost is None:
                reasons.append('NO_AUTHORIZED_COST')
            elif cost != self.authorized_cost:
                reasons.append('COST_DOES_NOT_MATCH_AUTHORIZED_OFFER')
            cap = to_money(getattr(self.config, 'max_entry_buyin', None))
            if cap is None:
                reasons.append('MISSING_ENTRY_CAP')
            elif cost > cap:
                reasons.append('COST_ABOVE_ENTRY_CAP')
            avail = self.ledger.available_budget(getattr(self.config, 'daily_budget', None))
            if avail is None:
                reasons.append('MISSING_SESSION_BUDGET')
            elif cost > avail:
                reasons.append('COST_ABOVE_AVAILABLE_BUDGET')

        # Modalidade consistente entre lobby e detalhes.
        if (card.get('modality') and details.get('modality')
                and card['modality'] != details['modality']):
            reasons.append('MODALITY_DIVERGENCE')

        # Inscrição aberta e não começou; late-reg off no piloto (§4).
        st = (details.get('status') or {}).get('state')
        if st != 'reg_open':
            reasons.append('REGISTRATION_NOT_OPEN_IN_DETAILS')

        # Dedup: já há compromisso ativo para esta identidade? (§4.6/§6)
        if ident is not None and self.ledger.active_for_identity(ident):
            reasons.append('ALREADY_RESERVED_SAME_IDENTITY')

        if reasons:
            return self._block(reasons)
        self.details = dict(details=details, cost=cost)
        self.flow_state = 'DETAILS_CHECKED'
        self._log('DETAILS_CHECKED', identity=ident, cost=str(cost),
                  currency=dcur, basis=basis)
        return self._result(cost=str(cost), currency=dcur)

    def _resolve_cost(self, src):
        """(Decimal, ok) do custo total — buy-in simples ou soma de parcelas (§5)."""
        if src.get('parcels'):
            return sum_parcels(src['parcels'], src.get('total'))
        c = to_money(src.get('buyin'))
        return (c, c is not None)

    # ---- ETAPA E: reserva atômica ---------------------------------------
    def reserve(self):
        """Reserva custo+vaga atomicamente e vai a AGUARDANDO CONFIRMAÇÃO (§E).

        Bloqueia se o gate de segurança não estiver RUNNING, se a capacidade/
        orçamento estourar com o novo compromisso, ou se a identidade já tiver
        reserva ativa (dedup via ledger).
        """
        if self.flow_state != 'DETAILS_CHECKED':
            return self._block(['INVALID_FLOW_STATE_FOR_RESERVE'])
        if not self._running():
            return self._block(['BOT_NOT_RUNNING'])
        cost = self.details['cost']
        d = self.details['details']

        # Capacidade de vagas, contando compromissos JÁ existentes (§6).
        if self.ledger.active_count() >= getattr(self.config, 'max_simultaneous', 1):
            return self._block(['MAX_SIMULTANEOUS_REACHED'])
        # Orçamento após a reserva (reconfere; pode ter mudado desde check_details).
        avail = self.ledger.available_budget(getattr(self.config, 'daily_budget', None))
        if avail is None or cost > avail:
            return self._block(['COST_ABOVE_AVAILABLE_BUDGET'])

        res = self.ledger.reserve(
            identity=self.identity, cost=cost, currency=self.currency,
            name=d.get('name'), club=d.get('club'), modality=d.get('modality'),
            start_time=d.get('start_time'), round_id=self.round_id,
            operator=self.operator,
            max_active=getattr(self.config, 'max_simultaneous', 1))
        if not res['ok']:
            # Limite atômico do ledger (corrida) usa o mesmo motivo do pré-check.
            reason = ('MAX_SIMULTANEOUS_REACHED' if res['reason'] == 'CAPACITY_FULL'
                      else res['reason'])
            return self._block([reason])
        self.token = res['token']
        self.flow_state = 'RESERVED'
        self.reserve_snapshot = self._offer_snapshot(d, cost)
        self._log('RESERVED', token=self.token, cost=str(cost))
        # Segue direto para o resumo de autorização (sincroniza o ledger também).
        self.ledger.set_state(self.token, 'AWAITING_CONFIRMATION')
        self.flow_state = 'AWAITING_CONFIRMATION'
        self._log('AWAITING_CONFIRMATION', token=self.token)
        return self._result(cost=str(cost), summary=self.summary())

    def _offer_snapshot(self, d, cost):
        return dict(identity=self.identity, cost=str(cost), currency=self.currency,
                    start_time=d.get('start_time'), modality=d.get('modality'))

    def summary(self):
        """Resumo para o usuário (§D): torneio, custo total, moeda, horário,
        orçamento restante APÓS a reserva e compromissos de vaga."""
        if self.token is None:
            return None
        d = self.details['details']
        conf, pend, active = self.ledger.committed()
        avail = self.ledger.available_budget(getattr(self.config, 'daily_budget', None))
        return dict(
            tournament=d.get('name'), club=d.get('club'),
            total_cost=self.details['cost'], currency=self.currency,
            start_time=d.get('start_time'),
            budget_remaining_after_reserve=avail,
            active_commitments=active,
            note='O bot NÃO envia o clique; a confirmação no cliente é do usuário.')

    # ---- ETAPA E/F: autorização explícita + ação do usuário --------------
    def authorize(self, *, confirm, revalidation_snapshot=None):
        """Confirmação explícita do usuário para ESTA inscrição (§E).

        `confirm` deve ser True. `revalidation_snapshot` (quando houver espera/
        mudança de tela) é revalidado contra a oferta reservada: qualquer mudança
        de custo/identidade/oferta BLOQUEIA — a autorização não se transfere a
        outro torneio ou custo (§E). Uma tentativa por rodada.
        """
        if self.flow_state != 'AWAITING_CONFIRMATION':
            return self._block(['INVALID_FLOW_STATE_FOR_AUTHORIZE'])
        if self.attempts >= 1:
            return self._block(['ATTEMPT_ALREADY_CONSUMED'])
        if not self._running():
            # pausa/intervenção antes da confirmação: cancela antes do envio (§10).
            self.ledger.release(self.token, reason='BOT_NOT_RUNNING_AT_AUTHORIZE')
            self.flow_state = 'CANCELLED_BEFORE_SEND'
            self._log('CANCELLED_BEFORE_SEND', reason='BOT_NOT_RUNNING')
            return self._result(reasons=['BOT_NOT_RUNNING'])
        if not confirm:
            self.ledger.release(self.token, reason='USER_DECLINED')
            self.flow_state = 'CANCELLED_BEFORE_SEND'
            self._log('CANCELLED_BEFORE_SEND', reason='USER_DECLINED')
            return self._result(reasons=['USER_DECLINED'])
        if revalidation_snapshot is not None and revalidation_snapshot != self.reserve_snapshot:
            # Mudança de oferta entre telas (§10): cancela antes do envio.
            self.ledger.release(self.token, reason='OFFER_CHANGED_BEFORE_SEND')
            self.flow_state = 'CANCELLED_BEFORE_SEND'
            self._log('CANCELLED_BEFORE_SEND', reason='OFFER_CHANGED',
                      snapshot=revalidation_snapshot)
            return self._result(reasons=['OFFER_CHANGED_BEFORE_SEND'])

        self.attempts += 1
        self.authorized = True
        self._log('AUTHORIZED', token=self.token)
        if self.mode in ('observation', 'simulation'):
            # Piloto sem adaptador: NÃO envia confirmação. Para aqui (§2/Etapa F).
            self._log('HELD_NO_SEND', mode=self.mode)
            return self._result(note='Autorizado; em %s o clique NÃO é enviado. '
                                'Conclua no cliente se for inscrever.' % self.mode,
                                awaiting_user_action=(self.mode == 'observation'))
        # real_supervised: o USUÁRIO clica no cliente; registramos a intenção.
        return self._result(note='Autorizado. REALIZE o clique de confirmação no '
                            'cliente; depois chame record_user_action().',
                            awaiting_user_action=True)

    def record_user_action(self):
        """Registra que o USUÁRIO enviou a confirmação no cliente (modo real).

        O bot não clicou — isto só marca CONFIRMATION_SENT para a reconciliação.
        """
        if self.mode != 'real_supervised':
            return self._block(['USER_ACTION_ONLY_IN_REAL_MODE'])
        if self.flow_state != 'AWAITING_CONFIRMATION' or not self.authorized:
            return self._block(['NOT_AUTHORIZED_OR_WRONG_STATE'])
        self.ledger.set_state(self.token, 'CONFIRMATION_SENT',
                              reason='USER_CLICKED_IN_CLIENT')
        self.flow_state = 'CONFIRMATION_SENT'
        self._log('CONFIRMATION_SENT', by='user')
        return self._result()

    # ---- ETAPA G: conciliação -------------------------------------------
    def reconcile(self, receipt):
        """Concilia contra uma evidência observável no cliente (§G/§9).

        `receipt` = dict com identity/cost/currency observados + `confirmed` bool.
        Só CONFIRMA se a evidência for suficiente E bater com a MESMA identidade/
        custo. Caso contrário, RESULTADO DESCONHECIDO (mantém a reserva, não
        reenvia). Pausa após o envio não desfaz; a confirmação é conciliada (§9).
        """
        if self.flow_state not in ('CONFIRMATION_SENT', 'UNKNOWN_RESULT'):
            return self._block(['INVALID_FLOW_STATE_FOR_RECONCILE'])
        r = receipt or {}
        same_identity = (r.get('identity') == self.identity and self.identity is not None)
        rcost = to_money(r.get('cost'))
        same_cost = (rcost is not None and rcost == self.details['cost'])
        same_cur = (not self.currency) or (r.get('currency') == self.currency)
        if r.get('confirmed') and same_identity and same_cost and same_cur:
            self.ledger.confirm(self.token, evidence_ref=r.get('evidence_ref'))
            self.flow_state = 'CONFIRMED'
            self._log('CONFIRMED', evidence_ref=r.get('evidence_ref'))
            return self._result(note='Inscrição conciliada e confirmada.')
        # Evidência insuficiente/divergente: desconhecido, interrompe novas intenções.
        self.ledger.mark_unknown(self.token, reason='RECEIPT_INSUFFICIENT_OR_MISMATCH',
                                 evidence_ref=r.get('evidence_ref'))
        self.flow_state = 'UNKNOWN_RESULT'
        self._log('UNKNOWN_RESULT', same_identity=same_identity,
                  same_cost=same_cost, same_cur=same_cur)
        return self._result(reasons=['RESULT_UNKNOWN_HOLD_RESERVATION'])

    def cancel_before_send(self, *, reason):
        """Prova de que a confirmação NÃO foi enviada: libera a reserva (§9)."""
        if self.flow_state not in ('RESERVED', 'AWAITING_CONFIRMATION'):
            return self._block(['CANNOT_CANCEL_AFTER_SEND'])
        self.ledger.release(self.token, reason=reason)
        self.flow_state = 'CANCELLED_BEFORE_SEND'
        self._log('CANCELLED_BEFORE_SEND', reason=reason)
        return self._result(reasons=[reason])
