"""Experimental community-card row on calibrated blue layout. No strategy/actions."""
import cv2
import numpy as np
from .inspect_cards import read_rank
from .suit_reader import read_suit
from .roi_geometry import get_roi


def read_board(table, *, _rank=read_rank, _suit=read_suit, hero_cards=()):
    result=dict(status='BOARD_NOT_CONFIRMED',street=None,cards=[],candidates=[],actions_allowed=False)
    if not isinstance(table,np.ndarray) or table.dtype!=np.uint8 or table.ndim!=3 or table.shape[2]!=3:
        return dict(result,status='INVALID_CROP')
    h,w=table.shape[:2]
    if not h or not w:return dict(result,status='INVALID_CROP')
    band=get_roi(w,h)
    x0,y0=band.left,band.top
    roi=table[band.slices]
    if not roi.size:return result
    hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
    hue,sat,val=cv2.split(hsv)
    # Red/green/cyan solid card faces, or dark neutral spade faces.
    colored=(sat>110)&(val>90)&((hue<12)|((hue>35)&(hue<109))|(hue>170))
    neutral=(sat<45)&(val>35)&(val<150)
    white=(sat<60)&(val>=150)   # faces BRANCAS de carta (ex. board do skin Karekas)
    mask=np.uint8(colored|neutral|white)*255
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    fragments=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        fragments.append((x+x0,y+y0,bw,bh))
        if .07*w<=bw<=.14*w and .06*h<=bh<=.12*h and .45<=bw/bh<=.85 and cv2.contourArea(c)/(bw*bh)>.75:
            if x==0 or y==0 or x+bw>=roi.shape[1] or y+bh>=roi.shape[0]:continue
            boxes.append((x+x0,y+y0,bw,bh))
    boxes.sort()
    result['candidates']=[list(b) for b in boxes]
    if len(boxes) not in (3,4,5):return result
    # This calibrated layout starts the community row near 20% of table width.
    # A contiguous suffix of an occluded river must not be called a turn/flop.
    if not .17*w <= boxes[0][0] <= .25*w:
        return dict(result,status='BOARD_PARTIAL_OR_OBSTRUCTED',reason='FIRST_CARD_ANCHOR_MISSING')
    heights=[b[3] for b in boxes];widths=[b[2] for b in boxes]
    if max(b[1] for b in boxes)-min(b[1] for b in boxes)>.012*h:return result
    if max(heights)/min(heights)>1.15 or max(widths)/min(widths)>1.15:return result
    if any(not 0<=b[0]-a[0]-a[2]<=.03*w for a,b in zip(boxes,boxes[1:])):return result
    # A fourth/fifth card fragment must not turn a partial turn/river into flop.
    row_top=min(b[1] for b in boxes);row_bottom=max(b[1]+b[3] for b in boxes)
    median_width=float(np.median(widths));median_height=float(np.median(heights))
    for fx,fy,fw,fh in fragments:
        if (fx,fy,fw,fh) in boxes:continue
        overlap=max(0,min(fy+fh,row_bottom)-max(fy,row_top))
        if (boxes[0][0]-median_width*.3 <= fx <= boxes[-1][0]+median_width*1.5
                and fw>=median_width*.18 and overlap>=median_height*.25):
            return dict(result,status='BOARD_PARTIAL_OR_OBSTRUCTED')
    def read_face(box):
        x,y,bw,bh=box
        face=cv2.resize(table[y:y+bh,x:x+bw],(90,130))
        try:
            rank=_rank(face[3:53,4:44]);suit=_suit(face[45:86,3:43])
            if suit.get('status')=='SUIT_UNREADABLE':
                native=table[y+round(bh*45/130):y+round(bh*86/130),
                             x+round(bw*3/90):x+round(bw*43/90)]
                retry=_suit(native)
                if retry.get('suit'):suit=dict(retry,source='NATIVE_PIXELS')
            card=(rank.get('rank') or '')+(suit.get('suit') or '') if rank.get('rank') and suit.get('suit') else None
            return dict(card=card,rank=rank,suit=suit)
        except Exception as exc:return dict(card=None,error=str(exc))
    from .concurrent_reads import ordered_board_reads
    readings=ordered_board_reads(read_face,boxes,enabled=_rank is read_rank and _suit is read_suit)
    result['readings']=readings
    cards=[r['card'] for r in readings]
    if not all(cards):return dict(result,status='BOARD_INCOMPLETE')
    if len(set(cards))!=len(cards) or set(cards)&{c for c in hero_cards if c}:
        return dict(result,status='BOARD_DUPLICATE_REJECTED')
    return dict(result,status='EXPERIMENTAL_BOARD',cards=cards,street={3:'FLOP',4:'TURN',5:'RIVER'}[len(cards)])
