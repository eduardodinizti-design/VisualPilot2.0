"""Coleta unica de recortes nativos UNLABELED; sem OCR, cliques ou treino."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid
import cv2
import numpy as np
from diagnostic_storage import store_bundle
from table_reading.automatic_table_crops import detect_table_crops
from table_reading.roi_geometry import get_roi

MAX_BUNDLE_BYTES=2*1024*1024

def collect_samples(frame,metadata,*,logs_root=Path('logs'),max_tables=6,provenance=None):
    if not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3 or not frame.size:
        raise ValueError('Expected nonempty BGR uint8 frame')
    if not isinstance(metadata,dict) or metadata.get('status')!='SUCCESS' or metadata.get('capture_success') is False:
        raise ValueError('Capture must have SUCCESS status')
    if metadata.get('image_shape')!=list(frame.shape):raise ValueError('Frame dimensions do not match metadata')
    origin=metadata.get('screen_origin')
    if not isinstance(origin,(list,tuple)) or len(origin)!=2 or any(type(v)is not int for v in origin):raise ValueError('Invalid screen origin')
    source={k:metadata.get(k)for k in ('hwnd','pid','process_created','executable')}
    if any(type(source[k])is not int or source[k]<=0 for k in ('hwnd','pid')):raise ValueError('Invalid HWND/PID identity')
    if not isinstance(source['process_created'],(int,float)) or not np.isfinite(source['process_created']) or source['process_created']<0:raise ValueError('Invalid process creation identity')
    if not isinstance(source['executable'],str) or not source['executable'].strip():raise ValueError('Missing executable identity')
    if type(max_tables)is not int or not 1<=max_tables<=6:raise ValueError('Max tables must be 1..6')
    digest=hashlib.sha256(frame.tobytes()).hexdigest()
    if metadata.get('frame_sha256') and metadata['frame_sha256']!=digest:raise ValueError('Frame hash does not match metadata')
    proposals=detect_table_crops(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),blockers=metadata.get('blockers',()),max_tables=max_tables)
    complete=[p for p in proposals if p.status=='COMPLETE_CANDIDATE']
    if not complete:raise ValueError('Nenhuma mesa completa; nenhuma amostra salva')
    if len(complete)>max_tables:raise ValueError('Table limit exceeded')
    snapshot=uuid.uuid4().hex;relative=Path('leitura')/('leitura-'+snapshot)
    report=dict(status='UNLABELED',purpose='HUMAN_LABEL_REVIEW',labels=None,schema='native-sample-bundle-v1',snapshot_id=snapshot,actions_allowed=False,ocr_used=False,training_imported=False,
                source=source,source_key=f"pid:{source['pid']}:created:{source['process_created']}:hwnd:{source['hwnd']}",
                capture_timestamp=metadata.get('timestamp'),frame_sha256=digest,image_shape=list(frame.shape),screen_origin=list(origin),provenance=provenance or {'kind':'CALLER_SUPPLIED'},
                rejected_regions=[p.to_dict()for p in proposals if p.status!='COMPLETE_CANDIDATE'],tables=[])
    files={};total=0
    for index,p in enumerate(complete,1):
        x,y,w,h=map(int,p.box)
        if x<0 or y<0 or w<=0 or h<=0 or x+w>frame.shape[1] or y+h>frame.shape[0]:raise ValueError('Invalid detected table bounds')
        band=get_roi(w,h)
        regions={'hero':(round(w*.51),round(h*.75),round(w*.80),round(h*.93)),
                 'board':(band.left,band.top,band.right,band.bottom),'buttons':(0,round(h*.92),w,h)}
        row=dict(table_index=index,status='UNLABELED',detector_status=p.status,table_box=[x,y,w,h],regions=[])
        for name,(left,top,right,bottom) in regions.items():
            if not(0<=left<right<=w and 0<=top<bottom<=h):raise ValueError('Invalid region bounds')
            crop=frame[y+top:y+bottom,x+left:x+right]
            ok,encoded=cv2.imencode('.png',crop)
            if not ok:raise RuntimeError('PNG encoding failed')
            data=encoded.tobytes();total+=len(data)
            if total>MAX_BUNDLE_BYTES:raise RuntimeError('Amostras excedem 2 MiB; nada salvo')
            filename=f'mesa-{index:02d}-{name}.png';files[str(relative/filename)]=data
            row['regions'].append(dict(region=name,status='UNLABELED',labels=None,file=filename,local_bounds=[left,top,right,bottom],frame_box=[x+left,y+top,right-left,bottom-top],
                                       image_shape=list(crop.shape),png_sha256=hashlib.sha256(data).hexdigest(),pixel_sha256=hashlib.sha256(crop.tobytes()).hexdigest(),resized=False))
        report['tables'].append(row)
    payload=json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    if total+len(payload)>MAX_BUNDLE_BYTES:raise RuntimeError('Amostras excedem 2 MiB; nada salvo')
    files[str(relative/'resultado.json')]=payload
    store_bundle(logs_root,files)
    return Path(logs_root)/relative,report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--hwnd',type=lambda s:int(s,0));group.add_argument('--image',type=Path)
    p.add_argument('--logs-root',type=Path,default=Path('logs'));p.add_argument('--metadata',type=Path);p.add_argument('--max-tables',type=int,choices=range(1,7),default=6)
    args=p.parse_args(argv)
    if bool(args.image)!=bool(args.metadata):p.error('--image exige --metadata; --hwnd nao aceita --metadata')
    try:
        if args.hwnd is not None:
            from window_capture_engine import WindowCaptureEngine
            frame,metadata=WindowCaptureEngine().capture_frame(hwnd=args.hwnd)
            if frame is None:raise RuntimeError('Captura estrita falhou: '+str(metadata))
            if metadata.get('hwnd')!=args.hwnd:raise ValueError('Returned HWND differs from requested HWND')
            provenance=dict(kind='LIVE_STRICT_WINDOW_CAPTURE',requested_hwnd=args.hwnd)
        else:
            data=args.image.read_bytes();frame=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            metadata=json.loads(args.metadata.read_text(encoding='utf-8-sig'))
            provenance=dict(kind='OFFLINE_IMAGE_WITH_SUPPLIED_METADATA',image_name=args.image.name,image_file_sha256=hashlib.sha256(data).hexdigest(),metadata_name=args.metadata.name)
        path,report=collect_samples(frame,metadata,logs_root=args.logs_root,max_tables=args.max_tables,provenance=provenance)
        print(f"Amostras UNLABELED: {path} | {len(report['tables'])} mesa(s). Sem OCR ou importacao para treino.")
        return 0
    except Exception as exc:
        print('FALHA:',exc);return 1

if __name__=='__main__':raise SystemExit(main())
