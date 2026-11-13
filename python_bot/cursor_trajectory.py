"""Gerador de trajetória de cursor — PURO, sem Windows, sem clique (Fase 3B).

Implementa a baseline da spec `ORIENTAÇÃO PARA MOVIMENTO NATURAL D.txt`:

- Progresso por mínimo jerk: s(u)=10u³−15u⁴+6u⁵ (começo/fim com velocidade e
  aceleração nulas no modelo contínuo). posição(u)=início+s(u)·(destino−início).
- Duração relacionada à distância/alvo (lei de Fitts T=a+b·log2(1+D/W)), NUNCA
  uma duração universal. Os coeficientes a,b são DEFAULTS marcados `calibrated=
  False` — a spec proíbe apresentar coeficiente inventado como medido. Calibre
  com movimentos reais do usuário (ver `calibrate`) antes de afirmar semelhança;
  sem dados, descreva o resultado como "movimento suave", não "humano".
- Relógio injetável; progresso pelo tempo REALMENTE decorrido (não pressupõe que
  cada sleep foi atendido). Quando o prazo expira, o COORDENADOR cancela a
  intenção em vez de acelerar um clique vencido — aqui só geramos a trajetória.
- Desktop virtual: coordenadas negativas são válidas; não presumir origem única.

Este módulo NÃO move o cursor e NÃO clica. É só a geometria/tempo do caminho.
"""
import math
import time


def min_jerk_s(u):
    """Perfil de progresso de mínimo jerk em [0,1]. s(0)=0, s(1)=1, s'(0)=s'(1)=0."""
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    return u * u * u * (10.0 - 15.0 * u + 6.0 * u * u)


# Defaults NÃO medidos (placeholder). NÃO são do usuário; servem só para produzir
# um "movimento suave" antes da calibração. a em segundos, b em segundos/bit.
DEFAULT_FITTS_A = 0.12
DEFAULT_FITTS_B = 0.10
MIN_DURATION_S = 0.12


def fitts_duration(distance, width, *, a, b, min_s=MIN_DURATION_S):
    """Duração estimada do movimento pela lei de Fitts, em segundos.

    T = a + b·log2(1 + D/W). W é a largura efetiva do alvo na direção da
    aproximação; use um valor > 0. Piso em `min_s`. Não some esperas aleatórias.
    """
    w = max(float(width), 1.0)
    d = max(float(distance), 0.0)
    t = a + b * math.log2(1.0 + d / w)
    return max(t, min_s)


class TrajectoryPlan:
    """Um caminho planejado início→destino com duração fixa. Amostre por tempo
    decorrido real; o plano é imutável e puro."""

    def __init__(self, start, dest, duration_s, *, clock=time.monotonic, t0=None):
        self.start = (float(start[0]), float(start[1]))
        self.dest = (float(dest[0]), float(dest[1]))
        self.duration_s = max(float(duration_s), 1e-6)
        self._clock = clock
        self.t0 = self._clock() if t0 is None else t0

    def progress(self, now=None):
        """u ∈ [0,1] pelo tempo realmente decorrido desde t0."""
        now = self._clock() if now is None else now
        return max(0.0, min(1.0, (now - self.t0) / self.duration_s))

    def point_at(self, u):
        s = min_jerk_s(u)
        return (self.start[0] + s * (self.dest[0] - self.start[0]),
                self.start[1] + s * (self.dest[1] - self.start[1]))

    def position(self, now=None):
        return self.point_at(self.progress(now))

    def done(self, now=None):
        return self.progress(now) >= 1.0

    def sample(self, step_s):
        """Lista de (t_rel, x, y) do caminho em passos de `step_s` (para teste/
        avaliação offline; não envia nada). Inclui o ponto final exato."""
        step_s = max(float(step_s), 1e-4)
        pts, t = [], 0.0
        while t < self.duration_s:
            u = t / self.duration_s
            x, y = self.point_at(u)
            pts.append((t, x, y))
            t += step_s
        x, y = self.point_at(1.0)
        pts.append((self.duration_s, x, y))
        return pts


def safe_point(rect, *, margin_frac=0.25):
    """Centro da região interna segura de um botão (rect=(x,y,w,h)), com margem
    das bordas. Baseline da spec: o centro é adequado para precisão enquanto não
    houver evidência que justifique outro ponto. Sem tremor/overshoot por padrão.
    """
    x, y, w, h = rect
    return (x + w / 2.0, y + h / 2.0, margin_frac)


def within_virtual_desktop(point, bounds):
    """True se `point` está dentro do desktop virtual `bounds`=(x,y,w,h). Aceita
    origem/coords negativas (multi-monitor)."""
    px, py = point[0], point[1]
    bx, by, bw, bh = bounds
    return bx <= px <= bx + bw and by <= py <= by + bh


class TrajectoryGenerator:
    """Planeja trajetórias min-jerk com duração por Fitts. Coeficientes default
    são NÃO medidos até `calibrate`."""

    def __init__(self, *, a=DEFAULT_FITTS_A, b=DEFAULT_FITTS_B, calibrated=False,
                 clock=time.monotonic):
        self.a = float(a)
        self.b = float(b)
        self.calibrated = bool(calibrated)
        self._clock = clock

    def plan(self, start, dest, *, width=48.0, t0=None):
        d = math.hypot(dest[0] - start[0], dest[1] - start[1])
        dur = fitts_duration(d, width, a=self.a, b=self.b)
        return TrajectoryPlan(start, dest, dur, clock=self._clock, t0=t0)

    def calibrate(self, a, b):
        """Fixa coeficientes medidos (ver cursor_calibration.fit_fitts) e marca
        `calibrated=True` — só então é honesto comparar com o padrão do usuário."""
        self.a, self.b, self.calibrated = float(a), float(b), True
        return self

    def quality_label(self):
        """Rótulo honesto: sem calibração, é 'movimento suave', não 'humano'."""
        return ('movimento calibrado' if self.calibrated
                else 'movimento suave (coeficientes NAO medidos)')
