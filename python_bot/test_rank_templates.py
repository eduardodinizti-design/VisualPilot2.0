"""Fastpath safety contracts. Template self-match is not accuracy validation."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import json
import cv2
import numpy as np
from table_reading import rank_templates as templates
from table_reading import segmented_rank
from table_reading.fastpath import template_mode

class RankTemplateContracts(unittest.TestCase):
    def setUp(self):
        self.glyph=cv2.imread(str(templates.ASSET_DIR/'2-0.png'),cv2.IMREAD_GRAYSCALE)
        self.crop=np.zeros((60,42,3),np.uint8)

    def read(self,glyph=None,parts=1):
        glyph=self.glyph if glyph is None else glyph
        with patch.object(templates,'segmented_masks',return_value=[(glyph,parts)]*2):
            return templates.read_template_rank(self.crop)

    def test_atlas_keeps_frozen_source_split(self):
        manifest=json.loads((templates.ASSET_DIR/'manifest.json').read_text())
        split=json.loads((templates.ASSET_DIR/'source_split.json').read_text())
        actual={r['source_sha256'] for r in manifest['templates']}
        self.assertEqual(actual,set(split['training_sources']))
        self.assertFalse(actual & set(split['evaluation_sources']))
        self.assertEqual(len(split['evaluation_sources']),9)

    def test_margin_compares_distinct_ranks_not_variant_count(self):
        norm=templates.normalized(self.glyph);holes=templates.hole_count(self.glyph);ratio=self.glyph.shape[1]/self.glyph.shape[0]
        good=('2',norm,holes,ratio)
        bad=('5',np.logical_not(norm),holes,ratio)
        with patch.object(templates,'load_templates',return_value=[good,good,good,bad]):
            self.assertEqual(self.read()['rank'],'2')

    def test_vectorized_scores_exactly_match_scalar_reference(self):
        atlas=templates.load_templates()
        random=np.random.default_rng(704)
        candidates=[np.zeros((64,48),bool),np.ones((64,48),bool)]
        candidates.extend(random.random((64,48))>.8 for _ in range(32))
        candidates.extend(row[1] for row in atlas.rows)
        for candidate in candidates:
            expected={}
            for rank,mask,holes,ratio in atlas.rows:
                score=float(np.logical_and(candidate,mask).sum()/max(1,np.logical_or(candidate,mask).sum()))
                if score>expected.get(rank,(-1,False))[0]:
                    expected[rank]=(score,1==holes and abs(.5/ratio-1)<=.12)
            self.assertEqual(atlas.scores(candidate,1,.5),expected)

    def test_vectorized_tie_keeps_first_template_geometry(self):
        mask=templates.normalized(self.glyph)
        atlas=templates.TemplateAtlas([('2',mask,0,.5),('2',mask,1,.5)])
        self.assertEqual(atlas.scores(mask,1,.5)['2'],(1.,False))

    def test_exact_asset_self_match_contract_only(self):
        self.assertEqual(self.read()['rank'],'2')

    def test_ambiguous_families_cannot_shortcut_ocr(self):
        for rank in ('A','4','3','8'):
            glyph=cv2.imread(str(templates.ASSET_DIR/f'{rank}-0.png'),0)
            self.assertIsNone(self.read(glyph))

    def test_competing_identical_glyph_rejected(self):
        norm=templates.normalized(self.glyph);holes=templates.hole_count(self.glyph);ratio=self.glyph.shape[1]/self.glyph.shape[0]
        with patch.object(templates,'load_templates',return_value=[('2',norm,holes,ratio),('5',norm,holes,ratio)]):
            self.assertIsNone(self.read())

    def test_missing_or_corrupt_atlas_delegates(self):
        for error in (FileNotFoundError('atlas'),ValueError('checksum')):
            with patch.object(templates,'load_templates',side_effect=error):self.assertIsNone(self.read())

    def test_blank_crop_delegates(self):
        self.assertIsNone(templates.read_template_rank(self.crop))

    def test_two_thresholds_must_agree(self):
        other=cv2.imread(str(templates.ASSET_DIR/'5-0.png'),0)
        with patch.object(templates,'segmented_masks',return_value=[(self.glyph,1),(other,1)]):
            self.assertIsNone(templates.read_template_rank(self.crop))

    def test_component_count_rejects_non_ten_pair(self):
        self.assertIsNone(self.read(parts=2))

    def test_toggle_disabled_never_invokes_template_reader(self):
        with template_mode(False),patch.object(segmented_rank,'read_template_rank') as fast:
            segmented_rank.read_segmented_rank(self.crop)
        fast.assert_not_called()

    def test_fastpath_avoids_ocr_only_when_candidate_exists(self):
        candidate={'rank':'2','status':'CANDIDATE_ONLY','evidence':'test'}
        with template_mode(True),patch.object(segmented_rank,'read_template_rank',return_value=candidate),patch.object(segmented_rank,'image_to_string') as ocr:
            self.assertEqual(segmented_rank.read_segmented_rank(self.crop),candidate)
        ocr.assert_not_called()

if __name__=='__main__':unittest.main()
