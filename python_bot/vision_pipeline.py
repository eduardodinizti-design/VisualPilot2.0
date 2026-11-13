"""Legacy capture-only adapter retained for capture contract tests.
Recognition lives exclusively in table_reading.pipeline.
"""
from window_capture_engine import WindowCaptureEngine

class PPPokerObserverPipeline:
    @staticmethod
    def capture_window(hwnd=None):
        frame, metadata = WindowCaptureEngine().capture_frame(hwnd=hwnd)
        return frame, metadata['status']
