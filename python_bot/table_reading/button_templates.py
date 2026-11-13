"""Whole-label ink templates for validated static button labels only."""
from functools import lru_cache
from pathlib import Path
import hashlib,json
import cv2
import numpy as np

ASSETS=Path(__file__).with_name('button_template_assets')
# Approximate Call-with-amount matching is unsupported; exact raster path is separate below.
LABELS=('F/C','Check','Fold','Raise')
# Enabled only after source-disjoint whole-label validation.
ENABLED_LABELS=frozenset(('F/C','Check','Fold','Raise'))

def normalize(clean):
    if not isinstance(clean,np.ndarray) or clean.dtype!=np.uint8 or clean.ndim!=2 or not clean.size or clean.size>2_000_000:
        return None
    ink=np.uint8(clean<128)*255
    points=cv2.findNonZero(ink)
    if points is None:return None
    x,y,w,h=cv2.boundingRect(points)
    if h<8 or w<6:return None
    ratio=w/h
    if not .25<=ratio<=12:return None
    # Preserve all ink, including digits, currency and unrecognized suffixes.
    mask=cv2.resize(ink[y:y+h,x:x+w],(max(1,round(32*ratio)),32),interpolation=cv2.INTER_AREA)>127
    return mask,ratio

@lru_cache(maxsize=1)
def templates():
    result=[]
    try:
        rows=json.loads((ASSETS/'provenance.json').read_text())['templates']
        if {row['label'] for row in rows}!=set(LABELS):return ()
        for row in rows:
            filename=row['file']
            if Path(filename).name!=filename:return ()
            path=ASSETS/filename
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row['template_sha256']:return ()
            clean=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
            normalized=normalize(clean)
            if normalized is None:return ()
            result.append((row['label'],*normalized))
    except (OSError,ValueError,KeyError,TypeError):return ()
    return result

def read_static_label(clean):
    normalized=normalize(clean)
    if normalized is None:return None
    mask,ratio=normalized;by_label={}
    for label,template,aspect in templates():
        if abs(ratio/aspect-1)>.035:
            by_label.setdefault(label,0.);continue
        resized=cv2.resize(np.uint8(mask),(template.shape[1],32),interpolation=cv2.INTER_NEAREST)>0
        union=np.count_nonzero(resized|template)
        score=np.count_nonzero(resized&template)/union if union else 0.
        by_label[label]=max(score,by_label.get(label,0.))
    scores=sorted(((score,label) for label,score in by_label.items()),reverse=True)
    if not scores or scores[0][0]<.90 or scores[0][1] not in ENABLED_LABELS:return None
    margin=scores[0][0]-(scores[1][0] if len(scores)>1 else 0.)
    if margin<.12:return None
    return dict(label=scores[0][1],evidence='WHOLE_LABEL_TEMPLATE',template_iou=round(scores[0][0],4),template_margin=round(margin,4))


def exact_ink(clean):
    """Return all native raster ink without resampling, filtering or suffix removal."""
    if not isinstance(clean,np.ndarray) or clean.dtype!=np.uint8 or clean.ndim!=2 or not clean.size or clean.size>2_000_000:
        return None
    ink=np.uint8(clean<128)
    points=cv2.findNonZero(ink)
    if points is None:return None
    x,y,w,h=cv2.boundingRect(points)
    return ink[y:y+h,x:x+w]


@lru_cache(maxsize=1)
def exact_call_template():
    try:
        row=json.loads((ASSETS/'exact_call_provenance.json').read_text())
        if row['label']!='Call 1,0 BB' or row['native_ink_shape']!=[24,123] or row['clean_ink_shape']!=[72,369]:return None
        name=row['asset']
        if Path(name).name!=name:return None
        path=ASSETS/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['asset_sha256']:return None
        clean=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
        ink=exact_ink(clean)
        if ink is None or list(ink.shape)!=row['clean_ink_shape']:return None
        return ink
    except (OSError,ValueError,TypeError,KeyError):return None


def read_exact_call(clean):
    """Recognize only the validated complete 1.0-BB raster, never infer digits."""
    ink=exact_ink(clean);template=exact_call_template()
    if ink is None or template is None or ink.shape!=template.shape:return None
    if not np.array_equal(ink,template):return None
    return dict(label='Call 1,0 BB',evidence='EXACT_WHOLE_LABEL_RASTER')
