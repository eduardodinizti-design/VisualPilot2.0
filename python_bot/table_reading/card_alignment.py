"""Local vertical card-pair boundary evidence for the calibrated blue layout."""
import cv2
import numpy as np


def locate_card_pair(table):
    if not isinstance(table,np.ndarray) or table.shape!=(1280,720,3):
        return {'status':'INVALID_ALIGNMENT_IMAGE'}
    f=table.astype(np.float32)
    def strength(y,a,b):
        return float(np.median(np.linalg.norm(f[y+2,a:b]-f[y-2,a:b],axis=1)))
    def score(y):
        return min(strength(y,405,440),strength(y,455,530))
    top=max(range(960,1040),key=score)
    bottom=max(range(top+80,top+151),key=score)
    top_score,bottom_score=score(top),score(bottom)
    if top_score<25 or bottom_score<25:
        return {'status':'CARD_BOUNDARY_UNCERTAIN','top_score':top_score,'bottom_score':bottom_score}
    # Reject multiple separated top-edge candidates of comparable strength.
    alternatives=[y for y in range(960,1040) if abs(y-top)>8 and score(y)>=top_score*.8]
    if alternatives:
        return {'status':'CARD_BOUNDARY_AMBIGUOUS','top':top}
    # The existing ROI has margin for small shifts; avoid resampling jitter.
    offset=0 if abs(top-1024)<=10 else top-1024
    return {'status':'LOCALIZED','top':top,'bottom':bottom,'vertical_offset':offset,
            'top_score':top_score,'bottom_score':bottom_score,
            'scope':'Vertical alignment only; calibrated blue-layout search bands.'}
