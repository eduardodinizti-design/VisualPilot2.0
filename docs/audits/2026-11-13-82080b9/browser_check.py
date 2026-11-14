"""Local read-only UI audit; starts only the currently broken, unarmed agent."""
from pathlib import Path
import json, os
from playwright.sync_api import sync_playwright

out=Path(os.environ.get('EVIDENCE_DIR',str(Path(__file__).parent)))
out.mkdir(parents=True,exist_ok=True)
base=os.environ.get('AUDIT_BASE_URL','http://localhost:3000')
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base,wait_until='networkidle')
    result={'initial_http_ok':True}
    if os.environ.get('AUDIT_START_BROKEN_AGENT')=='1':
        page.get_by_role('button',name='Iniciar Sessão',exact=True).click()
        page.wait_for_timeout(500)
        result['ui_active_after_process_failure']=page.get_by_text('Sessão Ativa',exact=True).count()>0
        result['backend_status']=page.request.get(base+'/api/bot/status').json()
    for button,name in [('Cérebro Pré-Flop','preflop'),('Cérebro Pós-Flop','postflop'),('Análise de Mãos','analysis')]:
        page.get_by_role('button',name=button,exact=True).click()
        result[name+'_opened']=True
    page.get_by_role('button',name='Carregar Exemplo PPPoker (.txt)',exact=True).click()
    page.get_by_title('Próxima ação',exact=True).click()
    result['sample_replayer_opened']=True
    page.screenshot(path=str(out/'ui.png'),full_page=True)
    result['page_errors']=errors
    (out/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    browser.close()
