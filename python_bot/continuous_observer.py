"""Sequential, memory-only observation. No clicks, disk writes or history."""
import math
import time
from table_reading.pipeline import analyze_tables
from observation_metrics import ObservationMetrics, sample_resources
from table_reading.presentation import describe_regions


def observe(engine, hwnd, *, interval=2.0, max_age=10.0, max_tables=6,
            max_cycles=0, read_buttons=False, read_community=False, analyze=analyze_tables, emit=print,
            clock=time.monotonic, sleep=time.sleep):
    if not math.isfinite(interval) or interval < .25:
        raise ValueError('Intervalo minimo: 0.25 segundos')
    if not math.isfinite(max_age) or max_age <= 0 or max_cycles < 0:
        raise ValueError('Limites invalidos')
    metrics=ObservationMetrics()
    identity=None
    cycle=0
    emit('OBSERVADOR: somente RAM, sem cliques ou arquivos. Ctrl+C para encerrar.')
    try:
        while not max_cycles or cycle < max_cycles:
            cycle+=1
            started=clock();cpu_started=time.process_time()
            # Clear before capture: previous output is historical, never current.
            emit(f'Ciclo {cycle}: capturando; leitura anterior invalidada.')
            frame=None;report=None
            try:
                frame,metadata=engine.capture_frame(hwnd=hwnd)
                if frame is None:
                    metrics.failure(metadata.get('status','CAPTURE_FAILED'))
                    emit(f"SEM LEITURA: {metadata.get('status','CAPTURE_FAILED')}")
                else:
                    current=tuple(metadata.get(k) for k in ('hwnd','pid','process_created','executable'))
                    if any(v is None for v in current):
                        raise ValueError('Identidade da captura incompleta')
                    if identity is not None and current!=identity:
                        emit('SOURCE_CHANGED: processo mudou; observador encerrado. Selecione a janela novamente.')
                        return 2
                    identity=current
                    report=analyze(frame,metadata,max_tables=max_tables,**({'read_buttons':True} if read_buttons else {}),**({'read_community':True} if read_community else {}))
                    age=clock()-started
                    metrics.add(metadata,report,age*1000,sample_resources(cpu_started))
                    if cycle % 10 == 0:
                        emit("TEMPOS (ms; ultimos 120 ciclos analisados): "+str(metrics.summary()))
                    if cycle % 10 == 0:emit('DIAGNOSTICO: '+str(metrics.counts()))
                    if age > max_age:
                        emit(f'SEM LEITURA: RESULT_EXPIRED ({age:.1f}s)')
                    elif not report['tables']:
                        emit('SEM LEITURA: nenhuma mesa completa localizada.')
                    else:
                        for line in describe_regions(report):
                            emit(f'Ciclo {cycle} | {line} | idade {age:.1f}s')
                        if report.get('ocr',{}).get('status')=='UNAVAILABLE':
                            emit('OCR INDISPONIVEL: '+report['ocr'].get('error',''))
            except Exception as exc:
                metrics.failure('PROCESSING_ERROR')
                emit(f'SEM LEITURA: {type(exc).__name__}: {exc}')
            finally:
                # No queue, cache, report history or full-frame retention.
                frame=None;report=None
            if not max_cycles or cycle < max_cycles:
                sleep(max(.05,interval-(clock()-started)))
    except KeyboardInterrupt:
        emit('Observador encerrado. Nenhuma imagem salva.')
    emit("DIAGNOSTICO FINAL: "+str(metrics.counts()))
    emit("TEMPOS FINAIS (ms): "+str(metrics.summary()))
    memory=metrics.memory_mb()
    if memory:emit("MEMORIA (RSS MiB): "+str(memory))
    return 0
