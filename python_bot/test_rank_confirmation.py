"""Contract tests with mocked OCR, not recognition-accuracy measurements."""
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from table_reading.segmented_rank import read_segmented_rank

class RankConfirmationTests(unittest.TestCase):
    def read(self, outputs):
        crop=np.zeros((60,42,3),dtype=np.uint8)
        cv2.putText(crop,'9',(8,43),cv2.FONT_HERSHEY_SIMPLEX,1.2,(255,255,255),2)
        with patch('table_reading.segmented_rank.pytesseract.image_to_string',side_effect=outputs) as ocr:
            result=read_segmented_rank(crop)
            return result,ocr.call_count
    def test_blank_variants_require_four_fresh_confirmations(self):
        r,n=self.read(['','','9','9']+['9']*4)
        self.assertEqual(r['rank'],'9');self.assertEqual(n,8)
    def test_conflicting_seven_nine_cannot_be_overridden(self):
        r,n=self.read(['7','9','9','9'])
        self.assertIsNone(r['rank']);self.assertEqual(n,4)
    def test_retry_conflict_abstains(self):
        r,_=self.read(['','','9','9']+['9','7','9','9'])
        self.assertIsNone(r['rank'])
    def test_retry_blank_abstains(self):
        r,_=self.read(['','','9','9']+['9','','9','9'])
        self.assertIsNone(r['rank'])
    def test_retry_error_abstains(self):
        r,_=self.read(['','','9','9',RuntimeError('timeout')])
        self.assertEqual(r['status'],'OCR_ERROR')
    def test_full_agreement_has_no_extra_ocr(self):
        r,n=self.read(['9']*4)
        self.assertEqual(r['rank'],'9');self.assertEqual(n,4)


class AceAspectTests(unittest.TestCase):
    read = RankConfirmationTests.read
    def test_distorted_ace_requires_undistorted_agreement(self):
        result,count=self.read(['A']*4+['7','7'])
        self.assertIsNone(result['rank'])
        self.assertEqual(result['evidence'],'ACE_REQUIRES_ORIGINAL_ASPECT')
        self.assertEqual(count,6)

    def test_blank_ace_can_use_four_smaller_undistorted_votes(self):
        result,count=self.read(['A']*4+['','']+['A']*4)
        self.assertEqual(result['rank'],'A')
        self.assertEqual(count,10)
        self.assertEqual(result['evidence'],'ACE_TWO_THRESHOLDS_SMALLER_ORIGINAL_ASPECT')

    def test_blank_ace_retry_conflict_abstains(self):
        result,count=self.read(['A']*4+['','']+['A','4','A','A'])
        self.assertIsNone(result['rank'])
        self.assertEqual(count,10)

    def test_one_blank_does_not_enable_smaller_retry(self):
        result,count=self.read(['A']*4+['A',''])
        self.assertIsNone(result['rank'])
        self.assertEqual(count,6)

    def test_blank_and_conflict_does_not_enable_smaller_retry(self):
        result,count=self.read(['A']*4+['','4'])
        self.assertIsNone(result['rank'])
        self.assertEqual(count,6)

    def test_blank_ace_retry_partial_abstains(self):
        result,count=self.read(['A']*4+['','']+['A','','A','A'])
        self.assertIsNone(result['rank'])

    def test_confirmed_ace_remains_accepted(self):
        result,count=self.read(['A']*6)
        self.assertEqual(result['rank'],'A')
        self.assertEqual(count,6)

if __name__=='__main__':unittest.main()
