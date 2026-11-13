import unittest
from unittest.mock import Mock
from continuous_observer import observe

META=dict(status='SUCCESS',hwnd=1,pid=2,process_created=3,executable='PPPoker.exe')
def report(cards,box=None):
    return dict(tables=[dict(status="COMPLETE_CANDIDATE",table_index=1,hero_cards=cards,local_box=box or [1,2,3,4],reading_status='EXPERIMENTAL_CANDIDATES')])

class ObserverTests(unittest.TestCase):
    def run_loop(self,captures,outputs,**kw):
        engine=Mock();engine.capture_frame.side_effect=captures
        reader=Mock(side_effect=outputs);lines=[]
        status=observe(engine,1,max_cycles=len(captures),analyze=reader,emit=lines.append,sleep=lambda _:None,**kw)
        return status,lines,reader
    def test_failure_does_not_repeat_cards_and_recovery_uses_new_box(self):
        _,lines,reader=self.run_loop([(object(),META),(None,{'status':'WINDOW_MINIMIZED'}),(object(),META)],
            [report(['Kh','8s']),report(['9d','9s'],[5,6,7,8])])
        self.assertEqual(reader.call_count,2)
        self.assertEqual(sum('Kh / 8s' in l for l in lines),1)
        self.assertTrue(any('WINDOW_MINIMIZED' in l for l in lines))
        self.assertTrue(any('[5, 6, 7, 8]' in l for l in lines))
    def test_source_change_stops_before_reading(self):
        status,_,reader=self.run_loop([(object(),META),(object(),dict(META,pid=8))],[report(['Kh','8s'])])
        self.assertEqual(status,2);self.assertEqual(reader.call_count,1)
    def test_expired_result_not_displayed(self):
        times=iter([0,11])
        _,lines,_=self.run_loop([(object(),META)],[report(['Kh','8s'])],clock=lambda:next(times))
        self.assertFalse(any('Kh / 8s' in l for l in lines))
        self.assertTrue(any('RESULT_EXPIRED' in l for l in lines))
    def test_exception_then_recovery(self):
        _,lines,_=self.run_loop([(object(),META),(object(),META)],[ValueError('bad frame'),report([None,None])])
        self.assertTrue(any('bad frame' in l for l in lines))
        self.assertTrue(any('NAO IDENTIFICADO / NAO IDENTIFICADO' in l for l in lines))
    def test_interrupt_clean_exit(self):
        engine=Mock();engine.capture_frame.side_effect=KeyboardInterrupt
        self.assertEqual(observe(engine,1,emit=lambda _:None),0)
    def test_invalid_interval(self):
        for value in [0,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):observe(Mock(),1,interval=value)
