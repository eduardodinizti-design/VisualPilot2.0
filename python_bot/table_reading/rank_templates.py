"""Conservative exact-glyph geometry fastpath; uncertainty delegates to OCR."""
from functools import lru_cache
from pathlib import Path
import json
import hashlib
import cv2
import numpy as np

ASSET_DIR = Path(__file__).with_name('rank_template_assets')
MIN_IOU = .92
MIN_MARGIN = .12
# These confusions need further independent coverage before shortcutting OCR.
OCR_ONLY_RANKS = frozenset({'A','4','3','8'})


def segmented_masks(crop):
    if not isinstance(crop,np.ndarray) or crop.ndim!=3 or crop.shape[2]!=3 or not crop.size:
        return []
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    neutral=hsv[:,:,1]<70
    values=hsv[:,:,2][neutral]
    if values.size<8:return []
    glyphs=[]
    for fraction in (.6,.8):
        mask=np.uint8(neutral & (hsv[:,:,2]>max(45,fraction*float(np.percentile(values,90)))))*255
        _,labels,stats,_=cv2.connectedComponentsWithStats(mask)
        parts=[(i,x,y,w,h) for i,(x,y,w,h,area) in enumerate(stats[1:],1)
               if area>=8 and h>=crop.shape[0]*.35 and w<crop.shape[1]*.85]
        if len(parts) not in (1,2):return []
        if any(x==0 or y==0 or x+w>=crop.shape[1] or y+h>=crop.shape[0] for _,x,y,w,h in parts):return []
        if len(parts)==2 and (abs(parts[0][2]-parts[1][2])>3 or abs(parts[0][4]-parts[1][4])>4):return []
        mask=np.uint8(np.isin(labels,[p[0] for p in parts]))*255
        ys,xs=np.where(mask)
        glyph=mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
        if glyph.shape[0]<16 or glyph.shape[1]<5:return []
        glyphs.append((glyph,len(parts)))
    return glyphs


def normalized(glyph):
    h,w=glyph.shape
    factor=min(56/h,40/w)
    resized=cv2.resize(glyph,(max(1,round(w*factor)),max(1,round(h*factor))),interpolation=cv2.INTER_AREA)>127
    canvas=np.zeros((64,48),bool)
    y=(64-resized.shape[0])//2;x=(48-resized.shape[1])//2
    canvas[y:y+resized.shape[0],x:x+resized.shape[1]]=resized
    return canvas


def hole_count(glyph):
    contours,hierarchy=cv2.findContours(np.uint8(glyph>0)*255,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:return 0
    return sum(h[3]>=0 and cv2.contourArea(c)>=2 for c,h in zip(contours,hierarchy[0]))


class TemplateAtlas:
    """Immutable precomputed masks; each pixel comparison runs in one NumPy batch."""
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.masks = np.stack([row[1].ravel() for row in self.rows])
        self.areas = np.count_nonzero(self.masks, axis=1)
        self.masks.flags.writeable = False
        self.areas.flags.writeable = False

    def scores(self, candidate, holes, ratio):
        intersections = np.count_nonzero(self.masks & candidate.ravel(), axis=1)
        unions = self.areas + np.count_nonzero(candidate) - intersections
        values = intersections / np.maximum(1, unions)
        result = {}
        # Preserve stable rank ordering and first-template tie behavior exactly.
        for index, (rank, _, expected_holes, expected_ratio) in enumerate(self.rows):
            score = float(values[index])
            if score > result.get(rank, (-1, False))[0]:
                result[rank] = (score, holes == expected_holes and abs(ratio / expected_ratio - 1) <= .12)
        return result


@lru_cache(maxsize=1)
def load_templates():
    manifest=json.loads((ASSET_DIR/'manifest.json').read_text())
    result=[]
    for row in manifest['templates']:
        payload=(ASSET_DIR/row['asset']).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=row['asset_sha256']:raise ValueError('Rank template checksum mismatch')
        glyph=cv2.imdecode(np.frombuffer(payload,np.uint8),cv2.IMREAD_GRAYSCALE)
        if glyph is None or not glyph.size:raise ValueError('Missing rank template')
        result.append((row['rank'],normalized(glyph),hole_count(glyph),glyph.shape[1]/glyph.shape[0]))
    if {r[0] for r in result}!=set('23456789TJQKA'):raise ValueError('Incomplete competitor atlas')
    return TemplateAtlas(result)


def read_template_rank(crop):
    try:templates=load_templates()
    except (OSError,ValueError,KeyError):return None
    if not isinstance(templates, TemplateAtlas):templates = TemplateAtlas(templates)
    glyphs=segmented_masks(crop)
    if len(glyphs)!=2:return None
    decisions=[]
    for glyph,parts in glyphs:
        candidate=normalized(glyph);holes=hole_count(glyph);ratio=glyph.shape[1]/glyph.shape[0]
        scores=templates.scores(candidate,holes,ratio)
        ranked=sorted(scores.items(),key=lambda item:item[1][0],reverse=True)
        if len(ranked)<2:return None
        rank,(score,geometry)=ranked[0];margin=score-ranked[1][1][0]
        if rank in OCR_ONLY_RANKS or score<MIN_IOU or margin<MIN_MARGIN or not geometry:return None
        if (parts==2)!=(rank=='T'):return None
        decisions.append((rank,score,margin))
    if decisions[0][0]!=decisions[1][0]:return None
    return {'rank':decisions[0][0],'status':'CANDIDATE_ONLY',
            'evidence':'REAL_GLYPH_TEMPLATES_TWO_THRESHOLDS',
            'template_iou':round(min(d[1] for d in decisions),4),
            'template_margin':round(min(d[2] for d in decisions),4)}
