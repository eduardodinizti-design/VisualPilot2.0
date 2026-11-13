"""Registrador supervisionado — demo em modo OBSERVAÇÃO (Fase 3A).

Percorre UMA rodada da máquina de estados sobre um alvo autorizado e PARA em
AGUARDANDO CONFIRMAÇÃO. O bot NÃO clica em nada: se você quiser de fato se
inscrever, o clique de confirmação é SEU, no cliente (spec §2 / Etapa F).

Esta demo usa dados de exemplo (não lê o lobby real). Ela existe para mostrar a
trilha de estados, a aritmética de custo/orçamento e o resumo de autorização.
Para operar com o lobby real, alimente `observe`/`check_details` com o que o
`grade_reader` leu e os detalhes conferidos no cliente.

Uso:
  python registrar_supervisionado.py
  python registrar_supervisionado.py --db reservas.db   # persistir entre runs
"""
import argparse
import sys

from registration_flow import RegistrationRound
from registration_ledger import RegistrationLedger
from session_config import SessionConfig

# --- dados de exemplo (NÃO é leitura de tela) ---------------------------------
EXEMPLO_CARD = dict(
    name='MINI FREEZE', buyin=50.0, modality='freezeout',
    players_registered=40, players_max=500, level_minutes=8,
    status=dict(state='reg_open', closes_in_min=30, starts_at=None),
    confidence='high')
EXEMPLO_DETALHES = dict(
    name='MINI FREEZE', club='Karekas', modality='freezeout', buyin=50.0,
    currency='BRL', start_time='2026-11-09 21:00', status=dict(state='reg_open'))


def _print(step, res):
    print('\n[%s] -> %s' % (step, res['flow_state']))
    if res.get('reasons'):
        print('   motivos:', ', '.join(res['reasons']))
    for k in ('cost', 'currency', 'available_budget', 'active_commitments'):
        if res.get(k) is not None:
            print('   %s: %s' % (k, res[k]))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Registrador supervisionado (demo, sem clique)')
    ap.add_argument('--db', default=':memory:', help='arquivo SQLite do ledger (persiste)')
    args = ap.parse_args(argv)

    config = SessionConfig(
        enabled=True, clubs_authorized=('Karekas', 'Veneza'),
        allowed_modalities=('freezeout', 'mko', 'pko'), currency='BRL',
        max_entry_buyin=100.0, daily_budget=500.0, bankroll_bi=200.0,
        max_simultaneous=4)
    ledger = RegistrationLedger(args.db)

    print('=' * 68)
    print('REGISTRADOR SUPERVISIONADO — MODO OBSERVAÇÃO (o bot NÃO clica)')
    print('=' * 68)

    r = RegistrationRound(
        round_id='demo-1', operator='eduardo', target_name='MINI FREEZE',
        authorized_cost=50.0, currency='BRL', config=config, ledger=ledger,
        mode='observation')

    _print('B observação', r.observe(EXEMPLO_CARD, club='Karekas', now_hhmm='20:30'))
    if r.flow_state == 'BLOCKED':
        return 1
    _print('C detalhes', r.check_details(EXEMPLO_DETALHES, now_hhmm='20:30'))
    if r.flow_state == 'BLOCKED':
        return 1
    res = r.reserve()
    _print('E reserva', res)
    if r.flow_state == 'BLOCKED':
        return 1

    s = res['summary']
    print('\n--- RESUMO PARA AUTORIZAÇÃO (§D) ---')
    print('  Torneio ...........:', s['tournament'], '/', s['club'])
    print('  Custo total .......:', s['total_cost'], s['currency'])
    print('  Início ............:', s['start_time'])
    print('  Orç. após reserva .:', s['budget_remaining_after_reserve'], s['currency'])
    print('  Compromissos ......:', s['active_commitments'])
    print('  Nota ..............:', s['note'])

    out = r.authorize(confirm=True)
    _print('F autorização', out)
    print('\n>>> PARADA EM AGUARDANDO CONFIRMAÇÃO.')
    print('    Em modo observação o clique NÃO é enviado. Para inscrever de'
          ' verdade,\n    confirme VOCÊ no cliente e concilie o recibo depois.')
    ledger.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
