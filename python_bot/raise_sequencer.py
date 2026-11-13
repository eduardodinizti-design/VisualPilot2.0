"""Fluxo MULTI-ETAPA do aumento (spec cursor §11): abrir painel → escolher preset
→ confirmar — cada clique passa pelas TRAVAS do CursorController (exclusão mútua,
prazo, cancelamento, verificação de envio, revalidação na chegada) e cada etapa é
relida FRESCA (nunca reaproveita painel/alvo antigo).

Sequência (ligada à mesa da decisão por `table_key`, não "a primeira detectada"):
  0) captura → localiza a MESMA mesa + confere vez do hero + botão RAISE.
  A) clica RAISE (via controlador) → recaptura → confirma que o PAINEL abriu.
  B) mapeia o multiplicador-alvo → PRESET (com tolerância) e clica (via controlador).
  C) relê o painel FRESCO → clica no CONFIRMAR (via controlador) → verifica o efeito.

Continuidade de geometria: a janela não pode ter se movido entre etapas (o
`detect_table_crops` falha com o painel aberto, então reusamos o retângulo do passo
0 SÓ enquanto a geometria da janela não mudar — senão aborta). Após falha parcial
em que um clique pode ter saído, retorna resultado DESCONHECIDO e NÃO reinicia.

`capture`/`window_rect`(tupla ou callable)/leitores/`input_adapter`/`bot_control`
são injetáveis → testável sem Windows.
"""
import time

import cv2

from table_reading.automatic_table_crops import detect_table_crops
from table_reading.action_buttons import read_action_buttons
from raise_panel import read_raise_panel, map_multiplier_to_preset
from screen_coords import rect_frame_to_screen
from cursor_controller import CursorController, Intent


