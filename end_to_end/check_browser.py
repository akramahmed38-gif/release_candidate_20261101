"""Execute existing local Chromium if installed; never installs a browser."""
from pathlib import Path
import hashlib,json,secrets,sys,threading,time,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine,DemoServer

def main():
    out=ROOT/'end_to_end'/('browser_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]);out.mkdir()
    token=secrets.token_urlsafe(40);engine=create_engine(out/'private_workspace');server=DemoServer(engine,token,out/'audit.jsonl');threading.Thread(target=server.serve_forever,daemon=True).start()
    report={'status':'NOT RUN','native':'NOT RUN','employee_access':False,'checks':[],'source_sha256':hashlib.sha256((ROOT/'source/demo_app.py').read_bytes()).hexdigest()}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:'+str(server.server_port))
            def check(name,value):
                report['checks'].append({'name':name,'passed':bool(value)})
                if not value:raise AssertionError(name)
            check('visible_unapproved_scope','UNAPPROVED EVIDENCE' in page.locator('body').inner_text())
            page.locator('#token').fill(token);page.locator('#connect').click();page.wait_for_function("document.getElementById('answer').textContent==='New isolated conversation'")
            check('token_cleared',page.locator('#token').input_value()=='')
            page.locator('#question').fill('What is the AXIS opening fee?');page.locator('#ask').click()
            page.wait_for_function("document.getElementById('answer').textContent.includes('F0010')")
            text=page.locator('#answer').inner_text();check('actual_answer_and_citation','0 EGP' in text and 'axis_wallet_sales_guide.pdf' in text)
            page.locator('#fresh').click();page.wait_for_function("document.getElementById('answer').textContent==='New isolated conversation'")
            page.locator('#question').fill('What is its opening fee?');page.locator('#ask').click()
            page.wait_for_function("document.getElementById('answer').textContent.includes('citations')")
            isolated=page.locator('#answer').inner_text();check('new_conversation_does_not_borrow_axis','F0010' not in isolated)
            check('no_browser_script_errors',not errors)
            report.update(status='PASS',actual_answer=text,isolated_answer=isolated,browser_errors=errors)
            browser.close()
    except Exception as exc:
        report.update(status='FAIL' if report['checks'] else 'BLOCKED',error_type=type(exc).__name__,error_summary=str(exc)[:500])
    finally:
        server.shutdown();server.server_close()
        (out/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'results':str(out/'RESULTS.json'),'status':report['status'],'checks':report['checks']}))

if __name__=='__main__':main()
