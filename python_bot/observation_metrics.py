"""Bounded rolling timings, no frames or files retained."""
from collections import deque, Counter
import math
import os
import statistics
import time


def current_rss_mb():
    """Resident set size (MiB) of this process, or None if psutil is unavailable."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss/1024/1024
    except Exception:
        return None


def sample_resources(cpu_started):
    """Per-cycle CPU time (ms) since `cpu_started` (a time.process_time() reading) and RSS (MiB)."""
    return {'cpu_ms':(time.process_time()-cpu_started)*1000, 'rss_mb':current_rss_mb()}


class ObservationMetrics:
    def __init__(self, limit=120):
        self.samples=deque(maxlen=limit)
        self.outcomes=deque(maxlen=limit)
        self.memory=deque(maxlen=limit)
    def add(self, capture, report, cycle_ms, resources=None):
        values={'capture':capture.get('duration_ms'), **report.get('timings_ms',{}), 'cycle':cycle_ms}
        ocr_work=report.get('ocr_work',{})
        if 'wall_ms' in ocr_work:values['ocr_wall']=ocr_work['wall_ms']
        attempts=report.get('attempts',{})
        for key in ('card_reading','button_reading','board_reading'):
            if attempts.get(key,0)==0:values.pop(key,None)
        if not any(attempts.values()):
            values.pop('ocr_setup',None);values.pop('ocr_wall',None)
        values['cycle_with_ocr' if any(attempts.values()) else 'cycle_without_ocr']=cycle_ms
        if resources:
            cpu=resources.get('cpu_ms')
            if isinstance(cpu,(int,float)) and math.isfinite(cpu) and cpu>=0:values['cpu']=cpu
            rss=resources.get('rss_mb')
            if isinstance(rss,(int,float)) and math.isfinite(rss) and rss>=0:self.memory.append(float(rss))
        self.outcomes.append(dict(status='ANALYZED',card_attempts=attempts.get('card_reading',0),
            rejected=sum(r.get('status')!='COMPLETE_CANDIDATE' for r in report.get('tables',[])),
            reasons=[reason for r in report.get('tables',[]) for reason in r.get('reasons',[])],
            ocr_work={k:report.get('ocr_work',{}).get(k,0) for k in ('requests','calls','hits')}))
        self.samples.append({k:float(v) for k,v in values.items()
                             if isinstance(v,(int,float)) and math.isfinite(v) and v>=0})
    def failure(self, status):
        self.outcomes.append(dict(status=status,card_attempts=0,rejected=0,reasons=[]))
    def counts(self):
        return dict(window=len(self.outcomes),statuses=dict(Counter(r['status'] for r in self.outcomes)),
                    ocr_work={k:sum(r.get('ocr_work',{}).get(k,0) for r in self.outcomes) for k in ('requests','calls','hits')},
                    cycles_with_card_reader=sum(r['card_attempts']>0 for r in self.outcomes),
                    rejected_regions=sum(r['rejected'] for r in self.outcomes),
                    rejection_reasons=dict(Counter(v for r in self.outcomes for v in r['reasons'])))
    def summary(self):
        result={}
        for key in sorted({k for row in self.samples for k in row}):
            values=sorted(row[key] for row in self.samples if key in row)
            result[key]={'n':len(values),'median_ms':round(statistics.median(values),1),
                         'p95_ms':round(values[math.ceil(.95*len(values))-1],1)}
        return result
    def memory_mb(self):
        if not self.memory:return None
        values=sorted(self.memory)
        return {'n':len(values),'median_mb':round(statistics.median(values),1),'peak_mb':round(values[-1],1)}
