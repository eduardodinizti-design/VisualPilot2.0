"""Testes do registrador supervisionado (Fase 3A).

Cobre os 18 cenários do §11 da spec `ESTRATÉGIA DE INSCRIÇ.txt`, mais a
atomicidade/dedup/persistência do ledger e as transições da máquina de estados.
Tudo é lógica pura + SQLite — roda no lab, sem Windows e sem cliente.
"""
import os
import tempfile
import unittest
from decimal import Decimal

from registration_ledger import (LedgerError, RegistrationLedger, make_identity,
                                  sum_parcels, to_money)
from registration_flow import RegistrationRound
from session_config import SessionConfig, SessionState


class _Control:
    """bot_control falso: RUNNING libera, PAUSED não."""
    def __init__(self, running=True):
        self.running = running

    def execution_allowed(self):
        return self.running


def ready_config(**over):
    base = dict(enabled=True, clubs_authorized=('Karekas', 'Veneza'),
                allowed_modalities=('freezeout', 'mko', 'pko'), currency='BRL',
                max_entry_buyin=100.0, daily_budget=500.0, bankroll_bi=200.0,
                max_simultaneous=4, grade_preset=())
    base.update(over)
    return SessionConfig(**base)


def card(name='MINI FREEZE', buyin=50.0, modality='freezeout', state='reg_open'):
    return dict(name=name, buyin=buyin, modality=modality,
                players_registered=40, players_max=500, level_minutes=8,
                status=dict(state=state, closes_in_min=30, starts_at=None),
                confidence='high')


def details(name='MINI FREEZE', club='Karekas', modality='freezeout',
            buyin=50.0, currency='BRL', start_time='2026-11-09 21:00',
            state='reg_open', parcels=None, total=None):
    d = dict(name=name, club=club, modality=modality, currency=currency,
             start_time=start_time, status=dict(state=state))
    if parcels is not None:
        d['parcels'], d['total'] = parcels, total
    else:
        d['buyin'] = buyin
    return d


def new_round(config=None, ledger=None, mode='real_supervised', control=None,
              cost=50.0, target='MINI FREEZE'):
    return RegistrationRound(
        round_id='R1', operator='eduardo', target_name=target,
        authorized_cost=cost, currency='BRL', config=config or ready_config(),
        ledger=ledger or RegistrationLedger(), mode=mode,
        bot_control=control or _Control(True))


class MoneyTest(unittest.TestCase):
    def test_decimal_exact_cents(self):
        self.assertEqual(to_money('50,50'.replace(',', '.')), Decimal('50.50'))
        self.assertEqual(to_money(50.5), Decimal('50.50'))

    def test_none_never_zero(self):
        self.assertIsNone(to_money(None))
        self.assertIsNone(to_money('abc'))
        self.assertIsNone(to_money(float('nan')))
        self.assertIsNone(to_money(-1))

    def test_sum_parcels_ok_and_mismatch(self):  # cenário 7
        s, ok = sum_parcels(['28,34'.replace(',', '.'), '14.16', '7.50'], total=50.00)
        self.assertEqual((s, ok), (Decimal('50.00'), True))
        s2, ok2 = sum_parcels(['28.34', '14.16', '7.50'], total=100.00)
        self.assertEqual((s2, ok2), (Decimal('50.00'), False))  # não soma total+parcelas

    def test_identity_needs_more_than_name(self):  # §4
        ident_none, basis = make_identity(name='MINI FREEZE')
        self.assertIsNone(ident_none)
        ident, _ = make_identity(name='MINI FREEZE', buyin=50, start_time='21:00')
        self.assertIsNotNone(ident)


