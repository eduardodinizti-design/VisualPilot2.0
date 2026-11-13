"""Scoped switch for comparing template readers with the preserved OCR path."""
from contextlib import contextmanager
from contextvars import ContextVar
_enabled = ContextVar('visualpilot_templates', default=True)

def templates_enabled():
    return _enabled.get()

@contextmanager
def template_mode(enabled=True):
    token = _enabled.set(bool(enabled))
    try:
        yield
    finally:
        _enabled.reset(token)
