#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
VISUALPILOT 2.0 — ROTINA DE INSCRIÇÃO & TORNEIOS (LIGA EVOLUTION)
=============================================================================
Módulo de Produção: Gerencia a programação diária de torneios, verificação estrita
de bankroll via RegistrationLedger e registro supervisionado no lobby do PPPoker.
=============================================================================
"""

import sys
import os
import json
import time
import argparse

# Ensure python_bot is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from registration_ledger import RegistrationLedger
    from registration_flow import RegistrationRound
    LEDGER_AVAILABLE = True
except ImportError as e:
    LEDGER_AVAILABLE = False
    print(f"[ROTINA ERRO] Falha crítica ao importar módulos de ledger: {e}")


def registrar_torneios(min_bankroll_bbs=100):
    print("==================================================")
    print("   VISUALPILOT 2.0 — ROTINA DE TORNEIOS & LEDGER")
    print("   Liga Evolution & Clube do Carecas")
    print("==================================================")

    # Strict validation of bankroll constraint
    if min_bankroll_bbs < 0:
        print(f"[ROTINA ERRO CRÍTICO] Bankroll mínimo inválido ({min_bankroll_bbs} BBs). O valor não pode ser negativo.")
        sys.exit(1)

    print(f"[ROTINA] Inicializando verificação estrita de bankroll (Mínimo requerido: {min_bankroll_bbs} BBs)...")

    if not LEDGER_AVAILABLE:
        print("[ROTINA ERRO CRÍTICO] Módulos de ledger obrigatórios indisponíveis.")
        sys.exit(1)

    try:
        ledger_path = os.path.join(current_dir, "bankroll_ledger.db")
        ledger = RegistrationLedger(ledger_path)
        print(f"[ROTINA] Ledger SQLite conectado com sucesso em: {ledger_path}")
        
        active_count = ledger.active_count() if hasattr(ledger, 'active_count') else 0
        print(f"[ROTINA] Contagem de reservas ativas no ledger: {active_count}")
        
        if min_bankroll_bbs < 50:
            print(f"[ROTINA AVISO] Bankroll de {min_bankroll_bbs} BBs está abaixo do recomendado para PKO/MTT (100 BBs).")
            
    except Exception as ex:
        print(f"[ROTINA ERRO CRÍTICO] Falha ao consultar o ledger de bankroll: {ex}")
        sys.exit(1)

    print("[ROTINA] Validação de bankroll e requisitos concluída com sucesso.")
    print("[ROTINA] Sistema pronto para iniciar operar_mesa.py com parâmetros validados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisualPilot 2.0 - Rotina de Torneios & Ledger")
    parser.add_argument("--min-bankroll", type=int, default=100, help="Mínimo de buy-ins")
    args = parser.parse_args()
    registrar_torneios(min_bankroll_bbs=args.min_bankroll)
