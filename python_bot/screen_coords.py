"""Transform pixel do FRAME capturado -> coordenada de TELA do cursor (passo 2).

O frame é capturado em pixels FÍSICOS (DPI-aware): ex. 5760×2160 para uma janela
que é 3840×1440 em coordenadas LÓGICAS (DPI 1.5×). O adaptador de cursor
(`WindowsCursorInput`) opera em coordenadas LÓGICAS (GetSystemMetrics/GetCursorPos
DPI-unaware). Então, para o SendInput clicar no lugar certo, convertemos:

    tela_x = janela_x + fx * (janela_w / frame_w)
    tela_y = janela_y + fy * (janela_h / frame_h)

onde (janela_x, janela_y, janela_w, janela_h) é o rect LÓGICO da janela (do
`discover_pppoker`) e (frame_w, frame_h) é o tamanho FÍSICO do frame. A razão
janela/frame é 1/DPI. Coordenadas negativas (multi-monitor) são válidas.

NÃO move o cursor e NÃO clica. É só a geometria. A validação empírica (mover o
cursor até um botão e conferir visualmente, sem clicar) é separada.
"""


def frame_to_screen(point, *, window_rect, frame_size):
    """(fx, fy) físico do frame -> (sx, sy) na coordenada lógica do cursor.

    window_rect = (x, y, w, h) LÓGICO (discover_pppoker: x,y,w,h).
    frame_size  = (W, H) FÍSICO (meta image_shape = [H, W, 3] -> (W, H)).
    """
    fx, fy = point
    wx, wy, ww, wh = window_rect
    fw, fh = frame_size
    if fw <= 0 or fh <= 0:
        raise ValueError('frame_size invalido')
    return (wx + fx * (ww / fw), wy + fy * (wh / fh))


def rect_frame_to_screen(rect, *, window_rect, frame_size):
    """Retângulo (x,y,w,h) do frame -> retângulo na tela lógica (escala por eixo)."""
    x, y, w, h = rect
    sx, sy = frame_to_screen((x, y), window_rect=window_rect, frame_size=frame_size)
    ww, wh = window_rect[2], window_rect[3]
    fw, fh = frame_size
    return (sx, sy, w * (ww / fw), h * (wh / fh))


def dpi_scale(window_rect, frame_size):
    """(escala_x, escala_y) físico/lógico = frame/janela (ex.: 1.5)."""
    return (frame_size[0] / window_rect[2], frame_size[1] / window_rect[3])
