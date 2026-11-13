"""Read-only audit probes. Run from the repository root with Python dependencies installed."""
from pathlib import Path
import ast, contextlib, copy, io, json, subprocess, sys

root = Path.cwd().resolve()
sys.path.insert(0, str(root / 'python_bot'))
from preflop_advisor import PreflopAdvisor, infer_live_spot
from test_preflop_advisor import pack_with_node
from test_preflop_context import pack_open_and_call

def concise(advice):
    return {k:advice.get(k) for k in ['status','spot','node_id','recommended','validated','execution_allowed','caveats']}

positions = dict(zip(['utg','u1','u2','lj','hj','co','hero','sb','bb'],['UTG','UTG+1','UTG+2','LJ','HJ','CO','BTN','SB','BB']))
def state(bets):
    return dict(positions=positions, seats={k:dict(occupied=True,stack_bb=25) for k in positions}, bets=[dict(seat=k,bet_bb=v) for k,v in bets.items()],pot=dict(pot_bb=10),to_call=dict(to_call_bb=2.5),dealer=dict(seat='hero'))

limps=state({'utg':1,'hj':1,'sb':0.5,'bb':1})
limp_advice=PreflopAdvisor(pack_with_node()).advise_from_reading(limps,['Ah','Ad'])
callers=state({'utg':2.5,'hj':2.5,'co':2.5,'sb':0.5,'bb':1})
multi_pack=pack_open_and_call(['AA'],['AA'],opener='UTG',caller='BTN')
multi_advice=PreflopAdvisor(multi_pack).advise_from_reading(callers,['Ah','Ad'])

# Evaluate only the pure authorization method; no cursor/capture imports.
executor_tree=ast.parse((root/'python_bot/action_executor.py').read_text())
executor_class=next(n for n in executor_tree.body if isinstance(n,ast.ClassDef) and n.name=='ActionExecutor')
eligible_method=next(n for n in executor_class.body if isinstance(n,ast.FunctionDef) and n.name=='_eligible')
isolated=ast.ClassDef(name='EligibilityProbe',bases=[],keywords=[],body=[eligible_method],decorator_list=[])
scope={}
exec(compile(ast.fix_missing_locations(ast.Module(body=[isolated],type_ignores=[])),'eligibility_probe','exec'),scope)
gate=scope['EligibilityProbe']();gate.call_margin=.03

pack=pack_with_node(); second=copy.deepcopy(pack['nodes'][0]); second['id']='same_key_second_source'
second['freq']['raise'],second['freq']['fold']=second['freq']['fold'],second['freq']['raise']
pack['nodes'].append(second)
def lookup(p):return concise(PreflopAdvisor(p).advise(hero_cards=['Ah','Ad'],hero_position='BTN',stack_bb=25,spot='open_raise'))
reversed_pack=copy.deepcopy(pack);reversed_pack['nodes'].reverse()

# Execute only argparse construction, never the agent main or any input adapter.
tree=ast.parse((root/'python_bot/operar_mesa.py').read_text())
main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
body=[]
for node in main.body:
    body.append(node)
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='args' for t in node.targets):break
import argparse
def parse_case(argv):
    scope={'argparse':argparse,'__doc__':'isolated parser probe','argv':argv,'DEFAULT_RANGES':'external-range.json'}
    errors=io.StringIO()
    with contextlib.redirect_stderr(errors):
        try:
            exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),'parser_probe','exec'),scope)
            return dict(exit=0,parsed=vars(scope['args']))
        except SystemExit as exc:return dict(exit=exc.code,error=errors.getvalue().strip().splitlines()[-1])

cli=[['--hwnd','0x12FA,','0x34BC','--bounty-bb','--overlay','--human-mouse'],['--hwnd','0x12FA','0x34BC','--bounty-bb','--overlay','--human-mouse'],['--hwnd','0x12FA','0x34BC','--bounty-bb','1','--overlay','--human-mouse'],['--hwnd','0x12FA','0x34BC','--bounty-bb','1','--human-mouse']]
def subprocess_probe(args):
    p=subprocess.run([sys.executable,*args],capture_output=True,text=True)
    return dict(exit=p.returncode,stderr=p.stderr.strip())

results={
 'two_limpers':dict(classification=infer_live_spot(limps),advice=concise(limp_advice)),
 'open_two_callers':dict(classification=infer_live_spot(callers),advice=concise(multi_advice),isolated_call_eligibility=gate._eligible(multi_advice,'CALL')),
 'duplicate_key_source_order':dict(first=lookup(pack),reversed=lookup(reversed_pack),has_manifest=hasattr(PreflopAdvisor(pack),'manifest')),
 'launcher_parser':[{ 'argv':argv, **parse_case(argv)} for argv in cli],
 'startup_help':subprocess_probe(['python_bot/operar_mesa.py','--help']),
 'engine_bridge':subprocess_probe(['python_bot/modules/engine_bridge.py'])
}
print(json.dumps(results,ensure_ascii=False,indent=2))
