import json,os,tempfile,unittest,sys,types
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
import coletar_amostras as collector

class SampleCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(os.environ.get('VISUALPILOT_ASSETS','public/assets/aistudio'))
        cls.frame=cv2.imread(str(root/'_8C143E80-F85C-4DE6-ADCD-0641771AE2E6__2a4e7ea0.png'))
        if cls.frame is None:raise RuntimeError('Missing real fixture')
    def metadata(self):return dict(status='SUCCESS',image_shape=list(self.frame.shape),screen_origin=[-1920,0],hwnd=123,pid=456,process_created=1.0,executable='PPPoker.exe')
    def test_real_fixture_only_native_regions_and_unlabeled_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'logs';target,report=collector.collect_samples(self.frame,self.metadata(),logs_root=root)
            self.assertEqual(target.parent,root/'leitura')
            self.assertEqual(report['status'],'UNLABELED');self.assertIsNone(report['labels'])
            self.assertFalse(report['training_imported']);self.assertFalse(report['actions_allowed'])
            self.assertEqual(len(list(target.glob('*.png'))),3)
            self.assertLess(sum(p.stat().st_size for p in target.iterdir()),collector.MAX_BUNDLE_BYTES)
            for row in report['tables']:
                for r in row['regions']:
                    x,y,w,h=r['frame_box'];crop=cv2.imread(str(target/r['file']))
                    np.testing.assert_array_equal(crop,self.frame[y:y+h,x:x+w])
                    self.assertEqual(list(crop.shape),r['image_shape']);self.assertEqual(len(r['png_sha256']),64)
    def test_wrong_metadata_never_creates_logs(self):
        for changes in ({'status':'FAILED'},{'image_shape':[1,1,3]},{'pid':None},{'frame_sha256':'bad'}):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'logs';meta=self.metadata();meta.update(changes)
                with self.assertRaises(ValueError):collector.collect_samples(self.frame,meta,logs_root=root)
                self.assertFalse(root.exists())
    def test_incoming_budget_failure_never_creates_logs(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(collector,'MAX_BUNDLE_BYTES',1):
            root=Path(tmp)/'logs'
            with self.assertRaises(RuntimeError):collector.collect_samples(self.frame,self.metadata(),logs_root=root)
            self.assertFalse(root.exists())
    def test_max_table_limit_and_missing_table_never_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'logs'
            with self.assertRaises(ValueError):collector.collect_samples(self.frame,self.metadata(),logs_root=root,max_tables=7)
            with patch.object(collector,'detect_table_crops',return_value=[]):
                with self.assertRaises(ValueError):collector.collect_samples(self.frame,self.metadata(),logs_root=root)
            self.assertFalse(root.exists())
    def test_mock_strict_live_capture_passes_requested_hwnd(self):
        calls=[];frame=self.frame;meta=self.metadata()
        class Engine:
            def capture_frame(self,*,hwnd):calls.append(hwnd);return frame,meta
        module=types.ModuleType('window_capture_engine');module.WindowCaptureEngine=Engine
        with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,{'window_capture_engine':module}):
            root=Path(tmp)/'logs';code=collector.main(['--hwnd','123','--logs-root',str(root)])
            self.assertEqual(code,0);self.assertEqual(calls,[123])
            report=json.loads(next(root.glob('leitura/*/resultado.json')).read_text())
            self.assertEqual(report['provenance']['kind'],'LIVE_STRICT_WINDOW_CAPTURE')
    def test_cli_requires_explicit_mode_and_paired_metadata(self):
        for args in ([],['--image','x'],['--hwnd','123','--metadata','x']):
            with self.assertRaises(SystemExit):collector.main(args)

    def test_live_failure_or_other_hwnd_never_saves(self):
        frame=self.frame;meta=self.metadata()
        for returned_frame,returned_meta in [(None,{'status':'WINDOW_INVALID_HWND'}),(frame,dict(meta,hwnd=999))]:
            class Engine:
                def capture_frame(self,*,hwnd):return returned_frame,returned_meta
            module=types.ModuleType('window_capture_engine');module.WindowCaptureEngine=Engine
            with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,{'window_capture_engine':module}):
                root=Path(tmp)/'logs'
                self.assertEqual(collector.main(['--hwnd','123','--logs-root',str(root)]),1)
                self.assertFalse(root.exists())
