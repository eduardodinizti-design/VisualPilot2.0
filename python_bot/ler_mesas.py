"""Read-only table crop diagnostic. Default: analyze latest successful saved capture."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from table_reading.pipeline import analyze_tables
from table_reading.presentation import describe_regions


def latest_capture(directory):
    for path in sorted(directory.glob('capture-*.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:
            metadata=json.loads(path.read_text(encoding='utf-8-sig'))
            if metadata.get('status')!='SUCCESS' or not metadata.get('capture_success'):continue
            image=Path(str(metadata.get('image_path','')).replace('\\','/'))
            if not image.is_file():image=path.with_suffix('.png')
            if image.is_file():return image,metadata
        except (ValueError,OSError):continue
    raise RuntimeError('Nenhuma captura SUCCESS com PNG em logs/diagnostics. Execute windows_capture_diagnostics.py primeiro.')


def save_result(frame, report, directory, budget=100*1024*1024):
    files={}
    overlay=frame.copy()
    for row in report['tables']:
        x,y,w,h=row['local_box']
        valid=row['status']=='COMPLETE_CANDIDATE'
        cv2.rectangle(overlay,(x,y),(x+w-1,y+h-1),(0,200,0) if valid else (0,180,255),2)
        cv2.putText(overlay,f"Mesa {row['table_index']}: {row['status']}",(x,max(18,y-8)),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
        if valid:
            ok,data=cv2.imencode('.png',frame[y:y+h,x:x+w])
            if not ok:raise RuntimeError('Erro ao salvar recorte')
            name=f"mesa-{row['table_index']:02d}.png";files[name]=data.tobytes();row['crop_file']=name
    ok,data=cv2.imencode('.png',overlay)
    if not ok:raise RuntimeError('Erro ao salvar imagem anotada')
    files['mesas-anotadas.png']=data.tobytes()
    report['frame_sha256']=hashlib.sha256(frame.tobytes()).hexdigest()
    files['resultado.json']=json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    from diagnostic_storage import store_bundle
    target=directory/('leitura-'+report['snapshot_id'])
    # Both standard diagnostic producers share the parent logs budget.
    root=directory.parent
    store_bundle(root,{str(Path(directory.name)/target.name/name):data for name,data in files.items()},budget)
    return target


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path)
    parser.add_argument('--metadata',type=Path)
    parser.add_argument('--hwnd',type=lambda s:int(s,0),help='Optional live capture of an explicitly selected HWND')
    parser.add_argument('--diagnostics-dir',type=Path,default=Path('logs/diagnostics'))
    parser.add_argument('--output-dir',type=Path,default=Path('logs/leitura'))
    parser.add_argument('--max-tables',type=int,choices=range(1,7),default=6)
    parser.add_argument('--save',action='store_true',help='Salvar evidencia; captura ao vivo fica em RAM por padrao')
    parser.add_argument('--continuo',action='store_true',help='Observador continuo em memoria')
    parser.add_argument('--intervalo',type=float,default=2.0,help='Intervalo minimo entre inicios de captura em segundos')
    parser.add_argument('--botoes',action='store_true',help='Ler rotulos dos botoes experimentalmente, sem cliques')
    parser.add_argument('--board',action='store_true',help='Leitura experimental das cartas comunitarias')
    args=parser.parse_args(argv)
    if args.continuo and (args.hwnd is None or args.image or args.metadata or args.save):
        parser.error('--continuo exige --hwnd e nao aceita --image, --metadata ou --save')
    if args.hwnd is not None and (args.image or args.metadata):parser.error('Use --hwnd OU --image/--metadata')
    if bool(args.image)!=bool(args.metadata):parser.error('--image exige --metadata e vice-versa')
    try:
        if args.continuo:
            from continuous_observer import observe
            from window_capture_engine import WindowCaptureEngine
            return observe(WindowCaptureEngine(),args.hwnd,interval=args.intervalo,max_tables=args.max_tables,read_buttons=args.botoes,read_community=args.board)
        if args.hwnd is not None:
            from window_capture_engine import WindowCaptureEngine
            frame,metadata=WindowCaptureEngine().capture_frame(hwnd=args.hwnd)
            if frame is None:raise RuntimeError(json.dumps(metadata,ensure_ascii=False))
        else:
            if args.image:
                image=args.image;metadata=json.loads(args.metadata.read_text(encoding='utf-8-sig'))
            else:image,metadata=latest_capture(args.diagnostics_dir)
            print('Captura existente:',image)
            frame=cv2.imdecode(np.frombuffer(image.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        report=analyze_tables(frame,metadata,max_tables=args.max_tables,read_buttons=args.botoes,read_community=args.board)
        target=save_result(frame,report,args.output_dir) if args.hwnd is None or args.save else None
        print('Fonte:',report['source_key'])
        for line in describe_regions(report): print(line)
        if report['ocr']['status']=='UNAVAILABLE':print('OCR:',report['ocr']['error'])
        print('Resultado salvo em:',target) if target else print('Processado em memoria; nenhuma imagem salva. Use --save para diagnostico.')
        print('Leitura experimental de captura unica; sem cliques, sem rastreamento continuo.')
        return 0
    except Exception as exc:
        print('FALHA:',exc)
        return 1

if __name__=='__main__':raise SystemExit(main())
