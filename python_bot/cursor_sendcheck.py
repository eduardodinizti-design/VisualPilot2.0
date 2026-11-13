"""Validação do ENVIO real do adaptador SendInput (Fase 3B, bloco 2).

Move o cursor para coordenadas conhecidas via SendInput, confere a posição
OBSERVADA (coord enviada × observada, §7 da spec) e RESTAURA a posição original.
NÃO clica, não aponta para app nenhum — só valida a precisão do movimento/
normalização no desktop virtual real. Movimentos pequenos ao redor da posição
atual + um ao centro do desktop, para ser pouco intrusivo.
"""
import argparse
import math
import sys
import time

from cursor_input_win import WindowsCursorInput


def default_targets(origin, bounds):
    ox, oy = origin
    bx, by, bw, bh = bounds
    center = (bx + bw // 2, by + bh // 2)
    return [(ox + 120, oy), (ox, oy + 120), (ox - 120, oy - 120), center]


def send_check(targets=None, *, settle_s=0.06, restore=True, adapter=None,
               sleep=time.sleep):
    """Move para cada alvo, mede erro (observado − enviado) e restaura. Retorna
    um relatório. Puro quanto à lógica; o I/O é do adaptador (injetável)."""
    inp = adapter or WindowsCursorInput()
    bounds = inp.virtual_bounds()
    origin = inp.cursor_pos()
    pts = targets or default_targets(origin, bounds)
    results = []
    for (tx, ty) in pts:
        r = inp.move_to(tx, ty, bounds)
        sleep(settle_s)
        obs = inp.cursor_pos()
        results.append(dict(target=(tx, ty), observed=obs,
                            error_px=math.hypot(obs[0] - tx, obs[1] - ty),
                            accepted=r['accepted'], norm=r['norm']))
    if restore:
        inp.move_to(origin[0], origin[1], bounds)
        sleep(settle_s)
    errs = [r['error_px'] for r in results]
    return dict(origin=origin, bounds=bounds, restored=restore, results=results,
                max_error_px=max(errs) if errs else None,
                mean_error_px=(sum(errs) / len(errs)) if errs else None,
                all_accepted=all(r['accepted'] == 1 for r in results))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--no-restore', dest='restore', action='store_false')
    args = ap.parse_args(argv)
    rep = send_check(restore=args.restore)
    print('desktop virtual :', rep['bounds'])
    print('origem (restaurada=%s):' % rep['restored'], rep['origin'])
    for r in rep['results']:
        print('  alvo %-16s -> observado %-16s erro %.1f px  aceito=%d  norm=%s'
              % (r['target'], r['observed'], r['error_px'], r['accepted'], r['norm']))
    print('ERRO max %.1f px / medio %.1f px | todos aceitos: %s'
          % (rep['max_error_px'], rep['mean_error_px'], rep['all_accepted']))
    print('Nenhum clique enviado.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
