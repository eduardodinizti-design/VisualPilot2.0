import json,os,unittest
from pathlib import Path
import cv2
from table_reading.table_corner_anchors import corner_evidence,_measure,REGIONS

class CornerSamplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows=json.loads(Path('docs/table-reading/development-labels.json').read_text())['tables']
        cls.crops=[]
        root=Path(os.environ.get('VISUALPILOT_ASSETS','public/assets/aistudio'))
        for row in rows:
            im=cv2.imread(str(root/row['source']));x,y,w,h=row['box']
            if im is None:raise RuntimeError('Missing fixture')
            im=cv2.cvtColor(im[y:y+h,x:x+w],cv2.COLOR_BGR2RGB)
            im[round(h*.93):]=0 # Controlled removal of buttons, not a real spectator capture.
            cls.crops.append(im)
    def test_native_mask_recovers_sampling_loss_without_controls(self):
        before=after=0
        for crop in self.crops:
            for scale in (1,.75,.5):
                image=cv2.resize(crop,None,fx=scale,fy=scale)
                old=_measure(image);new=corner_evidence(image)
                before+=old['accepted'];after+=new['accepted']
                if old['accepted']:self.assertTrue(new['accepted'])
                if new['accepted']:self.assertTrue(all(v>=.65 for v in new['scores'].values()))
        self.assertGreater(after,before)
    def test_missing_corner_still_rejected(self):
        crop=self.crops[1]
        for name,(x,y,w,h) in REGIONS.items():
            image=cv2.resize(crop,(400,704));image[y:y+h,x:x+w]=0
            self.assertFalse(corner_evidence(image)['accepted'],name)
    def test_uniform_blue_is_not_table(self):
        image=cv2.resize(self.crops[1],(400,704));image[:]=[30,80,150]
        self.assertFalse(corner_evidence(image)['accepted'])
