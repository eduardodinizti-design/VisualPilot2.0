"""Leitor do HUD VIP do PPPoker (8 stats por vilão) por TEMPLATE MATCHING de dígitos.

OCR do Tesseract NÃO serve nesses dígitos minúsculos (~8px) — confirmado. O caminho
robusto (como o leitor de rank) é: localizar a caixa do HUD por assento, dividir a
grade 4×2 (colunas iguais), segmentar os dígitos por componentes conectados (split de
dígitos colados), e casar cada dígito contra um ATLAS de templates (vizinho mais
próximo por correlação). A caixa é REFINADA por confiança (busca local que maximiza o
match) — o alinhamento preciso é o que faz a leitura ir a 48/48 nos HUDs rotulados.

Ordem fixa dos 8 stats (HUD VIP): VPIP·PFR·Steal·CheckRaise / 3Bet·Fold3Bet·CBet·FoldCBet.
O VALOR é a %/stat; o hero não tem HUD de si. Gating: campo só sai se a confiança mínima
dos seus dígitos >= HUD_MIN_CC — senão None (nunca confiante-errado).
"""
from pathlib import Path

import cv2
import numpy as np

from .seat_layout import SEAT_ANCHORS

HUD_W_FRAC = 0.182      # largura da caixa do HUD (fração do crop)
HUD_H_FRAC = 0.032      # altura (2 linhas)
_UPSCALE = 4
_BIN = 120              # threshold de binarização (dígitos brancos)
_DIGIT_W_UP = 26        # largura típica de um dígito (no upscale 4x) — p/ split de colados
_TS = (16, 24)          # (w, h) do template normalizado
_MIN_AREA = 70
HUD_MIN_CC = 0.45       # correlação mínima por dígito p/ aceitar o campo
HUD_FLOOR_CC = 0.52     # casamento médio mínimo da caixa (senão localizou em ruído)

STAT_NAMES = ('vpip', 'pfr', 'steal', 'cr', 'threebet', 'fold3bet', 'cbet', 'foldcbet')

# Posição ROUGH da caixa do HUD por assento (top-left, fração), ponto de partida da
# busca; a REFINAÇÃO por confiança (±px) acerta o alinhamento fino. Calibrado no skin
# MINI FREEZE (gabarito sessao-164218). top_center/bot_right extrapolados (UNVALIDATED).
HUD_SEARCH = {
    'left_up':    (0.000, 0.376), 'left_low':  (0.000, 0.612), 'bot_left':  (0.000, 0.791),
    'top_left':   (0.021, 0.179), 'top_right': (0.784, 0.178), 'right_up':  (0.788, 0.379),
    'right_low':  (0.792, 0.614), 'top_center': (0.300, 0.230), 'bot_right': (0.790, 0.791),
}
HUD_UNVALIDATED = frozenset({'top_center', 'bot_right'})

_ATLAS = None


def _load_atlas():
    global _ATLAS
    if _ATLAS is None:
        data = np.load(str(Path(__file__).with_name('hud_digit_atlas.npz')))
        _ATLAS = (data['templates'].astype(np.float32), data['labels'])
    return _ATLAS


