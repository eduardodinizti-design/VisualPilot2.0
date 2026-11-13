#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
VISUALPILOT 2.0 — REAL MOUSE CONTROLLER MODULE
Anti-cheat biomechanical mouse movement and click execution using pyautogui
and cubic Bézier curves.
=============================================================================
"""

import time
import random
import math

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.01
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class RealMouseController:
    """Production-grade biomechanical mouse controller using pyautogui & Bézier curves."""
    
    @staticmethod
    def move_to(target_x, target_y, start_x=None, start_y=None, curvature=0.35, jitter=4):
        if not PYAUTOGUI_AVAILABLE:
            raise RuntimeError("[MOUSE ERROR] PyAutoGUI não está disponível neste ambiente. Necessário para cliques reais.")

        if start_x is None or start_y is None:
            current_pos = pyautogui.position()
            start_x, start_y = current_pos.x, current_pos.y
        
        # Control points for cubic Bézier curve
        ctrl_x = (start_x + target_x) / 2 + random.uniform(-80, 80) * curvature
        ctrl_y = (start_y + target_y) / 2 + random.uniform(-80, 80) * curvature
        
        steps = random.randint(20, 35)
        for i in range(steps + 1):
            t = i / float(steps)
            # Cubic Bézier formula
            bx = (1 - t)**3 * start_x + 3 * (1 - t)**2 * t * ctrl_x + 3 * (1 - t) * t**2 * ctrl_x + t**3 * target_x
            by = (1 - t)**3 * start_y + 3 * (1 - t)**2 * t * ctrl_y + 3 * (1 - t) * t**2 * ctrl_y + t**3 * target_y
            
            # Spatial jitter
            jx = bx + random.uniform(-jitter, jitter) * (1 - t)
            jy = by + random.uniform(-jitter, jitter) * (1 - t)
            
            pyautogui.moveTo(int(jx), int(jy), duration=0.0)
            time.sleep(random.uniform(0.003, 0.01))
            
        print(f"[MOUSE REAL] Movimento Bézier concluído para ({target_x}, {target_y})")

    @staticmethod
    def click(x, y):
        if not PYAUTOGUI_AVAILABLE:
            raise RuntimeError("[MOUSE ERROR] PyAutoGUI não está disponível neste ambiente.")
        
        RealMouseController.move_to(x, y)
        time.sleep(random.uniform(0.03, 0.08))
        pyautogui.click(int(x), int(y))
        print(f"[MOUSE REAL] Clique real executado com sucesso em ({x}, {y})")


if __name__ == "__main__":
    print("[MOUSE] RealMouseController carregado (PyAutoGUI:", PYAUTOGUI_AVAILABLE, ")")
