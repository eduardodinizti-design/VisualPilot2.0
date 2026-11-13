"""Snapshot pipeline: detect complete blue tables then read each native crop."""
import hashlib
import os
from pathlib import Path
import shutil
import time
import uuid
import cv2
import numpy as np
from .automatic_table_crops import detect_table_crops
from .ocr_runtime import snapshot_ocr


def _tessdata_dir(tesseract_cmd):
    """Locate the tessdata directory holding eng.traineddata for the engine."""
    roots=[os.environ.get('TESSDATA_PREFIX'),
           str(Path(tesseract_cmd).resolve().parent/'tessdata')]
    for root in roots:
        if root and (Path(root)/'eng.traineddata').is_file():
            return root
        if root and (Path(root)/'tessdata'/'eng.traineddata').is_file():
            return str(Path(root)/'tessdata')
    return None


def _enable_inprocess_ocr(tesseract_cmd):
    """Turn on the in-process tesserocr backend if it and the traineddata exist.
    Pure speedup over the subprocess; silently stays on pytesseract otherwise."""
    try:
        import tesserocr  # noqa: F401
    except Exception:
        return 'subprocess'
    tessdata=_tessdata_dir(tesseract_cmd)
    if not tessdata:
        return 'subprocess'
    try:
        from .ocr_runtime import use_inprocess_ocr
        use_inprocess_ocr(tessdata)
        return 'inprocess'
    except Exception:
        return 'subprocess'


def configure_ocr():
    import pytesseract
    candidates=[os.environ.get('TESSERACT_CMD'),shutil.which('tesseract')]
    for root in (os.environ.get('ProgramFiles'),os.environ.get('LOCALAPPDATA')):
        if root:
            candidates.extend([str(Path(root)/'Tesseract-OCR/tesseract.exe'),
                               str(Path(root)/'Programs/Tesseract-OCR/tesseract.exe')])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd=candidate
            try:
                version=str(pytesseract.get_tesseract_version())
                if 'eng' in pytesseract.get_languages(config=''):
                    return {'status':'READY','version':version,'engine':_enable_inprocess_ocr(candidate)}
            except Exception:
                pass
    raise RuntimeError('TESSERACT_UNAVAILABLE: instale Tesseract com idioma English ou configure TESSERACT_CMD.')


