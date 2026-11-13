"""Ponte lobby real → registrador supervisionado (Fase 3A, plug no lobby).

Liga a leitura validada do lobby (`grade_reader`) + o seletor de política (F1,
`select_from_grade`) ao fluxo de inscrição 3A (`registration_flow`), SEM clicar.

Descoberta de calibração (09/11): entre os crops que `detect_table_crops`
propõe no canvas do PPPoker, o LOBBY é o que contém badges de buy-in (os cartões
de torneio); uma mesa tem zero. É assim que separamos o painel do lobby da mesa.

Fonte de verdade: o LEDGER. `session_state_from_ledger` reconstrói o
`SessionState` a partir das reservas reais, para o pré-filtro `evaluate_card` ver
orçamento/vagas coerentes com o que já foi reservado (resolve a nota de "duas
fontes" da 3A).
"""
import cv2

from grade_reader import find_buyin_badges, read_grade
from registration_ledger import ACTIVE_STATES, _ACTIVE_SQL
from session_config import SessionState, select_from_grade
from table_reading.automatic_table_crops import detect_table_crops


def find_lobby_crop(frame_bgr, *, max_crops=6, detector=detect_table_crops,
                    badger=find_buyin_badges):
    """(crop_bgr, box, n_badges) do painel do lobby no frame, ou (None, None, 0).

    O lobby é o crop com mais badges de buy-in (>=1), independente do status de
    MESA do detector: o lobby não é uma mesa, então costuma vir UNCERTAIN (não
    tem geometria de feltro). O sinal confiável são os badges, não o status.
    """
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    best = None
    for p in detector(rgb, max_tables=max_crops):
        x, y, w, h = map(int, p.box)
        crop = frame_bgr[y:y + h, x:x + w]
        n = len(badger(crop))
        if n and (best is None or n > best[2]):
            best = (crop, (x, y, w, h), n)
    return best if best else (None, None, 0)


def read_lobby(image_bgr, *, is_crop=False, reader=read_grade, **kw):
    """Lê os cartões do lobby.

    is_crop=True trata `image_bgr` como o painel do lobby JÁ recortado (ex.: o
    crop `mesa-1`); caso contrário localiza o painel no frame inteiro.
    """
    if is_crop:
        crop = image_bgr
        box = (0, 0, crop.shape[1], crop.shape[0])
        n = len(find_buyin_badges(crop))
    else:
        crop, box, n = find_lobby_crop(image_bgr, **kw)
        if crop is None:
            return dict(ok=False, reason='NO_LOBBY_CROP_FOUND', cards=[], box=None)
    return dict(ok=True, cards=reader(crop), box=box, n_badges=n)


def merge_cards(frames_cards):
    """Mescla N leituras do lobby. A 3ª linha do cartão Karekas ALTERNA entre o
    stack inicial e "Registro encerra em N min" (~1 Hz), então uma captura só é
    sorte. Em N frames, para cada cartão (chave nome+buy-in) mantemos o status
    mais informativo (reg_open/not_started vence unknown). Fail-safe preservado:
    nunca inventamos reg_open — ele só entra se ALGUM frame o leu de verdade.
    """
    merged, order = {}, []
    for cards in frames_cards:
        for c in cards:
            key = ((c.get('name') or '').strip(), c.get('buyin'))
            if key not in merged:
                merged[key] = dict(c)
                order.append(key)
            else:
                cur = merged[key]
                cur_st = (cur.get('status') or {}).get('state')
                new_st = (c.get('status') or {}).get('state')
                if cur_st in (None, 'unknown') and new_st not in (None, 'unknown'):
                    cur['status'] = c['status']
    return [merged[k] for k in order]


def read_lobby_multi(capture, *, frames=5, delay=0.5, sleep=None, **kw):
    """Lê o lobby em N frames e mescla (ver merge_cards). `capture` é um callable
    () -> frame_bgr (BGR) ou None. `sleep` injetável para teste."""
    import time as _t
    sleep = sleep or _t.sleep
    reads, box, n = [], None, 0
    for i in range(max(1, frames)):
        frame = capture()
        if frame is not None:
            out = read_lobby(frame, **kw)
            if out['ok']:
                reads.append(out['cards'])
                box, n = out['box'], max(n, out['n_badges'])
        if i < frames - 1:
            sleep(delay)
    if not reads:
        return dict(ok=False, reason='NO_LOBBY_CROP_FOUND', cards=[], box=None)
    return dict(ok=True, cards=merge_cards(reads), box=box, n_badges=n,
                frames=len(reads))


def session_state_from_ledger(ledger):
    """SessionState coerente com o ledger: reservas pendentes → committed;
    confirmados → confirmed_spend. Nada contado duas vezes."""
    st = SessionState()
    rows = ledger.db.execute(
        'SELECT name,cost,state FROM reservations WHERE state IN (%s)' % _ACTIVE_SQL,
        ACTIVE_STATES).fetchall()
    for name, cost, state in rows:
        if state == 'CONFIRMED':
            st.confirmed_spend += float(cost)
        else:
            st.committed.append(dict(name=name, buyin=float(cost)))
    return st


def details_from_card(card, *, club, currency, start_time=None):
    """Detalhes derivados do CARTÃO do lobby + moeda informada pelo operador.

    IMPORTANTE (honesto): a 3A NÃO abre a tela de detalhes (isso exigiria um
    clique). Então estes "detalhes" vêm do lobby + o que o operador confirma; a
    conferência lobby×detalhes do §C fica degradada (mesma fonte) e é sinalizada
    por `details_source`. `currency` NUNCA é inventada — se None, o fluxo bloqueia.
    """
    status = card.get('status') or {}
    return dict(name=card.get('name'), club=club, modality=card.get('modality'),
                buyin=card.get('buyin'), currency=currency,
                start_time=start_time or status.get('starts_at'),
                status=status, details_source='lobby+operator')


def select_lobby(cards, config, ledger, *, club=None, now_hhmm=None):
    """(elegíveis, bloqueados) do lobby, usando o ledger como fonte de verdade."""
    state = session_state_from_ledger(ledger)
    return select_from_grade(cards, config, state, club=club, now_hhmm=now_hhmm)
