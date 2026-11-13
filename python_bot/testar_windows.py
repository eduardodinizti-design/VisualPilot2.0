"""Windows: current recognition plus explicitly selected, single manual clicks."""
import argparse
import ctypes
from ctypes import wintypes as W
import time
import numpy as np
from table_reading.pipeline import analyze_tables
from table_reading.presentation import describe_regions


def signature(meta):
    return tuple(str(meta.get(k)) for k in ('hwnd','pid','process_created','executable','client_rect','screen_origin','image_shape'))


def options(report):
    result=[]
    for row in report['tables']:
        panel=row.get('action_buttons',{})
        if row['status']!='COMPLETE_CANDIDATE' or panel.get('status')!='EXPERIMENTAL_BUTTON_ROW':continue
        for button in panel.get('buttons',[]):
            if button.get('status')=='EXPERIMENTAL_LABEL' and button.get('action') in {'FOLD','CHECK','CALL','BET','RAISE'}:
                result.append((row,button))
    return result


def key(item):
    row,b=item
    return (tuple(row['local_box']),tuple(b['box']),b['action'],b.get('amount'),b.get('unit'),
            tuple(row.get('hero_cards',[])),tuple(row.get('board',{}).get('cards',[])))


def patch(frame,item):
    row,b=item
    tx,ty,_,_=row['local_box'];x,y,w,h=b['box'];x+=tx;y+=ty
    if min(x,y)<0 or w<=0 or h<=0 or x+w>frame.shape[1] or y+h>frame.shape[0]:
        raise RuntimeError('Botao fora da captura')
    return frame[y:y+h,x:x+w],(x+w//2,y+h//2)


def verify_pixels(reference,reference_meta,current,current_meta,item):
    if current is None or current_meta.get('status')!='SUCCESS' or signature(reference_meta)!=signature(current_meta):
        raise RuntimeError('Janela, processo ou geometria mudou; clique cancelado')
    old,point=patch(reference,item);new,_=patch(current,item)
    if not np.array_equal(old,new):raise RuntimeError('Botao mudou; clique cancelado')
    return point


class WindowsInput:
    def __init__(self,engine,hwnd):
        self.engine,self.hwnd=engine,hwnd
        self.u=ctypes.WinDLL('user32',use_last_error=True)
        for name,args,result in [
            ('SetForegroundWindow',[W.HWND],W.BOOL),('GetForegroundWindow',[],W.HWND),
            ('GetAncestor',[W.HWND,W.UINT],W.HWND),('WindowFromPoint',[W.POINT],W.HWND),
            ('SetCursorPos',[ctypes.c_int,ctypes.c_int],W.BOOL),
            ('mouse_event',[W.DWORD,W.DWORD,W.DWORD,W.DWORD,ctypes.c_size_t],None)]:
            fn=getattr(self.u,name);fn.argtypes=args;fn.restype=result
    def foreground(self):
        self.u.SetForegroundWindow(self.hwnd)
        time.sleep(.15)
        if self.u.GetForegroundWindow()!=self.hwnd:raise RuntimeError('Nao foi possivel ativar a janela selecionada')
    def click(self,point,meta):
        with self.engine._native().physical_pixels():
            state=self.engine._state(self.engine._native(),self.hwnd)
            if self.engine._signature(state)!=self.engine._signature(meta):raise RuntimeError('Janela mudou antes do clique')
            x,y=point;x+=meta['screen_origin'][0];y+=meta['screen_origin'][1]
            def check():
                hit=self.u.WindowFromPoint(W.POINT(x,y))
                if self.u.GetForegroundWindow()!=self.hwnd or (hit!=self.hwnd and self.u.GetAncestor(hit,2)!=self.hwnd):
                    raise RuntimeError('Alvo coberto ou sem foco; clique cancelado')
            check()
            if not self.u.SetCursorPos(x,y):raise RuntimeError('Falha ao posicionar cursor')
            check()
            self.u.mouse_event(2,0,0,0,0)
            try:pass
            finally:self.u.mouse_event(4,0,0,0,0)


def snapshot(engine,hwnd):
    frame,meta=engine.capture_frame(hwnd=hwnd)
    if frame is None or meta.get('hwnd')!=hwnd:raise RuntimeError(str(meta))
    report=analyze_tables(frame,meta,read_buttons=True,read_community=True)
    return frame,meta,report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hwnd',type=lambda s:int(s,0))
    p.add_argument('--listar',action='store_true')
    p.add_argument('--cliques',action='store_true',help='Habilita um clique por escolha manual no console')
    args=p.parse_args(argv)
    from window_capture_engine import WindowCaptureEngine
    engine=WindowCaptureEngine()
    if args.listar:
        for w in engine.locate_target_windows():print('HWND:',w['hwnd'],'PID:',w['pid'],'Titulo:',w.get('title'))
        return 0
    if not args.hwnd:p.error('Informe --hwnd NUMERO ou --listar')
    control=WindowsInput(engine,args.hwnd) if args.cliques else None
    print('RAM somente. Enter: atualizar. q: sair. Cada numero solicita UM clique manual.' if control else 'Observacao: Enter atualiza, q sai. Sem cliques.')
    while True:
        try:
            frame,meta,report=snapshot(engine,args.hwnd)
            for line in describe_regions(report):print(line)
            choices=options(report)
            for i,(row,b) in enumerate(choices,1):print(i,'Mesa',row['table_index'],b.get('label'),b.get('amount') or '')
            command=input('Numero do botao / Enter / q: ').strip().lower()
            if command=='q':return 0
            if not command:continue
            if not control:print('Cliques desabilitados.');continue
            index=int(command)-1
            if not 0<=index<len(choices):raise ValueError('Numero invalido')
            selected=choices[index]
            control.foreground()
            fresh,info,reading=snapshot(engine,args.hwnd)
            matches=[v for v in options(reading) if key(v)==key(selected)]
            if signature(meta)!=signature(info) or len(matches)!=1:raise RuntimeError('Mesa, cartas ou botao mudou; atualize e escolha novamente')
            started=time.monotonic()
            last,last_meta=engine.capture_frame(hwnd=args.hwnd)
            point=verify_pixels(fresh,info,last,last_meta,matches[0])
            if time.monotonic()-started>.25:raise RuntimeError('Captura final demorou mais de 250 ms; clique cancelado')
            control.click(point,last_meta)
            print('Um clique enviado. Bet/Raise pode apenas abrir o painel de valor; nenhum segundo clique e enviado.')
        except (KeyboardInterrupt,EOFError):return 0
        except Exception as exc:
            print('FALHA:',exc)
            try:
                if input('Enter para atualizar; q para sair: ').strip().lower()=='q':return 1
            except (KeyboardInterrupt,EOFError):return 1

if __name__=='__main__':raise SystemExit(main())
