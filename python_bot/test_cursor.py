"""Testes do controlador de cursor (Fase 3B) — puro/lab, sem Windows real.

Cobre o gerador de trajetória, o adaptador de entrada (backend falso), a máquina
de estados do coordenador (revalidação na chegada, cancelamento, clique único,
exclusão mútua, gate) e o ajuste de Fitts.
"""
import threading
import unittest

from cursor_trajectory import (TrajectoryGenerator, TrajectoryPlan,
                               fitts_duration, min_jerk_s, safe_point,
                               within_virtual_desktop)
from cursor_input_win import WindowsCursorInput, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
from cursor_controller import CursorController, Intent, center_of
from cursor_calibration import fit_fitts, MovementRecorder
from cursor_eval import movement_metrics, summarize_trials, make_trials


class StepClock:
    """Relógio injetável que avança `dt` a cada chamada."""
    def __init__(self, start=1000.0, dt=0.1):
        self.t = start
        self.dt = dt

    def __call__(self):
        v = self.t
        self.t += self.dt
        return v


# ---------- trajetória -------------------------------------------------------
class TrajectoryTest(unittest.TestCase):
    def test_min_jerk_endpoints_and_mid(self):
        self.assertEqual(min_jerk_s(0.0), 0.0)
        self.assertEqual(min_jerk_s(1.0), 1.0)
        self.assertAlmostEqual(min_jerk_s(0.5), 0.5, places=9)
        self.assertEqual(min_jerk_s(-0.3), 0.0)   # clamp
        self.assertEqual(min_jerk_s(2.0), 1.0)

    def test_min_jerk_zero_velocity_at_ends(self):
        eps = 1e-5
        v0 = (min_jerk_s(eps) - min_jerk_s(0)) / eps
        v1 = (min_jerk_s(1.0) - min_jerk_s(1.0 - eps)) / eps
        self.assertLess(v0, 1e-3)   # começa parado
        self.assertLess(v1, 1e-3)   # termina parado

    def test_monotonic_progress(self):
        prev = -1
        for i in range(101):
            s = min_jerk_s(i / 100.0)
            self.assertGreaterEqual(s, prev)
            prev = s

    def test_fitts_duration_formula_and_floor(self):
        import math
        d, w, a, b = 1000.0, 50.0, 0.1, 0.1
        self.assertAlmostEqual(fitts_duration(d, w, a=a, b=b),
                               a + b * math.log2(1 + d / w), places=9)
        self.assertEqual(fitts_duration(0, 50, a=0.1, b=0.1, min_s=0.2), 0.2)

    def test_plan_positions_and_done(self):
        clk = StepClock(dt=0.0)   # tempo fixo p/ amostrar manualmente
        plan = TrajectoryPlan((0, 0), (100, 200), 1.0, clock=clk, t0=0.0)
        self.assertEqual(plan.point_at(0.0), (0.0, 0.0))
        self.assertEqual(plan.point_at(1.0), (100.0, 200.0))
        self.assertAlmostEqual(plan.position(now=0.5)[0], 50.0, places=6)
        self.assertTrue(plan.done(now=1.0))
        self.assertFalse(plan.done(now=0.3))

    def test_sample_includes_endpoints(self):
        plan = TrajectoryPlan((0, 0), (10, 0), 1.0, t0=0.0)
        pts = plan.sample(0.25)
        self.assertEqual(pts[0][1:], (0.0, 0.0))
        self.assertEqual(pts[-1][1:], (10.0, 0.0))

    def test_safe_point_center(self):
        cx, cy, m = safe_point((10, 20, 100, 40), margin_frac=0.2)
        self.assertEqual((cx, cy, m), (60.0, 40.0, 0.2))

    def test_virtual_desktop_negative_coords(self):
        bounds = (-1280, 0, 3840, 1440)
        self.assertTrue(within_virtual_desktop((-1280, 0), bounds))
        self.assertTrue(within_virtual_desktop((640, 720), bounds))
        self.assertFalse(within_virtual_desktop((3000, 0), bounds))

    def test_generator_calibration_flag(self):
        g = TrajectoryGenerator(clock=StepClock(dt=0.0))
        self.assertFalse(g.calibrated)
        self.assertIn('NAO medidos', g.quality_label())
        g.calibrate(0.2, 0.15)
        self.assertTrue(g.calibrated)
        self.assertEqual((g.a, g.b), (0.2, 0.15))


