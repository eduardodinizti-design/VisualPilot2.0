"""Offline hero-rank diagnostics for the supplied blue PPPoker layout. No clicks."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
import pytesseract
from .ocr_runtime import image_to_string
from .suit_reader import read_suit
from .card_alignment import locate_card_pair
from .segmented_rank import read_segmented_rank


def read_rank(crop):
    if not isinstance(crop, np.ndarray) or crop.ndim != 3 or crop.shape[2] != 3 or min(crop.shape[:2]) < 8:
        return {"rank": None, "status": "INVALID_RANK_CROP"}
    foreground=read_segmented_rank(crop)
    if foreground['status'] in ('CANDIDATE_ONLY','OCR_AMBIGUOUS','OCR_ERROR'):
        return foreground
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    enlarged = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, raw = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    linear = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    _, linear = cv2.threshold(linear, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates = [raw, linear]
    multiple_white_glyphs=False
    _, mask = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    neutral=hsv[:,:,1]<70
    values=hsv[:,:,2][neutral]
    cutoff=max(60,min(170,.8*float(np.percentile(values,90)))) if values.size else 170
    white=np.uint8(neutral&(hsv[:,:,2]>cutoff))*255
    for ink in (mask,white):
        _, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
        parts=[]
        for i, (x,y,w,h,area) in enumerate(stats[1:],1):
            if area>=8 and h>=gray.shape[0]*.35 and w<gray.shape[1]*.85:
                parts.append((i,x,y,w,h))
            if area >= 20 and h >= gray.shape[0] * .35 and w < gray.shape[1] * .85:
                clean = np.where(labels[y:y+h,x:x+w] == i, 0, 255).astype(np.uint8)
                clean = cv2.copyMakeBorder(clean,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
                candidates.append(cv2.resize(clean,None,fx=4,fy=4))
        # Keep aligned adjacent digits together; a ten is not two separate ranks.
        if len(parts)==2 and abs(parts[0][2]-parts[1][2])<=3 and abs(parts[0][4]-parts[1][4])<=4:
            if ink is white:multiple_white_glyphs=True
            x=min(p[1] for p in parts);y=min(p[2] for p in parts)
            right=max(p[1]+p[3] for p in parts);bottom=max(p[2]+p[4] for p in parts)
            clean=np.where(np.isin(labels[y:bottom,x:right],[p[0] for p in parts]),0,255).astype(np.uint8)
            clean=cv2.copyMakeBorder(clean,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
            candidates.append(cv2.resize(clean,None,fx=4,fy=4))
    found = set()
    try:
        for variant in candidates:
            text = image_to_string(variant,config='--psm 10 -c tessedit_char_whitelist=AKQJT1098765432',timeout=3).strip()
            if text in list('AKQJT98765432') + ['10']:
                found.add('T' if text == '10' else text)
    except Exception as exc:
        return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
    if not found:
        # Alternate polarity only on abstention, with two segmentation modes
        # agreeing. Never replace an existing conflict or map a lone 0 to ten.
        _,binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        inverted=cv2.copyMakeBorder(255-binary,10,10,10,10,cv2.BORDER_CONSTANT,value=255)
        inverted=cv2.resize(inverted,None,fx=4,fy=4)
        try:
            readings=[image_to_string(inverted,config=f'--psm {mode} -c tessedit_char_whitelist=AKQJT1098765432',timeout=3).strip() for mode in (7,10)]
        except Exception as exc:
            return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
        if readings[0]==readings[1] and readings[0] in list('AKQJT98765432')+['10']:
            found.add('T' if readings[0]=='10' else readings[0])
    if multiple_white_glyphs and found and found!={'T'}:
        return {'rank':None,'status':'OCR_AMBIGUOUS','alternatives':sorted(found),'evidence':'MULTIPLE_GLYPHS','suit':None}
    return {'rank':next(iter(found)) if len(found)==1 else None,
            'status':'CANDIDATE_ONLY' if len(found)==1 else 'OCR_AMBIGUOUS' if found else 'OCR_UNREADABLE',
            'alternatives':sorted(found),'suit':None}


def read_native_white_rank(table, left, vertical_offset=0):
    """Two nearby search bounds accommodate rounding at small resolutions.

    Each accepted rank requires agreement of both OCR modes; any conflicting
    valid rank or OCR error across either region blocks the entire result.
    """
    attempts=[_read_native_white_rank(table,left,bottom,vertical_offset=vertical_offset) for bottom in (1066,1070)]
    if any(a['status']=='OCR_ERROR' for a in attempts):
        return {'rank':None,'status':'OCR_ERROR','attempts':attempts}
    observed={('T' if v=='10' else v) for a in attempts for v in a.get('readings',[])
              if v in list('AKQJT98765432')+['10']}
    accepted={a['rank'] for a in attempts if a['rank'] is not None}
    if not accepted and not observed:
        # Thin adjacent digits can merge perceptually for OCR at native size.
        # Retry cleaned ink with wider spacing only after both normal regions
        # abstain. Never override a valid conflicting rank or an OCR error.
        retry=_read_native_white_rank(table,left,1070,clean_wide=True,vertical_offset=vertical_offset)
        attempts.append(retry)
        if retry['status']=='OCR_ERROR':
            return {'rank':None,'status':'OCR_ERROR','attempts':attempts}
        if retry['rank'] is not None:
            accepted.add(retry['rank']);observed.add(retry['rank'])
    value=next(iter(accepted)) if len(accepted)==1 and len(observed)==1 else None
    return {'rank':value,'status':'CANDIDATE_ONLY' if value else 'NATIVE_OCR_UNREADABLE_OR_CONFLICT','attempts':attempts}


def _read_native_white_rank(table, left, bottom, clean_wide=False,vertical_offset=0):
    """Experimental white-ink fallback, cropped before canonical resizing.

    Uses a broad normalized search area, then trims to the actual ink bounds.
    Never treats a lone zero or one as ten.
    """
    height,width=table.shape[:2]
    x1=round((left-5)*width/720);x2=round((left+42)*width/720)
    y1=round((1008+vertical_offset)*height/1280);y2=round((bottom+vertical_offset)*height/1280)
    region=table[y1:y2,x1:x2]
    if not region.size:return {'rank':None,'status':'NATIVE_REGION_EMPTY'}
    hsv=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
    mask=np.uint8((hsv[:,:,1]<90)&(hsv[:,:,2]>150))*255
    if clean_wide:
        _,labels,stats,_=cv2.connectedComponentsWithStats(mask)
        keep=[i for i,(_,_,cw,ch,area) in enumerate(stats[1:],1)
              if area>=8 and cw>=2 and ch>=max(6,region.shape[0]*.25)]
        mask=np.uint8(np.isin(labels,keep))*255
    ys,xs=np.where(mask)
    if not len(xs):return {'rank':None,'status':'NATIVE_INK_MISSING'}
    bx,by,bw,bh=int(xs.min()),int(ys.min()),int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)
    if bw<3 or bh<6 or (mask>0).mean()>.65:
        return {'rank':None,'status':'NATIVE_INK_INSUFFICIENT'}
    clean=255-mask[by:by+bh,bx:bx+bw]
    clean=cv2.resize(clean,None,fx=12 if clean_wide else 8,fy=8,interpolation=cv2.INTER_NEAREST)
    clean=cv2.copyMakeBorder(clean,40,40,40,40,cv2.BORDER_CONSTANT,value=255)
    try:
        readings=[image_to_string(clean,config=f'--psm {mode} -c tessedit_char_whitelist=AKQJT1098765432',timeout=3).strip() for mode in (7,10)]
    except Exception as exc:return {'rank':None,'status':'OCR_ERROR','error':str(exc)}
    value=readings[0] if readings[0]==readings[1] and readings[0] in list('AKQJT98765432')+['10'] else None
    return {'rank':'T' if value=='10' else value,'status':'CANDIDATE_ONLY' if value else 'NATIVE_OCR_UNREADABLE_OR_CONFLICT',
            'readings':readings,'clean_wide':clean_wide,'native_ink_box':[x1+bx,y1+by,bw,bh]}


def read_bright_rank(crop):
    """Lê um rank CLARO sobre um tile ESCURO de baixo contraste (ex.: o '8' cinza
    em carta de espada no skin Karekas), que o OCR por OTSU/segmentação do
    read_rank perde. Usa um threshold alto relativo ao brilho (isola o glifo) e
    exige que >=2 thresholds concordem no MESMO dígito (discordância = abstém).

    Só é chamado quando o leitor primário E o fallback nativo já abstiveram, então
    não altera nada nos skins já validados (lá o primário resolve)."""
    if crop is None or getattr(crop, 'size', 0) == 0:
        return None
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mx = int(g.max())
    if mx < 80:                                   # sem nada claro o bastante
        return None
    up = cv2.resize(g, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    votes = {}
    for frac in (0.84, 0.88, 0.92):
        _, b = cv2.threshold(up, int(frac * mx), 255, cv2.THRESH_BINARY)
        if not (0.03 <= (b > 0).mean() <= 0.30):  # fora da faixa de 1 glifo
            continue
        for psm in (10, 8):
            try:
                t = image_to_string(b, config='--psm %d -c tessedit_char_whitelist=AKQJT1098765432' % psm, timeout=3).strip()
            except Exception:                     # noqa: BLE001
                return None
            if t in list('AKQJT98765432') + ['10']:
                key = 'T' if t == '10' else t
                votes[key] = votes.get(key, 0) + 1
                break
    if not votes:
        return None
    best = max(votes, key=votes.get)
    return best if votes[best] >= 2 else None     # >=2 thresholds concordam


def inspect(image, box):
    if image is None:
        raise ValueError('Imagem não pôde ser aberta')
    x,y,w,h = box
    if min(x,y) < 0 or min(w,h) <= 0 or x+w > image.shape[1] or y+h > image.shape[0]:
        raise ValueError('Recorte fora da imagem')
    if not .45 <= w/h <= .65:
        raise ValueError('Selecione uma mesa vertical inteira, não o desktop')
    native_table=image[y:y+h,x:x+w]
    table = cv2.resize(native_table, (720,1280))
    alignment=locate_card_pair(table)
    if alignment['status']!='LOCALIZED':
        return {'status':'LAB_ONLY_NOT_CALIBRATED','table_box':list(box),'alignment':alignment,
                'hero_rank_candidates':[{'rank':None,'suit':None,'card_candidate':None,'status':alignment['status']} for _ in range(2)]}
    dy=alignment['vertical_offset']
    results = []
    for left in (402,447):
        rank = read_rank(table[1010+dy:1070+dy,left:left+42])
        if rank['status']=='OCR_UNREADABLE':
            native=read_native_white_rank(native_table,left,dy)
            rank['native_fallback']=native
            if native['rank'] is not None:
                rank['rank']=native['rank'];rank['status']='CANDIDATE_ONLY'
        # Dígito claro em tile escuro (ex. Karekas): só quando ainda ilegível.
        if rank.get('rank') is None and rank.get('status')=='OCR_UNREADABLE':
            bright=read_bright_rank(table[1010+dy:1070+dy,left:left+42])
            if bright is not None:
                rank['rank']=bright;rank['status']='CANDIDATE_ONLY';rank['bright_fallback']=bright
        rank['suit_result'] = read_suit(table[1055+dy:1105+dy,left-2:left+43])
        if rank['suit_result']['status']=='SUIT_UNREADABLE':
            nh,nw=native_table.shape[:2]
            native_suit=native_table[round((1055+dy)*nh/1280):round((1105+dy)*nh/1280),
                                    round((left-2)*nw/720):round((left+43)*nw/720)]
            native_result=read_suit(native_suit)
            rank['native_suit_result']=native_result
            if native_result['suit'] is not None:
                rank['suit_result']={**native_result,'source':'NATIVE_PIXELS'}
        rank['suit'] = rank['suit_result']['suit']
        rank['card_candidate'] = rank['rank'] + rank['suit'] if rank['rank'] and rank['suit'] else None
        rank['roi_canonical'] = [left,1010+dy,42,60]
        results.append(rank)
    return {'status':'LAB_ONLY_NOT_CALIBRATED', 'table_box':list(box), 'alignment':alignment,'hero_rank_candidates':results}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--box', nargs=4, type=int, required=True, metavar=('X','Y','W','H'))
    parser.add_argument('--output', default='card_diagnostic.json')
    args = parser.parse_args()
    report = inspect(cv2.imread(args.image), args.box)
    Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
