"""Top-level window enumeration via Win32 (discovery only, never input).

Adapted from the user's own NVT Mesas project (github.com/eduardodinizti-design,
commit c5d7584, module nvtmesas/windows.py). Trimmed to the discovery/identity
surface VisualPilot needs: WindowInfo + enum_windows + is_alive. The pywin32
imports are lazy so this module imports on any OS (the lab runs on Linux); the
Win32 calls themselves only run on Windows. No window is moved, resized or
focused here — organizing/opening tables is out of scope.

Uses only the public Window APIs (the same Task Manager / Alt+Tab use). It does
not read memory or traffic of any client.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    pid: int
    process: str
    rect: tuple  # (left, top, right, bottom)
    minimized: bool
    maximized: bool
    room: str = ''
    extra: dict = field(default_factory=dict)

    @property
    def x(self) -> int:
        return self.rect[0]

    @property
    def y(self) -> int:
        return self.rect[1]

    @property
    def w(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def h(self) -> int:
        return self.rect[3] - self.rect[1]


def _process_name(pid: int) -> str:
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        return ''


def enum_windows(include_hidden: bool = False) -> list:
    """Lista janelas de topo visíveis com título (candidatas a mesa). Windows-only."""
    import win32con
    import win32gui
    import win32process
    results = []

    def _cb(hwnd, _):
        if not include_hidden and not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return True
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex_style & win32con.WS_EX_TOOLWINDOW:
            return True
        try:
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            placement = win32gui.GetWindowPlacement(hwnd)
            minimized = placement[1] == win32con.SW_SHOWMINIMIZED
            maximized = placement[1] == win32con.SW_SHOWMAXIMIZED
            results.append(WindowInfo(
                hwnd=hwnd,
                title=title,
                class_name=win32gui.GetClassName(hwnd),
                pid=pid,
                process=_process_name(pid),
                rect=win32gui.GetWindowRect(hwnd),
                minimized=minimized,
                maximized=maximized,
            ))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(_cb, None)
    return results


def is_alive(hwnd: int) -> bool:
    import win32gui
    return bool(win32gui.IsWindow(hwnd))
