"""Compatibility entry point: all captures use the strict client-area engine."""
import logging
from window_capture_engine import WindowCaptureEngine

_engine = WindowCaptureEngine()
last_capture_metadata = {}

def capture_pppoker_window(hwnd=None):
    global last_capture_metadata
    frame, last_capture_metadata = _engine.capture_frame(hwnd=hwnd)
    if frame is None:
        logging.getLogger(__name__).warning('Capture rejected: %s', last_capture_metadata)
    return frame
