"""Bounded passive session: native captures and reports, never gameplay input."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
import cv2
from table_reading.pipeline import analyze_tables
from observation_metrics import current_rss_mb
import stage_metrics


def identity(meta):
    return tuple(meta.get(k) for k in ('hwnd','pid','process_created','executable'))


def run_session(engine, hwnds, *, minutes=30, interval=2, budget_mb=16, samples=False,
                output=Path('logs/sessoes'), analyze=analyze_tables,
                clock=time.monotonic, sleep=time.sleep):
    if not 1<=minutes<=120 or not .25<=interval<=60 or not 1<=budget_mb<=64:
        raise ValueError('Duracao 1..120 min; intervalo .25..60 s; limite 1..64 MiB')
    hwnds=list(dict.fromkeys(hwnds))
    if not hwnds or len(hwnds)>6 or any(h<=0 for h in hwnds):raise ValueError('Selecione 1..6 HWNDs validos')
    folder=Path(output)/('sessao-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    start=clock();deadline=start+minutes*60;counts=Counter();known={};used=0;seq=0;stop='DURATION_COMPLETE';durations=[];stage_rows=[]
    limit=int(budget_mb*1024*1024);reserve=65536
    image_limit=limit//4 if samples else 0
    log_limit=limit-image_limit-reserve
    image_used=0;log_used=0;last_sample={}
    print('Pasta:',folder.resolve(),flush=True)
    print('COLETA V2: texto; imagens DESLIGADAS.' if not samples else 'COLETA V2: texto e recortes aceitos/rejeitados; nova condicao ou 60s, com cota.',flush=True)
    print('Sem cliques. Limite por sessao:',budget_mb,'MiB. Ctrl+C encerra.',flush=True)
    try:
        with (folder/'leituras.jsonl').open('wb') as log:
            while clock()<deadline:
                cycle=clock()
                for hwnd in hwnds:
                    if clock()>=deadline:break
                    seq+=1;t=clock();cpu0=time.process_time();frame=None;report=None
                    record=dict(sequence=seq,hwnd=hwnd,started_utc=datetime.now(timezone.utc).isoformat(),elapsed_s=round(t-start,3),actions_executed=False)
                    try:
                        frame,meta=engine.capture_frame(hwnd=hwnd);record['capture']=meta
                        if frame is None or meta.get('status')!='SUCCESS' or meta.get('hwnd')!=hwnd:
                            record['status']='CAPTURE_FAILED';counts['capture_failures']+=1
                        else:
                            ident=identity(meta)
                            if any(v is None for v in ident) or (hwnd in known and known[hwnd]!=ident):
                                record['status']='SOURCE_CHANGED';stop='SOURCE_CHANGED'
                            else:
                                known[hwnd]=ident
                                try:
                                    report=analyze(frame,meta,max_tables=6,read_buttons=True,read_community=True)
                                    record.update(status='ANALYZED',report=report)
                                    counts['analyzed_frames']+=1
                                    if report.get('ocr',{}).get('status')=='UNAVAILABLE':counts['ocr_unavailable']+=1
                                    for row in report.get('tables',[]):
                                        counts['table_regions']+=1
                                        if row.get('status')!='COMPLETE_CANDIDATE':counts['rejected_regions']+=1;continue
                                        counts['complete_table_observations']+=1
                                        counts['hero_complete' if all(row.get('hero_cards',[None,None])) else 'hero_incomplete']+=1
                                        counts['board_'+str(row.get('board',{}).get('status','NOT_READ'))]+=1
                                        counts['buttons_'+str(row.get('action_buttons',{}).get('status','NOT_READ'))]+=1
                                except Exception as exc:
                                    record.update(status='ANALYSIS_ERROR',error=repr(exc));counts['analysis_errors']+=1
                    except Exception as exc:
                        record.update(status='ERROR',error=repr(exc));counts['errors']+=1
                    ms=(clock()-t)*1000;durations.append(ms)
                    record['duration_ms']=round(ms,2)
                    record['cpu_ms']=round((time.process_time()-cpu0)*1000,2)
                    record['rss_mb']=current_rss_mb()
                    stage_rows.append(stage_metrics.row_from_record(record))
                    # Optional bounded native table samples; never encode the full surface.
                    if samples and frame is not None and report is not None and image_used<image_limit:
                        record['samples']=[]
                        for row in report.get('tables',[])[:6]:
                            sample_key=(hwnd,row['table_index'],row.get('status'))
                            if clock()-last_sample.get(sample_key,-1e9)<60:continue
                            last_sample[sample_key]=clock()
                            x,y,w,h=map(int,row['local_box'])
                            if min(x,y)<0 or min(w,h)<=0 or x+w>frame.shape[1] or y+h>frame.shape[0]:continue
                            ok,encoded=cv2.imencode('.png',frame[y:y+h,x:x+w],[cv2.IMWRITE_PNG_COMPRESSION,3])
                            if not ok:continue
                            data=encoded.tobytes()
                            if image_used+len(data)>image_limit:counts['sample_budget_skips']+=1;continue
                            name=f"sample-{seq:06d}-mesa-{row['table_index']}.png"
                            (folder/name).write_bytes(data);image_used+=len(data);used+=len(data)
                            record['samples'].append(dict(file=name,local_box=[x,y,w,h],region_status=row.get('status'),reasons=row.get('reasons',[]),sequence=seq))
                            counts['saved_samples']+=1
                            counts['saved_accepted_samples' if row.get('status')=='COMPLETE_CANDIDATE' else 'saved_rejected_samples']+=1
                    payload=(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
                    if log_used+len(payload)<=log_limit:
                        log.write(payload);log.flush();log_used+=len(payload);used+=len(payload);counts['saved_records']+=1
                    else:
                        counts['records_omitted_at_budget']+=1
                        if counts['records_omitted_at_budget']==1:print('Cota de texto atingida: leitura continua; registros adicionais nao serao salvos.',flush=True)
                    print(f"{seq}: HWND {hwnd} | {record['status']} | {ms:.0f} ms | {used/1024/1024:.1f} MiB",flush=True)
                    if 'report' in record:
                        from table_reading.presentation import describe_regions
                        for line in describe_regions(record['report']):print(line,flush=True)
                    if stop=='SOURCE_CHANGED':break
                if stop!='DURATION_COMPLETE':break
                sleep(min(max(0,interval-(clock()-cycle)),max(0,deadline-clock())))
    except KeyboardInterrupt:stop='USER_STOP'
    except Exception as exc:stop='IO_OR_SESSION_ERROR';counts['session_errors']+=1;print(repr(exc))
    finally:
        values=sorted(durations)
        summary=dict(stop_reason=stop,elapsed_s=round(clock()-start,2),requested_minutes=minutes,
                     hwnds=hwnds,interval_s=interval,budget_mib=budget_mb,bytes_written_before_summary=used,
                     format_version=2,images_enabled=samples,image_bytes=image_used,log_bytes=log_used,
                     image_budget_bytes=image_limit,log_budget_bytes=log_limit,
                     counts=dict(counts),capture_and_read_ms=dict(n=len(values),median=values[len(values)//2] if values else None,
                     p95=values[min(len(values)-1,int(len(values)*.95))] if values else None),
                     stage_profile=stage_metrics.summarize(stage_rows),
                     accuracy_validated=False,actions_executed=False,
                     limitations=['Periodic samples, not video: events between captures can be missed.',
                     'Displayed buttons do not prove which action the user took.',
                     'No persistent table identity across moves; source HWND plus per-frame boxes only.',
                     'Pots, stacks and full action history are not decoded by this reader.',
                     'No full-frame images saved. Optional table samples only; quotas can omit evidence, counted explicitly.'])
        (folder/'resumo.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
        print('Encerrado:',stop,'| Resultado:',folder.resolve(),flush=True)
    return folder,summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hwnds',nargs='+',type=lambda s:int(s,0))
    p.add_argument('--minutos',type=float,default=30)
    p.add_argument('--intervalo',type=float,default=2)
    p.add_argument('--limite-mb',type=int,default=16)
    p.add_argument('--amostras',action='store_true',help='Recortes aceitos/rejeitados por estado a cada 60s; cota de 25%% do limite')
    p.add_argument('--pppoker',action='store_true',help='Descobre as mesas PPPoker abertas (pula lobby/login) e observa automaticamente')
    args=p.parse_args()
    from window_capture_engine import WindowCaptureEngine
    engine=WindowCaptureEngine()
    if args.pppoker and not args.hwnds:
        from table_discovery.pppoker import discover_pppoker
        found=discover_pppoker()['windows']
        for w in found:print('PPPoker | HWND',w['hwnd'],'| PID',w['pid'],'|',f"{w['w']}x{w['h']}",'em',f"({w['x']},{w['y']})",'|',w['title'],flush=True)
        if not found:raise SystemExit('Nenhuma janela PPPoker aberta. Abra o PPPoker (lobby ou mesa) e tente de novo.')
        args.hwnds=[w['hwnd'] for w in found[:6]]
        print('Observando',len(args.hwnds),'janela(s). A mesa (feltro azul) e o lobby sao separados na leitura.',flush=True)
    if not args.hwnds:
        windows=engine.locate_target_windows()
        for w in windows:print('HWND:',w['hwnd'],'PID:',w['pid'],'Titulo:',w.get('title'),'Area:',w['client_rect'])
        if not windows:raise SystemExit('Nenhuma janela disponivel. Abra PPPoker e tente novamente.')
        args.hwnds=[int(v,0) for v in input('Digite HWND(s) separados por espacos: ').split()]
        if not set(args.hwnds)<=set(w['hwnd'] for w in windows):raise SystemExit('HWND nao listado')
    from table_reading.pipeline import configure_ocr
    configure_ocr()
    _,summary=run_session(engine,args.hwnds,minutes=args.minutos,interval=args.intervalo,budget_mb=args.limite_mb,samples=args.amostras)
    return 0 if summary['stop_reason'] in ('DURATION_COMPLETE','USER_STOP') else 1

if __name__=='__main__':raise SystemExit(main())