class LedgerTest(unittest.TestCase):
    def test_reserve_blocks_without_identity_cost_currency(self):
        led = RegistrationLedger()
        self.assertRaises(LedgerError, led.reserve, identity=None, cost=50, currency='BRL')
        self.assertRaises(LedgerError, led.reserve, identity='x', cost=None, currency='BRL')
        self.assertRaises(LedgerError, led.reserve, identity='x', cost=50, currency='')

    def test_dedup_same_identity(self):  # cenário 11 (repetir intenção)
        led = RegistrationLedger()
        a = led.reserve(identity='id1', cost=50, currency='BRL')
        b = led.reserve(identity='id1', cost=50, currency='BRL')
        self.assertTrue(a['ok'])
        self.assertFalse(b['ok'])
        self.assertEqual(b['reason'], 'ALREADY_RESERVED')
        self.assertEqual(led.active_count(), 1)

    def test_atomic_dedup_across_connections(self):  # cenário 11 (concorrência)
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            l1, l2 = RegistrationLedger(path), RegistrationLedger(path)
            r1 = l1.reserve(identity='idX', cost=50, currency='BRL', token='t1')
            r2 = l2.reserve(identity='idX', cost=50, currency='BRL', token='t2')
            self.assertTrue(r1['ok'])
            self.assertFalse(r2['ok'])          # a segunda corrida NÃO duplica a vaga
            l1.close(); l2.close()
        finally:
            os.remove(path)

    def test_capacity_limit_atomic_across_connections(self):  # reserva concorrente
        # Caso reproduzido: o limite de vagas precisa ser ATÔMICO. Duas conexões
        # (processos) ao mesmo .db não podem ultrapassar max_active numa corrida.
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            l1, l2 = RegistrationLedger(path), RegistrationLedger(path)
            r1 = l1.reserve(identity='A', cost=10, currency='BRL', token='t1', max_active=2)
            r2 = l2.reserve(identity='B', cost=10, currency='BRL', token='t2', max_active=2)
            r3 = l1.reserve(identity='C', cost=10, currency='BRL', token='t3', max_active=2)
            self.assertTrue(r1['ok'] and r2['ok'])
            self.assertFalse(r3['ok'])                 # a 3ª estoura o limite
            self.assertEqual(r3['reason'], 'CAPACITY_FULL')
            self.assertEqual(l1.active_count(), 2)     # limite respeitado
            l1.close(); l2.close()
        finally:
            os.remove(path)

    def test_persists_across_restart(self):  # cenário 15
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            led = RegistrationLedger(path)
            r = led.reserve(identity='idP', cost=50, currency='BRL', token='tP')
            led.mark_unknown('tP', reason='EXCEPTION_AFTER_SEND')
            led.close()
            reopened = RegistrationLedger(path)   # "reinício" do programa
            got = reopened.get('tP')
            self.assertEqual(got['state'], 'UNKNOWN_RESULT')
            self.assertEqual(reopened.active_count(), 1)   # reserva preservada
            reopened.close()
        finally:
            os.remove(path)

    def test_budget_confirmed_plus_pending(self):  # §5
        led = RegistrationLedger()
        led.reserve(identity='a', cost=50, currency='BRL', token='ta')
        led.reserve(identity='b', cost=30, currency='BRL', token='tb')
        led.set_state('ta', 'AWAITING_CONFIRMATION')
        led.set_state('ta', 'CONFIRMATION_SENT')
        led.confirm('ta')
        conf, pend, n = led.committed()
        self.assertEqual((conf, pend, n), (Decimal('50.00'), Decimal('30.00'), 2))
        self.assertEqual(led.available_budget(200), Decimal('120.00'))

    def test_release_frees_slot_and_budget(self):  # cenário 16
        led = RegistrationLedger()
        led.reserve(identity='a', cost=50, currency='BRL', token='ta')
        led.release('ta', reason='PROVEN_NOT_SENT')
        self.assertEqual(led.active_count(), 0)
        self.assertEqual(led.available_budget(200), Decimal('200.00'))

    def test_no_release_after_send(self):  # §9: pós-envio não libera por suposição
        led = RegistrationLedger()
        led.reserve(identity='a', cost=50, currency='BRL', token='ta')
        led.set_state('ta', 'AWAITING_CONFIRMATION')
        led.set_state('ta', 'CONFIRMATION_SENT')
        self.assertRaises(LedgerError, led.set_state, 'ta', 'CANCELLED_BEFORE_SEND')


