"""Menu extraction negatives use synthetic masks, not gameplay captures."""
import unittest
import numpy as np
from table_reading.table_corner_anchors import _menu_stripes

class DetectorBatchTests(unittest.TestCase):
    def bars(self):
        mask=np.zeros((70,65),np.uint8)
        for y in (19,25,32):mask[y:y+3,16:37]=255
        return mask
    def test_title_line_is_excluded_without_changing_three_bars(self):
        clean=self.bars();dirty=clean.copy();dirty[0,11:59]=255
        np.testing.assert_array_equal(_menu_stripes(dirty),clean)
    def test_two_bars_do_not_synthesize_third(self):
        mask=self.bars();mask[32:35]=0;mask[0,11:59]=255
        np.testing.assert_array_equal(_menu_stripes(mask),mask)
    def test_occluding_badge_is_not_menu(self):
        mask=np.zeros((70,65),np.uint8);mask[17:42,:64]=255
        np.testing.assert_array_equal(_menu_stripes(mask),mask)
    def test_ambiguous_groups_are_not_cherry_picked(self):
        mask=self.bars();mask[39:42,16:37]=255
        np.testing.assert_array_equal(_menu_stripes(mask),mask)
    def test_misaligned_bars_do_not_match(self):
        mask=self.bars();mask[32:35]=0;mask[32:35,35:56]=255
        np.testing.assert_array_equal(_menu_stripes(mask),mask)