# ---------- adaptador de entrada --------------------------------------------
class FakeBackend:
    def __init__(self, bounds=(-1280, 0, 3840, 1440), pos=(100, 100),
                 accept=None, raise_on=None, up_accept=None):
        self._bounds = bounds
        self._pos = pos
        self.sent = []          # lista de (flags_list, abs_xy)
        self._accept = accept   # dict flag->count, ou None => len
        self._raise_on = raise_on
        self._up_accept = up_accept   # força o nº aceito do mouse-up (p/ teste)

    def virtual_bounds(self):
        return self._bounds

    def get_cursor_pos(self):
        return self._pos

    def send(self, flags_list, abs_xy=None):
        if self._raise_on is not None and self._raise_on in flags_list:
            raise RuntimeError('falha de envio simulada')
        self.sent.append((tuple(flags_list), abs_xy))
        if self._up_accept is not None and MOUSEEVENTF_LEFTUP in flags_list:
            return self._up_accept
        return len(flags_list)


class InputAdapterTest(unittest.TestCase):
    def test_normalize_abs_virtual_desktop(self):
        inp = WindowsCursorInput(_backend=FakeBackend())
        b = (-1280, 0, 3840, 1440)
        self.assertEqual(inp.normalize_abs(-1280, 0, b), (0, 0))
        self.assertEqual(inp.normalize_abs(-1280 + 3839, 1439, b), (65535, 65535))
        cx, _ = inp.normalize_abs(-1280 + 1920, 720, b)
        self.assertTrue(32000 < cx < 33000)

    def test_move_reports_accepted(self):
        be = FakeBackend()
        inp = WindowsCursorInput(_backend=be)
        r = inp.move_to(0, 720)
        self.assertEqual(r['accepted'], 1)
        self.assertEqual(len(be.sent), 1)

    def test_click_once_down_then_up_released(self):
        be = FakeBackend()
        inp = WindowsCursorInput(_backend=be, sleep=lambda s: None)
        r = inp.click_once(0, 0)
        flags_seq = [f[0][0] for f in be.sent]   # move, down, up
        self.assertIn(MOUSEEVENTF_LEFTDOWN, flags_seq)
        self.assertEqual(flags_seq[-1], MOUSEEVENTF_LEFTUP)   # up por último
        self.assertTrue(r['released'])

    def test_release_unconfirmed_when_up_rejected(self):
        # Caso reproduzido: mouse-up RECUSADO pela API (up_accepted=0) -> a soltura
        # NÃO deve ser dada como confirmada (botão poderia ficar preso).
        be = FakeBackend(up_accept=0)
        inp = WindowsCursorInput(_backend=be, sleep=lambda s: None)
        r = inp.click_once(0, 0)
        self.assertEqual(r['up_accepted'], 0)
        self.assertFalse(r['released'])          # não confirma soltura
        self.assertIn(MOUSEEVENTF_LEFTUP, [f[0][0] for f in be.sent])  # mas tentou soltar

    def test_click_release_guaranteed_on_error(self):
        # Se o hold (sleep) lançar, o up ainda é enviado (finally).
        be = FakeBackend()

        def boom(_):
            raise RuntimeError('interrompido entre down e up')
        inp = WindowsCursorInput(_backend=be, sleep=boom)
        with self.assertRaises(RuntimeError):
            inp.click_once(0, 0)
        flags_seq = [f[0][0] for f in be.sent]
        self.assertIn(MOUSEEVENTF_LEFTDOWN, flags_seq)
        self.assertIn(MOUSEEVENTF_LEFTUP, flags_seq)   # soltura garantida


# ---------- coordenador ------------------------------------------------------
class FakeInput:
    def __init__(self, pos=(0, 0), released=True, down_accept=1, move_accept=1,
                 track_pos=True, raise_cursor_pos=False):
        self.pos = pos
        self.moves = []
        self.clicks = 0
        self.released = released
        self.down_accept = down_accept
        self.move_accept = move_accept
        self.track_pos = track_pos          # cursor acompanha o move (chega ao alvo)
        self.raise_cursor_pos = raise_cursor_pos

    def cursor_pos(self):
        if self.raise_cursor_pos:
            raise RuntimeError('sem leitura do cursor')
        return self.pos

    def move_to(self, x, y, bounds=None):
        self.moves.append((x, y))
        if self.track_pos:
            self.pos = (x, y)
        return dict(requested=1, accepted=self.move_accept)

    def click_once(self, x, y=None, bounds=None, hold_s=None):
        self.clicks += 1
        if x is not None and y is not None and self.track_pos:
            self.pos = (x, y)
        return dict(released=self.released, down_accepted=self.down_accept,
                    up_accepted=1 if self.released else 0,
                    moved=dict(requested=1, accepted=self.move_accept))


