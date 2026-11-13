"""Regression for a rejected frame contour masking an interior real table."""
import os,unittest
from pathlib import Path
import cv2
import numpy as np
from table_reading.automatic_table_crops import detect_table_crops

class DetectorProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(os.environ.get('VISUALPILOT_ASSETS','public/assets/aistudio'))
        source=root/'_8C143E80-F85C-4DE6-ADCD-0641771AE2E6__2a4e7ea0.png'
        im=cv2.imread(str(source))
        if im is None:raise RuntimeError('Missing real regression fixture '+str(source))
        cls.rgb=cv2.cvtColor(im,cv2.COLOR_BGR2RGB)
    def test_full_frame_rejection_does_not_suppress_real_table(self):
        rows=detect_table_crops(self.rgb)
        complete=[r for r in rows if r.status=='COMPLETE_CANDIDATE']
        self.assertEqual(len(complete),1)
        self.assertEqual(complete[0].box,(703,54,686,1237))
        self.assertEqual(complete[0].evidence,'FOUR_CORNER_BLUE_SURFACE')
        self.assertTrue(all(v>=.65 for v in complete[0].corner_scores.values()))
        self.assertTrue(any(r.status=='PARTIAL' and 'TOUCHES_FRAME_EDGE' in r.reasons for r in rows))
    def test_explicit_occlusion_remains_rejected(self):
        rows=detect_table_crops(self.rgb,blockers=[(900,500,50,50)])
        self.assertFalse(any(r.status=='COMPLETE_CANDIDATE' for r in rows))
        self.assertTrue(any(r.status=='OCCLUDED' for r in rows))
    def test_nested_blue_regions_without_anchors_never_become_tables(self):
        # Synthetic negative only: disconnected interior rectangle inside a
        # frame-touching blue border produces nested bounding rectangles.
        im=np.zeros((900,600,3),np.uint8)
        im[:8]=im[-8:]=[20,70,160];im[:,:8]=im[:,-8:]=[20,70,160]
        im[100:800,110:490]=[20,70,160]
        rows=detect_table_crops(im)
        self.assertFalse(any(r.status=='COMPLETE_CANDIDATE' for r in rows))
    def test_frame_touching_table_is_still_partial(self):
        # Derived crop, not an independent gameplay capture.
        im=self.rgb[54:1291,703:1389].copy()
        self.assertFalse(any(r.status=='COMPLETE_CANDIDATE' for r in detect_table_crops(im)))
