"""App de teste do cursor — medição do usuário + validação do clique real (3B b2).

Alvos INOFENSIVOS (quadrados numa janela Tk). NUNCA aponta para o PPPoker.

Modos:
  --measure : VOCÊ move o mouse até cada alvo e clica. Grava a telemetria do
              movimento, ajusta a lei de Fitts (fit_fitts) e salva um relatório.
  --auto    : o CONTROLADOR move o cursor via SendInput e clica em cada alvo
              (experimental). Mede coord enviada×observada e se o clique surtiu
              efeito. Pressione ESC a qualquer momento para ABORTAR.

Relatórios vão para logs/cursor/*.json. Rode no Windows com tkinter.
"""
import argparse
import json
import os
import sys
import threading
import time

from cursor_eval import make_trials, movement_metrics, summarize_trials
from cursor_calibration import fit_fitts

OUT_DIR = os.path.join('logs', 'cursor')


def _save(report, prefix):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, '%s-%s.json' % (prefix, time.strftime('%Y%m%d-%H%M%S')))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return path


# --------------------------------------------------------------------------- #
# MEDIÇÃO (humano)
# --------------------------------------------------------------------------- #
class MeasureApp:
    def __init__(self, root, trials):
        import tkinter as tk
        self.tk = tk
        self.root = root
        self.trials = trials
        self.i = 0
        self.points = []
        self.t0 = None
        self.records = []
        self.canvas = tk.Canvas(root, bg='#101418', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.info = self.canvas.create_text(20, 20, anchor='nw', fill='#9fb3c8',
                                            font=('Segoe UI', 12), text='')
        self.rect = None
        root.bind('<Motion>', self.on_motion)
        self.canvas.bind('<Button-1>', self.on_click)
        root.bind('<Escape>', lambda e: self.finish(aborted=True))
        root.after(300, self.next_trial)

    def next_trial(self):
        if self.i >= len(self.trials):
            return self.finish()
        tr = self.trials[self.i]
        x, y, w, h = tr['rect']
        if self.rect is not None:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(x, y, x + w, y + h,
                                                 fill='#2dd4bf', outline='#0b7285', width=2)
        self.canvas.itemconfig(self.info, text='Alvo %d/%d — mova e CLIQUE no quadrado. ESC aborta.'
                               % (self.i + 1, len(self.trials)))
        self.points = []
        self.t0 = time.monotonic()

    def on_motion(self, e):
        if self.t0 is not None:
            self.points.append((time.monotonic(), e.x_root, e.y_root))

    def on_click(self, e):
        if self.i >= len(self.trials):
            return                      # já terminou; ignora cliques tardios
        tr = self.trials[self.i]
        x, y, w, h = tr['rect']
        if not (x <= e.x <= x + w and y <= e.y <= y + h):
            return                      # fora do alvo: ignora
        cx_root = e.x_root - e.x + (x + w / 2.0)   # centro do alvo em coords de tela
        cy_root = e.y_root - e.y + (y + h / 2.0)
        self.points.append((time.monotonic(), e.x_root, e.y_root))
        m = movement_metrics(self.points, target=(cx_root, cy_root), width=tr['width'])
        if m.get('reason') is None:
            self.records.append(m)
        self.i += 1
        self.next_trial()

    def finish(self, aborted=False):
        samples = [dict(distance=m['straight_distance'], width=m['width'],
                        duration=m['duration']) for m in self.records
                   if m.get('straight_distance') and m.get('duration')]
        fit = fit_fitts(samples)
        report = dict(mode='measure', aborted=aborted, n_trials=len(self.records),
                      samples=samples, fit=fit,
                      metrics_summary=summarize_trials(self.records))
        path = _save(report, 'measure')
        self.canvas.itemconfig(self.info, text='FIM. n=%d  fit measured=%s  a=%s b=%s\nSalvo: %s'
                               % (len(self.records), fit['measured'],
                                  _fmt(fit['a']), _fmt(fit['b']), path))
        print('Relatorio de medicao salvo em:', path)
        self.root.after(2500, self.root.destroy)


def _fmt(v):
    return ('%.4f' % v) if isinstance(v, float) else str(v)


# --------------------------------------------------------------------------- #
# AUTO (controlador move + clica — experimental)
# --------------------------------------------------------------------------- #
class AutoApp:
    def __init__(self, root, n=6):
        import tkinter as tk
        from cursor_input_win import WindowsCursorInput
        self.tk = tk
        self.root = root
        self.last_clicked = None
        self.abort = False
        self.buttons = []
        self.results = []
        self._finished = False
        self._report_path = None
        self._input = WindowsCursorInput()
        # Janela por cima: os cliques em coords absolutas devem cair nos NOSSOS
        # botões, não em algo atrás. ESC aborta.
        root.attributes('-topmost', True)
        root.lift()
        try:
            root.focus_force()
        except Exception:                      # noqa: BLE001
            pass
        root.bind('<Escape>', lambda e: setattr(self, 'abort', True))
        frame = tk.Frame(root, bg='#101418')
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='AUTO: o bot vai mover e clicar nos botoes. ESC aborta.',
                 bg='#101418', fg='#9fb3c8', font=('Segoe UI', 12)).pack(pady=8)
        grid = tk.Frame(frame, bg='#101418')
        grid.pack(expand=True)
        for k in range(n):
            b = tk.Button(grid, text='ALVO %d' % k, width=12, height=3,
                          command=lambda i=k: self._clicked(i))
            b.grid(row=k // 3, column=k % 3, padx=18, pady=18)
            self.buttons.append(b)
        root.after(1500, lambda: threading.Thread(target=self._run, daemon=True).start())
        root.after(200, self._poll)   # fecha a janela na MAIN thread quando terminar

    def _poll(self):
        if self._finished:
            self.root.destroy()
            return
        self.root.after(150, self._poll)

    def _clicked(self, i):
        self.last_clicked = (i, time.monotonic())

    def _screen_rect(self, widget):
        return (widget.winfo_rootx(), widget.winfo_rooty(),
                widget.winfo_width(), widget.winfo_height())

    def _run(self):
        from cursor_controller import CursorController, Intent, make_intervention_check
        inp = self._input
        ctrl = CursorController(
            input_adapter=inp,
            validator=lambda it, now: dict(ok=not self.abort, target_rect=it.target_rect,
                                           reasons=['ABORTED'] if self.abort else []),
            verifier=self._verify,
            cancel_check=make_intervention_check(inp, tol_px=40))
        for k, b in enumerate(self.buttons):
            if self.abort:
                break
            self.last_clicked = None
            rect = self._screen_rect(b)
            it = Intent(id='auto-%d' % k, action='click', source_key='testapp',
                        target_rect=rect, deadline=time.monotonic() + 8.0)
            out = ctrl.execute(it)
            self.results.append(dict(target=k, rect=rect, state=out['state'],
                                     reasons=out['reasons'],
                                     confirmed=(self.last_clicked is not None
                                                and self.last_clicked[0] == k)))
            time.sleep(0.4)
        # caso de CANCELAMENTO: intenção já vencida -> não clica
        if not self.abort and self.buttons:
            rect = self._screen_rect(self.buttons[0])
            it = Intent(id='auto-expired', action='click', source_key='testapp',
                        target_rect=rect, deadline=time.monotonic() - 1.0)
            out = CursorController(input_adapter=inp, validator=lambda i, n: dict(ok=True),
                                   ).execute(it)
            self.results.append(dict(target='expired-demo', state=out['state'],
                                     reasons=out['reasons'], confirmed=False))
        path = _save(dict(mode='auto', aborted=self.abort, results=self.results), 'auto')
        print('Relatorio AUTO salvo em:', path)
        self._report_path = path
        self._finished = True                  # a MAIN thread fecha (ver _poll)

    def _verify(self, intent, now):
        # Tk processa o clique no thread principal; aqui (bg) fazemos poll curto.
        deadline = time.monotonic() + 0.4
        k = int(intent.id.split('-')[1])
        while time.monotonic() < deadline:
            lc = self.last_clicked
            if lc is not None and lc[0] == k:
                return dict(confirmed=True)
            time.sleep(0.02)
        return dict(confirmed=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--measure', action='store_true',
                    help='Modo medicao do usuario (default se --auto ausente)')
    ap.add_argument('--auto', action='store_true', help='Bot move+clica (experimental)')
    ap.add_argument('--trials', type=int, default=12, help='Nº de alvos (measure)')
    ap.add_argument('--size', default='1100x740', help='Tamanho da janela')
    ap.add_argument('--check', action='store_true', help='So checa tkinter e sai')
    args = ap.parse_args(argv)

    try:
        import tkinter as tk
    except Exception as e:  # noqa: BLE001
        print('tkinter indisponivel:', e)
        return 2
    if args.check:
        print('tkinter OK')
        return 0

    root = tk.Tk()
    root.title('VisualPilot — cursor test (alvos inofensivos)')
    root.geometry(args.size)
    if args.auto:
        AutoApp(root)
    else:
        w, h = (int(v) for v in args.size.lower().split('x'))
        MeasureApp(root, make_trials((w, h - 40), n=args.trials, seed=int(time.time()) % 1000))
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
