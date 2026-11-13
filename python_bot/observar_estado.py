"""Observador de estado AO VIVO (Camadas A+B), SEM cliques.

Amostra N frames da janela PPPoker, roda os leitores + advisor + StateObserver e
registra a StateView por frame (render no stdout + JSONL), salvando o crop de
cada mesa. Serve para validar a reconciliação INTRA-MÃO (street/commit/gap)
contra o ground truth do usuário. NÃO clica, não envia input.

Uso:
  python observar_estado.py --hwnd 0x... --frames 30 --intervalo 2.0 --save-crops
"""
import argparse
import json
import os
import time

import cv2

from table_reading.pipeline import configure_ocr
from table_reading.automatic_table_crops import detect_table_crops
from table_advisor import advise_table
from preflop_advisor import PreflopAdvisor
from preflop_context import PreflopAggressorTracker
from reader_cache import ReaderCache
from state_observer import StateObserver, render
from action_coordinator import plan_action, describe_plan
from window_capture_engine import WindowCaptureEngine

DEFAULT_RANGES = r'C:\Meus Projetos\Aplicativos\nvt-ranges-validados.json'
DEFAULT_DEEP = r'C:\Meus Projetos\Aplicativos\nvt-ranges-deep.json'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--hwnd', type=lambda s: int(s, 0), required=True)
    p.add_argument('--ranges', default=DEFAULT_RANGES)
    p.add_argument('--deep', default=None, help='Pacote deep 40/100bb (reference)')
    p.add_argument('--frames', type=int, default=30)
    p.add_argument('--intervalo', type=float, default=2.0)
    p.add_argument('--max-tables', type=int, default=6)
    p.add_argument('--bounty-bb', type=float, default=None,
                   help='PKO: valor do bounty em BB p/ o overlay de call-off')
    p.add_argument('--mode', choices=('chip_ev', 'icm', 'pko', 'pko_icm'), default=None,
                   help='Forca o modo do torneio (sobrepoe a deteccao por nome)')
    p.add_argument('--stage', choices=('pre_itm', 'bubble', 'ft', 'mid'), default=None,
                   help='Forca a fase do torneio')
    p.add_argument('--hud', action='store_true', help='Le o HUD VIP p/ exploit no pos-flop')
    p.add_argument('--out', default=None)
    p.add_argument('--save-crops', action='store_true')
    p.add_argument('--dry-run-actions', action='store_true',
                   help='Mostra a ACAO pretendida (botao+coord) por frame, SEM enviar')
    args = p.parse_args(argv)

    configure_ocr()
    deep = args.deep or (DEFAULT_DEEP if os.path.exists(DEFAULT_DEEP) else None)
    advisor = (PreflopAdvisor.from_files(args.ranges, deep) if deep
               else PreflopAdvisor.from_file(args.ranges))
    engine = WindowCaptureEngine()
    obs = StateObserver()
    aggr_tracker = PreflopAggressorTracker()   # agressor pré-flop p/ pós-flop em contexto
    read_cache = ReaderCache()                 # cache de HUD/bounty (latência)
    outdir = args.out or os.path.join('logs', 'estado',
                                      'sessao-' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(outdir, exist_ok=True)
    logpath = os.path.join(outdir, 'estado.jsonl')
    print('Observando %d frames (intervalo %.1fs). Saida: %s. SEM cliques.'
          % (args.frames, args.intervalo, outdir), flush=True)

    with open(logpath, 'w', encoding='utf-8') as log:
        for i in range(args.frames):
            t0 = time.monotonic()
            frame, meta = engine.capture_frame(hwnd=args.hwnd)
            if frame is None:
                print('[%02d] SEM LEITURA: %s' % (i, meta.get('status')), flush=True)
                time.sleep(max(0.1, args.intervalo - (time.monotonic() - t0)))
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            idx = 0
            for prop in detect_table_crops(rgb, max_tables=args.max_tables):
                x, y, w, h = map(int, prop.box)
                crop = frame[y:y + h, x:x + w]
                # Chave estável por mesa aceita; crops rejeitados (não-mesa) retornam
                # cedo no advise_table e NÃO tocam o tracker, então reusar o idx é seguro.
                key = '%s#%d' % (meta.get('source_key', args.hwnd), idx)
                try:
                    result = advise_table(crop, advisor, table_key=key, tracker=aggr_tracker,
                                          bounty_bb=args.bounty_bb, mode=args.mode, stage=args.stage,
                                          enable_hud=args.hud, read_cache=read_cache)
                except Exception:                      # noqa: BLE001
                    continue
                if not result.get('is_table'):
                    continue
                idx += 1
                view = obs.observe(result, table_key=key)
                print('[%02d] %s' % (i, render(view)), flush=True)
                if args.dry_run_actions:
                    plan = plan_action(crop, result.get('advice') or {}, origin=(x, y))
                    print('       ' + describe_plan(plan), flush=True)
                log.write(json.dumps(dict(
                    frame=i, key=key, hand=view['hand'], reconcile=view['reconcile'],
                    advice=view.get('advice'), changed=view['changed'],
                    pending=view['pending']), ensure_ascii=False) + '\n')
                if args.save_crops:
                    cv2.imwrite(os.path.join(
                        outdir, 'f%02d-%d.png' % (i, idx - 1)), crop)
            time.sleep(max(0.1, args.intervalo - (time.monotonic() - t0)))
    print('FIM. Log em', logpath, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
