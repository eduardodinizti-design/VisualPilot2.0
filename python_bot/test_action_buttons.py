import unittest
from unittest.mock import patch
import cv2
import numpy as np
from table_reading.action_buttons import parse_label,read_action_buttons

class ButtonTests(unittest.TestCase):
    def image(self):
        image=np.zeros((1280,720,3),np.uint8)
        for x,color in zip([8,248,488],[(40,40,190),(50,160,20),(20,160,180)]):
            cv2.rectangle(image,(x,1200),(x+223,1260),color,-1)
        return image
    def test_three_labels_and_amount(self):
        values=iter(['Fold']*2+['Call 2,2 BB']*2+['Raise']*2)
        result=read_action_buttons(self.image(),_ocr=lambda *_:next(values))
        self.assertEqual([b['action'] for b in result['buttons']],['FOLD','CALL','RAISE'])
        self.assertEqual(result['buttons'][1]['amount'],'2.2')
        self.assertFalse(result['hero_turn_confirmed']);self.assertFalse(result['actions_allowed'])
    def test_conflicting_text_is_not_guessed(self):
        values=iter(['Call 2 BB','Call 3 BB']+['Pagar']*4)
        result=read_action_buttons(self.image(),_ocr=lambda *_:next(values))
        self.assertTrue(all(b['action'] is None for b in result['buttons']))
    def test_empty_does_not_call_ocr(self):
        with patch('table_reading.action_buttons.pytesseract.image_to_string') as ocr:
            result=read_action_buttons(np.zeros((1280,720,3),np.uint8))
        ocr.assert_not_called();self.assertEqual(result['buttons'],[])
    def test_preselection_not_action(self):
        self.assertEqual(parse_label('F/C')['kind'],'PRESELECT')
        self.assertIsNone(parse_label('F/C')['action'])
        for text in ['Fold 2 BB','Raise garbage','Call 1,2,3 BB','Pagar','']:
            self.assertIsNone(parse_label(text))
    def test_preselection_context_applies_to_entire_row(self):
        values=iter(['F/C']*2+['Call 1,0 BB']*2+['Raise']*2)
        result=read_action_buttons(self.image(),_ocr=lambda *_:next(values))
        self.assertEqual(result['status'],'PRESELECTION_ROW')
        self.assertTrue(all(b['action'] is None for b in result['buttons']))
        self.assertEqual(result['buttons'][1]['label_action'],'CALL')
        self.assertEqual(result['buttons'][1]['amount'],'1.0')
    def test_resize(self):
        result=read_action_buttons(cv2.resize(self.image(),(360,640)),_ocr=lambda *_:'Check')
        self.assertEqual(len(result['buttons']),3)
    def test_error_cannot_reuse_previous_label(self):
        def fail(*args):raise RuntimeError('timeout')
        result=read_action_buttons(self.image(),_ocr=fail)
        self.assertTrue(all(b['status']=='OCR_ERROR' and b['action'] is None for b in result['buttons']))
