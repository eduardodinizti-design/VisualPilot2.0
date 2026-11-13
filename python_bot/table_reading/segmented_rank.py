"""Foreground-first rank reading for neutral ink on coloured cards."""
import cv2
import numpy as np
import pytesseract
from .ocr_runtime import image_to_string
from .fastpath import templates_enabled
from .rank_templates import read_template_rank

VALID=set('AKQJT98765432')|{'10'}

def read_segmented_rank(crop):
    if templates_enabled():
        fast = read_template_rank(crop)
        if fast is not None:return fast
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    neutral=hsv[:,:,1]<70
    values=hsv[:,:,2][neutral]
    if values.size<8:return {'rank':None,'status':'SEGMENTATION_UNAVAILABLE'}
    readings=[];counts=[];original_shapes=[]
    for fraction in (.6,.8):
        mask=np.uint8(neutral & (hsv[:,:,2]>max(45,fraction*float(np.percentile(values,90)))))*255
        _,labels,stats,_=cv2.connectedComponentsWithStats(mask)
        parts=[(i,x,y,w,h) for i,(x,y,w,h,area) in enumerate(stats[1:],1)
               if area>=8 and h>=crop.shape[0]*.35 and w<crop.shape[1]*.85]
        if len(parts) not in (1,2):return {'rank':None,'status':'SEGMENTATION_UNAVAILABLE'}
        if any(x==0 or y==0 or x+w>=crop.shape[1] or y+h>=crop.shape[0] for _,x,y,w,h in parts):
            return {'rank':None,'status':'SEGMENTATION_UNAVAILABLE'}
        if len(parts)==2 and (abs(parts[0][2]-parts[1][2])>3 or abs(parts[0][4]-parts[1][4])>4):
            return {'rank':None,'status':'SEGMENTATION_UNAVAILABLE'}
        mask=np.uint8(np.isin(labels,[p[0] for p in parts]))*255
        ys,xs=np.where(mask);clean=255-mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
        original_shape=clean.copy()
        original_shapes.append(original_shape)
        clean=cv2.resize(clean,None,fx=12,fy=8,interpolation=cv2.INTER_NEAREST)
        clean=cv2.copyMakeBorder(clean,40,40,40,40,cv2.BORDER_CONSTANT,value=255)
        counts.append(len(parts))
        try:
            readings.extend(image_to_string(clean,config=f'--psm {mode} -c tessedit_char_whitelist=AKQJT1098765432',timeout=3).strip() for mode in (7,10))
        except Exception as exc:
            return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
    found={r for r in readings if r in VALID}
    if len(found)>1 or (2 in counts and any(r!='10' for r in found)):
        return {'rank':None,'status':'OCR_AMBIGUOUS','readings':readings,'evidence':'SEGMENTED_INK_CONFLICT'}
    if len(set(readings))==1 and readings[0] in VALID:
        # Horizontal widening confuses A/4 and can turn a reduced 7 into A.
        # Both A and 4 require independent undistorted confirmation.
        if readings[0] in {'4','A'}:
            original_shape=cv2.resize(original_shape,None,fx=8,fy=8,interpolation=cv2.INTER_NEAREST)
            original_shape=cv2.copyMakeBorder(original_shape,40,40,40,40,cv2.BORDER_CONSTANT,value=255)
            try:
                confirmation=[image_to_string(original_shape,config=f'--psm {mode} -c tessedit_char_whitelist=AKQJT1098765432',timeout=3).strip() for mode in (7,10)]
            except Exception as exc:return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
            # An oversized isolated glyph can produce blank OCR despite intact
            # strokes. Retry only all-blank A confirmation at smaller, still
            # undistorted scale; an observed conflicting rank is never bypassed.
            if readings[0]=='A' and confirmation==['','']:
                retry=[]
                try:
                    for glyph in original_shapes:
                        small=cv2.resize(glyph,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)
                        small=cv2.copyMakeBorder(small,40,40,40,40,cv2.BORDER_CONSTANT,value=255)
                        retry.extend(image_to_string(small,config=f'--psm {mode} -c tessedit_char_whitelist=AKQJT1098765432',timeout=3).strip() for mode in (7,10))
                except Exception as exc:return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
                if retry==['A']*4:
                    return {'rank':'A','status':'CANDIDATE_ONLY','readings':readings,
                            'aspect_confirmation':confirmation,'smaller_aspect_confirmation':retry,
                            'evidence':'ACE_TWO_THRESHOLDS_SMALLER_ORIGINAL_ASPECT'}
                return {'rank':None,'status':'OCR_AMBIGUOUS','readings':readings,
                        'aspect_confirmation':confirmation,'smaller_aspect_confirmation':retry,
                        'evidence':'ACE_REQUIRES_ORIGINAL_ASPECT'}
            if confirmation!=[readings[0],readings[0]]:
                return {'rank':None,'status':'OCR_AMBIGUOUS','readings':readings,'aspect_confirmation':confirmation,'evidence':'FOUR_REQUIRES_ORIGINAL_ASPECT' if readings[0]=='4' else 'ACE_REQUIRES_ORIGINAL_ASPECT'}
        return {'rank':'T' if readings[0]=='10' else readings[0],'status':'CANDIDATE_ONLY',
                'readings':readings,'evidence':'SEGMENTED_INK_TWO_THRESHOLDS_TWO_MODES'}
    if found:
        # Retry incomplete agreement using undistorted glyphs. Blank OCR output
        # is not a vote; require all four new observations, with no disagreement
        # against any earlier valid rank. Conflicts above never reach this path.
        confirmation=[]
        try:
            for glyph in original_shapes:
                clean=cv2.resize(glyph,None,fx=8,fy=8,interpolation=cv2.INTER_NEAREST)
                clean=cv2.copyMakeBorder(clean,40,40,40,40,cv2.BORDER_CONSTANT,value=255)
                confirmation.extend(image_to_string(clean,
                    config=f'--psm {mode} -c tessedit_char_whitelist=AKQJT1098765432',
                    timeout=3).strip() for mode in (7,10))
        except Exception as exc:
            return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
        if len(confirmation)==4 and len(set(confirmation))==1 and set(confirmation)==found:
            value=confirmation[0]
            return {'rank':'T' if value=='10' else value,'status':'CANDIDATE_ONLY',
                    'readings':readings,'aspect_confirmation':confirmation,
                    'evidence':'ORIGINAL_ASPECT_TWO_THRESHOLDS_TWO_MODES'}
        return {'rank':None,'status':'OCR_AMBIGUOUS','readings':readings,'aspect_confirmation':confirmation,'evidence':'SEGMENTED_INK_INCOMPLETE_AGREEMENT'}
    return {'rank':None,'status':'SEGMENTATION_UNREADABLE','readings':readings}
