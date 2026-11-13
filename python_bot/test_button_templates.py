import unittest
from unittest.mock import patch
import cv2
import numpy as np
from table_reading.button_templates import ASSETS,normalize,read_static_label,templates
from table_reading.fastpath import template_mode
from table_reading.action_buttons import read_action_buttons
import test_action_buttons

class ButtonTemplateTests(unittest.TestCase):
    def clean(self,label='Check'):
        return cv2.imread(str(ASSETS/(label+'.png')),cv2.IMREAD_GRAYSCALE)
    def test_packaged_static_labels(self):
        for label in ('F_C','Check','Fold','Raise'):
            result=read_static_label(self.clean(label))
            self.assertEqual(result['label'],label.replace('_','/'))
            self.assertEqual(result['evidence'],'WHOLE_LABEL_TEMPLATE')
    def test_whole_text_includes_added_amount(self):
        clean=self.clean();points=cv2.findNonZero(np.uint8(clean<128));x,y,w,h=cv2.boundingRect(points)
        changed=clean.copy();cv2.putText(changed,' 2 BB',(x+w+5,y+h),cv2.FONT_HERSHEY_SIMPLEX,.7,0,2)
        self.assertIsNone(read_static_label(changed))
    def test_unknown_blank_and_partial_do_not_match(self):
        self.assertIsNone(read_static_label(np.full((80,300),255,np.uint8)))
        clean=self.clean();clean[:,clean.shape[1]//2:]=255
        self.assertIsNone(read_static_label(clean))
        self.assertIsNone(read_static_label(None))
    def test_missing_competitor_disables_entire_bank(self):
        clean=self.clean();original=cv2.imread
        def missing(path,*args):
            return None if path.endswith('Raise.png') else original(path,*args)
        templates.cache_clear()
        try:
            with patch('table_reading.button_templates.cv2.imread',side_effect=missing):
                self.assertIsNone(read_static_label(clean))
        finally:templates.cache_clear()
    def test_hash_mismatch_disables_bank(self):
        clean=self.clean()
        templates.cache_clear()
        try:
            with patch('table_reading.button_templates.Path.read_bytes',return_value=b'corrupt'):
                self.assertIsNone(read_static_label(clean))
        finally:templates.cache_clear()
    def test_extreme_aspect_abstains_before_resize(self):
        with patch('table_reading.button_templates.cv2.resize') as resize:
            self.assertIsNone(normalize(np.zeros((8,10000),np.uint8)))
        resize.assert_not_called()
    def test_ambiguous_templates_abstain(self):
        clean=self.clean();mask,ratio=normalize(clean)
        with patch('table_reading.button_templates.templates',return_value=[('Check',mask,ratio),('Bet',mask,ratio)]):
            self.assertIsNone(read_static_label(clean))
    def test_injected_ocr_always_bypasses_templates(self):
        with patch('table_reading.action_buttons.read_static_label') as template:
            result=read_action_buttons(test_action_buttons.ButtonTests().image(),_ocr=lambda *_:'Check')
        template.assert_not_called()
        self.assertTrue(all('ocr_readings' in b for b in result['buttons']))
    def test_disabled_mode_bypasses_templates(self):
        with template_mode(False),patch('table_reading.action_buttons.read_static_label') as template,patch('table_reading.action_buttons.image_to_string',return_value='Check'):
            read_action_buttons(test_action_buttons.ButtonTests().image())
        template.assert_not_called()
    def test_template_evidence_does_not_fabricate_ocr(self):
        with patch('table_reading.action_buttons.read_static_label',return_value=dict(label='F/C',evidence='WHOLE_LABEL_TEMPLATE',template_iou=1.,template_margin=1.)),patch('table_reading.action_buttons.image_to_string') as ocr:
            result=read_action_buttons(test_action_buttons.ButtonTests().image())
        ocr.assert_not_called()
        self.assertEqual(result['status'],'PRESELECTION_ROW')
        self.assertTrue(all('ocr_readings' not in b and b['action'] is None for b in result['buttons']))
