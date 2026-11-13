"""Recognize which top-level windows are poker TABLES, via configurable rules.

Vendored from the user's own NVT Mesas project (github.com/eduardodinizti-design,
commit c5d7584, module nvtmesas/detector.py), kept faithful. Detection is a
heuristic pre-selection; a caller can always force a window in/out. The Win32
screen grab used by the green-felt check is lazy-imported inside the function,
so this module imports on any OS.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from .windows import WindowInfo, enum_windows

_green_cache: dict = {}


def looks_like_green_table(hwnd: int, ttl: float = 3.0) -> bool:
    """Capture the window (PrintWindow) and check for green felt (table) vs none
    (lobby/login). Cached for a few seconds. Read-only; sends no input."""
    import time
    now = time.time()
    hit = _green_cache.get(hwnd)
    if hit and now - hit[0] < ttl:
        return hit[1]
    ok = True
    try:
        import ctypes
        import numpy as np
        import win32gui
        import win32ui
        from PIL import Image
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        W, H = max(1, r - l), max(1, b - t)
        hwdc = win32gui.GetWindowDC(hwnd)
        mdc = win32ui.CreateDCFromHandle(hwdc)
        sdc = mdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mdc, W, H)
        sdc.SelectObject(bmp)
        try:
            ctypes.windll.user32.PrintWindow(hwnd, sdc.GetSafeHdc(), 2)
            info = bmp.GetInfo()
            img = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']), bmp.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
        finally:
            sdc.DeleteDC()
            mdc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwdc)
            win32gui.DeleteObject(bmp.GetHandle())
        a = np.array(img.resize((max(1, W // 4), max(1, H // 4))))
        rr, gg, bb = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
        green = ((gg > rr + 25) & (gg > bb + 25) & (gg > 60)).mean()
        ok = green >= 0.12
    except Exception:
        ok = True
    _green_cache[hwnd] = (now, ok)
    return ok


_blue_cache: dict = {}


def looks_like_blue_table(hwnd: int, ttl: float = 3.0) -> bool:
    """Capture the window (PrintWindow) and check for the PPPoker BLUE felt vs a
    dark lobby/login. Calibrated on real crops: table ~0.64 blue fraction, lobby
    ~0.15; threshold 0.35. Cached a few seconds. Read-only; sends no input."""
    import time
    now = time.time()
    hit = _blue_cache.get(hwnd)
    if hit and now - hit[0] < ttl:
        return hit[1]
    ok = True
    try:
        import ctypes
        import numpy as np
        import win32gui
        import win32ui
        from PIL import Image
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        W, H = max(1, r - l), max(1, b - t)
        hwdc = win32gui.GetWindowDC(hwnd)
        mdc = win32ui.CreateDCFromHandle(hwdc)
        sdc = mdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mdc, W, H)
        sdc.SelectObject(bmp)
        try:
            ctypes.windll.user32.PrintWindow(hwnd, sdc.GetSafeHdc(), 2)
            info = bmp.GetInfo()
            img = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']), bmp.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
        finally:
            sdc.DeleteDC()
            mdc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwdc)
            win32gui.DeleteObject(bmp.GetHandle())
        a = np.array(img.resize((max(1, W // 4), max(1, H // 4))))
        rr, gg, bb = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
        blue = ((bb > rr + 20) & (bb > gg + 10) & (bb > 60)).mean()
        ok = blue >= 0.35
    except Exception:
        ok = True
    _blue_cache[hwnd] = (now, ok)
    return ok


@dataclass
class RoomRule:
    name: str
    processes: list = field(default_factory=list)
    title_include: list = field(default_factory=list)
    title_exclude: list = field(default_factory=list)
    min_w: int = 0
    min_h: int = 0
    max_w: int = 2600
    max_h: int = 2600
    lobby_titles: list = field(default_factory=list)
    content_check: str = ''

    def __post_init__(self):
        self._proc = {p.lower() for p in self.processes}
        self._inc = [re.compile(p) for p in self.title_include]
        self._exc = [re.compile(p) for p in self.title_exclude]
        self._lobby = [re.compile(p) for p in self.lobby_titles]

    def matches_process(self, proc: str) -> bool:
        return proc.lower() in self._proc

    def is_lobby(self, w: WindowInfo) -> bool:
        if any(rx.search(w.title) for rx in self._lobby):
            return True
        if self.content_check == 'green' and w.w >= 150 and w.h >= 150:
            return not looks_like_green_table(w.hwnd)
        if self.content_check == 'blue' and w.w >= 150 and w.h >= 150:
            return not looks_like_blue_table(w.hwnd)
        return False

    def is_table(self, w: WindowInfo) -> bool:
        if w.w < self.min_w or w.h < self.min_h:
            return False
        if w.w > self.max_w or w.h > self.max_h:
            return False
        if self.is_lobby(w):
            return False
        if any(rx.search(w.title) for rx in self._exc):
            return False
        if self._inc and not any(rx.search(w.title) for rx in self._inc):
            return False
        return True


class Detector:
    def __init__(self, rooms: list):
        self.rooms = rooms
        self.force_include = set()
        self.force_exclude = set()

    @classmethod
    def from_file(cls, path) -> 'Detector':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        rooms = [
            RoomRule(
                name=r['name'],
                processes=r.get('processes', []),
                title_include=r.get('title_include', []),
                title_exclude=r.get('title_exclude', []),
                min_w=r.get('min_w', 0),
                min_h=r.get('min_h', 0),
                max_w=r.get('max_w', 2600),
                max_h=r.get('max_h', 2600),
                lobby_titles=r.get('lobby_titles', []),
                content_check=r.get('content_check', ''))
            for r in data.get('rooms', [])]
        return cls(rooms)

    def room_for(self, w: WindowInfo):
        for r in self.rooms:
            if r.matches_process(w.process):
                return r
        return None

    def classify(self, windows: list) -> list:
        """Mark w.room and w.extra['is_table']/['is_lobby']/['known_room'] per window."""
        for w in windows:
            rule = self.room_for(w)
            w.room = rule.name if rule else ''
            w.extra['known_room'] = rule is not None
            w.extra['is_lobby'] = bool(rule and w.w >= 150 and w.h >= 150 and rule.is_lobby(w))
            auto = bool(rule and rule.is_table(w))
            if w.hwnd in self.force_exclude:
                w.extra['is_table'] = False
            elif w.hwnd in self.force_include:
                w.extra['is_table'] = True
            else:
                w.extra['is_table'] = auto
            w.extra['auto_table'] = auto
        return windows

    def tables(self, windows=None) -> list:
        windows = self.classify(windows if windows is not None else enum_windows())
        return [w for w in windows if w.extra.get('is_table')]

    def lobbies(self, windows=None) -> list:
        windows = self.classify(windows if windows is not None else enum_windows())
        return [w for w in windows if w.extra.get('is_lobby') and not w.minimized]

    def mark(self, hwnd: int, is_table: bool) -> None:
        self.force_include.discard(hwnd)
        self.force_exclude.discard(hwnd)
        if is_table:
            self.force_include.add(hwnd)
            return
        self.force_exclude.add(hwnd)

    def clear_mark(self, hwnd: int) -> None:
        self.force_include.discard(hwnd)
        self.force_exclude.discard(hwnd)