def _table_key(x, y):
    return '%dx%d' % (x // 100, y // 100)


class RaiseSequencer:
    def __init__(self, *, capture, window_rect, input_adapter, target_mult,
                 bot_control=None, table_key=None, hand=None, max_tables=6,
                 sleep=time.sleep, clock=time.monotonic, step_deadline=5.0,
                 read_actions=read_action_buttons, read_panel=read_raise_panel,
                 detect=detect_table_crops):
        self.capture = capture
        self._geom = window_rect if callable(window_rect) else (lambda: window_rect)
        self.input = input_adapter
        self.target_mult = target_mult
        self.bot = bot_control
        self.table_key = table_key
        self.hand = hand
        self.max_tables = max_tables
        self._sleep = sleep
        self._clock = clock
        self.step_deadline = float(step_deadline)
        self._ra = read_actions
        self._rp = read_panel
        self._detect = detect
        self.log = []
        self._crop_box = None
        self._win0 = None

    # ---- helpers --------------------------------------------------------
    def _armed(self):
        return self.bot is None or bool(self.bot.execution_allowed())

    def _win(self):
        return self._geom()

    def _geom_ok(self):
        cur = self._win()
        return cur is not None and (self._win0 is None or tuple(cur) == tuple(self._win0))

    def _fail(self, reason):
        self.log.append(('FAIL', reason))
        return dict(ok=False, reason=reason, log=self.log)

    def _unknown(self, reason, out):
        """Resultado DESCONHECIDO: um clique pode ter saído; não reinicia sozinho."""
        self.log.append(('UNKNOWN', reason))
        return dict(ok=False, reason=reason, unknown=True, maybe_sent=True,
                    log=self.log, result_state=(out or {}).get('state'))

    def _locate(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        for p in self._detect(rgb, max_tables=self.max_tables):
            x, y, w, h = map(int, p.box)
            if self.table_key is None or _table_key(x, y) == self.table_key:
                return (x, y, w, h)
        return None

    def _crop(self, frame):
        if self._crop_box is None or frame is None:
            return None
        x, y, w, h = self._crop_box
        return frame[y:y + h, x:x + w]

    def _read_panel_fresh(self):
        """Relê o painel do zero na mesa ligada. None se captura/geometria falhar."""
        if not self._geom_ok():
            return None
        frame, _ = self.capture()
        crop = self._crop(frame)
        return self._rp(crop) if crop is not None else None

    # ---- alvos (lidos FRESCOS dentro do validator) ----------------------
    def _tf_raise(self, crop):
        br = self._ra(crop)
        if br['status'] != 'EXPERIMENTAL_BUTTON_ROW':
            return None
        rb = next((b for b in br['buttons'] if b.get('action') == 'RAISE'), None)
        return rb['box'] if rb else None

    def _tf_preset(self, crop):
        panel = self._rp(crop)
        if panel.get('status') != 'EXPERIMENTAL_RAISE_PANEL':
            return None
        pr = map_multiplier_to_preset(self.target_mult, panel.get('presets') or [])
        return pr['box'] if pr else None

    def _tf_confirm(self, crop):
        panel = self._rp(crop)
        if panel.get('status') != 'EXPERIMENTAL_RAISE_PANEL':
            return None
        c = panel.get('confirm')
        return c['box'] if c else None

    def _validator(self, target_fn, identity):
        """Revalida NA CHEGADA (e no início): geometria estável, mesa ligada, alvo
        presente FRESCO. Devolve target_rect (tela atual) + identity -> o controlador
        cancela em TARGET_MOVED/IDENTITY_CHANGED."""
        def v(intent, now):
            if not self._geom_ok():
                return dict(ok=False, reasons=['GEOMETRIA_MUDOU'])
            frame, _ = self.capture()
            crop = self._crop(frame)
            if crop is None:
                return dict(ok=False, reasons=['RECAPTURE_FAILED'])
            box = target_fn(crop)
            if box is None:
                return dict(ok=False, reasons=['ALVO_AUSENTE'])
            bx, by, bw, bh = box
            cx0, cy0, _, _ = self._crop_box
            rect = rect_frame_to_screen((cx0 + bx, cy0 + by, bw, bh),
                                        window_rect=self._win(),
                                        frame_size=(frame.shape[1], frame.shape[0]))
            return dict(ok=True, target_rect=rect, identity=identity)
        return v

    def _verify_bet(self, intent, now):
        """Indício do efeito na MESMA mesa: a linha de botões sumiu. Ausência não é
        prova (#8) -> sem isso, confirmed=False e o controlador devolve UNKNOWN."""
        frame, _ = self.capture()
        crop = self._crop(frame)
        if crop is None:
            return dict(confirmed=False)
        return dict(confirmed=(self._ra(crop)['status'] != 'EXPERIMENTAL_BUTTON_ROW'))

    def _step(self, what, target_fn, verifier=None):
        identity = (self.table_key, self.hand, what)
        intent = Intent(id='raise-%s-%s-%s' % (self.table_key, self.hand, what),
                        action='RAISE_%s' % what, source_key=identity,
                        target_rect=(0, 0, 1, 1), deadline=self._clock() + self.step_deadline,
                        hand=self.hand, expected=dict(step=what, table_key=self.table_key))
        ctrl = CursorController(input_adapter=self.input,
                                validator=self._validator(target_fn, identity),
                                verifier=verifier, bot_control=self.bot,
                                clock=self._clock, sleep=self._sleep)
        out = ctrl.execute(intent)
        self.log.append((what, out['state'], tuple(out.get('reasons') or ())))
        return out

    # ---- fluxo ----------------------------------------------------------
    def run(self):
        frame, _ = self.capture()
        if frame is None:
            return self._fail('SEM_CAPTURA')
        self._win0 = self._win()
        if self._win0 is None:
            return self._fail('SEM_GEOMETRIA')
        box = self._locate(frame)
        if box is None:
            return self._fail('SEM_MESA')
        self._crop_box = box
        crop = self._crop(frame)
        br = self._ra(crop)
        if br['status'] != 'EXPERIMENTAL_BUTTON_ROW':
            return self._fail('NAO_E_VEZ_DO_HERO')
        if not any(b.get('action') == 'RAISE' for b in br['buttons']):
            return self._fail('SEM_BOTAO_RAISE')
        if not self._armed():
            return self._fail('BOT_PAUSADO')

        # A) abrir o painel
        out_a = self._step('ABRIR', self._tf_raise)
        if out_a['state'] == 'CANCELLED':
            return self._fail('ABRIR_CANCELADO')          # não clicou (ou revalidação barrou)
        self._sleep(0.3)
        panel = self._read_panel_fresh()
        if not panel or panel.get('status') != 'EXPERIMENTAL_RAISE_PANEL':
            return self._unknown('PAINEL_NAO_ABRIU', out_a)

        # B) escolher o preset (com tolerância; sem preset compatível -> abster)
        preset = map_multiplier_to_preset(self.target_mult, panel['presets'])
        if preset is None:
            return self._fail('SEM_PRESET_PARA_ALVO:%s' % self.target_mult)
        out_b = self._step('PRESET_%sx' % preset['mult'], self._tf_preset)
        if out_b['state'] == 'CANCELLED':
            return self._unknown('PRESET_CANCELADO', out_b)   # o abrir já saiu -> desconhecido
        self._sleep(0.25)

        # C) confirmar — relê o painel FRESCO; NUNCA reusa o anterior
        panel2 = self._read_panel_fresh()
        if not panel2 or panel2.get('status') != 'EXPERIMENTAL_RAISE_PANEL' \
                or not panel2.get('confirm'):
            return self._unknown('CONFIRMAR_SEM_PAINEL', out_b)
        out_c = self._step('CONFIRMAR', self._tf_confirm, verifier=self._verify_bet)
        if out_c['state'] == 'CANCELLED':
            return self._unknown('CONFIRMAR_CANCELADO', out_c)
        return dict(ok=True, confirmed=(out_c['state'] == 'DONE'), preset=preset['mult'],
                    target_mult=self.target_mult, result_state=out_c['state'], log=self.log)
