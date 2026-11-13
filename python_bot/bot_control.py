"""Pause / takeover control plane — the safety gate that must exist BEFORE any
input is ever sent to the client.

Three states: RUNNING (the bot operates), PAUSED (you took over the tables; the
bot sends no input), DISABLED (the bot is off). The default is PAUSED: the bot is
never operating until it is explicitly armed. Any future executor MUST call
`execution_allowed()` immediately before every action and send nothing unless it
returns True; pause is therefore instant and always wins.

`HotkeyListener` polls global hotkeys (default Ctrl+Alt+P pause / R resume /
D disable) in a background thread so you can take over at any moment regardless
of which window has focus. The control itself is pure and thread-safe; the
listener's key reader is injectable so the state machine is testable without
Windows.
"""
import threading
import time

RUNNING = 'RUNNING'
PAUSED = 'PAUSED'
DISABLED = 'DISABLED'


class BotControl:
    """Thread-safe RUNNING/PAUSED/DISABLED state. Safe default = PAUSED."""

    def __init__(self, on_change=None):
        self._state = PAUSED
        self._lock = threading.Lock()
        self._on_change = on_change

    @property
    def state(self):
        with self._lock:
            return self._state

    def execution_allowed(self):
        """The only sanctioned gate for sending input. True ONLY while RUNNING."""
        with self._lock:
            return self._state == RUNNING

    def _apply(self, next_state):
        """Compute and commit the next state atomically: `next_state(current)`
        runs under the lock, so a concurrent transition can never read a stale
        state and overwrite a newer one (e.g. a late resume undoing a disable).
        The on_change callback fires after the lock is released."""
        with self._lock:
            new = next_state(self._state)
            if new == self._state:
                return False
            self._state = new
            cb = self._on_change
        if cb:
            try:
                cb(new)
            except Exception:
                pass
        return True

    def resume(self):
        """Step up one level of activity: DISABLED -> PAUSED, PAUSED -> RUNNING.
        Reactivating a disabled bot only arms it (PAUSED); a second resume is
        needed to actually run, so it never jumps straight from off to operating.
        A no-op when already RUNNING."""
        return self._apply(lambda s: PAUSED if s == DISABLED else (RUNNING if s == PAUSED else s))

    def pause(self):
        """Take over: go PAUSED. A no-op from DISABLED (disable is deliberate and
        sticky — only resume() reactivates)."""
        return self._apply(lambda s: s if s == DISABLED else PAUSED)

    def disable(self):
        """Turn the bot off from any state. Only resume() brings it back."""
        return self._apply(lambda s: DISABLED)


# Windows virtual-key codes.
VK_CONTROL = 0x11
VK_ALT = 0x12
VK_P = 0x50
VK_R = 0x52
VK_D = 0x44

DEFAULT_BINDINGS = {
    'pause': (VK_CONTROL, VK_ALT, VK_P),
    'resume': (VK_CONTROL, VK_ALT, VK_R),
    'disable': (VK_CONTROL, VK_ALT, VK_D),
}


def _win32_key_down(vk):
    import win32api
    return bool(win32api.GetAsyncKeyState(vk) & 0x8000)


class HotkeyListener(threading.Thread):
    """Poll global hotkeys and drive a BotControl. Edge-triggered: an action
    fires once per press (all keys of the combo down), not while held."""

    def __init__(self, control, bindings=None, key_down=None, poll=0.04):
        super().__init__(daemon=True)
        self._control = control
        self._bindings = dict(bindings or DEFAULT_BINDINGS)
        self._key_down = key_down or _win32_key_down
        self._poll = poll
        self._stop_event = threading.Event()   # not _stop: Thread._stop is an internal method
        self._was_down = {name: False for name in self._bindings}

    def _combo_down(self, combo):
        return all(self._key_down(vk) for vk in combo)

    def poll_once(self):
        """Check every binding once; fire the control method on a press edge.
        Returns the list of actions fired this tick (for tests)."""
        fired = []
        for name, combo in self._bindings.items():
            down = self._combo_down(combo)
            if down and not self._was_down[name]:
                getattr(self._control, name)()
                fired.append(name)
            self._was_down[name] = down
        return fired

    def run(self):
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                pass
            time.sleep(self._poll)

    def stop(self):
        self._stop_event.set()
