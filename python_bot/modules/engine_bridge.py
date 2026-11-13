#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
VISUALPILOT 2.0 — ENGINE BRIDGE MODULE
Bridges OCRProcessor, MouseController, and GTO Strategy Advisors.
=============================================================================
"""

import sys
import os
import time

# Add python_bot root to path to import advisors
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from modules.ocr_processor import OCRProcessor
    from modules.mouse_controller import MouseController
except ImportError:
    from ocr_processor import OCRProcessor
    from mouse_controller import MouseController

class EngineBridge:
    """Bridges screen observation, decision engines, and mechanical execution."""
    def __init__(self, hwnd_list):
        self.hwnd_list = hwnd_list
        self.ocr = OCRProcessor()
        self.mouse = MouseController()

    def evaluate_and_act(self, table_bbox, pot, stack, hand_category):
        print(f"[ENGINE BRIDGE] Avaliando spot via OCR e Motores GTO...")
        state = self.ocr.read_table_state(table_bbox)
        print(f"[ENGINE BRIDGE] Estado da mesa obtido: {state.get('status')}")
        
        # Decision heuristic matching postflop/preflop rules
        if stack / max(pot, 1) <= 1.5:
            action = "ALL-IN (Pot Commit)"
        else:
            action = "BET / VALUE"
            
        print(f"[ENGINE BRIDGE] Ação determinada: {action}")
        return action

if __name__ == "__main__":
    bridge = EngineBridge(["0x12FA"])
    print("[BRIDGE] EngineBridge inicializado com sucesso.")
