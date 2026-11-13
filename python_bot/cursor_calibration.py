"""Calibração do movimento de referência do usuário (Fase 3B).

A spec `ORIENTAÇÃO PARA MOVIMENTO NATURAL` §3/§5 exige medir movimentos REAIS do
usuário antes de afirmar semelhança a um padrão humano, e proíbe apresentar
coeficientes inventados como medidos. Este módulo:

- Guarda amostras de trajetória (coordenadas + eventos, não imagens) com limite.
- Ajusta a lei de Fitts T = a + b·log2(1 + D/W) por mínimos quadrados sobre as
  amostras, retornando n e R² — e separando calibração de avaliação.

A medição em si (o usuário movendo o mouse num app de teste) é feita por um
app/registrador à parte; aqui ficam a estrutura das amostras e o ajuste.
"""
import json
import math
import time


class MovementRecorder:
    """Acumula amostras de movimento voluntário (sem ação de jogo). Guarda só
    telemetria necessária, com teto de itens (não grava tela)."""

    def __init__(self, *, max_items=20000, clock=time.monotonic):
        self.samples = []       # cada: dict(distance, width, duration, dir, t0)
        self.points = []        # (t_mono, x, y) brutos, para avaliação
        self._max = int(max_items)
        self._clock = clock
        self.dropped = 0

    def add_move(self, *, distance, width, duration, direction=None):
        if len(self.samples) >= self._max:
            self.dropped += 1
            return False
        self.samples.append(dict(distance=float(distance), width=float(width),
                                 duration=float(duration), direction=direction,
                                 t0=self._clock()))
        return True

    def add_point(self, x, y, t=None):
        if len(self.points) >= self._max:
            self.dropped += 1
            return False
        self.points.append(((self._clock() if t is None else t), float(x), float(y)))
        return True

    def to_json(self, path):
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(dict(samples=self.samples, points=self.points,
                           dropped=self.dropped), fh)
        return path


def fit_fitts(samples, *, min_n=5):
    """Ajusta (a, b) de T = a + b·x, x = log2(1 + D/W), por mínimos quadrados.

    `samples`: iterável de dicts com distance/width/duration (W>0, duração>0).
    Retorna dict(a, b, n, r2, measured, reason). measured=False (com reason) se
    houver poucas amostras ou variância nula em x — nunca devolve um coeficiente
    inventado como medido.
    """
    xs, ys = [], []
    for s in samples:
        w = float(s.get('width', 0) or 0)
        d = float(s.get('distance', 0) or 0)
        t = float(s.get('duration', 0) or 0)
        if w <= 0 or t <= 0 or d < 0:
            continue
        xs.append(math.log2(1.0 + d / w))
        ys.append(t)
    n = len(xs)
    if n < min_n:
        return dict(a=None, b=None, n=n, r2=None, measured=False,
                    reason='INSUFFICIENT_SAMPLES')
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return dict(a=None, b=None, n=n, r2=None, measured=False,
                    reason='NO_VARIANCE_IN_DIFFICULTY')   # todos no mesmo D/W
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    syy = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = (1.0 - ss_res / syy) if syy > 1e-12 else None
    return dict(a=a, b=b, n=n, r2=r2, measured=True, reason=None)
