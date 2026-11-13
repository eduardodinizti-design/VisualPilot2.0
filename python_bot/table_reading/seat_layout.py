"""9-max PPPoker seat geometry as fractions of the table crop (experimental).

Derived from real blue-felt table gabaritos (750x1334). Fractions, so they
transfer across crop sizes of the same layout; other table sizes or skins are
NOT yet validated. A nameplate holds a name line and a stack line (XXX,X BB).

The hero is the bottom-centre seat (its cards are face-up); CLOCKWISE lists the
seats in poker action order starting at the hero, for deriving positions from
the dealer button once that is read.
"""

# Nameplate centre as (fx, fy) fractions of the crop, per physical seat.
SEAT_ANCHORS = {
    'hero':       (0.50, 0.90),
    'bot_right':  (0.89, 0.765),
    'right_low':  (0.90, 0.58),
    'right_up':   (0.89, 0.355),
    'top_right':  (0.69, 0.19),
    'top_center': (0.50, 0.215),
    'top_left':   (0.31, 0.19),
    'left_up':    (0.11, 0.355),
    'left_low':   (0.10, 0.58),
    'bot_left':   (0.11, 0.765),
}
# `top_center` é o assento do TOPO das mesas PPPoker 8-max (um só assento no topo, não
# os dois `top_left`/`top_right` do 9-max). Validado em 2 frames reais: RM6702 26,6 BB
# (MACHINE PKO) e Dekkii 48,8 BB (CRAZY REBUY), ambos lidos em (0.50, 0.215). Uma mesa
# real nunca ocupa top_center E top_left/top_right ao mesmo tempo (8-max XOR 9-max), e a
# ocupação por feltro azul descarta o vazio, então as 10 âncoras coexistem sem conflito.

# Ordem HORÁRIA (ordem de ação do poker) começando no hero. O assento seguinte é
# o SB quando o hero é o BTN. Direção corrigida 09/11 contra ground truth REAL de
# duas mesas Karekas (fichas de blind + botão "Call 0,5 BB"): o SB é o assento
# horário IMEDIATAMENTE após o BTN. A ordem anterior estava invertida (dava o CO
# no lugar do SB) e nunca fora conferida contra a postagem real de blinds.
CLOCKWISE = ['hero', 'bot_left', 'left_low', 'left_up', 'top_left', 'top_center',
             'top_right', 'right_up', 'right_low', 'bot_right']

NAMEPLATE_W = 0.22  # fraction of crop width
NAMEPLATE_H = 0.06  # fraction of crop height

# The avatar sits just above the nameplate; this circular photo is what tells an
# occupied seat from empty blue felt.
AVATAR_DY = 0.075   # how far above the nameplate centre the avatar centre is
AVATAR_W = 0.055    # half-width fraction
AVATAR_H = 0.045    # half-height fraction


def nameplate_box(width, height, seat):
    """Pixel box (x0, y0, x1, y1) of a seat's nameplate within a width x height crop."""
    fx, fy = SEAT_ANCHORS[seat]
    cx, cy = int(fx * width), int(fy * height)
    w2, h2 = int(NAMEPLATE_W * width / 2), int(NAMEPLATE_H * height / 2)
    return max(0, cx - w2), max(0, cy - h2), min(width, cx + w2), min(height, cy + h2)


def avatar_box(width, height, seat):
    """Pixel box (x0, y0, x1, y1) of a seat's avatar within a width x height crop."""
    fx, fy = SEAT_ANCHORS[seat]
    cx, cy = int(fx * width), int((fy - AVATAR_DY) * height)
    w2, h2 = int(AVATAR_W * width), int(AVATAR_H * height)
    return max(0, cx - w2), max(0, cy - h2), min(width, cx + w2), min(height, cy + h2)


# Centro do PILL de bounty (ícone de moeda + número) acima do avatar, por assento, em
# fração do crop. Calibrado no fixture MACHINE PKO (todos leem 135). O offset acima da
# âncora VARIA por assento (oval em perspectiva), por isso é por-assento, não um dy fixo.
# top_left/top_right NÃO têm jogador no fixture 8-max -> extrapolados (flag UNVALIDATED).
# Box do número do bounty por assento: (cx, cy, meia-largura) em fração; a meia-largura
# varia (o pill/ número têm tamanhos diferentes por assento) p/ ficar SOBRE o número e
# FORA do ícone de moeda (à esquerda). Calibrado no fixture MACHINE PKO (todos leem 135).
# EXPERIMENTAL: pills minúsculos + 1 frame -> confirmar no crop client-area ao vivo.
# top_left/top_right não têm jogador no fixture 8-max -> extrapolados (UNVALIDATED).
BOUNTY_BOXES = {
    'hero':       (0.50, 0.786, 0.06),
    'bot_right':  (0.88, 0.680, 0.06),
    'right_low':  (0.91, 0.496, 0.05),
    'right_up':   (0.88, 0.285, 0.05),
    'top_center': (0.50, 0.116, 0.05),
    'top_left':   (0.31, 0.100, 0.06),   # UNVALIDATED (9-max, sem amostra)
    'top_right':  (0.69, 0.100, 0.06),   # UNVALIDATED (9-max, sem amostra)
    'left_up':    (0.10, 0.276, 0.07),
    'left_low':   (0.10, 0.506, 0.05),
    'bot_left':   (0.10, 0.680, 0.06),
}
BOUNTY_HH = 0.017   # meia-altura do box (fração)
BOUNTY_UNVALIDATED = frozenset({'top_left', 'top_right'})


def bounty_box(width, height, seat):
    """Pixel box (x0, y0, x1, y1) do número do bounty do assento (acima do avatar)."""
    cx_f, cy_f, hw_f = BOUNTY_BOXES[seat]
    cx, cy = int(cx_f * width), int(cy_f * height)
    w2, h2 = int(hw_f * width), int(BOUNTY_HH * height)
    return max(0, cx - w2), max(0, cy - h2), min(width, cx + w2), min(height, cy + h2)