class FlowHappyPathTest(unittest.TestCase):
    def test_full_confirm_real_mode(self):  # cenários 1 + 13
        r = new_round()
        self.assertEqual(r.observe(card(), club='Karekas')['flow_state'], 'CANDIDATE')
        self.assertEqual(r.check_details(details())['flow_state'], 'DETAILS_CHECKED')
        res = r.reserve()
        self.assertEqual(res['flow_state'], 'AWAITING_CONFIRMATION')
        self.assertIsNotNone(res['summary'])
        self.assertFalse(r.execution_allowed)                 # o bot nunca clica
        self.assertEqual(r.authorize(confirm=True)['flow_state'], 'AWAITING_CONFIRMATION')
        self.assertEqual(r.record_user_action()['flow_state'], 'CONFIRMATION_SENT')
        rec = r.reconcile(dict(confirmed=True, identity=r.identity, cost=50.0,
                               currency='BRL', evidence_ref='recibo-1'))
        self.assertEqual(rec['flow_state'], 'CONFIRMED')
        self.assertEqual(rec['committed_confirmed'], '50.00')

    def test_observation_mode_never_sends(self):  # §2
        r = new_round(mode='observation')
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        out = r.authorize(confirm=True)
        self.assertEqual(out['flow_state'], 'AWAITING_CONFIRMATION')   # para aqui
        self.assertTrue(out['awaiting_user_action'])
        # record_user_action não é válido em observação
        self.assertEqual(r.record_user_action()['flow_state'], 'BLOCKED')

    def test_available_budget_in_summary(self):  # §D
        r = new_round()
        r.observe(card(), club='Karekas'); r.check_details(details())
        s = r.reserve()['summary']
        self.assertEqual(s['budget_remaining_after_reserve'], Decimal('450.00'))
        self.assertEqual(s['currency'], 'BRL')