def _norm(binimg):
    ys, xs = np.where(binimg > 0)
    if len(xs) == 0:
        return np.zeros((_TS[1], _TS[0]), np.float32)
    crop = binimg[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return cv2.resize(crop, _TS).astype(np.float32)


def _nv(arr):
    v = arr.astype(np.float32) - float(arr.mean())
    return (v / (np.linalg.norm(v) + 1e-6)).ravel()


def _blobs_cell(cell_gray):
    """Vetores normalizados dos dígitos de uma célula (esq->dir), com split de colados."""
    if cell_gray.size == 0:
        return []
    cell = cv2.resize(cell_gray, None, fx=_UPSCALE, fy=_UPSCALE, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(cell, _BIN, 255, cv2.THRESH_BINARY)
    n, _, st, _ = cv2.connectedComponentsWithStats(bw, 8)
    comps = sorted([st[i][:4] for i in range(1, n)
                    if 30 < st[i][3] < 95 and 8 < st[i][2] < 95 and st[i][4] > _MIN_AREA],
                   key=lambda s: s[0])
    out = []
    for x, y, w, h in comps:
        k = max(1, round(w / _DIGIT_W_UP))
        if k == 1:
            out.append(_nv(_norm(bw[y:y + h, x:x + w])))
            continue
        sub = bw[y:y + h, x:x + w]
        proj = sub.sum(axis=0)
        cuts = [0]
        for j in range(1, k):
            c = int(j * w / k)
            cuts.append(c - 8 + int(np.argmin(proj[max(0, c - 8):c + 8])))
        cuts.append(w)
        for i in range(len(cuts) - 1):
            out.append(_nv(_norm(sub[:, cuts[i]:cuts[i + 1]])))
    return out


def _cells(crop, x0, y0, bw, bh):
    H, W = crop.shape[:2]
    x0 = max(0, min(x0, W - bw))
    y0 = max(0, min(y0, H - bh))
    g = cv2.cvtColor(crop[y0:y0 + bh, x0:x0 + bw], cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    return [g[int(r * h / 2) + 1:int((r + 1) * h / 2) - 1, int(c * w / 4) + 2:int((c + 1) * w / 4) - 2]
            for r in range(2) for c in range(4)]


def _read_box(crop, x0, y0, bw, bh):
    """8 campos (valor, conf_min) + confiança total, p/ a posição de caixa dada."""
    V, L = _load_atlas()
    fields, total = [], 0.0
    for cell in _cells(crop, x0, y0, bw, bh):
        digs, mincc = '', 1.0
        for vec in _blobs_cell(cell):
            cc = V @ vec
            i = int(cc.argmax())
            digs += str(int(L[i]))
            total += float(cc[i])
            mincc = min(mincc, float(cc[i]))
        fields.append((int(digs) if digs else None, mincc if digs else 0.0))
    return fields, total


def _scan(crop, cx, cy, bw, bh, rx, ry, step):
    """Melhor (conf, x0, y0, fields) numa janela [±rx, ±ry] com passo `step`."""
    H, W = crop.shape[:2]
    best = (-9.0, cx, cy, None)
    for dx in range(-rx, rx + 1, step):
        for dy in range(-ry, ry + 1, step):
            x0 = max(0, min(cx + dx, W - bw))
            y0 = max(0, min(cy + dy, H - bh))
            fields, conf = _read_box(crop, x0, y0, bw, bh)
            if conf > best[0]:
                best = (conf, x0, y0, fields)
    return best


def _refine(crop, x0r, y0r, bw, bh):
    """Refina a caixa por confiança numa janela LOCAL (precisão > alcance: uma busca
    larga trava em falsos máximos e erra a leitura). A robustez vem do PISO de confiança
    em read_hud (abstém num locate ruim), não de alargar a busca — os skins PPPoker
    client-area casam no mesmo rough. Devolve (x0, y0, fields, conf)."""
    conf, x0, y0, fields = _scan(crop, x0r, y0r, bw, bh, rx=12, ry=8, step=2)
    return x0, y0, fields, conf


def read_hud(crop, seat):
    """Lê o HUD de um assento (localiza ROUGH pelo HUD_SEARCH + refina + casa). Devolve
    {stats:{nome:valor|None}, confidence, raw, box, min_cc} ou None se o assento não tem
    HUD legível (hero / vazio / confiança baixa)."""
    if seat not in HUD_SEARCH:
        return None
    H, W = crop.shape[:2]
    bw, bh = int(HUD_W_FRAC * W), int(HUD_H_FRAC * H)
    fx, fy = HUD_SEARCH[seat]
    x0, y0, fields, conf = _refine(crop, int(fx * W), int(fy * H), bw, bh)
    if fields is None:
        return None
    stats, ccs = {}, []
    for name, (val, cc) in zip(STAT_NAMES, fields):
        ok = val is not None and cc >= HUD_MIN_CC
        stats[name] = val if ok else None
        if ok:
            ccs.append(cc)
    read = sum(1 for v in stats.values() if v is not None)
    # Piso: metade dos campos legíveis E casamento médio decente (senão a caixa
    # localizou em ruído/skin não calibrado -> sem HUD, nunca inventa).
    if read < 4 or (ccs and sum(ccs) / len(ccs) < HUD_FLOOR_CC):
        return None
    return dict(stats=stats, raw=[f[0] for f in fields], box=(round(x0 / W, 3), round(y0 / H, 3)),
                min_cc=round(min(ccs), 3) if ccs else 0.0,
                confidence='high' if read == 8 else 'partial')


def read_seat_huds(crop, occupied_seats):
    """Lê o HUD de cada assento OCUPADO (hero sem HUD). Devolve {seat: read} só dos que
    têm HUD legível (abstém no resto, nunca inventa)."""
    out = {}
    for seat in occupied_seats:
        if seat == 'hero':
            continue
        r = read_hud(crop, seat)
        if r is not None:
            out[seat] = r
    return out
