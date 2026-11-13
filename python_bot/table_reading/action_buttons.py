"""Experimental blue-layout button labels; observation only, never hero-turn proof."""
import re
import cv2
import numpy as np
import pytesseract
from .ocr_runtime import image_to_string
from .fastpath import templates_enabled
from .button_templates import read_static_label,read_exact_call


def parse_label(text):
    text=' '.join(text.strip().split())
    if text.casefold() in {'f/c','fold/check','check/fold'}:
        return dict(kind='PRESELECT',action=None,amount=None,unit=None)
    match=re.fullmatch(r'(Fold|Check|Call|Bet|Raise)(?:\s+(\d+(?:[.,]\d+)?)\s*(BB)?)?',text,re.I)
    if not match:return None
    action=match[1].upper()
    if action in {'FOLD','CHECK'} and match[2]:return None
    return dict(kind='ACTION_LABEL',action=action,amount=match[2].replace(',','.') if match[2] else None,
                unit='BB' if match[3] else None)


def read_action_buttons(crop, *, _ocr=None):
    result=dict(status='NO_BUTTON_ROW',buttons=[],hero_turn_confirmed=False,actions_allowed=False)
    if not isinstance(crop,np.ndarray) or crop.ndim!=3 or crop.shape[2]!=3 or crop.dtype!=np.uint8:
        return dict(result,status='INVALID_CROP')
    h,w=crop.shape[:2]
    if h<250 or w<150:return dict(result,status='CROP_TOO_SMALL')
    # Coordinates relative to the current table, never the desktop or old frame.
    offset=round(h*.92)
    band=crop[offset:h]
    hsv=cv2.cvtColor(band,cv2.COLOR_BGR2HSV)
    mask=np.uint8((hsv[:,:,1]>90)&(hsv[:,:,2]>65))*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if .22*w<=bw<=.38*w and .025*h<=bh<=.08*h and cv2.contourArea(contour)/(bw*bh)>.55:
            boxes.append((x,y,bw,bh))
    boxes.sort()
    if len(boxes)!=3:return result
    if max(b[1] for b in boxes)-min(b[1] for b in boxes)>.015*h:return result
    if any(a[0]+a[2]>=b[0] for a,b in zip(boxes,boxes[1:])):return result
    result['status']='EXPERIMENTAL_BUTTON_ROW'
    for x,y,bw,bh in boxes:
        # Interior text only; do not infer action from red/green/yellow or slot.
        region=band[y+round(bh*.18):y+round(bh*.82),x+round(bw*.08):x+round(bw*.92)]
        hsv_text=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
        ink=np.uint8((hsv_text[:,:,1]<85)&(hsv_text[:,:,2]>165))*255
        clean=cv2.resize(255-ink,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
        clean=cv2.copyMakeBorder(clean,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
        button=dict(box=[x,y+offset,bw,bh],status='NOT_IDENTIFIED',label=None,action=None,amount=None,unit=None)
        template=(read_exact_call(clean) or read_static_label(clean)) if _ocr is None and templates_enabled() else None
        if template is not None:
            parsed=parse_label(template['label'])
            button.update(parsed,**template,status='PRESELECT' if parsed['kind']=='PRESELECT' else 'EXPERIMENTAL_LABEL')
            result['buttons'].append(button)
            continue
        try:
            texts=[(_ocr(clean,mode) if _ocr else image_to_string(clean,config=f'--psm {mode}',timeout=2)).strip() for mode in (7,6)]
            parsed=[parse_label(t) for t in texts]
            button['ocr_readings']=texts
            if parsed[0] is not None and parsed[0]==parsed[1]:
                button.update(parsed[0],label=texts[0],status='PRESELECT' if parsed[0]['kind']=='PRESELECT' else 'EXPERIMENTAL_LABEL')
        except Exception as exc:button.update(status='OCR_ERROR',error=str(exc))
        result['buttons'].append(button)
    # A row containing F/C is a preselection panel. Other textual labels in
    # that same row must not be exposed as currently available actions.
    if any(b.get('kind')=='PRESELECT' for b in result['buttons']):
        result['status']='PRESELECTION_ROW'
        for button in result['buttons']:
            if button.get('action'):
                button['label_action']=button['action']
                button['action']=None
                button['kind']='PRESELECT'
                button['status']='PRESELECT'
    return result
