#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
VISUALPILOT 2.0 — ROTINA DE INSCRIÇÃO & POLÍTICA FINANCEIRA (LIGA EVOLUTION)
=============================================================================
Módulo de Produção: Gerencia a programação diária de torneios, verificação estrita
de saldo disponível, custo de inscrição, compromissos em reservas ativas (Ledger)
e execução do fluxo supervisionado RegistrationRound.
=============================================================================
"""

import sys
import os
import json
import time
import argparse
from decimal import Decimal

# Ensure python_bot is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from registration_ledger import RegistrationLedger, to_money
    from registration_flow import RegistrationRound
    LEDGER_AVAILABLE = True
except ImportError as e:
    LEDGER_AVAILABLE = False
    print(f"[ROTINA ERRO] Falha ao importar módulos de ledger e fluxo: {e}")


def registrar_torneios(min_buyins=100, available_balance=5000.00, tournament_cost=50.00):
    print("==================================================")
    print("   VISUALPILOT 2.0 — POLÍTICA FINANCEIRA & LEDGER")
    print("   Liga Evolution & Clube do Carecas")
    print("==================================================")

    # Unit & parameter validation
    if min_buyins < 0 or available_balance < 0 or tournament_cost <= 0:
        print(f"[ROTINA ERRO CRÍTICO] Parâmetros financeiros inválidos: buy-ins={min_buyins}, saldo={available_balance}, custo={tournament_cost}")
        sys.exit(1)

    print(f"[ROTINA] Validando política financeira:")
    print(f"         - Mínimo de Buy-ins exigido: {min_buyins}")
    print(f"         - Custo por Inscrição: R$ {tournament_cost:.2f}")
    print(f"         - Saldo Disponível em Conta: R$ {available_balance:.2f}")

    required_bankroll = Decimal(str(min_buyins)) * Decimal(str(tournament_cost))
    balance_dec = to_money(available_balance)
    cost_dec = to_money(tournament_cost)

    if balance_dec < required_bankroll:
        print(f"[ROTINA ERRO] Saldo insuficiente (R$ {balance_dec}) para o requisito mínimo de {min_buyins} buy-ins (R$ {required_bankroll}).")
        sys.exit(1)

    if not LEDGER_AVAILABLE:
        print("[ROTINA ERRO CRÍTICO] Módulos de ledger obrigatórios indisponíveis.")
        sys.exit(1)

    try:
        ledger_path = os.path.join(current_dir, "bankroll_ledger.db")
        ledger = RegistrationLedger(ledger_path)
        print(f"[ROTINA] Ledger SQLite conectado em: {ledger_path}")

        active_count = ledger.active_count() if hasattr(ledger, 'active_count') else 0
        print(f"[ROTINA] Reservas ativas comprometidas no ledger: {active_count}")

        # Calculate total committed funds from active reservations if ledger supports it
        committed_funds = Decimal('0.00')
        if hasattr(ledger, 'list_active_reservations'):
            for res in ledger.list_active_reservations():
                committed_funds += to_money(res.get('cost', 0))

        net_available = balance_dec - committed_funds

        print(f"         - Valores comprometidos (Reservas Ativas): R$ {committed_funds:.2f}")
        print(f"         - Saldo Líquido Disponível: R$ {net_available:.2f}")

        if net_available < cost_dec:
            print(f"[ROTINA ERRO] Saldo líquido (R$ {net_available}) menor que o custo do torneio (R$ {cost_dec}) após contabilizar reservas ativas.")
            sys.exit(1)

        # Initialize supervised RegistrationRound flow to validate state compliance
        print(f"[ROTINA] Inicializando fluxo supervisionado (RegistrationRound) para validação...")
        dummy_config = {"max_buyin": float(cost_dec), "session_limit": float(balance_dec)}
        round_checker = RegistrationRound(
            round_id="ROUND_AUDIT_01",
            operator="VisualPilot_Core",
            target_name="Evolution PKO High Roller",
            authorized_cost=cost_dec,
            currency="BRL",
            config=dummy_config,
            ledger=ledger,
            mode='observation'
        )
        print(f"[ROTINA] Estado inicial do fluxo supervisionado: {round_checker.flow_state}")

    except Exception as ex:
        print(f"[ROTINA ERRO CRÍTICO] Falha na auditoria do ledger financeiro: {ex}")
        sys.exit(1)

    print("[ROTINA] Validação financeira, compromissos de reservas e requisitos concluída com sucesso.")
    print("[ROTINA] Sistema pronto para operar mesas com autorização financeira auditada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisualPilot 2.0 - Política Financeira & Torneios")
    parser.add_argument("--min-buyins", type=int, default=100, help="Mínimo de buy-ins")
    parser.add_argument("--balance", type=float, default=5000.00, help="Saldo disponível (R$)")
    parser.add_argument("--cost", type=float, default=50.00, help="Custo do torneio (R$)")
    args = parser.parse_args()
    registrar_torneios(min_buyins=args.min_buyins, available_balance=args.balance, tournament_cost=args.cost)
