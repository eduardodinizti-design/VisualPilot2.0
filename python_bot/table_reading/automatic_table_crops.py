"""Offline table proposals. No reference boxes, OCR, window control or identity guesses.

The calibrated blue layout needs bottom controls or all four corner anchors
before experimental OCR. Felt-only regions remain diagnostic candidates.
"""
from dataclasses import dataclass,asdict,field
import cv2
import numpy as np
from .table_boundaries import detect_control_anchored_tables
from .table_corner_anchors import corner_evidence

@dataclass
class TableCrop:
    box: tuple
    status: str
    reasons: list
    evidence: str
    corner_scores: dict = field(default_factory=dict)
    corner_diagnostics: dict = field(default_factory=dict)
    def to_dict(self):return asdict(self)


def intersection(a,b):
    x,y,w,h=a;u,v,s,t=b
    return max(0,min(x+w,u+s)-max(x,u))*max(0,min(y+h,v+t)-max(y,v))


def detect_table_crops(rgb, blockers=(), max_tables=6):
    """Input RGB uint8, blocker rectangles relative to this frame (optional).

    Blockers can come from real window visibility metadata; they are not table
    annotations. Pixel-only detection cannot prove that no overlay exists.
    """
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or not rgb.size:
        raise ValueError('Expected nonempty RGB uint8 frame')
    if max_tables<1 or max_tables>6:raise ValueError('max_tables must be 1..6')
    height,width=rgb.shape[:2]
    if height*width>36_000_000:raise ValueError('Frame exceeds laboratory pixel limit')
    for b in blockers:
        if len(b)!=4 or b[2]<=0 or b[3]<=0:raise ValueError('Invalid blocker')
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    anchors=detect_control_anchored_tables(rgb,_hsv=hsv)
    proposals=[(b,'THREE_CONTROLS_BLUE_SURFACE') for b in anchors]
    for lower,upper in [((35,45,30),(130,255,255)),((105,45,30),(130,255,255)),((110,45,30),(130,255,255))]:
        mask=cv2.inRange(hsv,lower,upper)
        contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
        if lower[0]!=110 and any(cv2.boundingRect(c)[0]==0 for c in contours):
            mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
            contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
        # Prefer enclosing proposals over interior felt fragments.
        for contour in sorted(contours,key=lambda c: cv2.boundingRect(c)[2]*cv2.boundingRect(c)[3],reverse=True):
            box=cv2.boundingRect(contour);x,y,w,h=box
            if w<150 or h<250 or not .35<=w/h<=.85:continue
            # An edge-touching contour cannot establish a complete table and
            # must not suppress an interior candidate (desktop blue regions
            # can surround a genuine table). Keep ordinary enclosing-first
            # deduplication elsewhere, including repeated partial proposals.
            interior=x>1 and y>1 and x+w<width-1 and y+h<height-1
            def suppresses(existing):
                bx,by,bw,bh=existing
                existing_partial=bx<=1 or by<=1 or bx+bw>=width-1 or by+bh>=height-1
                return not (interior and existing_partial) and intersection(box,existing)/min(w*h,bw*bh)>=.5
            if any(suppresses(b) for b,_ in proposals):continue
            proposals.append((box,'FELT_ONLY'))
    results=[]
    for box,evidence in proposals:
        x,y,w,h=box;reasons=[];corner_scores={};corners={}
        if evidence=='FELT_ONLY' and .50<=w/h<=.63:
            corners=corner_evidence(rgb[y:y+h,x:x+w]);corner_scores=corners.get('scores',{})
            if corners['accepted']:evidence='FOUR_CORNER_BLUE_SURFACE'

        if x<=1 or y<=1 or x+w>=width-1 or y+h>=height-1:
            status='PARTIAL';reasons.append('TOUCHES_FRAME_EDGE')
        elif any(intersection((x-1,y-1,w+2,h+2),b)>0 for b in blockers):
            status='OCCLUDED';reasons.append('OVERLAPPING_WINDOW')
        elif evidence=='FELT_ONLY':
            status='UNCERTAIN'
            green=cv2.inRange(hsv[y:y+h,x:x+w],(35,45,30),(90,255,255))>0
            reasons.append('UNSUPPORTED_GREEN_LAYOUT' if green.mean()>.35 else 'FULL_BOUNDARY_NOT_ESTABLISHED')
        elif not .50<=w/h<=.63:
            status='UNCERTAIN';reasons.append('LAYOUT_PROPORTIONS_UNSUPPORTED')
        else:
            crop=rgb[y:y+h,x:x+w];blue=cv2.inRange(hsv[y:y+h,x:x+w],(90,45,30),(130,255,255))>0
            # A long horizontal void can indicate a foreground window or a cut.
            rows=blue[:round(h*.90)].mean(axis=1)<.18
            edges=np.diff(np.r_[False,rows,False].astype(np.int8))
            lengths=np.flatnonzero(edges==-1)-np.flatnonzero(edges==1)
            if len(lengths) and max(lengths)>.04*h:
                status='UNCERTAIN';reasons.append('HORIZONTAL_VISIBILITY_GAP')
            elif float(crop.std())<15 or blue.mean()<.55:
                status='UNCERTAIN';reasons.append('INSUFFICIENT_LAYOUT_EVIDENCE')
            else:status='COMPLETE_CANDIDATE'
        results.append(TableCrop(box,status,reasons,evidence,corner_scores,corners))
    if sum(r.status=='COMPLETE_CANDIDATE' for r in results)>max_tables:
        for r in results:
            if r.status=='COMPLETE_CANDIDATE':r.status='UNCERTAIN';r.reasons.append('TABLE_LIMIT_EXCEEDED')
    return sorted(results,key=lambda r:(r.box[1],r.box[0]))
