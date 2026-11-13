import tempfile
from pathlib import Path
import unittest
import numpy as np
from coletar_sessao import run_session

class Clock:
    def __init__(self):self.t=0
    def __call__(self):return self.t
    def sleep(self,n):self.t+=n
class Engine:
    def __init__(self,clock,change=False):self.clock=clock;self.n=0;self.change=change
    def capture_frame(self,hwnd):
        self.clock.t+=15;self.n+=1
        return np.zeros((20,30,3),np.uint8),dict(status='SUCCESS',hwnd=hwnd,pid=2,process_created=self.n if self.change else 1,executable='PPPoker.exe')
class SessionTests(unittest.TestCase):
    def run_case(self,**kwargs):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);clock=Clock()
        return run_session(Engine(clock,kwargs.pop('change',False)),[1,2],minutes=1,output=Path(tmp.name),clock=clock,sleep=clock.sleep,analyze=lambda *a,**k:{'tables':[]},**kwargs)
    def test_duration_and_all_captures(self):
        folder,s=self.run_case();self.assertEqual(s['stop_reason'],'DURATION_COMPLETE');self.assertEqual(s['counts']['saved_records'],4)
        self.assertEqual(len(list(folder.glob('*.png'))),0);self.assertFalse(s['accuracy_validated']);self.assertFalse(s['actions_executed'])
    def test_identity_change_stops(self):
        _,s=self.run_case(change=True);self.assertEqual(s['stop_reason'],'SOURCE_CHANGED')
    def test_budget(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);c=Clock()
        _,s=run_session(Engine(c),[1],minutes=1,budget_mb=1,output=Path(tmp.name),clock=c,sleep=c.sleep,analyze=lambda *a,**k:{'tables':[],'large':'x'*1100000})
        self.assertEqual(s['stop_reason'],'DURATION_COMPLETE');self.assertEqual(s['counts']['records_omitted_at_budget'],4);self.assertLess(sum(p.stat().st_size for p in Path(tmp.name).rglob('*') if p.is_file()),1024*1024)
    def test_default_never_encodes_images(self):
        from unittest.mock import patch
        with patch('coletar_sessao.cv2.imencode',side_effect=AssertionError('must not encode')):
            _,s=self.run_case()
        self.assertEqual(s['counts']['saved_records'],4)
    def test_optional_samples_are_native_crops(self):
        import cv2
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);c=Clock()
        row={'status':'COMPLETE_CANDIDATE','table_index':1,'local_box':[2,3,10,12],'hero_cards':[None,None]}
        from unittest.mock import patch
        with patch('table_reading.presentation.describe_regions',return_value=[]):
            folder,s=run_session(Engine(c),[1],minutes=1,samples=True,output=Path(tmp.name),clock=c,sleep=c.sleep,analyze=lambda *a,**k:{'tables':[row]})
        images=list(folder.glob('*.png'));self.assertEqual(len(images),1)
        self.assertEqual(cv2.imread(str(images[0])).shape,(12,10,3))
    def test_rejection_transition_saved_without_waiting_one_minute(self):
        import json
        from unittest.mock import patch
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);c=Clock()
        def analyze(*args,**kwargs):
            return {'tables':[{'status':'COMPLETE_CANDIDATE' if c.t<=15 else 'UNCERTAIN',
                'table_index':1,'local_box':[2,3,10,12],'hero_cards':[None,None],
                'reasons':[] if c.t<=15 else ['FULL_BOUNDARY_NOT_ESTABLISHED']}]}
        with patch('table_reading.presentation.describe_regions',return_value=[]):
            folder,s=run_session(Engine(c),[1],minutes=1,samples=True,output=Path(tmp.name),clock=c,sleep=c.sleep,analyze=analyze)
        self.assertEqual(s['counts']['saved_samples'],2)
        self.assertEqual(s['counts']['saved_rejected_samples'],1)
        rows=[json.loads(line) for line in (folder/'leituras.jsonl').read_text().splitlines()]
        sample=rows[1]['samples'][0]
        self.assertEqual(sample['region_status'],'UNCERTAIN')
        self.assertEqual(sample['reasons'],['FULL_BOUNDARY_NOT_ESTABLISHED'])
        self.assertEqual(sample['sequence'],2)
        self.assertTrue((folder/sample['file']).exists())
if __name__=='__main__' :unittest.main()
