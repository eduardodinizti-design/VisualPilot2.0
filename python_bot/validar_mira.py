"""Valida a MIRA (passo 2): calcula a coordenada de tela de um botão de ação e
MOVE o cursor até ele, **SEM CLICAR**, restaurando a posição. Confirme visual-
mente se o cursor parou em cima do botão. Precisa ser a VEZ do hero (botões na
tela). Nenhum clique é enviado.

Uso: python validar_mira.py --hwnd 0x... [--button FOLD]
"""
import argparse
import sys
import time

import cv2

from table_reading.pipeline import configure_ocr
from table_reading.automatic_table_crops import detect_table_crops
from table_reading.action_buttons import read_action_buttons
from screen_coords import frame_to_screen
from cursor_input_win import WindowsCursorInput
from window_capture_engine import WindowCaptureEngine
from table_discovery.pppoker import discover_pppoker


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hwnd', type=lambda s: int(s, 0), required=True)
    p.add_argument('--button', default='FOLD', help='FOLD/CHECK/CALL/BET/RAISE')
    p.add_argument('--settle', type=float, default=2.0, help='segundos parado no botao')
    p.add_argument('--max-tables', type=int, default=6)
    args = p.parse_args(argv)

    configure_ocr()
    wins = [w for w in discover_pppoker()['windows'] if w['hwnd'] == args.hwnd]
    if not wins:
        print('Janela nao encontrada.'); return 1
    w = wins[0]
    win_rect = (w['x'], w['y'], w['w'], w['h'])

    eng = WindowCaptureEngine()
    frame, meta = eng.capture_frame(hwnd=args.hwnd)
    if frame is None:
        print('Captura falhou:', meta.get('status')); return 1
    fh, fw = frame.shape[:2]
    frame_size = (fw, fh)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    found = None
    for prop in detect_table_crops(rgb, max_tables=args.max_tables):
        x, y, bw, bh = map(int, prop.box)
        crop = frame[y:y + bh, x:x + bw]
        br = read_action_buttons(crop)
        if br['status'] == 'EXPERIMENTAL_BUTTON_ROW':
            btn = next((b for b in br['buttons'] if b.get('action') == args.button), None)
            if btn:
                found = (x, y, btn)
                break
    if found is None:
        print('Sem o botao %s agora (talvez nao seja sua vez). Rode na sua vez de agir.'
              % args.button)
        return 2

    ox, oy, btn = found
    bx, by, bbw, bbh = btn['box']        # coords no crop (y ja com offset)
    cx_frame = ox + bx + bbw / 2.0       # centro do botao no FRAME (fisico)
    cy_frame = oy + by + bbh / 2.0
    sx, sy = frame_to_screen((cx_frame, cy_frame), window_rect=win_rect, frame_size=frame_size)

    inp = WindowsCursorInput()
    origin = inp.cursor_pos()
    print('Botao %s: frame (%.0f,%.0f) -> tela (%.0f,%.0f). Movendo SEM clicar...'
          % (args.button, cx_frame, cy_frame, sx, sy), flush=True)
    inp.move_to(sx, sy)
    time.sleep(args.settle)
    inp.move_to(origin[0], origin[1])    # restaura
    print('Cursor restaurado. CONFIRME: ele parou em cima do botao %s? '
          '(nenhum clique foi enviado)' % args.button, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
