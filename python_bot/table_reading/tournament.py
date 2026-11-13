"""Read the tournament phase from the table and map it to a strategy stage.

The PPPoker table prints "Lugares pagos: N" (paid places) and "Minha posicao:
rank/left" (left = players remaining). From those we pick the ICM stage the range
pack models (pre_itm / bubble / ft) or fall back to chip EV far from the money.

These thresholds are a first proposal, to calibrate with use; every answer says
which stage was chosen so it is never silent. No capture, no clicks.
"""
import re

import cv2

from .ocr_runtime import image_to_string

FINAL_TABLE = 9
# "Lugares pagos: N". OCR puts noise between "pagos" and N on some frames, which
# dropped the paid count (and with it the whole ICM/PKO stage, back to chip_ev).
# Tolerate a short run of non-digits, bounded so a distant number is never taken.
_PAID = re.compile(r'pagos\D{0,8}(\d+)', re.I)
# "Minha posicao: rank/left". OCR mangles the "cao" tail ("posig&o", "posigao"),
# so skip anything between "posi" and the rank/left pair instead of requiring a
# clean ":"; accept a '|' for the slash. The pair is anchored to "posi" so the
# blinds ("5,000/10K", also a slash) are never matched.
_POSITION = re.compile(r'posi.*?(\d+)\s*[/|]\s*(\d+)', re.I)
_NAME = re.compile(r'^(.*?)\s*Blinds', re.I)
# Mystery KO: bounty only AFTER the money (plays vanilla until ITM). "MISTERY" is
# the Portuguese spelling seen on the table.
_MYSTERY = re.compile(r'MYSTER|MIST[EÉ]R|\bM[\s.]?KO\b', re.I)
# Regular bounty (PKO): bounty from the start.
_PKO = re.compile(r'\bP[\s.]?KO\b|BOUNTY', re.I)
# Once in the money the table replaces "Lugares pagos" with "Premio atual"
# (your current prize). Seeing it means we are ITM even though paid stops reading.
_PRIZE = re.compile(r'pr.{0,2}mio\s*atual', re.I)   # "Premio/Prêmio/Pr?mio" (OCR mangles ê)


def is_mystery(name):
    """Mystery KO: the bounty is unlocked only once in the money."""
    return bool(name) and bool(_MYSTERY.search(name))


def is_pko(name):
    """Regular bounty from the start (PKO/Bounty), not a mystery KO."""
    return bool(name) and bool(_PKO.search(name)) and not is_mystery(name)


def read_tournament(crop):
    """{paid, players_left, hero_rank, name, is_pko, is_mystery, in_money, raw, confidence}.

    `in_money` is set when the "Premio atual" line is present, which the table
    shows (replacing "Lugares pagos") only once the hero is in the money."""
    h, w = crop.shape[:2]
    region = crop[int(0.49 * h):int(0.62 * h), int(0.25 * w):int(0.75 * w)]
    raw = ' '.join(image_to_string(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY), config='--psm 6').split())
    paid = _PAID.search(raw)
    pos = _POSITION.search(raw)
    name = _NAME.search(raw)
    paid_n = int(paid.group(1)) if paid else None
    left_n = int(pos.group(2)) if pos else None
    rank_n = int(pos.group(1)) if pos else None
    name_s = name.group(1).strip() if name else None
    conf = 'high' if (paid_n and left_n) else ('medium' if (paid_n or left_n) else 'abstain')
    return dict(paid=paid_n, players_left=left_n, hero_rank=rank_n, name=name_s,
                is_pko=is_pko(name_s), is_mystery=is_mystery(name_s),
                in_money=bool(_PRIZE.search(raw)), raw=raw, confidence=conf)


def tournament_stage(players_left, paid):
    """ICM stage the pack models, or 'far' (chip EV), or None if unknown.

    ft at the final table; bubble just before the money; pre_itm approaching it;
    'far' when deep before the money. In the money but before the final table has
    no matching pack stage, so it returns None (the caller uses chip EV). The final
    table is knowable from the seats alone, so it is detected even when paid stops
    reading (which happens in the money, when the table hides 'Lugares pagos')."""
    if not isinstance(players_left, int) or players_left <= 0:
        return None
    if players_left <= FINAL_TABLE:
        return 'ft'                   # detectable by seats alone, paid not needed
    if not isinstance(paid, int) or paid <= 0:
        return None                   # without paid, only the final table is knowable
    if players_left <= paid:          # in the money, before the final table: no pack stage
        return None
    band = max(1, round(0.15 * paid))
    if players_left <= paid + band:
        return 'bubble'
    if players_left <= round(paid * 1.6):
        return 'pre_itm'
    return 'far'


def tournament_context(tourney):
    """(mode, stage) for the advisor. A regular PKO carries the bounty from the
    start; a Mystery KO plays vanilla until the money, so its bounty only counts
    once in the money. Near the money -> icm/pko_icm at the stage; far -> chip_ev
    or pko at 'mid'. Detection is by name and still unvalidated."""
    paid, left = tourney.get('paid'), tourney.get('players_left')
    stage = tournament_stage(left, paid)
    # In the money either by count (left <= paid) or by the "Premio atual" signal,
    # which survives when paid stops reading ITM. A Mystery KO's bounty needs this.
    in_money = (isinstance(left, int) and isinstance(paid, int) and left <= paid) or bool(tourney.get('in_money'))
    bounty = bool(tourney.get('is_pko')) or (bool(tourney.get('is_mystery')) and in_money)
    if stage in ('ft', 'bubble', 'pre_itm'):
        return ('pko_icm' if bounty else 'icm'), stage
    if in_money and bounty:            # ITM with an active bounty but no exact ICM stage
        return 'pko', 'mid'
    return ('pko' if bounty else 'chip_ev'), 'mid'
