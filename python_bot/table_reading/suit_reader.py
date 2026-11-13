"""Experimental shape-only suit recognition. RGB colour is never a default suit."""
from pathlib import Path
import cv2
import numpy as np


class TemplateError(RuntimeError):
    pass


def load_templates(directory=None):
    directory=Path(directory) if directory is not None else Path(__file__).with_name('suit_templates')
    result={}
    for suit in 'shdc':
        path=directory/(suit+'.png')
        try:
            encoded=path.read_bytes()
        except OSError as exc:
            raise TemplateError(f'Arquivo de naipe ausente ou inacessivel: {path}. Extraia o ZIP completo.') from exc
        image=cv2.imdecode(np.frombuffer(encoded,dtype=np.uint8),cv2.IMREAD_GRAYSCALE) if encoded else None
        if image is None or image.size==0:
            raise TemplateError(f'Imagem de naipe invalida: {path}. Extraia novamente o pacote.')
        result[suit]=normalize(image)
    return result


def normalize(mask):
    if not isinstance(mask,np.ndarray) or mask.ndim != 2 or not mask.size:
        raise TemplateError("Mascara de naipe invalida")
    ys,xs=np.where(mask>0)
    if not len(xs):return np.zeros((40,40),np.uint8)
    mask=mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
    h,w=mask.shape;scale=34/max(h,w)
    m=cv2.resize(mask,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA)>127
    out=np.zeros((40,40),bool);y=(40-m.shape[0])//2;x=(40-m.shape[1])//2
    out[y:y+m.shape[0],x:x+m.shape[1]]=m
    return out


def pointed_spade_geometry(mask):
    """Independent contour evidence: pointed crown, broad lower body, narrow stem.

    Clubs have a rounded crown/neck; diamonds narrow again below their middle.
    This is only supporting evidence, never a stand-alone suit classifier.
    """
    ys,xs=np.where(mask>0)
    if not len(xs):return False
    m=mask[ys.min():ys.max()+1,xs.min():xs.max()+1]>0
    h,w=m.shape
    if h<10 or w<8:return False
    widths=m.sum(axis=1)/w
    crown=widths[:max(2,round(h*.15))].mean()
    body=widths[round(h*.60):round(h*.80)].mean()
    stem=widths[round(h*.88):].mean()
    upper=widths[:round(h*.65)]
    # Permit one pixel of antialiasing noise, but reject a club's crown/neck valley.
    monotonic=bool(np.all(np.diff(upper)>=-1/w))
    growth=widths[round(h*.40)]-widths[round(h*.15)]
    # At low resolution, antialiasing widens the first three rows of a
    # pointed tip. Require a narrow first row plus sustained widening instead.
    upper_end=max(4,round(h*.55))
    ramp=all(widths[i+3]-widths[i]>=.12 for i in range(upper_end-3))
    narrow_tip = crown<=.24 or (widths[0]<=.20 and widths[round(h*.15)]<=.50 and ramp)
    return bool(narrow_tip and body>=.78 and stem<=.48 and growth>=.22 and monotonic)


def read_suit(crop):
    if not isinstance(crop,np.ndarray) or crop.ndim!=3 or crop.shape[2]!=3 or not crop.size:
        return {'suit':None,'status':'INVALID_SUIT_CROP'}
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    # Dark/coloured ink on a white card, or white ink on a coloured card.
    masks=[np.uint8((hsv[:,:,2]<150)|((hsv[:,:,1]>100)&(hsv[:,:,2]<245)))*255,
           np.uint8((hsv[:,:,1]<65)&(hsv[:,:,2]>180))*255,
           # Four-colour decks print a vividly saturated pip (red hearts, blue
           # diamonds, green clubs) on a light card. The dark-ink mask above can
           # merge that pip with a neighbouring shadow or gap into one blob and
           # lose its shape; a saturation-only mask isolates the pip cleanly.
           # Black spades keep low saturation, so they stay on the masks above.
           # Shape validation, thresholds and conflict rejection are unchanged,
           # so a disagreeing mask still abstains (SUIT_AMBIGUOUS) rather than guess.
           np.uint8((hsv[:,:,1]>90)&(hsv[:,:,2]>60))*255]
    # Dimmed cards retain neutral glyphs on coloured/darker backgrounds.
    # Estimate the split only among neutral pixels; keep shape validation and
    # conflict rejection unchanged. This reads appearance, not active-hand state.
    neutral=hsv[:,:,1]<65
    values=hsv[:,:,2][neutral]
    if values.size>=25:
        threshold,_=cv2.threshold(values,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        # If almost all neutral pixels belong to the glyph, Otsu can split
        # inside its antialiasing instead of between glyph and background.
        # Cap the split below the neutral highlight, retaining contour edges.
        threshold=max(60,min(threshold,.8*float(np.percentile(values,90))))
        masks.append(np.uint8(neutral & (hsv[:,:,2]>threshold))*255)
    templates=load_templates()
    candidates=[]
    for mask in masks:
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask)
        for i,(x,y,w,h,area) in enumerate(stats[1:],1):
            if area<25 or h<10 or w<8 or x==0 or y==0 or x+w>=crop.shape[1] or y+h>=crop.shape[0]:continue
            a=normalize(np.uint8(labels==i)*255)
            scores=sorted(((float(np.logical_and(a,t).sum()/max(1,np.logical_or(a,t).sum())),s) for s,t in templates.items()),reverse=True)
            score,suit=scores[0];margin=score-scores[1][0]
            evidence = 'template_margin'
            by_suit={s:v for v,s in scores}
            pointed=pointed_spade_geometry(labels==i)
            component=(labels==i)[y:y+h,x:x+w]
            profile=component.sum(axis=1)/w
            crown=profile[:max(2,round(h*.15))].mean()
            plateau=profile[round(h*.15):max(round(h*.15)+2,round(h*.35))]
            rounded=bool(crown>=.25 and np.ptp(plateau)<=.16)
            # Low-resolution clubs retain a narrow upper lobe plateau followed
            # by wider side lobes. Spades instead widen continuously.
            club_lobes=bool(len(plateau)>=3 and np.ptp(plateau)<=.08
                            and .30<=plateau.mean()<=.60
                            and profile[round(h*.50)]>=.85
                            and profile[round(h*.88):].mean()<=.35)

            if {scores[0][1],scores[1][1]} == {'s','c'}:
                # The font comparison alone confuses these suits under resampling.
                if by_suit['s']>=.68 and pointed:
                    candidates.append((by_suit['s'],'s',margin,'template_and_pointed_contour'))
                elif suit=='c' and ((score>=.68 and margin>=.07 and rounded) or (score>=.74 and margin>=.04 and club_lobes)):
                    candidates.append((score,suit,margin,'template_and_rounded_crown' if score>=.68 and margin>=.07 and rounded else 'template_and_three_lobe_profile'))
            elif score>=.68 and margin>=.07:
                candidates.append((score,suit,margin,evidence))
    suits={c[1] for c in candidates}
    if len(suits)!=1:return {'suit':None,'status':'SUIT_AMBIGUOUS' if suits else 'SUIT_UNREADABLE'}
    score,suit,margin,evidence=max(candidates)
    return {'suit':suit,'status':'CANDIDATE_ONLY','shape_iou':round(score,3),'margin':round(margin,3),'evidence':evidence}
