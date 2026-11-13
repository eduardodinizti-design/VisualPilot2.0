import unittest
from unittest.mock import patch
import cv2
import numpy as np
from table_reading.button_templates import ASSETS,read_exact_call,exact_call_template
from table_reading.action_buttons import read_action_buttons
import test_action_buttons

class ExactCallTests(unittest.TestCase):
    def clean(self):return cv2.imread(str(ASSETS/'Call_1_0_BB_exact.png'),cv2.IMREAD_GRAYSCALE)
    def test_exact_full_amount(self):
        self.assertEqual(read_exact_call(self.clean()),dict(label='Call 1,0 BB',evidence='EXACT_WHOLE_LABEL_RASTER'))
    def test_single_pixel_change_rejected(self):
        clean=self.clean();clean[35,180]=255-clean[35,180]
        self.assertIsNone(read_exact_call(clean))
    def test_resize_rejected(self):
        for factor in (.5,1.5,2):self.assertIsNone(read_exact_call(cv2.resize(self.clean(),None,fx=factor,fy=factor)))
    def test_missing_or_corrupt_asset_falls_back(self):
        clean=self.clean()
        for replacement in (FileNotFoundError('missing'),None):
            exact_call_template.cache_clear()
            try:
                if replacement:
                    with patch('table_reading.button_templates.Path.read_bytes',side_effect=replacement):self.assertIsNone(read_exact_call(clean))
                else:
                    with patch('table_reading.button_templates.Path.read_bytes',return_value=b'corrupt'):self.assertIsNone(read_exact_call(clean))
            finally:exact_call_template.cache_clear()
    def test_blank_and_suffix_rejected(self):
        self.assertIsNone(read_exact_call(np.full((72,369),255,np.uint8)))
        clean=cv2.copyMakeBorder(self.clean(),0,0,0,30,cv2.BORDER_CONSTANT,value=255);clean[20:40,-10:]=0
        self.assertIsNone(read_exact_call(clean))
    def test_mixed_preselection_keeps_amount_but_disables_action(self):
        exact=iter([None,dict(label='Call 1,0 BB',evidence='EXACT_WHOLE_LABEL_RASTER'),None])
        static=iter([dict(label='F/C',evidence='WHOLE_LABEL_TEMPLATE'),dict(label='Raise',evidence='WHOLE_LABEL_TEMPLATE')])
        with patch('table_reading.action_buttons.read_exact_call',side_effect=lambda _:next(exact)),patch('table_reading.action_buttons.read_static_label',side_effect=lambda _:next(static)),patch('table_reading.action_buttons.image_to_string') as ocr:
            result=read_action_buttons(test_action_buttons.ButtonTests().image())
        ocr.assert_not_called();self.assertEqual(result['status'],'PRESELECTION_ROW')
        call=result['buttons'][1]
        self.assertEqual(call['amount'],'1.0');self.assertEqual(call['unit'],'BB');self.assertEqual(call['label_action'],'CALL');self.assertIsNone(call['action']);self.assertNotIn('ocr_readings',call)
    def test_injected_reader_bypasses_exact_shortcut(self):
        with patch('table_reading.action_buttons.read_exact_call') as exact:
            read_action_buttons(test_action_buttons.ButtonTests().image(),_ocr=lambda *_:'Check')
        exact.assert_not_called()
