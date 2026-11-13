"""Read the PPPoker lobby grid (the 'grade'): one record per tournament card.

Observation only, experimental. Each MTT card has a bright blue buy-in badge on
the left (one per card) with "Buy-in: X" and the format, and to its right the
name, the players (registered/max), the blind-level minutes and a registration
status ("Registro encerra em N min" or "Horario de inicio: ..."). We anchor on
the badge and read the fields around it.

Calibrated on the Karekas (Evolution league) lobby, client v228, window ~746 px
wide. Other skins/scales need their own gabarito. No clicks, no registration:
this only reads the grid so the selector/policy can decide. The modality label
is a best-effort guess from the name; an unknown one is flagged, never assumed.
"""
import re
from decimal import Decimal, InvalidOperation
import cv2
import numpy as np

from table_reading.ocr_runtime import image_to_string
from table_reading.tournament import is_mystery, is_pko

_PLAYERS = re.compile(r'(\d+)\s*/\s*(\d+)')
_LEVEL_MIN = re.compile(r'(\d+)\s*min', re.I)
_CLOSES = re.compile(r'encerra\s*em\s*(\d+)\s*min', re.I)
_STARTS = re.compile(r'in[ií]cio[:\s]*(.+)$', re.I)
_MONEY = re.compile(r'\d+(?:[.,]\d+)?')


def _ocr(gray, cfg='--psm 7'):
    return ' '.join(image_to_string(gray, config=cfg).split())


def classify_modality(name):
    """Best-effort modality from the card name. 'unknown' when no keyword hits;
    the caller must not register an unknown modality without confirmation."""
    if not name:
        return 'unknown'
    up = name.upper()
    if is_mystery(name):
        return 'mko'
    if is_pko(name):
        return 'pko'
    if 'REBUY' in up:
        return 'rebuy'
    if 'ADD-ON' in up or 'ADDON' in up or 'ADD ON' in up:
        return 'addon'
    if 'FREEZE' in up or 'FREEZEOUT' in up:
        return 'freezeout'
    if 'DEEP' in up:
        return 'deep'
    return 'unknown'


def parse_buyin(raw):
    """Total buy-in from the badge/detail text, as a float WITH cents, or None.

    Keeps the decimals ('50,50' -> 50.5, not 50) and sums a composite buy-in
    (entry + fee + bounty, 'a + b + c' -> the total) so a cap check sees the real
    cost. A single value is not summed with any stray number near it."""
    text = (raw or '').split(':', 1)[-1]
    tokens = _MONEY.findall(text) if '+' in text else _MONEY.findall(text)[:1]
    if not tokens:
        return None
    try:
        total = sum((Decimal(t.replace(',', '.')) for t in tokens), Decimal(0))
    except InvalidOperation:
        return None
    return float(total)


def parse_players(raw):
    """(registered, max) from 'X/Y', or (None, None).

    The player icon can glue a stray digit onto the registered count ('71/105'
    read as '271/105'). registered > max is impossible, so recover by dropping a
    leading digit when that resolves it, else drop the registered value rather
    than report an impossible count. The max is kept when it reads."""
    m = _PLAYERS.search(raw or '')
    if not m:
        return (None, None)
    registered, maximum = int(m.group(1)), int(m.group(2))
    if registered > maximum:
        stripped = m.group(1)[1:]
        registered = int(stripped) if stripped and int(stripped) <= maximum else None
    return (registered, maximum)


def parse_level_minutes(raw):
    """Blind-level minutes from 'N min', or None (the first 'N min' on the line)."""
    m = _LEVEL_MIN.search(raw or '')
    return int(m.group(1)) if m else None


