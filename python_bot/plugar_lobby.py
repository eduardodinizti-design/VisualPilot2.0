"""Pluga o registrador 3A no lobby REAL — observação, sem clique.

Captura (ou carrega) o lobby do PPPoker, lê os cartões com `grade_reader`,
aplica o seletor de política (F1) e, para um alvo autorizado, percorre o fluxo
de inscrição até AGUARDANDO CONFIRMAÇÃO — e PARA. O bot não clica: a confirmação
no cliente é sua.

Uso:
  # frame ao vivo (na sua máquina Windows, com a janela PPPoker aberta):
  python plugar_lobby.py --hwnd 0x12345 --club Karekas --currency BRL \
      --max-entry 100 --budget 500 --bankroll 200 \
      --target "DEEP FREEZEOUT" --authorized-cost 50

  # crop de lobby salvo (lab): a imagem já é o painel do lobby
  python plugar_lobby.py --image logs/.../sample-000001-mesa-1.png --is-crop \
      --club Karekas --currency BRL --max-entry 100 --budget 500 --bankroll 200 \
      --target "DEEP FREEZEOUT" --authorized-cost 50
"""
import argparse
import sys

import cv2

from bot_control import BotControl
from lobby_runner import (details_from_card, read_lobby, read_lobby_multi,
                          select_lobby)
from registration_flow import RegistrationRound
from registration_ledger import RegistrationLedger
from session_config import SessionConfig
from table_reading.pipeline import configure_ocr