class Control:
    def __init__(self, running=True):
        self.running = running

    def execution_allowed(self):
        return self.running


def _intent(deadline=1e12, iid='i1'):
    return Intent(id=iid, action='confirm', source_key='tbl#1',
                  target_rect=(100, 100, 80, 40), deadline=deadline)


def _ctrl(inp, validator, **kw):
    kw.setdefault('clock', StepClock(dt=0.1))
    kw.setdefault('sleep', lambda s: None)
    kw.setdefault('trajectory', TrajectoryGenerator(clock=kw['clock']))
    return CursorController(input_adapter=inp, validator=validator, **kw)


def _ok(intent, now):
    return dict(ok=True, target_rect=intent.target_rect)


class ControllerTest(unittest.TestCase):
    def test_happy_path_single_click_done(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok, bot_control=Control(True),
                  verifier=lambda i, n: dict(confirmed=True))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'DONE')
        self.assertEqual(inp.clicks, 1)              # clique ÚNICO
        self.assertGreater(len(inp.moves), 0)        # houve movimento

    def test_not_armed_refuses(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok, bot_control=Control(False))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('BOT_NOT_RUNNING', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_expired_intent_no_click(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok, clock=StepClock(start=1000, dt=0.1))
        out = c.execute(_intent(deadline=500))       # já vencida
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('INTENT_EXPIRED', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_cancel_on_user_intervention_no_click(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok, cancel_check=lambda i, n, p: 'USER_INTERVENTION')
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('USER_INTERVENTION', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_arrival_revalidation_fail_no_click(self):
        inp = FakeInput()
        seq = [dict(ok=True, target_rect=(100, 100, 80, 40)),
               dict(ok=False, reasons=['WINDOW_MOVED'])]
        it = iter(seq)
        c = _ctrl(inp, lambda i, n: next(it))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('ARRIVAL_REVALIDATION_FAILED', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_target_moved_on_arrival_no_click(self):
        inp = FakeInput()
        seq = [dict(ok=True, target_rect=(100, 100, 80, 40)),
               dict(ok=True, target_rect=(300, 300, 80, 40))]
        it = iter(seq)
        c = _ctrl(inp, lambda i, n: next(it))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('TARGET_MOVED_ON_ARRIVAL', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_no_verifier_unknown_after_click(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok)
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'UNKNOWN_RESULT')
        self.assertIn('NO_VERIFIER', out['reasons'])
        self.assertEqual(inp.clicks, 1)

    def test_effect_unconfirmed_is_unknown(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok, verifier=lambda i, n: dict(confirmed=False))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'UNKNOWN_RESULT')
        self.assertIn('EFFECT_UNCONFIRMED', out['reasons'])

    def test_intent_not_clicked_twice(self):
        inp = FakeInput()
        c = _ctrl(inp, _ok, verifier=lambda i, n: dict(confirmed=True))
        it = _intent(iid='dup')
        self.assertEqual(c.execute(it)['state'], 'DONE')
        out2 = c.execute(it)                          # mesma intenção de novo
        self.assertEqual(out2['state'], 'CANCELLED')
        self.assertIn('INTENT_ALREADY_CONSUMED', out2['reasons'])
        self.assertEqual(inp.clicks, 1)               # nunca dois cliques

    def test_release_unconfirmed_is_unknown(self):
        inp = FakeInput(released=False)
        c = _ctrl(inp, _ok, verifier=lambda i, n: dict(confirmed=True))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'UNKNOWN_RESULT')
        self.assertIn('RELEASE_UNCONFIRMED', out['reasons'])

    def test_concurrent_same_intent_clicks_once(self):
        # Caso reproduzido: duas THREADS executando a MESMA intenção. O check de
        # consumo pré-lock não basta (ambas passam antes de qualquer consumo); o
        # check autoritativo DENTRO do lock garante um único clique.
        import threading
        import time as _t
        inp = FakeInput()
        c = CursorController(input_adapter=inp, validator=_ok,
                             verifier=lambda i, n: dict(confirmed=True),
                             clock=_t.monotonic, sleep=lambda s: None,
                             trajectory=TrajectoryGenerator(clock=_t.monotonic),
                             step_s=0.0)
        it = _intent(iid='race')
        out = []
        threads = [threading.Thread(target=lambda: out.append(c.execute(it)['state']))
                   for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(inp.clicks, 1)            # clique ÚNICO sob corrida
        self.assertEqual(sorted(out), ['CANCELLED', 'DONE'])

    def test_identity_change_on_arrival_no_click(self):
        # Caso reproduzido: a mesa/janela troca durante a trajetória; o botão
        # aparece na MESMA coordenada, mas a identidade mudou -> não clica.
        inp = FakeInput()
        seq = [dict(ok=True, target_rect=(100, 100, 80, 40), identity='tbl#1'),
               dict(ok=True, target_rect=(100, 100, 80, 40), identity='tbl#2')]
        it = iter(seq)
        c = _ctrl(inp, lambda i, n: next(it))
        out = c.execute(_intent())                 # source_key='tbl#1'
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('IDENTITY_CHANGED_ON_ARRIVAL', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_cursor_pos_unavailable_cancels_without_assuming(self):
        # §1d: falha ao ler a posição do cursor -> CANCELA (não assume o alvo).
        inp = FakeInput(raise_cursor_pos=True)
        c = _ctrl(inp, _ok, verifier=lambda i, n: dict(confirmed=True))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('CURSOR_POS_UNAVAILABLE', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_invalid_target_geometry_no_click(self):
        # §2c: alvo com geometria inválida -> sem clique.
        inp = FakeInput()
        c = _ctrl(inp, lambda i, n: dict(ok=True, target_rect=(100, 100, 0, 40)))
        out = c.execute(Intent(id='g', action='click', source_key='t',
                               target_rect=(100, 100, 0, 40), deadline=1e12))
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('TARGET_GEOMETRY_INVALID', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_cursor_not_at_target_no_click(self):
        # §2e: se o cursor NÃO chegou ao alvo, não pressiona.
        inp = FakeInput(pos=(0, 0), track_pos=False)   # move não leva o cursor
        c = _ctrl(inp, _ok)
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('CURSOR_NOT_AT_TARGET', out['reasons'])
        self.assertEqual(inp.clicks, 0)

    def test_down_not_accepted_is_unknown(self):
        # §1b: mouse-down RECUSADO -> não declarar sucesso (desconhecido).
        inp = FakeInput(down_accept=0)
        c = _ctrl(inp, _ok, verifier=lambda i, n: dict(confirmed=True))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'UNKNOWN_RESULT')
        self.assertIn('DOWN_NOT_ACCEPTED', out['reasons'])

    def test_move_not_accepted_is_unknown(self):
        # §1b: movimento do clique RECUSADO -> desconhecido.
        inp = FakeInput(move_accept=0)
        c = _ctrl(inp, _ok, verifier=lambda i, n: dict(confirmed=True))
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'UNKNOWN_RESULT')
        self.assertIn('MOVE_NOT_ACCEPTED', out['reasons'])

    def test_serialization_busy_lock_no_click(self):
        inp = FakeInput()
        lock = threading.Lock()
        lock.acquire()                                # outra intenção "em curso"
        c = _ctrl(inp, _ok, lock=lock, lock_timeout=0.05)
        out = c.execute(_intent())
        self.assertEqual(out['state'], 'CANCELLED')
        self.assertIn('CURSOR_BUSY', out['reasons'])
        self.assertEqual(inp.clicks, 0)
        lock.release()


# ---------- calibração -------------------------------------------------------
class CalibrationTest(unittest.TestCase):
    def test_fit_recovers_coefficients(self):
        import math
        a, b = 0.15, 0.09
        samples = []
        for d, w in [(100, 50), (400, 50), (900, 30), (1600, 40), (50, 20), (800, 25)]:
            t = a + b * math.log2(1 + d / w)
            samples.append(dict(distance=d, width=w, duration=t))
        fit = fit_fitts(samples)
        self.assertTrue(fit['measured'])
        self.assertAlmostEqual(fit['a'], a, places=4)
        self.assertAlmostEqual(fit['b'], b, places=4)
        self.assertGreater(fit['r2'], 0.999)

    def test_insufficient_samples_not_measured(self):
        fit = fit_fitts([dict(distance=100, width=50, duration=0.3)])
        self.assertFalse(fit['measured'])
        self.assertEqual(fit['reason'], 'INSUFFICIENT_SAMPLES')

    def test_no_variance_not_measured(self):
        samples = [dict(distance=100, width=50, duration=0.3 + i * 0.01)
                   for i in range(6)]   # mesmo D/W
        fit = fit_fitts(samples)
        self.assertFalse(fit['measured'])
        self.assertEqual(fit['reason'], 'NO_VARIANCE_IN_DIFFICULTY')

    def test_recorder_bounded(self):
        rec = MovementRecorder(max_items=2)
        self.assertTrue(rec.add_move(distance=100, width=50, duration=0.3))
        self.assertTrue(rec.add_move(distance=200, width=50, duration=0.4))
        self.assertFalse(rec.add_move(distance=300, width=50, duration=0.5))
        self.assertEqual(rec.dropped, 1)


class SendCheckTest(unittest.TestCase):
    class _FakeMove:
        def __init__(self, bounds=(-1920, 0, 4480, 1440), pos=(100, 100)):
            self._bounds, self._pos, self.moves = bounds, pos, []

        def virtual_bounds(self):
            return self._bounds

        def cursor_pos(self):
            return self._pos

        def move_to(self, x, y, bounds=None):
            self.moves.append((x, y))
            self._pos = (int(x), int(y))
            return dict(requested=1, accepted=1, norm=(0, 0))

    def test_move_measures_and_restores(self):
        from cursor_sendcheck import send_check
        fake = self._FakeMove(pos=(500, 500))
        rep = send_check(adapter=fake, sleep=lambda s: None)
        self.assertTrue(rep['all_accepted'])
        self.assertLess(rep['max_error_px'], 1.5)       # backend perfeito -> ~0
        self.assertEqual(rep['origin'], (500, 500))
        self.assertEqual(fake.moves[-1], (500, 500))    # restaurou a origem


class EvalTest(unittest.TestCase):
    def _straight(self):
        return [(i * 0.1, i * 10.0, 0.0) for i in range(11)]   # (0,0)->(100,0)

    def test_straight_path_metrics(self):
        m = movement_metrics(self._straight(), target=(100.0, 0.0), width=48)
        self.assertAlmostEqual(m['straight_distance'], 100.0, places=6)
        self.assertAlmostEqual(m['curvature_ratio'], 1.0, places=6)
        self.assertAlmostEqual(m['peak_velocity'], 100.0, places=4)
        self.assertEqual(m['reversals'], 0)
        self.assertAlmostEqual(m['final_error'], 0.0, places=6)

    def test_curved_path_has_curvature(self):
        pts = [(0.0, 0, 0), (0.1, 50, 50), (0.2, 100, 0)]
        m = movement_metrics(pts, target=(100.0, 0.0))
        self.assertGreater(m['curvature_ratio'], 1.4)

    def test_overshoot_and_reversal(self):
        pts = [(0.0, 0, 0), (0.1, 120, 0), (0.2, 100, 0)]
        m = movement_metrics(pts, target=(100.0, 0.0))
        self.assertAlmostEqual(m['overshoot_frac'], 0.2, places=6)
        self.assertEqual(m['reversals'], 1)

    def test_too_few_points_abstains(self):
        self.assertEqual(movement_metrics([(0.0, 1, 1)])['reason'], 'TOO_FEW_POINTS')

    def test_summarize(self):
        a = movement_metrics(self._straight(), target=(100.0, 0.0))
        s = summarize_trials([a, dict(reason='TOO_FEW_POINTS')])
        self.assertEqual(s['n'], 1)
        self.assertIn('mean_duration', s)

    def test_make_trials_deterministic_and_bounded(self):
        t1 = make_trials((800, 600), n=10, seed=7)
        t2 = make_trials((800, 600), n=10, seed=7)
        self.assertEqual(t1, t2)                      # determinístico
        for tr in t1:
            x, y, w, h = tr['rect']
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x + w, 800)
            self.assertLessEqual(y + h, 600)


if __name__ == '__main__':
    unittest.main()
