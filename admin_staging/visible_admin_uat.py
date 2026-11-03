"""Visible existing-app UI checks with a strictly manual login pause.

No credential fields, browser storage, cookies, login traffic or traces read.
The owned browser stays open for the administrator after the test sequence.
"""
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from urllib.parse import urlsplit
import json,os,time,uuid
ROOT=Path(__file__).resolve().parent
BASE='http://127.0.0.1:8765'

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    opener=build_opener(ProxyHandler({}))
    with opener.open(BASE+'/health',timeout=3) as response:health=json.load(response)
    if health.get('environment')!='isolated_admin_staging' or health.get('production') is not False:raise RuntimeError('Verified isolated application required')
    from playwright.sync_api import sync_playwright
    run_id=uuid.uuid4().hex
    out=ROOT/'state/browser_sessions'/run_id;out.mkdir(parents=True)
    control=ROOT/'.private'/('browser_control_'+run_id+'.json')
    rows=[]
    receipt={'pid':os.getpid(),'run_id':run_id,'url':BASE+'/training/login?lang=en','state':'starting','control_file':str(control),'results_directory':str(out),'credential_inspection':False}
    def state(value):receipt['state']=value;save(ROOT/'VISIBLE_BROWSER.json',receipt)
    def command():
        if not control.exists():return None
        value=json.loads(control.read_text(encoding='utf-8'));control.unlink();return value.get('action')
    def record(name,passed,**detail):
        row={'name':name,'passed':bool(passed),**detail};rows.append(row);save(out/'RESULTS.json',{'suite':'actual Training application UI','independent':False,'native':'NOT RUN','rows':rows,'passed':sum(r['passed'] for r in rows),'total':len(rows)})
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False,executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args=['--disable-background-networking','--disable-component-update','--no-default-browser-check','--disable-sync'])
        context=browser.new_context(viewport={'width':1280,'height':900})
        page=context.new_page();page.goto(receipt['url'])
        if urlsplit(page.url).hostname!='127.0.0.1' or not page.locator('#staging-environment').count():raise RuntimeError('Staging page verification failed')
        state('awaiting_manual_login')
        print(json.dumps({'state':'awaiting_manual_login','url':receipt['url'],'run_id':run_id}),flush=True)
        # No browser automation occurs between opening login and explicit user
        # confirmation. Only this private command file is polled.
        while True:
            action=command()
            if action=='stop':browser.close();state('stopped');return
            if action=='login_completed':break
            time.sleep(.25)
        state('testing_after_user_confirmation')
        try:
            response=context.request.get(BASE+'/training/api/v1/audit/logs')
            record('authenticated_admin_api',response.status==200,http_status=response.status)
            if response.status!=200:raise RuntimeError('Manual admin login not verified')
            page.goto(BASE+'/training/admin/audit?lang=en')
            page.get_by_text('Audit Trail',exact=False).first.wait_for()
            record('actual_admin_audit_screen',True)
            page.goto(BASE+'/training/admin/knowledge-workspace')
            page.wait_for_function("document.querySelectorAll('#selection input').length>0")
            expected=json.loads((ROOT/'PENDING_CATALOG_IMPORT.json').read_text())['counts']
            observed=page.locator('#service option').count()-1
            record('all_profiles_rendered',observed==expected['profile'],observed=observed,expected=expected['profile'])
            page.locator('details').first.locator('summary').click()
            def ask(name,q,mode,ids,wanted,complete):
                page.locator('#mode').select_option(mode)
                for box in page.locator('#selection input').all():box.set_checked(box.get_attribute('value') in ids)
                page.locator('#question').fill(q);started=time.perf_counter()
                with page.expect_response(lambda r:r.url.endswith('/api/v1/admin/knowledge-ask') and r.request.method=='POST') as received:page.locator('#ask').click()
                response=received.value;actual=response.json();page.wait_for_function("!document.querySelector('#ask').disabled")
                record(name,response.status==200 and set(actual.get('supported_fact_ids',[]))==set(wanted) and actual.get('complete')==complete and not(actual.get('complete') and actual.get('clarification_needed')),
                       question=q,http_status=response.status,http_ms=(time.perf_counter()-started)*1000,expected_fact_ids=wanted,expected_complete=complete,actual=actual)
            ask('approved_gate','What is the AXIS opening fee?','approved',[],[],False)
            ask('english_preview','What is the AXIS opening fee?','review_preview',['F0010'],['F0010'],True)
            page.locator('#fresh').click()
            ask('arabic_preview','رسوم سحب QNB من ATM كام؟','review_preview',['F0076'],['F0076'],True)
            page.locator('#fresh').click()
            ask('channel_comparison','Compare AXIS deposit fees at ATMs and Fawry Plus.','review_preview',['F0001','F0002'],['F0001','F0002'],True)
            page.locator('#fresh').click()
            ask('selection_boundary','AXIS opening fee and minimum initial deposit','review_preview',['F0010'],['F0010'],False)
            page.locator('#fresh').click()
            ask('adib_code','What is the ADIB remittance cash-out service code?','review_preview',['F0036'],['F0036'],True)
            anonymous=browser.new_context()
            for path in ['/training/api/v1/admin/knowledge-status','/training/admin/knowledge-workspace','/training/api/v1/chatbot/diagnostics']:
                response=anonymous.request.get(BASE+path);record('anonymous_rejected:'+path,response.status in {401,403},http_status=response.status)
            anonymous.close()
            # This page has only synthetic test questions and source-bound
            # fixture metadata, no account fields or credential-bearing traces.
            page.screenshot(path=str(out/'KNOWLEDGE_WORKSPACE.png'),full_page=True)
            state('tests_complete_browser_available')
        except Exception as exc:
            record('ui_execution_error',False,error_type=type(exc).__name__)
            state('test_failure_browser_available')
        print(json.dumps({'state':receipt['state'],'passed':sum(r['passed'] for r in rows),'total':len(rows),'results':str(out/'RESULTS.json')}),flush=True)
        while True:
            if command()=='stop':break
            time.sleep(.5)
        browser.close();state('stopped')

if __name__=='__main__':main()
