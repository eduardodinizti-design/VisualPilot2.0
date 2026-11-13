"""Windows client-area capture only. No OCR, input injection or simulated fallback."""
from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
from copy import deepcopy
from ctypes import wintypes as W
import ntpath
import platform
import time

ALLOWED_EXECUTABLES = frozenset({'pppoker.exe', 'ppclient.exe'})
MAX_PIXELS = 36_000_000

class CaptureError(RuntimeError):
    def __init__(self, status, detail=''):
        super().__init__(detail or status)
        self.status = status

class _BitmapHeader(ctypes.Structure):
    _fields_ = [('size', W.DWORD), ('width', W.LONG), ('height', W.LONG),
                ('planes', W.WORD), ('bits', W.WORD), ('compression', W.DWORD),
                ('image_size', W.DWORD), ('xppm', W.LONG), ('yppm', W.LONG),
                ('used', W.DWORD), ('important', W.DWORD)]

class _NativeBackend:
    def __init__(self):
        import numpy
        import psutil
        self.np, self.psutil = numpy, psutil
        self.u = ctypes.WinDLL('user32', use_last_error=True)
        self.g = ctypes.WinDLL('gdi32', use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        signatures = [
            (self.u.EnumWindows, [self.callback, W.LPARAM], W.BOOL),
            (self.u.IsWindow, [W.HWND], W.BOOL),
            (self.u.IsWindowVisible, [W.HWND], W.BOOL),
            (self.u.IsIconic, [W.HWND], W.BOOL),
            (self.u.GetWindowTextLengthW, [W.HWND], ctypes.c_int),
            (self.u.GetWindowTextW, [W.HWND, W.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.u.GetWindowThreadProcessId, [W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD),
            (self.u.GetClientRect, [W.HWND, ctypes.POINTER(W.RECT)], W.BOOL),
            (self.u.ClientToScreen, [W.HWND, ctypes.POINTER(W.POINT)], W.BOOL),
            (self.u.GetDC, [W.HWND], W.HDC),
            (self.u.ReleaseDC, [W.HWND, W.HDC], ctypes.c_int),
            (self.u.SetThreadDpiAwarenessContext, [ctypes.c_void_p], ctypes.c_void_p),
            (self.u.GetThreadDpiAwarenessContext, [], ctypes.c_void_p),
            (self.u.GetAwarenessFromDpiAwarenessContext, [ctypes.c_void_p], ctypes.c_int),
            (self.g.CreateCompatibleDC, [W.HDC], W.HDC),
            (self.g.CreateCompatibleBitmap, [W.HDC, ctypes.c_int, ctypes.c_int], W.HANDLE),
            (self.g.SelectObject, [W.HDC, W.HANDLE], W.HANDLE),
            (self.g.BitBlt, [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            W.HDC, ctypes.c_int, ctypes.c_int, W.DWORD], W.BOOL),
            (self.g.GetDIBits, [W.HDC, W.HANDLE, W.UINT, W.UINT, ctypes.c_void_p,
                               ctypes.c_void_p, W.UINT], ctypes.c_int),
            (self.g.DeleteObject, [W.HANDLE], W.BOOL),
            (self.g.DeleteDC, [W.HDC], W.BOOL),
        ]
        for fn, args, result in signatures:
            fn.argtypes, fn.restype = args, result

    @contextmanager
    def physical_pixels(self):
        old = self.u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        if not old:
            raise CaptureError('DPI_CONTEXT_FAILED')
        try:
            ctx = self.u.GetThreadDpiAwarenessContext()
            if self.u.GetAwarenessFromDpiAwarenessContext(ctx) != 2:
                raise CaptureError('DPI_CONTEXT_UNVERIFIED')
            yield
        finally:
            if not self.u.SetThreadDpiAwarenessContext(old):
                raise CaptureError('DPI_CONTEXT_RESTORE_FAILED')

    def handles(self):
        handles = []
        cb = self.callback(lambda hwnd, _: handles.append(int(hwnd)) or True)
        if not self.u.EnumWindows(cb, 0):
            raise CaptureError('WINDOW_ENUMERATION_FAILED')
        return handles

    def state(self, hwnd):
        if not self.u.IsWindow(hwnd):
            raise CaptureError('WINDOW_INVALID_HWND')
        if not self.u.IsWindowVisible(hwnd):
            raise CaptureError('WINDOW_NOT_VISIBLE')
        if self.u.IsIconic(hwnd):
            raise CaptureError('WINDOW_MINIMIZED')
        pid = W.DWORD()
        if not self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
            raise CaptureError('PROCESS_QUERY_FAILED')
        try:
            process = self.psutil.Process(pid.value)
            executable, created = process.exe(), process.create_time()
        except Exception as exc:
            raise CaptureError('PROCESS_QUERY_FAILED', str(exc)) from exc
        name = ntpath.basename(executable).casefold()
        if name not in ALLOWED_EXECUTABLES:
            raise CaptureError('EXECUTABLE_NOT_ALLOWED', name)
        rect, origin = W.RECT(), W.POINT(0, 0)
        if not self.u.GetClientRect(hwnd, ctypes.byref(rect)):
            raise CaptureError('INVALID_CLIENT_GEOMETRY')
        if not self.u.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise CaptureError('INVALID_CLIENT_ORIGIN')
        title = ctypes.create_unicode_buffer(self.u.GetWindowTextLengthW(hwnd)+1)
        self.u.GetWindowTextW(hwnd, title, len(title))
        return dict(hwnd=hwnd, pid=pid.value, executable=executable, process_created=created,
                    title=title.value, client_rect=(rect.left, rect.top, rect.right, rect.bottom),
                    screen_origin=(origin.x, origin.y))

    def pixels(self, hwnd, width, height):
        source = memory = bitmap = previous = None
        selected = False
        cleanup = []
        def checked(value, label):
            if not value or value == ctypes.c_void_p(-1).value:
                raise CaptureError(label, f'Win32 error {ctypes.get_last_error()}')
            return value
        try:
            source = checked(self.u.GetDC(hwnd), 'GET_CLIENT_DC_FAILED')
            memory = checked(self.g.CreateCompatibleDC(source), 'CREATE_MEMORY_DC_FAILED')
            bitmap = checked(self.g.CreateCompatibleBitmap(source, width, height), 'CREATE_BITMAP_FAILED')
            previous = checked(self.g.SelectObject(memory, bitmap), 'SELECT_BITMAP_FAILED')
            selected = True
            checked(self.g.BitBlt(memory, 0, 0, width, height, source, 0, 0, 0x00CC0020), 'BITBLT_FAILED')
            checked(self.g.SelectObject(memory, previous), 'RESTORE_BITMAP_FAILED')
            selected = False
            header = _BitmapHeader()
            header.size = ctypes.sizeof(header)
            header.width, header.height = width, -height  # Top-down BGRA, no vertical flip.
            header.planes, header.bits = 1, 32
            buffer = (ctypes.c_ubyte * (width*height*4))()
            lines = self.g.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(header), 0)
            if lines != height:
                raise CaptureError('GET_BITMAP_PIXELS_FAILED')
            return self.np.frombuffer(buffer, dtype=self.np.uint8).reshape(height, width, 4)[:, :, :3].copy()
        finally:
            # A borrowed client DC is released, NEVER DeleteDC'd.
            def release(fn, *args):
                try:
                    if not fn(*args): cleanup.append(fn.__name__)
                except Exception as exc:
                    cleanup.append(str(exc))
            if selected and memory and previous:
                release(self.g.SelectObject, memory, previous)
            if bitmap: release(self.g.DeleteObject, bitmap)
            if memory: release(self.g.DeleteDC, memory)
            if source: release(self.u.ReleaseDC, hwnd, source)
            if cleanup:
                raise CaptureError('GDI_CLEANUP_FAILED', '; '.join(cleanup))

class WindowCaptureEngine:
    VALID_EXECUTABLES = ALLOWED_EXECUTABLES

    def __init__(self, title_substring='PPPoker', *, _backend=None):
        self.title_substring = title_substring  # Compatibility only; never authorizes a process.
        self._backend = _backend
        self.is_windows = platform.system() == 'Windows'
        self.dpi_status = False
        self.last_diagnostics = []
        self._last_capture_info = {'status': 'CAPTURE_NOT_STARTED'}

    def get_diagnostic_info(self):
        """Copy of last capture metadata; no capture, OCR or disk write."""
        return deepcopy(self._last_capture_info)

    def _native(self):
        if self._backend is not None:  # Explicit dependency injection only, used by tests.
            return self._backend
        if not self.is_windows:
            raise CaptureError('ENVIRONMENT_NOT_WINDOWS')
        try:
            self._backend = _NativeBackend()
        except Exception as exc:
            raise CaptureError('WINDOWS_BACKEND_UNAVAILABLE', str(exc)) from exc
        return self._backend

    def _state(self, backend, hwnd):
        state = backend.state(hwnd)
        if state['hwnd'] != hwnd or not state.get('pid') or state.get('process_created') is None:
            raise CaptureError('PROCESS_QUERY_FAILED')
        if ntpath.basename(state['executable']).casefold() not in ALLOWED_EXECUTABLES:
            raise CaptureError('EXECUTABLE_NOT_ALLOWED')
        l,t,r,b = state['client_rect']
        if r <= l or b <= t or (r-l)*(b-t) > MAX_PIXELS:
            raise CaptureError('INVALID_CLIENT_GEOMETRY')
        return state

    @staticmethod
    def _signature(s):
        return (s['hwnd'], s['pid'], s['process_created'], s['executable'].casefold(),
                tuple(s['client_rect']), tuple(s['screen_origin']))

    def _candidates(self, backend):
        accepted = []
        self.last_diagnostics = []
        for hwnd in backend.handles():
            try:
                state = self._state(backend, hwnd)
                accepted.append(state)
                self.last_diagnostics.append(dict(state, status='ACCEPTED'))
            except Exception as exc:
                self.last_diagnostics.append(dict(hwnd=hwnd, status=getattr(exc, 'status', 'WINDOW_QUERY_FAILED'), error=str(exc)))
        return accepted

    def locate_target_windows(self):
        backend = self._native()
        with backend.physical_pixels():
            return self._candidates(backend)

    def _validate_process(self, hwnd):
        try:
            backend = self._native()
            with backend.physical_pixels():
                state = self._state(backend, hwnd)
            return True, state['executable'], state['pid']
        except Exception:
            return False, 'UNQUERYABLE', None

    def capture_frame(self, hwnd=None):
        meta = dict(status='CAPTURE_NOT_STARTED', timestamp=datetime.now(timezone.utc).isoformat(),
                    backend='GDI_CLIENT_BITBLT', dpi_effective=False, native_windows_validated=False)
        started = time.monotonic()
        self.dpi_status = False
        self.last_diagnostics = []
        try:
            backend = self._native()
            with backend.physical_pixels():
                self.dpi_status = meta['dpi_effective'] = True
                if hwnd is None:
                    candidates = self._candidates(backend)
                    meta['candidates'] = self.last_diagnostics
                    if not candidates: raise CaptureError('WINDOW_NOT_FOUND')
                    if len(candidates) != 1: raise CaptureError('WINDOW_AMBIGUOUS')
                    hwnd = candidates[0]['hwnd']
                    selected = candidates[0]
                else:
                    if not isinstance(hwnd, int) or hwnd <= 0: raise CaptureError('WINDOW_INVALID_HWND')
                    selected = self._state(backend, hwnd)
                meta.update(selected)
                before = self._state(backend, hwnd)
                if self._signature(selected) != self._signature(before):
                    raise CaptureError('WINDOW_CHANGED_PRE_CAPTURE')
                l,t,r,b = before['client_rect']
                frame = backend.pixels(hwnd, r-l, b-t)
                after = self._state(backend, hwnd)
                if self._signature(before) != self._signature(after):
                    raise CaptureError('WINDOW_CHANGED_DURING_CAPTURE')
                if frame is None or frame.shape != (b-t, r-l, 3):
                    raise CaptureError('INVALID_FRAME_SHAPE')
                if not frame.any(): raise CaptureError('BLACK_FRAME_UNVERIFIED')
                meta.update(status='SUCCESS', image_shape=list(frame.shape))
            return frame, meta
        except Exception as exc:
            meta.update(status=getattr(exc, 'status', 'CAPTURE_FAILED'), error=str(exc), exception_type=type(exc).__name__)
            return None, meta
        finally:
            meta['duration_ms'] = (time.monotonic()-started)*1000
            self._last_capture_info = deepcopy(meta)