def _read_lobby_for(args):
    """Lê o lobby: imagem única (--image) ou N frames ao vivo (--hwnd), mesclando
    a linha de status que alterna stack<->countdown."""
    if args.image:
        im = cv2.imread(args.image)
        if im is None:
            raise SystemExit('Nao consegui ler a imagem: %s' % args.image)
        return read_lobby(im, is_crop=args.is_crop), dict(source='image')
    from window_capture_engine import WindowCaptureEngine
    engine = WindowCaptureEngine()
    lob = read_lobby_multi(lambda: engine.capture_frame(hwnd=args.hwnd)[0],
                           frames=args.frames)
    return lob, dict(source='hwnd (%d frames)' % lob.get('frames', 0))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument('--hwnd', type=lambda s: int(s, 0), help='HWND da janela PPPoker')
    src.add_argument('--image', help='Caminho de um frame/crop de lobby salvo')
    p.add_argument('--is-crop', action='store_true',
                   help='A imagem JA e o painel do lobby recortado (ex.: mesa-1)')
    p.add_argument('--club', default='Karekas')
    p.add_argument('--currency', required=True, help='Moeda explicita (nunca inventada)')
    p.add_argument('--max-entry', type=float, required=True, help='Teto por inscricao')
    p.add_argument('--budget', type=float, required=True, help='Orcamento da sessao')
    p.add_argument('--bankroll', type=float, required=True, help='Banca em buy-ins')
    p.add_argument('--max-simultaneous', type=int, default=4)
    p.add_argument('--cutoff', default=None, help='HH:MM limite para novas inscricoes')
    p.add_argument('--now', default=None, help='HH:MM atual (para a regra de cutoff)')
    p.add_argument('--target', default=None, help='Nome do torneio autorizado')
    p.add_argument('--authorized-cost', type=float, default=None,
                   help='Custo da oferta autorizada p/ o alvo (obrigatorio com --target)')
    p.add_argument('--assert-open', action='store_true',
                   help='Operador AFIRMA que o alvo esta com inscricao aberta. '
                        'Necessario neste cliente, cujo cartao NAO mostra o status '
                        'de inscricao. Marcado como asseveracao do operador, nao lido.')
    p.add_argument('--db', default=':memory:', help='SQLite do ledger (persiste)')
    p.add_argument('--frames', type=int, default=5,
                   help='Frames a amostrar ao vivo (a linha de status alterna '
                        'stack<->countdown ~1Hz; varios frames pegam o countdown)')
    args = p.parse_args(argv)

    if args.target and args.authorized_cost is None:
        raise SystemExit('--target exige --authorized-cost (a oferta autorizada, §5)')

    configure_ocr()
    lob, meta = _read_lobby_for(args)

    config = SessionConfig(
        enabled=True, clubs_authorized=(args.club,),
        allowed_modalities=('freezeout', 'mko', 'pko'), currency=args.currency,
        max_entry_buyin=args.max_entry, daily_budget=args.budget,
        bankroll_bi=args.bankroll, max_simultaneous=args.max_simultaneous,
        registration_cutoff=args.cutoff)
    ledger = RegistrationLedger(args.db)

    print('=' * 70)
    print('PLUG NO LOBBY — MODO OBSERVACAO (o bot NAO clica) | fonte:', meta.get('source', 'hwnd'))
    print('=' * 70)
    if not lob['ok']:
        print('Sem lobby:', lob['reason'])
        return 1
    print('Cartoes lidos: %d (badges %d)' % (len(lob['cards']), lob['n_badges']))
    for c in lob['cards']:
        print('  - %-26r buyin=%-7s mod=%-9s st=%-11s conf=%s' % (
            (c['name'] or '')[:26], c['buyin'], c['modality'],
            (c['status'] or {}).get('state'), c['confidence']))

    eligible, blocked = select_lobby(lob['cards'], config, ledger,
                                     club=args.club, now_hhmm=args.now)
    print('\nELEGIVEIS:', [d['name'] for d in eligible] or '(nenhum)')
    for d in blocked:
        print('  BLOQUEADO %-26r -> %s' % ((d['name'] or '')[:26], ', '.join(d['reasons'])))

    if not args.target:
        print('\n(sem --target: so leitura/selecao; nada reservado)')
        ledger.close()
        return 0

    card = next((c for c in lob['cards'] if (c['name'] or '').strip() == args.target), None)
    if card is None:
        print('\nAlvo %r nao encontrado no lobby lido.' % args.target)
        ledger.close()
        return 1

    if args.assert_open and (card.get('status') or {}).get('state') != 'reg_open':
        # Este cliente nao imprime o status de inscricao no cartao. O operador
        # AFIRMA que o alvo esta aberto; marcamos como asseveracao, nao leitura.
        card = dict(card, status=dict(state='reg_open', closes_in_min=None,
                                      starts_at=None, operator_asserted=True))
        print('\n*** REGISTRO ABERTO = ASSEVERACAO DO OPERADOR (nao lido do cartao) ***')

    control = BotControl()
    control.resume()   # observação só lê, mas o gate é o mesmo do executor futuro
    r = RegistrationRound(
        round_id='lobby-1', operator='eduardo', target_name=args.target,
        authorized_cost=args.authorized_cost, currency=args.currency, config=config,
        ledger=ledger, mode='observation', bot_control=control)

    print('\n--- FLUXO SUPERVISIONADO sobre %r ---' % args.target)
    for step, res in [
            ('B observacao', r.observe(card, club=args.club, now_hhmm=args.now))]:
        print('[%s] -> %s %s' % (step, res['flow_state'], res.get('reasons') or ''))
    if r.flow_state == 'BLOCKED':
        ledger.close(); return 1

    det = details_from_card(card, club=args.club, currency=args.currency)
    print('   (detalhes de origem %s — a 3A nao abre a tela de detalhes)' % det['details_source'])
    res = r.check_details(det, now_hhmm=args.now)
    print('[C detalhes] -> %s %s' % (res['flow_state'], res.get('reasons') or ''))
    if r.flow_state == 'BLOCKED':
        ledger.close(); return 1

    res = r.reserve()
    print('[E reserva] -> %s %s' % (res['flow_state'], res.get('reasons') or ''))
    if r.flow_state == 'BLOCKED':
        ledger.close(); return 1

    s = res['summary']
    print('\n--- RESUMO PARA AUTORIZACAO (§D) ---')
    print('  Torneio ...........:', s['tournament'], '/', s['club'])
    print('  Custo total .......:', s['total_cost'], s['currency'])
    print('  Inicio ............:', s['start_time'])
    print('  Orc. apos reserva .:', s['budget_remaining_after_reserve'], s['currency'])
    print('  Compromissos ......:', s['active_commitments'])
    print('\n>>> PARADA EM AGUARDANDO CONFIRMACAO. Detalhes vieram do LOBBY (nao de'
          ' uma tela\n    de detalhes conferida). Se for inscrever, confirme VOCE no'
          ' cliente.')
    ledger.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
