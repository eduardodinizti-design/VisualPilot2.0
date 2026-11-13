import unittest
from dataclasses import FrozenInstanceError
import numpy as np
from table_reading.roi_geometry import get_roi,clear_cache,cache_info,Rect
from table_reading.community_cards import read_board

class RoiGeometryTests(unittest.TestCase):
    def setUp(self):clear_cache()
    def test_matches_existing_board_band_across_resolutions(self):
        for w,h in ((703,1237),(686,1237),(300,534),(1920,1080),(1,1)):
            rect=get_roi(w,h)
            self.assertEqual(rect,Rect(round(w*.17),round(h*.35),round(w*.85),round(h*.50)))
            self.assertTrue(0<=rect.left<=rect.right<=w and 0<=rect.top<=rect.bottom<=h)
    def test_translation_changes_only_diagnostics_not_cached_local_geometry(self):
        rect=get_roi(703,1237)
        shifted=rect.translated(-1920,150)
        self.assertEqual(shifted.left,rect.left-1920)
        self.assertEqual(shifted.top,rect.top+150)
        self.assertIs(get_roi(703,1237),rect)
        self.assertEqual(cache_info().currsize,1)
    def test_resize_uses_new_bounds_and_cache_is_bounded(self):
        first=get_roi(300,534)
        self.assertNotEqual(first,get_roi(703,1237))
        for i in range(500):get_roi(300+i,534+i)
        self.assertEqual(cache_info().currsize,128)
    def test_geometry_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):get_roi(703,1237).left=0
    def test_invalid_dimensions_and_unknown_profiles_rejected(self):
        for w,h in ((0,1),(1,0),(-1,1),(1.2,4),(True,2)):
            with self.assertRaises(ValueError):get_roi(w,h)
        with self.assertRaises(ValueError):get_roi(703,1237,layout='WHITE')
        with self.assertRaises(ValueError):get_roi(703,1237,region='unknown')
    def test_cached_geometry_reads_current_frame_pixels(self):
        a=np.zeros((100,100,3),np.uint8);b=np.full_like(a,255)
        rect=get_roi(100,100)
        self.assertEqual(int(a[rect.slices].max()),0)
        self.assertEqual(int(b[get_roi(100,100).slices].min()),255)
        self.assertFalse(any(isinstance(value,np.ndarray) for value in vars(rect).values()))
    def test_empty_board_crop_fails_cleanly(self):
        self.assertEqual(read_board(np.zeros((0,20,3),np.uint8))['status'],'INVALID_CROP')
