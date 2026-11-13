import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from table_reading.pipeline import analyze_tables
from ler_mesas import save_result, latest_capture


def tearDownModule():
    # analyze_tables may enable the in-process OCR backend via configure_ocr;
    # restore the default so later test modules are not affected.
    from table_reading import ocr_runtime
    ocr_runtime.disable_inprocess_ocr()

ASSETS=Path(os.environ.get('VISUALPILOT_ASSETS','public/assets/aistudio'))
SOURCE='_21D744E1-8BE6-4C79-82AF-5582DD6A9547__6988a9e2.png'
def metadata(frame,**kwargs):
    return dict(status='SUCCESS',image_shape=list(frame.shape),screen_origin=[-1920,0],
                hwnd=kwargs.get('hwnd',1),pid=kwargs.get('pid',2),process_created=100,
                executable='PPPoker.exe',timestamp='fixture')
def unknown(crop):return {'hero_rank_candidates':[{'card_candidate':None},{'card_candidate':None}]}

class PipelineContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ASSETS/SOURCE).is_file():raise RuntimeError('Required real fixture missing: '+str(ASSETS/SOURCE))
        cls.frame=cv2.imdecode(np.frombuffer((ASSETS/SOURCE).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    def test_buttons_receive_only_accepted_crop_when_enabled(self):
        with patch('table_reading.action_buttons.read_action_buttons',return_value={'status':'NO_BUTTON_ROW','buttons':[]}) as buttons:
            r=analyze_tables(self.frame,metadata(self.frame),_reader=unknown,read_buttons=True)
        self.assertEqual(buttons.call_count,r['complete_count'])
        self.assertTrue(any('action_buttons' in row for row in r['tables']))
        self.assertGreaterEqual(r['timings_ms']['button_reading'],0)

    def test_board_is_opt_in_and_uses_accepted_native_crop(self):
        with patch('table_reading.community_cards.read_board',return_value={'cards':[],'street':None,'status':'BOARD_NOT_CONFIRMED'}) as reader:
            disabled=analyze_tables(self.frame,metadata(self.frame),_reader=unknown)
            reader.assert_not_called()
            enabled=analyze_tables(self.frame,metadata(self.frame),_reader=unknown,read_community=True)
            self.assertEqual(reader.call_count,enabled['complete_count'])
            self.assertEqual(enabled['attempts']['board_reading'],reader.call_count)

    def test_real_pixels_are_cropped_and_routed(self):
        seen=[]
        def reader(crop):seen.append(crop);return unknown(crop)
        r=analyze_tables(self.frame,metadata(self.frame),_reader=reader)
        rows=[x for x in r['tables'] if x['status']=='COMPLETE_CANDIDATE']
        self.assertEqual(len(rows),1);self.assertEqual(len(seen),1)
        x,y,w,h=rows[0]['local_box']
        self.assertTrue(np.array_equal(seen[0],self.frame[y:y+h,x:x+w]))
        self.assertEqual(rows[0]['desktop_box'],[x-1920,y,w,h])
        self.assertIsNone(rows[0]['hero_cards'][0]);self.assertFalse(r['actions_allowed'])
    def test_scaled_moved_table_preserves_native_crop(self):
        table=cv2.resize(self.frame[36:1273,11:714],(352,619))
        frame=np.zeros((900,1400,3),np.uint8);frame[100:719,700:1052]=table
        r=analyze_tables(frame,metadata(frame),_reader=unknown)
        rows=[x for x in r['tables'] if x['status']=='COMPLETE_CANDIDATE']
        self.assertEqual(len(rows),1)
        x,y,w,h=rows[0]['local_box'];self.assertLess(abs(x-700),8);self.assertLess(abs(y-100),8)
        self.assertLess(w,370);self.assertLess(h,640)
    def test_six_limit_and_seven_refusal(self):
        table=cv2.resize(self.frame[36:1273,11:714],(352,619))
        for count in (6,7):
            a=np.zeros((720,400*count+20,3),np.uint8)
            for i in range(count):a[40:659,20+400*i:372+400*i]=table
            seen=[]
            r=analyze_tables(a,metadata(a),_reader=lambda c:seen.append(c.shape) or unknown(c))
            self.assertEqual(r['complete_count'],6 if count==6 else 0)
            self.assertEqual(len(seen),6 if count==6 else 0)
            if count==7:self.assertTrue(any('TABLE_LIMIT_EXCEEDED' in t['reasons'] for t in r['tables']))
    def test_separate_processes_and_snapshots_never_reuse_identity(self):
        r1=analyze_tables(self.frame,metadata(self.frame),_reader=unknown)
        r2=analyze_tables(self.frame,metadata(self.frame,pid=99,hwnd=4),_reader=unknown)
        r3=analyze_tables(self.frame,metadata(self.frame),_reader=unknown)
        self.assertNotEqual(r1['source_key'],r2['source_key'])
        self.assertEqual(r1['source_key'],r3['source_key'])
        self.assertNotEqual(r1['snapshot_id'],r3['snapshot_id'])
        self.assertFalse(r1['persistent_tracking'])
    def test_partial_is_not_read(self):
        frame=self.frame[:1000]
        def forbidden(c):self.fail('Partial crop must not reach OCR')
        self.assertEqual(analyze_tables(frame,metadata(frame),_reader=forbidden)['complete_count'],0)
    def test_missing_ocr_preserves_detected_crop(self):
        with patch('table_reading.pipeline.configure_ocr',side_effect=RuntimeError('missing')):
            r=analyze_tables(self.frame,metadata(self.frame))
        self.assertEqual(r['complete_count'],1)
        self.assertTrue(any(x['reading_status']=='OCR_UNAVAILABLE' for x in r['tables']))
    def test_metadata_mismatch_blocks_reading(self):
        m=metadata(self.frame);m['image_shape']=[1,1,3]
        with self.assertRaises(ValueError):analyze_tables(self.frame,m,_reader=unknown)
        m=metadata(self.frame);m['status']='WINDOW_AMBIGUOUS'
        with self.assertRaises(ValueError):analyze_tables(self.frame,m,_reader=unknown)
    def test_black_frame_has_no_tables(self):
        a=np.zeros((800,1600,3),np.uint8)
        self.assertEqual(analyze_tables(a,metadata(a),_reader=unknown)['tables'],[])
    def test_duplicate_card_is_not_accepted(self):
        r=analyze_tables(self.frame,metadata(self.frame),_reader=lambda c:{'hero_rank_candidates':[{'card_candidate':'As'}]*2})
        row=next(t for t in r['tables'] if t['status']=='COMPLETE_CANDIDATE')
        self.assertEqual(row['reading_status'],'DUPLICATE_CARD_REJECTED');self.assertEqual(row['hero_cards'],[None,None])
    def test_export_pixels_and_budget(self):
        r=analyze_tables(self.frame,metadata(self.frame),_reader=unknown)
        with tempfile.TemporaryDirectory() as f:
            root=Path(f)/"leitura"
            with self.assertRaises(RuntimeError):save_result(self.frame,r,root,budget=1)
            folder=save_result(self.frame,r,root)
            result=json.loads((folder/'resultado.json').read_text())
            row=next(t for t in result['tables'] if t['status']=='COMPLETE_CANDIDATE')
            crop=cv2.imdecode(np.frombuffer((folder/row['crop_file']).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            x,y,w,h=row['local_box'];self.assertTrue(np.array_equal(crop,self.frame[y:y+h,x:x+w]))
    def test_latest_skips_failed_reports(self):
        with tempfile.TemporaryDirectory() as f:
            p=Path(f);m=metadata(self.frame);m.update(capture_success=True,image_path='not-present.png')
            (p/'capture-1.json').write_text(json.dumps(m));(p/'capture-1.png').write_bytes(b'test')
            (p/'capture-2.json').write_text(json.dumps({'status':'WINDOW_INVALID_HWND'}))
            image,_=latest_capture(p);self.assertEqual(image.name,'capture-1.png')

if __name__=='__main__':unittest.main()
