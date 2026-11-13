"""Leitor do VALOR do bounty (PKO/MKO) — núcleo testável + leitor parametrizado.

Contexto: o overlay de bounty do call-off ([[preflop_advisor.advise_call_off]]) usa
`bounty_bb`. Hoje esse valor é entrada (--bounty-bb). Este módulo é o caminho para
LÊ-LO da mesa — porém a POSIÇÃO (ROI) do bounty no skin depende de ver uma amostra
real de mesa PKO regular (bounty desde o início, mostrado por jogador) ou Mystery KO
JÁ no ITM (a Mystery esconde o bounty até o dinheiro). Nenhuma captura atual mostra um
valor de bounty (as que temos são CRAZY REBUY, sem bounty, e BOX MISTERY pré-ITM, com
o bounty oculto), então o ROI ainda NÃO está calibrado.

Decisão de projeto (ver AGENTS.md): NÃO adivinhar ROI. `read_bounty` ABSTÉM enquanto
não receber uma ROI calibrada. O `parse_bounty` (puro) já fica pronto e testado para o
formato do número, e a unidade é reportada para a conversão correta a BB.
"""
import re

import cv2

from .ocr_runtime import image_to_string

_CURRENCY = re.compile(r'(R\$|\$|€|£)')
_BB = re.compile(r'\bBB\b', re.I)
# primeiro número da string, com milhares/decimal e sufixo k/m opcional
_NUM = re.compile(r'(\d[\d.,]*\d|\d)\s*([kKmM])?')


def _to_float(num):
    """Converte '2,5'/'2.5'/'48,8'/'1.200,50'/'1,200.50'/'1200' em float. Resolve a
    ambiguidade milhar×decimal: com os dois separadores, o mais à DIREITA é o decimal;
    com um só, é decimal quando sobra 1-2 dígitos depois dele, senão é milhar."""
    s = num.strip()
    try:
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):            # vírgula é o decimal
                s = s.replace('.', '').replace(',', '.')
            else:                                      # ponto é o decimal
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.') if len(s.split(',')[-1]) <= 2 else s.replace(',', '')
        elif '.' in s:
            if len(s.split('.')[-1]) > 2:              # ponto de milhar
                s = s.replace('.', '')
        return float(s)
    except ValueError:
        return None


def parse_bounty(text):
    """(dict) a partir do texto OCR do bounty. Campos: `value` (float|None), `unit`
    ('bb'|'currency'|'unknown'), `confidence` ('high'|'medium'|'abstain'), `raw`.

    NÃO adivinha: sem dígito -> abstain. A unidade guia a conversão a BB (só `bb`
    converte direto; `currency`/`unknown` precisam de fator externo, então o chamador
    não deve tratá-las como BB)."""
    raw = text
    # O->0 só quando colado a dígito/decimal (ex. 'O,5'->'0,5', '1O'->'10'); 'MKO'
    # NÃO vira 'MK0' (senão leria 0).
    t = re.sub(r'(?<=[\d.,])[Oo]|[Oo](?=[\d.,])', '0', (text or '')).strip()
    if not t:
        return dict(value=None, unit='unknown', confidence='abstain', raw=raw)
    has_cur = bool(_CURRENCY.search(t))
    has_bb = bool(_BB.search(t))
    matches = list(_NUM.finditer(t))
    if not matches:
        return dict(value=None, unit='unknown', confidence='abstain', raw=raw)
    # Pega o número com MAIS dígitos: o pill de bounty tem um ícone de moeda que o OCR
    # às vezes lê como um dígito solto ('2 135') — o valor real é o token mais longo.
    m = max(matches, key=lambda x: sum(c.isdigit() for c in x.group(1)))
    value = _to_float(m.group(1))
    if value is None:
        return dict(value=None, unit='unknown', confidence='abstain', raw=raw)
    suffix = (m.group(2) or '').lower()
    if suffix == 'k':
        value *= 1000
    elif suffix == 'm':
        value *= 1_000_000
    unit = 'currency' if has_cur else 'bb' if has_bb else 'unknown'
    confidence = 'high' if (has_cur or has_bb) else 'medium'
    return dict(value=round(value, 4), unit=unit, confidence=confidence, raw=raw)