def parse_status(raw):
    """(state, closes_in_min, starts_at) from the status line. state is
    'reg_open' when a close countdown is shown, 'not_started' when only a start
    time is shown, else 'unknown'. Registration being open is never assumed.

    ESTRITO de propósito: só reconhece 'reg_open' no "Registro encerra em N min"
    exato. Clientes cujo cartão NÃO imprime o status de inscrição (ex.: o skin
    Karekas atual, que mostra só jogadores/nível/stack) leem 'unknown' — e o
    seletor bloqueia (fail-safe). NÃO inferir reg_open do "N min" do NÍVEL: isso
    falseava inscrição aberta. Para esses clientes, o operador afirma o status
    aberto no fluxo supervisionado (flag operator_asserted), nunca o leitor.
    """
    t = raw or ''
    m = _CLOSES.search(t)
    if m:
        return dict(state='reg_open', closes_in_min=int(m.group(1)), starts_at=None)
    m = _STARTS.search(t)
    if m:
        return dict(state='not_started', closes_in_min=None, starts_at=m.group(1).strip())
    return dict(state='unknown', closes_in_min=None, starts_at=None)


def find_buyin_badges(crop):
    """(x, y, w, h) of each blue buy-in badge, top to bottom. One per card."""
    h, w = crop.shape[:2]
    b, g, r = crop[:, :, 0].astype(int), crop[:, :, 1].astype(int), crop[:, :, 2].astype(int)
    blue = ((b > 140) & (b > r + 40) & (g > 80) & (g < b + 20)).astype(np.uint8) * 255
    blue = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(blue, 8)
    badges = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw > 0.20 * w and 0.03 * h < bh < 0.12 * h and area > 0.01 * w * h and x < 0.5 * w:
            badges.append((int(x), int(y), int(bw), int(bh)))
    return sorted(badges, key=lambda bb: bb[1])


def read_grade(crop):
    """List of card records, top to bottom. Each: name, buyin, modality, players
    (registered/max), level_minutes, status, plus the raw OCR per field and a
    confidence. Pure read; no eligibility decision is made here."""
    if crop is None or crop.ndim != 3 or crop.shape[2] != 3:
        raise ValueError('Expected a BGR lobby crop')
    h, w = crop.shape[:2]
    cards = []
    badges = find_buyin_badges(crop)
    # Os offsets verticais de nome/info/status foram calibrados no gabarito v228
    # (750px, pitch de 170px entre cartões). Em outra escala (ex.: o painel de
    # 1005px do canvas ao vivo) o cartão é maior, então escalamos os offsets pelo
    # pitch REAL medido nos próprios badges. Em v228 (pitch=170) a escala é 1.0 e
    # as ROIs ficam idênticas — sem regressão.
    PITCH_REF = 170
    ys = [b[1] for b in badges]
    gaps = sorted(b - a for a, b in zip(ys, ys[1:]))
    pitch = gaps[len(gaps) // 2] if gaps else PITCH_REF
    scale = pitch / PITCH_REF

    def band(cy, top_px, bot_px):
        return slice(max(0, cy + int(round(top_px * scale))),
                     cy + int(round(bot_px * scale)))

    for x, y, bw, bh in badges:
        cy = y + bh // 2
        rx = x + bw + 15
        buyin_raw = _ocr(cv2.cvtColor(crop[y + bh // 5:y + bh // 2 + 2, x + 8:x + bw - 8], cv2.COLOR_BGR2GRAY))
        name_raw = _ocr(cv2.cvtColor(crop[band(cy, -70, -22), rx:w - 15], cv2.COLOR_BGR2GRAY))
        info_raw = _ocr(cv2.cvtColor(crop[band(cy, -18, 18), rx:w - 15], cv2.COLOR_BGR2GRAY))
        stat_raw = _ocr(cv2.cvtColor(crop[band(cy, 20, 60), rx:w - 15], cv2.COLOR_BGR2GRAY))
        name = name_raw.strip()
        buyin = parse_buyin(buyin_raw)
        registered, maximum = parse_players(info_raw)
        status = parse_status(stat_raw)
        conf = 'high' if (name and buyin is not None) else ('medium' if name else 'abstain')
        cards.append(dict(
            name=name, buyin=buyin, modality=classify_modality(name),
            players_registered=registered, players_max=maximum,
            level_minutes=parse_level_minutes(info_raw), status=status,
            badge=[x, y, bw, bh], confidence=conf,
            raw=dict(buyin=buyin_raw, name=name_raw, info=info_raw, status=stat_raw)))
    return cards
