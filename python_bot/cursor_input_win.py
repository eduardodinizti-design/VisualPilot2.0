"""Adaptador de entrada do Windows para o cursor — SendInput (Fase 3B).

Envia movimento/clique ao Windows via SendInput (API documentada; a spec
`ORIENTAÇÃO PARA MOVIMENTO NATURAL` §7 propõe migrar do SetCursorPos+mouse_event
do executor manual para SendInput). Responsabilidade ÚNICA: enviar eventos e
RELATAR quantos o sistema aceitou — isso confirma só aceitação de entrada, não a
execução da ação pela aplicação. O adaptador NÃO planeja trajetória, NÃO decide
alvo e NÃO valida mesa — isso é do coordenador.

- Coordenadas absolutas são normalizadas para o DESKTOP VIRTUAL (0..65535 com
  MOUSEEVENTF_VIRTUALDESK), tratando origem/múltiplos monitores e coords
  negativas. Confira o efeito das configurações do Windows antes de prometer
  correspondência entre coordenada enviada e posição observada.
- Clique ÚNICO: um mouse-down e um mouse-up para a MESMA intenção, com soltura
  GARANTIDA (try/finally) mesmo em erro. O tempo de pressionamento é documentado
  e validável no ambiente de teste — NÃO escolhido para alegar invisibilidade.
- win32 é carregado preguiçosamente (lazy): o módulo importa no lab Linux; o
  backend real só é construído quando usado sem um backend injetado (testes).

NUNCA aponte este adaptador para o PPPoker nesta fase. Use um app de teste.
"""
import time

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

DEFAULT_PRESS_S = 0.06   # documentado; validar no ambiente de teste


class CursorInputError(RuntimeError):
    pass


def _build_real_backend():
    """Backend ctypes real (só no Windows; construído sob demanda)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                    ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [('mi', MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [('type', wintypes.DWORD), ('u', _U)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)

    class _Real:
        def virtual_bounds(self):
            # SM_XVIRTUALSCREEN=76,77,78,79 (x,y,cx,cy do desktop virtual)
            return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
                    user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))

        def get_cursor_pos(self):
            p = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(p)):
                raise CursorInputError('GetCursorPos falhou')
            return (p.x, p.y)

        def send(self, flags_list, abs_xy=None):
            n = len(flags_list)
            arr = (INPUT * n)()
            for i, flags in enumerate(flags_list):
                mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
                if abs_xy is not None and (flags & MOUSEEVENTF_MOVE):
                    mi.dx, mi.dy = abs_xy
                arr[i] = INPUT(0, _U(mi))   # type 0 = INPUT_MOUSE
            sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
            return int(sent)

    return _Real()


class WindowsCursorInput:
    """Adaptador de entrada. Passe `_backend` nos testes (registra chamadas e
    devolve o nº aceito); em produção Windows o backend real é lazy."""

    def __init__(self, *, press_s=DEFAULT_PRESS_S, clock=time.monotonic,
                 sleep=time.sleep, _backend=None):
        self.press_s = float(press_s)
        self._clock = clock
        self._sleep = sleep
        self._backend = _backend

    @property
    def backend(self):
        if self._backend is None:
            self._backend = _build_real_backend()
        return self._backend

    def virtual_bounds(self):
        return self.backend.virtual_bounds()

    def cursor_pos(self):
        return self.backend.get_cursor_pos()

    def normalize_abs(self, x, y, bounds=None):
        """(nx, ny) em 0..65535 sobre o desktop virtual. Coords negativas OK."""
        bx, by, bw, bh = bounds or self.virtual_bounds()
        bw = max(bw - 1, 1)
        bh = max(bh - 1, 1)
        nx = int(round((float(x) - bx) * 65535.0 / bw))
        ny = int(round((float(y) - by) * 65535.0 / bh))
        return (max(0, min(65535, nx)), max(0, min(65535, ny)))

    def move_to(self, x, y, bounds=None):
        """Move absoluto para (x,y) físico. Retorna quantos eventos foram aceitos."""
        nx, ny = self.normalize_abs(x, y, bounds)
        flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        accepted = self.backend.send([flags], abs_xy=(nx, ny))
        return dict(requested=1, accepted=accepted, norm=(nx, ny))

    def click_once(self, x=None, y=None, *, bounds=None, hold_s=None):
        """Clique ÚNICO na posição atual ou em (x,y): move (se dado) → down → up,
        com soltura GARANTIDA. Retorna o relato de eventos enviados/aceitos."""
        hold = self.press_s if hold_s is None else float(hold_s)
        report = dict(moved=None, down_accepted=0, up_accepted=0, released=False)
        if x is not None and y is not None:
            report['moved'] = self.move_to(x, y, bounds)
        down_sent = False
        try:
            report['down_accepted'] = self.backend.send([MOUSEEVENTF_LEFTDOWN])
            down_sent = True
            if hold > 0:
                self._sleep(hold)
        finally:
            if down_sent:
                # Soltura só é CONFIRMADA se o sistema aceitou o mouse-up; aceitar
                # ≠ garantir, mas up_accepted=0 significa botão possivelmente preso.
                report['up_accepted'] = self.backend.send([MOUSEEVENTF_LEFTUP])
                report['released'] = report['up_accepted'] >= 1
        return report
