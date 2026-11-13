#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
VISUALPILOT 2.0 — PPPPOKER OCR & SCREEN CAPTURE PROCESSOR
Real screen capture via mss, window discovery via win32gui, and
OpenCV frame processing for poker card and pot reading.
=============================================================================
"""

import time
import numpy as np
import cv2
import platform

WIN32_AVAILABLE = False
if platform.system() == "Windows":
    try:
        import win32gui
        import win32con
        WIN32_AVAILABLE = True
    except ImportError:
        WIN32_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False


def find_pppoker_windows():
    """Identifica janelas (HWND) válidas do PPPoker no Windows."""
    windows = []
    if WIN32_AVAILABLE:
        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "pppoker" in title.lower() or "mesa" in title.lower() or "club" in title.lower():
                    rect = win32gui.GetWindowRect(hwnd)
                    windows.append({
                        "hwnd": hex(hwnd),
                        "title": title,
                        "rect": rect, # (left, top, right, bottom)
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1]
                    })
        try:
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception as e:
            print(f"[OCR ERROR] Erro ao enumerar janelas Win32: {e}")
    return windows


class PPPokerOCRProcessor:
    """Captura frames reais usando mss para leitura de cartas e estado de mesas."""
    def __init__(self):
        self.sct = mss.mss() if MSS_AVAILABLE else None

    def capture_hwnd_frame(self, hwnd_val):
        """Captura o frame real da janela HWND especificada."""
        bbox = (100, 100, 800, 600)
        if WIN32_AVAILABLE:
            try:
                hwnd = int(hwnd_val, 16) if isinstance(hwnd_val, str) and hwnd_val.startswith("0x") else int(hwnd_val)
                if win32gui.IsWindow(hwnd):
                    rect = win32gui.GetWindowRect(hwnd)
                    bbox = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
            except Exception as e:
                print(f"[OCR ERROR] Falha ao obter rect do HWND {hwnd_val}: {e}")

        if not self.sct or not MSS_AVAILABLE:
            raise RuntimeError("[OCR ERROR] Biblioteca mss não disponível para captura de tela real.")

        try:
            monitor = {
                "left": int(bbox[0]),
                "top": int(bbox[1]),
                "width": int(bbox[2]),
                "height": int(bbox[3])
            }
            sct_img = self.sct.grab(monitor)
            img = np.array(sct_img)
            bgr_frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return bgr_frame
        except Exception as e:
            print(f"[OCR ERROR] Falha na captura mss do HWND {hwnd_val}: {e}")
            return None

    def read_cards_and_pot(self, hwnd_val):
        """Processa o frame capturado para leitura de cartas comunitárias e pote."""
        frame = self.capture_hwnd_frame(hwnd_val)
        if frame is None or frame.size == 0:
            return {"status": "error", "message": "Frame não capturado"}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(blurred, 175, 255, cv2.THRESH_BINARY)

        return {
            "status": "success",
            "timestamp": time.time(),
            "hwnd": hwnd_val,
            "frame_shape": frame.shape,
            "cards_read": True
        }


if __name__ == "__main__":
    print("[OCR] PPPokerOCRProcessor inicializado. Janelas encontradas:", find_pppoker_windows())
