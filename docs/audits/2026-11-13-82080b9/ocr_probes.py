"""Synthetic OCR probes; never captures a real screen or sends input."""
from pathlib import Path
import json, types
from unittest.mock import patch
import numpy as np

p=Path('python_bot/modules/ocr_processor.py')
m=types.ModuleType('audit_ocr')
exec(compile(p.read_text(),str(p),'exec'),m.__dict__)
o=m.PPPokerOCRProcessor.__new__(m.PPPokerOCRProcessor)
o.capture_hwnd_frame=lambda _:np.zeros((80,80,3),dtype=np.uint8)
blank=o.read_cards_and_pot('unused')
class Capture:
    def grab(self,region):
        self.region=region
        return np.zeros((region['height'],region['width'],4),dtype=np.uint8)
fake=Capture()
o.sct=fake
m.win32gui=types.SimpleNamespace(IsWindow=lambda _:False)
with patch.object(m,'WIN32_AVAILABLE',True),patch.object(m,'MSS_AVAILABLE',True):
    m.PPPokerOCRProcessor.capture_hwnd_frame(o,123)
print(json.dumps({'blank_frame_result':blank,'invalid_window_capture_region':fake.region},ensure_ascii=False,indent=2))
