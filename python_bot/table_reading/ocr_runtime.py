"""Exact OCR reuse within one snapshot only. No cross-frame card state.

OCR runs either through pytesseract (one tesseract.exe subprocess per call,
~73 ms of spawn overhead measured) or, when enabled, through an in-process
libtesseract binding (tesserocr) that reuses one engine per thread (~0.4 ms per
call, byte-identical output: same tesseract build and traineddata). The backend
is a pure performance swap; it changes no recognition result or threshold.
pytesseract stays the default and the fallback, so the lab (no tesserocr) is
unaffected."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from threading import RLock
import re
import threading
import time
import numpy as np
import pytesseract

_state = ContextVar('snapshot_ocr', default=None)
MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 256

# In-process OCR backend (tesserocr). Off by default; configure_ocr turns it on
# when tesserocr and a tessdata path are available.
_INPROC = {'enabled': False, 'path': None}
_tls = threading.local()
_PSM_RE = re.compile(r'--psm\s+(\d+)')
_WHITELIST_RE = re.compile(r'tessedit_char_whitelist=(\S+)')


def use_inprocess_ocr(tessdata_path, enabled=True):
    """Route OCR through tesserocr using the traineddata at tessdata_path."""
    _INPROC['enabled'] = bool(enabled)
    _INPROC['path'] = tessdata_path


def disable_inprocess_ocr():
    _INPROC['enabled'] = False


def inprocess_enabled():
    return _INPROC['enabled']


def _parse_config(config):
    """Extract (psm, char_whitelist) from a pytesseract-style config string."""
    config = config or ''
    psm_match = _PSM_RE.search(config)
    whitelist_match = _WHITELIST_RE.search(config)
    return (int(psm_match.group(1)) if psm_match else 3,
            whitelist_match.group(1) if whitelist_match else '')


def _inproc_api():
    """One tesserocr API per thread (PyTessBaseAPI is not thread-safe)."""
    api = getattr(_tls, 'api', None)
    if api is None:
        from tesserocr import PyTessBaseAPI
        api = PyTessBaseAPI(path=_INPROC['path'])
        _tls.api = api
    return api


def _inproc_ocr(image, config='', **_ignored):
    """OCR one image in-process. Same inputs the readers pass; timeout/lang are
    irrelevant without a subprocess. Char whitelist is reset every call so a
    previous call never leaks into one that passes none."""
    from PIL import Image
    api = _inproc_api()
    psm, whitelist = _parse_config(config)
    api.SetPageSegMode(psm)
    api.SetVariable('tessedit_char_whitelist', whitelist)
    if isinstance(image, np.ndarray):
        arr = image if image.flags['C_CONTIGUOUS'] else np.ascontiguousarray(image)
        pil = Image.fromarray(arr)
    elif isinstance(image, str):
        pil = Image.open(image)
    else:
        pil = image
    api.SetImage(pil)
    return api.GetUTF8Text()


def _run_ocr(image, **kwargs):
    """Dispatch to the in-process backend when enabled, else the subprocess.
    Any in-process failure falls back to pytesseract, so output never degrades."""
    if _INPROC['enabled']:
        try:
            return _inproc_ocr(image, **kwargs)
        except Exception:
            pass
    return pytesseract.image_to_string(image, **kwargs)

@contextmanager
def ocr_frame(enabled=True):
    existing = _state.get()
    if existing is not None:
        yield existing['stats']
        return
    state = dict(enabled=enabled, cache={}, lock=RLock(), stats=dict(requests=0, calls=0, hits=0, bytes=0, wall_ms=0.0))
    token = _state.set(state)
    try:
        yield state['stats']
    finally:
        _state.reset(token)
        state['cache'].clear()


def image_to_string(image, **kwargs):
    state = _state.get()
    if state is None:
        return _run_ocr(image, **kwargs)
    stats = state['stats']
    with state['lock']:stats['requests'] += 1
    key = None
    if state['enabled'] and isinstance(image, np.ndarray) and image.dtype == np.uint8 and image.nbytes <= MAX_BYTES:
        try:
            options = tuple(sorted(kwargs.items()))
            hash(options)
            key = (image.shape, image.dtype.str, image.tobytes(), options, pytesseract.pytesseract.tesseract_cmd)
        except TypeError:
            pass
    with state['lock']:
        if key is not None and key in state['cache']:
            stats['hits'] += 1
            return state['cache'][key]
        stats['calls'] += 1
    started = time.perf_counter()
    try:
        result = _run_ocr(image, **kwargs)
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        with state['lock']:stats['wall_ms'] += elapsed
    # Errors never reach here, and mutable/non-string outputs are not retained.
    if key is not None and isinstance(result, str):
        size = len(key[2]) + len(result.encode('utf8'))
        with state['lock']:
            if key not in state['cache'] and len(state['cache']) < MAX_ENTRIES and stats['bytes'] + size <= MAX_BYTES:
                state['cache'][key] = result
                stats['bytes'] += size
    return result


def snapshot_ocr(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with ocr_frame() as stats:
            result = function(*args, **kwargs)
            result['ocr_work'] = dict(stats)
            return result
    return wrapped