class FlowScenariosTest(unittest.TestCase):
    def test_2_event_not_in_list(self):
        r = new_round(target='MINI FREEZE')
        out = r.observe(card(name='OUTRO TORNEIO'), club='Karekas')
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('NOT_THE_AUTHORIZED_TARGET', out['reasons'])

    def test_3_same_name_different_identity(self):
        i1, _ = make_identity(name='DAILY', buyin=50, start_time='20:00')
        i2, _ = make_identity(name='DAILY', buyin=50, start_time='22:00')
        self.assertNotEqual(i1, i2)   # mesmo nome, horários diferentes = ids distintos
        led = RegistrationLedger()
        self.assertTrue(led.reserve(identity=i1, cost=50, currency='BRL')['ok'])
        self.assertTrue(led.reserve(identity=i2, cost=50, currency='BRL')['ok'])

    def test_4_above_entry_cap(self):
        r = new_round(config=ready_config(max_entry_buyin=10.0), cost=50.0)
        out = r.observe(card(buyin=50.0), club='Karekas')
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('BUYIN_ABOVE_CAP', out['reasons'])

    def test_5_insufficient_remaining_budget(self):
        led = RegistrationLedger()
        led.reserve(identity='pre', cost=470, currency='BRL', token='pre')  # consome banca
        r = new_round(ledger=led, config=ready_config(daily_budget=500.0))
        r.observe(card(), club='Karekas')
        out = r.check_details(details())
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('COST_ABOVE_AVAILABLE_BUDGET', out['reasons'])

    def test_6_seat_limit_reached(self):
        led = RegistrationLedger()
        led.reserve(identity='x', cost=10, currency='BRL', token='x')
        r = new_round(ledger=led, config=ready_config(max_simultaneous=1))
        r.observe(card(), club='Karekas'); r.check_details(details())
        out = r.reserve()
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('MAX_SIMULTANEOUS_REACHED', out['reasons'])

    def test_7_composite_cost_mismatch_blocks(self):
        r = new_round(cost=50.0)
        r.observe(card(buyin=50.0), club='Karekas')
        out = r.check_details(details(parcels=[28.34, 14.16, 7.50], total=100.00,
                                      buyin=None))
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('COST_UNKNOWN_OR_PARCEL_MISMATCH', out['reasons'])

    def test_7b_composite_cost_ok(self):
        r = new_round(cost=50.0)
        r.observe(card(buyin=50.0), club='Karekas')
        out = r.check_details(details(parcels=[28.34, 14.16, 7.50], total=50.00,
                                      buyin=None))
        self.assertEqual(out['flow_state'], 'DETAILS_CHECKED')

    def test_8_currency_unknown(self):
        r = new_round()
        r.observe(card(), club='Karekas')
        out = r.check_details(details(currency=None))
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('CURRENCY_UNKNOWN', out['reasons'])

    def test_8b_price_illegible(self):
        r = new_round()
        r.observe(card(), club='Karekas')
        out = r.check_details(details(buyin=None))
        self.assertIn('COST_UNKNOWN_OR_PARCEL_MISMATCH', out['reasons'])

    def test_9_registration_not_open(self):
        r = new_round()
        out = r.observe(card(state='not_started'), club='Karekas')
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('REGISTRATION_NOT_OPEN', out['reasons'])

    def test_10_cost_divergence_lobby_vs_details(self):
        r = new_round(cost=50.0, config=ready_config(max_entry_buyin=60.0))
        r.observe(card(buyin=50.0), club='Karekas')
        out = r.check_details(details(buyin=70.0))
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('COST_DIVERGENCE_LOBBY_VS_DETAILS', out['reasons'])

    def test_10b_offer_changed_before_send(self):
        r = new_round()
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        changed = dict(r.reserve_snapshot); changed['cost'] = '60.00'
        out = r.authorize(confirm=True, revalidation_snapshot=changed)
        self.assertEqual(out['flow_state'], 'CANCELLED_BEFORE_SEND')
        self.assertIn('OFFER_CHANGED_BEFORE_SEND', out['reasons'])
        self.assertEqual(r.ledger.active_count(), 0)   # reserva liberada

    def test_11_duplicate_intent_in_flow(self):
        led = RegistrationLedger()
        r1 = new_round(ledger=led)
        r1.observe(card(), club='Karekas'); r1.check_details(details()); r1.reserve()
        r2 = new_round(ledger=led)
        r2.observe(card(), club='Karekas')
        out = r2.check_details(details())   # mesma identidade já reservada
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('ALREADY_RESERVED_SAME_IDENTITY', out['reasons'])

    def test_12_pause_before_confirmation(self):
        ctrl = _Control(True)
        r = new_round(control=ctrl)
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        ctrl.running = False   # usuário pausou antes de confirmar
        out = r.authorize(confirm=True)
        self.assertEqual(out['flow_state'], 'CANCELLED_BEFORE_SEND')
        self.assertEqual(r.ledger.active_count(), 0)

    def test_12b_reserve_blocked_when_not_running(self):
        r = new_round(control=_Control(False))
        r.observe(card(), club='Karekas'); r.check_details(details())
        out = r.reserve()
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('BOT_NOT_RUNNING', out['reasons'])

    def test_14_receipt_for_other_event_is_unknown(self):
        r = new_round()
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        r.authorize(confirm=True); r.record_user_action()
        out = r.reconcile(dict(confirmed=True, identity='outra-id', cost=50.0,
                               currency='BRL'))
        self.assertEqual(out['flow_state'], 'UNKNOWN_RESULT')
        self.assertEqual(r.ledger.active_count(), 1)   # mantém a reserva

    def test_14b_absent_confirmation_is_unknown(self):
        r = new_round()
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        r.authorize(confirm=True); r.record_user_action()
        out = r.reconcile(dict(confirmed=False, identity=r.identity, cost=50.0))
        self.assertEqual(out['flow_state'], 'UNKNOWN_RESULT')

    def test_16_proven_failure_before_send_releases(self):
        r = new_round()
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        out = r.cancel_before_send(reason='CLIENT_CLOSED_BEFORE_SEND')
        self.assertEqual(out['flow_state'], 'CANCELLED_BEFORE_SEND')
        self.assertEqual(r.ledger.active_count(), 0)
        self.assertEqual(r.ledger.available_budget(500), Decimal('500.00'))

    def test_17_valid_confirmation_after_pause_no_resend(self):
        ctrl = _Control(True)
        r = new_round(control=ctrl)
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        r.authorize(confirm=True); r.record_user_action()
        ctrl.running = False   # pausa DEPOIS do envio não desfaz a inscrição
        out = r.reconcile(dict(confirmed=True, identity=r.identity, cost=50.0,
                               currency='BRL', evidence_ref='recibo-tardio'))
        self.assertEqual(out['flow_state'], 'CONFIRMED')
        self.assertEqual(r.attempts, 1)   # nenhuma nova tentativa

    def test_18_rebuy_blocked_in_pilot(self):
        r = new_round(target='SUPER REBUY')
        out = r.observe(card(name='SUPER REBUY', modality='rebuy'), club='Karekas')
        self.assertEqual(out['flow_state'], 'BLOCKED')
        self.assertIn('REBUY_ONLY_IN_PKO', out['reasons'])

    def test_single_attempt_per_round(self):
        r = new_round()
        r.observe(card(), club='Karekas'); r.check_details(details()); r.reserve()
        r.authorize(confirm=True)
        again = r.authorize(confirm=True)   # segunda autorização = bloqueada
        self.assertEqual(again['flow_state'], 'BLOCKED')
        self.assertIn('ATTEMPT_ALREADY_CONSUMED', again['reasons'])


if __name__ == '__main__':
    unittest.main()
