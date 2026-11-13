import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(os.environ.get('EVIDENCE_DIR',str(Path(__file__).parent)))
out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1080})
    errors=[]; requests=[]
    page.on('pageerror',lambda err: errors.append(str(err)))
    page.on('request',lambda req: requests.append({'method':req.method,'url':req.url}) if '/api/' in req.url else None)
    page.goto(os.environ.get('AUDIT_BASE_URL','http://localhost:3000'),wait_until='networkidle')
    initial=page.locator('body').inner_text()
    page.screenshot(path=str(out/'initial.png'),full_page=True)
    page.get_by_role('button',name='Iniciar Sessão',exact=True).click()
    page.wait_for_timeout(200)
    session={'active_label':page.get_by_text('Sessão Ativa',exact=True).count(),'api_requests':list(requests)}
    page.get_by_role('button',name='Cérebro Pré-Flop',exact=True).click()
    page.screenshot(path=str(out/'preflop.png'),full_page=True)
    pre=page.locator('body').inner_text()
    page.get_by_role('button',name='Cérebro Pós-Flop',exact=True).click()
    page.screenshot(path=str(out/'postflop.png'),full_page=True)
    post=page.locator('body').inner_text()
    page.get_by_role('button',name='Análise de Mãos',exact=True).click()
    analysis=page.locator('body').inner_text()
    page.get_by_role('button',name='Carregar Exemplo PPPoker (.txt)',exact=True).click()
    page.get_by_title('Próxima ação',exact=True).click()
    sample={'replayer_present':page.get_by_text('Pote Atual:',exact=False).count()>0}
    if os.environ.get('AUDIT_EXPECT_NO_GEMINI_KEY') == '1':
        page.get_by_role('button',name='Analisar Erros Pós-Flop com IA',exact=True).click()
        page.wait_for_timeout(300)
        sample['missing_key_error_shown']='Chave da API Gemini' in page.locator('body').inner_text()
    page.screenshot(path=str(out/'analysis.png'),full_page=True)
    page.reload(wait_until='networkidle')
    session['reset_on_reload']=page.get_by_role('button',name='Iniciar Sessão',exact=True).count()==1
    (out/'browser.json').write_text(json.dumps({'session':session,'sample':sample,'page_errors':errors,'api_requests':requests,'initial_text':initial,'preflop_text':pre,'postflop_text':post,'analysis_text':analysis},ensure_ascii=False,indent=2))
    print(json.dumps({'session':session,'sample':sample,'page_errors':errors,'api_requests':requests},ensure_ascii=False,indent=2))
    browser.close()
