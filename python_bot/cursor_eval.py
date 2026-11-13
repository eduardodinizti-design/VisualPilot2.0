"""Avaliação independente do movimento do cursor (Fase 3B, bloco 2).

Métricas §12 da spec `ORIENTAÇÃO PARA MOVIMENTO NATURAL` sobre amostras de
trajetória (medidas do usuário OU geradas pela baseline): duração vs distância/
alvo, comprimento/curvatura do caminho, perfis de velocidade, estabilidade de
chegada, erro de posição final, correções. PURO — não move cursor, não clica.

A spec exige: medir a naturalidade nas amostras de AVALIAÇÃO (separadas das de
calibração); informar n e limitações; NÃO prometer percentual de semelhança sem
métrica, conjunto e método definidos. Semelhança medida ≠ prova de origem humana.
"""
import math
import random


def _pts(points):
    return [(float(t), float(x), float(y)) for t, x, y in points]


def movement_metrics(points, *, target=None, width=None):
    """Métricas de UM movimento. `points`=[(t,x,y),...] em ordem de tempo.

    Retorna dict com duration, straight_distance, path_length, curvature_ratio,
    peak_velocity, time_to_peak_frac, final_error (se target), overshoot_frac,
    reversals (correções de direção ao longo do eixo start→alvo). n<2 → abstém.
    """
    p = _pts(points)
    if len(p) < 2:
        return dict(n=len(p), reason='TOO_FEW_POINTS')
    t0 = p[0][0]
    start = (p[0][1], p[0][2])
    end = (p[-1][1], p[-1][2])
    aim = target if target is not None else end
    axis = (aim[0] - start[0], aim[1] - start[1])
    straight = math.hypot(*axis)
    ux, uy = ((axis[0] / straight, axis[1] / straight) if straight > 1e-9 else (0.0, 0.0))

    path = 0.0
    peak_v = 0.0
    peak_t = t0
    max_proj = 0.0
    prev_along_v = None
    reversals = 0
    for (ta, xa, ya), (tb, xb, yb) in zip(p, p[1:]):
        seg = math.hypot(xb - xa, yb - ya)
        path += seg
        dt = tb - ta
        if dt > 1e-9:
            v = seg / dt
            if v > peak_v:
                peak_v, peak_t = v, tb
            along_v = ((xb - xa) * ux + (yb - ya) * uy) / dt
            if prev_along_v is not None and along_v * prev_along_v < 0:
                reversals += 1
            prev_along_v = along_v
        proj = (xb - start[0]) * ux + (yb - start[1]) * uy
        max_proj = max(max_proj, proj)

    duration = p[-1][0] - t0
    out = dict(
        n=len(p), duration=duration, straight_distance=straight, path_length=path,
        curvature_ratio=(path / straight if straight > 1e-9 else None),
        peak_velocity=peak_v,
        time_to_peak_frac=((peak_t - t0) / duration if duration > 1e-9 else None),
        overshoot_frac=(max(max_proj - straight, 0.0) / straight if straight > 1e-9 else None),
        reversals=reversals,
    )
    if target is not None:
        out['final_error'] = math.hypot(end[0] - target[0], end[1] - target[1])
    if width is not None:
        out['width'] = float(width)
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def summarize_trials(trials_metrics):
    """Agrega métricas de vários movimentos (médias + n). Reporta limitações: é
    descritivo, não uma alegação de semelhança humana."""
    m = [t for t in trials_metrics if t.get('reason') is None]
    n = len(m)
    if n == 0:
        return dict(n=0, reason='NO_VALID_TRIALS')
    keys = ('duration', 'curvature_ratio', 'peak_velocity', 'time_to_peak_frac',
            'overshoot_frac', 'final_error', 'reversals')
    summary = {('mean_' + k): _mean([t.get(k) for t in m]) for k in keys}
    summary['n'] = n
    summary['note'] = ('Descritivo das amostras; NAO e prova de origem humana. '
                       'Compare contra as amostras do usuario antes de afirmar '
                       'semelhanca.')
    return summary


def make_trials(area, *, n=12, widths=(32, 48, 64, 96), seed=0, margin=40):
    """Gera N alvos variados (distância/direção/tamanho) dentro de `area`=(w,h),
    para a medição de calibração. Determinístico por `seed`. Alvos ficam dentro
    da margem; inclui o ponto de partida sugerido (centro)."""
    rng = random.Random(seed)
    aw, ah = area
    center = (aw / 2.0, ah / 2.0)
    trials = []
    for i in range(n):
        w = rng.choice(widths)
        h = max(24, w // 2)
        x = rng.uniform(margin, max(margin, aw - margin - w))
        y = rng.uniform(margin, max(margin, ah - margin - h))
        cx, cy = x + w / 2.0, y + h / 2.0
        trials.append(dict(index=i, rect=(round(x), round(y), w, h),
                           center=(cx, cy), width=w,
                           distance_from_center=math.hypot(cx - center[0], cy - center[1])))
    return trials