def read_bounty(crop, *, roi=None, psm=7):
    """Lê o valor do bounty de uma ROI CALIBRADA `roi`=(fx0,fy0,fx1,fy1) (fração do
    crop). SEM ROI calibrada -> ABSTÉM (não adivinha a posição no skin; calibrar com
    uma amostra real de mesa PKO/MKO-no-ITM). Devolve {bounty_bb, unit, confidence,
    source, raw}: `bounty_bb` só é preenchido quando a unidade lida é BB (currency/
    unknown não vira BB sem um fator de conversão externo)."""
    if roi is None:
        return dict(bounty_bb=None, unit='unknown', confidence='abstain',
                    source='no_calibrated_roi', raw=None)
    h, w = crop.shape[:2]
    fx0, fy0, fx1, fy1 = roi
    region = crop[int(fy0 * h):int(fy1 * h), int(fx0 * w):int(fx1 * w)]
    raw = ' '.join(image_to_string(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY),
                                   config='--psm %d' % psm).split())
    parsed = parse_bounty(raw)
    bounty_bb = parsed['value'] if parsed['unit'] == 'bb' else None
    return dict(bounty_bb=bounty_bb, unit=parsed['unit'], confidence=parsed['confidence'],
                source='ocr_roi', raw=raw, value=parsed['value'])


def read_seat_bounties(crop, *, seats=None, profile=None):
    """Bounty por assento (PKO). Cada jogador tem um pill (moeda + número) acima do
    avatar; o VALOR cresce quando ele acumula KOs (alvo mais gordo). Extrai o número por
    assento; a conversão p/ BB-EV não é derivável da mesa (ver read_bounty) — o número
    serve p/ achar o alvo mais gordo e escalar a caça relativo à base.

    Posição do pill: `seat_layout.bounty_box` (calibrado por assento). Com `profile`
    (= {seat: (fx0,fy0,fx1,fy1)}) usa ROIs explícitas (p/ outro skin). `seats` limita
    quais assentos ler (passe os OCUPADOS p/ não ler feltro vazio); padrão = todos.
    Abstém no assento ilegível. Devolve {seat: {value, unit, confidence, raw}}."""
    from .seat_layout import SEAT_ANCHORS, bounty_box
    out = {}
    if profile is not None:
        for seat, roi in profile.items():
            r = read_bounty(crop, roi=roi)
            out[seat] = dict(value=r['value'], unit=r['unit'], confidence=r['confidence'], raw=r['raw'])
        return out
    h, w = crop.shape[:2]
    for seat in (seats if seats is not None else SEAT_ANCHORS):
        out[seat] = _vote_seat_bounty(crop, w, h, bounty_box(w, h, seat))
    return out


# Jitters (em px) p/ a votação: OCR num pill minúsculo é frágil (1px flipa 135↔139↔'');
# ler vários boxes vizinhos e votar no valor mais frequente bate o ruído. Discordância
# sem maioria -> abstém (nunca inventa).
_BOUNTY_JITTERS = ((0, 0), (-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2))


def _vote_seat_bounty(crop, w, h, box):
    x0, y0, x1, y1 = box
    from collections import Counter
    votes = Counter()
    raws = []
    for dx, dy in _BOUNTY_JITTERS:
        sx0, sy0 = max(0, x0 + dx), max(0, y0 + dy)
        sx1, sy1 = min(w, x1 + dx), min(h, y1 + dy)
        region = crop[sy0:sy1, sx0:sx1]
        if region.size == 0:
            continue
        raw = ' '.join(image_to_string(
            cv2.cvtColor(region, cv2.COLOR_BGR2GRAY),
            config='--psm 7 -c tessedit_char_whitelist=0123456789.,').split())
        raws.append(raw)
        v = parse_bounty(raw)['value']
        if v is not None:
            votes[v] += 1
    (top, n) = votes.most_common(1)[0] if votes else (None, 0)
    # Só emite com MAIORIA FORTE dos votos válidos (>= metade do nº de jitters e > 1/2
    # dos votos válidos). Caso contrário ABSTÉM — nunca devolve um número ambíguo
    # (princípio do projeto: nada de confiante-errado). Assim o valor emitido é confiável
    # ou não vem; a leitura relativa (achar o alvo mais gordo) tolera assentos ausentes.
    strong = n >= max(2, len(_BOUNTY_JITTERS) // 2) and n > sum(votes.values()) / 2
    if not strong:
        return dict(value=None, unit='unknown', confidence='abstain',
                    raw=(raws[0] if raws else ''), votes=dict(votes))
    return dict(value=top, unit='unknown', confidence='high',
                raw=(raws[0] if raws else ''), votes=dict(votes))