@snapshot_ocr
def analyze_tables(frame_bgr, metadata, max_tables=6, *, _reader=None, read_buttons=False, read_community=False):
    if not isinstance(frame_bgr,np.ndarray) or frame_bgr.dtype!=np.uint8 or frame_bgr.ndim!=3 or frame_bgr.shape[2]!=3 or not frame_bgr.size:
        raise ValueError('Expected nonempty BGR uint8 frame')
    if not 1 <= max_tables <= 6:raise ValueError('Current limit is 1..6 tables per snapshot')
    if metadata.get('status')!='SUCCESS':raise ValueError('Capture must have SUCCESS status')
    if list(frame_bgr.shape)!=list(metadata.get('image_shape',[])):
        raise ValueError('Frame dimensions do not match capture metadata')
    if len(metadata.get('screen_origin',[]))!=2:raise ValueError('Capture origin is required')
    source={k:metadata.get(k) for k in ['hwnd','pid','process_created','executable']}
    if any(v is None for v in source.values()):raise ValueError('Capture identity is required')
    source_key=f"pid:{source['pid']}:created:{source['process_created']}:hwnd:{source['hwnd']}"
    snapshot=uuid.uuid4().hex
    started=time.monotonic()
    # Conversion only; do not resize the whole Unity surface.
    proposals=detect_table_crops(cv2.cvtColor(frame_bgr,cv2.COLOR_BGR2RGB),
                                blockers=metadata.get('blockers',()),max_tables=max_tables)
    detection_ms=(time.monotonic()-started)*1000
    ocr_started=time.monotonic()
    ocr={'status':'NOT_NEEDED'}
    if any(p.status=='COMPLETE_CANDIDATE' for p in proposals):
        try:
            if _reader is None:
                ocr=configure_ocr()
                from .inspect_cards import inspect
                _reader=lambda crop:inspect(crop,(0,0,crop.shape[1],crop.shape[0]))
            else:ocr={'status':'TEST_READER_INJECTED'}
        except Exception as exc:ocr={'status':'UNAVAILABLE','error':str(exc)}
    ocr_setup_ms=(time.monotonic()-ocr_started)*1000
    reading_ms=0.0
    button_ms=0.0
    card_attempts=button_attempts=board_attempts=0
    board_ms=0.0
    rows=[]
    for i,p in enumerate(proposals,1):
        x,y,w,h=map(int,p.box)
        row=dict(p.to_dict(),table_index=i,snapshot_table_id=f'{snapshot}:{i}',source_key=source_key,
                 local_box=[x,y,w,h],desktop_box=[metadata['screen_origin'][0]+x,metadata['screen_origin'][1]+y,w,h],
                 reading_status='NOT_READ',hero_cards=[None,None],actions_allowed=False)
        if p.status=='COMPLETE_CANDIDATE':
            crop=frame_bgr[y:y+h,x:x+w].copy()
            row['crop_sha256']=hashlib.sha256(crop.tobytes()).hexdigest()
            row['crop_shape']=list(crop.shape)
            if ocr['status']=='UNAVAILABLE':row['reading_status']='OCR_UNAVAILABLE'
            else:
                try:
                    card_attempts+=1
                    read_started=time.monotonic()
                    try:
                        reading=_reader(crop)
                    finally:
                        reading_ms+=(time.monotonic()-read_started)*1000
                    cards=[c.get('card_candidate') for c in reading.get('hero_rank_candidates',[])]
                    if len(cards)!=2:cards=[None,None]
                    if cards[0] and cards[0]==cards[1]:
                        row['reading_status']='DUPLICATE_CARD_REJECTED';cards=[None,None]
                    else:row['reading_status']='EXPERIMENTAL_CANDIDATES' if all(cards) else 'NOT_IDENTIFIED'
                    row.update(hero_cards=cards,reading=reading)
                except Exception as exc:row.update(reading_status='READING_ERROR',error=str(exc))
        if read_buttons and p.status=='COMPLETE_CANDIDATE':
            if ocr['status']=='UNAVAILABLE':
                row['action_buttons']={'status':'OCR_UNAVAILABLE','buttons':[],'actions_allowed':False}
            else:
                from .action_buttons import read_action_buttons
                button_attempts+=1
                button_started=time.monotonic()
                try: row['action_buttons']=read_action_buttons(crop)
                except Exception as exc:
                    row['action_buttons']={'status':'READING_ERROR','buttons':[],'error':str(exc),'actions_allowed':False}
                finally: button_ms+=(time.monotonic()-button_started)*1000
        if read_community and p.status=='COMPLETE_CANDIDATE':
            if ocr['status']=='UNAVAILABLE':row['board']={'status':'OCR_UNAVAILABLE','cards':[],'street':None}
            else:
                from .community_cards import read_board
                board_attempts+=1
                board_started=time.monotonic()
                try:row['board']=read_board(crop,hero_cards=row['hero_cards'])
                except Exception as exc:row['board']={'status':'BOARD_ERROR','cards':[],'street':None,'error':str(exc)}
                finally:board_ms+=(time.monotonic()-board_started)*1000
        rows.append(row)
    return dict(status='SNAPSHOT_ANALYZED',snapshot_id=snapshot,source=source,source_key=source_key,
                capture_timestamp=metadata.get('timestamp'),origin=metadata['screen_origin'],
                image_shape=list(frame_bgr.shape),max_tables=max_tables,ocr=ocr,tables=rows,
                complete_count=sum(r['status']=='COMPLETE_CANDIDATE' for r in rows),
                duration_ms=round((time.monotonic()-started)*1000,2),
                attempts=dict(card_reading=card_attempts,button_reading=button_attempts,board_reading=board_attempts),
                timings_ms=dict(detection=detection_ms,ocr_setup=ocr_setup_ms,card_reading=reading_ms,button_reading=button_ms,board_reading=board_ms),actions_allowed=False,
                persistent_tracking=False,scope='BLUE_LAYOUT_PASSIVE_READING_EXPERIMENTAL',
                enabled_readers=dict(hero=True,buttons=read_buttons,board=read_community))
