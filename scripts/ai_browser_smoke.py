"""Chrome smoke tests using an isolated PostgreSQL database; no main DB fixtures."""
import base64
import io
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

WORKSPACE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(WORKSPACE))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
os.environ['PYTHONIOENCODING']='utf-8'
from django.conf import settings
import psycopg
from psycopg import sql

def run():
    config=settings.DATABASES['default'].copy(); dbname='smart_restaurant_ai_browser_'+uuid.uuid4().hex[:8]
    params={'host':config['HOST'],'port':config['PORT'],'user':config['USER'],'password':config['PASSWORD'],'dbname':'postgres'}
    admin=psycopg.connect(**params,autocommit=True); created=False; processes=[]; handles=[]; ws=None
    output=WORKSPACE/'qa_browser'; output.mkdir(exist_ok=True)
    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(dbname))); created=True
        settings.DATABASES['default']['NAME']=dbname
        import django
        django.setup()
        from django.core.management import call_command
        from django.test import Client
        from django.contrib.auth.models import User
        from customers.rbac import assign_role
        call_command('migrate',verbosity=0,stdout=io.StringIO())
        call_command('seed_rbac',stdout=io.StringIO()); call_command('seed_menu',stdout=io.StringIO())
        call_command('seed_module07_recipes',stdout=io.StringIO())
        actor=User.objects.create_user('browser-manager'); assign_role(actor,'MANAGER')
        client=Client(enforce_csrf_checks=True,HTTP_HOST='127.0.0.1'); client.force_login(actor); cookie=client.cookies['sessionid'].value
        env={**os.environ,'DB_NAME':dbname}
        server_log=(output/'server.log').open('w',encoding='utf-8'); handles.append(server_log)
        server=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8767','--noreload'],cwd=WORKSPACE,env=env,stdout=server_log,stderr=server_log,creationflags=subprocess.CREATE_NO_WINDOW); processes.append(server)
        chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        chrome_log=(output/'chrome.log').open('w',encoding='utf-8'); handles.append(chrome_log)
        with tempfile.TemporaryDirectory(prefix='ai-chrome-',dir=output,ignore_cleanup_errors=True) as profile:
            browser=subprocess.Popen([str(chrome),'--headless','--disable-gpu','--no-sandbox','--disable-features=NetworkServiceSandbox','--no-proxy-server','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-extensions','--remote-debugging-port=9225','--user-data-dir='+profile,'about:blank'],stdout=chrome_log,stderr=chrome_log,creationflags=subprocess.CREATE_NO_WINDOW); processes.append(browser)
            for _ in range(100):
                try:
                    targets=json.load(urllib.request.urlopen('http://127.0.0.1:9225/json',timeout=2))
                    urllib.request.urlopen('http://127.0.0.1:8767/ai/chat/',timeout=2).close()
                    break
                except Exception: time.sleep(.2)
            import websocket
            ws=websocket.create_connection(targets[0]['webSocketDebuggerUrl'],timeout=30,suppress_origin=True)
            counter=0
            def cdp(method,params=None):
                nonlocal counter
                counter+=1; request_id=counter; ws.send(json.dumps({'id':request_id,'method':method,'params':params or {}}))
                while True:
                    response=json.loads(ws.recv())
                    if response.get('id')==request_id:
                        if 'error' in response: raise RuntimeError(response['error'])
                        return response.get('result',{})
            def evaluate(expression):
                result=cdp('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
                if 'exceptionDetails' in result: raise RuntimeError(result['exceptionDetails'])
                return result.get('result',{}).get('value')
            cdp('Page.enable'); cdp('Runtime.enable'); cdp('Network.enable')
            cdp('Network.setCookie',{'name':'sessionid','value':cookie,'url':'http://127.0.0.1:8767/'})
            outcomes=[]
            routes=[('/management/ai/','AI Dashboard'),('/management/ai/forecast/','Dự báo nhu cầu'),('/management/ai/inventory/','AI đề xuất nguyên liệu'),('/management/ai/faces/','Quản lý khuôn mặt'),('/recommendations/',''),('/ai/chat/','Trợ lý AI')]
            for mobile in [False,True]:
                cdp('Emulation.setDeviceMetricsOverride',{'width':390 if mobile else 1440,'height':844 if mobile else 1000,'deviceScaleFactor':1,'mobile':mobile})
                for index,(route,title) in enumerate(routes):
                    response=client.get(route)
                    if response.status_code!=200: raise AssertionError('Django response '+route+' '+str(response.status_code))
                    html=response.content.decode('utf-8')
                    scripts=re.findall(r'<script[^>]*src="/static/([^"?]+)[^"]*"[^>]*></script>',html)
                    html=re.sub(r'<script[^>]*src="[^"]*"[^>]*></script>','',html)
                    def style(match):
                        path=WORKSPACE/'static'/match[1]
                        return '<style>'+path.read_text(encoding='utf-8')+'</style>' if path.exists() else ''
                    html=re.sub(r'<link[^>]*href="/static/([^"?]+)[^"]*"[^>]*>',style,html)
                    frame_id=cdp('Page.getFrameTree')['frameTree']['frame']['id']
                    cdp('Page.setDocumentContent',{'frameId':frame_id,'html':html})
                    for source in scripts:
                        path=WORKSPACE/'static'/source
                        if path.exists(): evaluate(path.read_text(encoding='utf-8')+'\n;true')
                    evaluate('document.dispatchEvent(new Event("DOMContentLoaded")); true')
                    for _ in range(150):
                        ready=evaluate('document.readyState === "complete" && '+('!!document.querySelector("#main h1")' if route.startswith('/management/') else '!!document.querySelector("main h1")'))
                        if ready: break
                        time.sleep(.2)
                    body=evaluate('document.body.innerText') or ''
                    if title and title not in body: raise AssertionError('Missing UI title '+route+' '+str(evaluate('({url:location.href,html:document.documentElement.outerHTML.slice(0,1000)})')))
                    if 'Traceback' in body or 'Exception Type:' in body: raise AssertionError('Django error page '+route)
                    outcomes.append({'route':route,'mobile':mobile,'title_present':bool(title in body) if title else None,'horizontal_overflow':evaluate('document.documentElement.scrollWidth > innerWidth'),'method':'Chrome DOM/layout checks; screenshots unavailable on this host'})
                    (output/'results.json').write_text(json.dumps(outcomes,ensure_ascii=False,indent=2),encoding='utf-8')
            # HTTP middleware/CSRF test through Django client; Chromium navigation
            # is blocked in this host, so report browser rendering separately.
            token=evaluate('document.querySelector("[name=csrfmiddlewaretoken]").value')
            result=client.post('/ai/chat/message/',json.dumps({'message':'Giá Súp bào ngư hải sâm?'}),content_type='application/json',HTTP_X_CSRFTOKEN=token)
            if result.status_code!=200 or '289.000' not in result.json()['answer']: raise AssertionError('CSRF chat HTTP assertion')
            outcomes.append({'django_csrf_chat_price':'PASS','browser_mode':'Django HTML + local CSS/JS injected into Chrome; live HTTP navigation unavailable (ERR_ABORTED)','database':'isolated temporary PostgreSQL','main_db_mutated':False})
            (output/'results.json').write_text(json.dumps(outcomes,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(outcomes,ensure_ascii=True))
            ws.close(); ws=None; browser.terminate(); browser.wait(timeout=20); processes.remove(browser)
    finally:
        if ws: ws.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=20)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        for handle in handles: handle.close()
        from django.db import connections
        connections.close_all()
        if created:
            admin.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',(dbname,))
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(dbname)))
        admin.close()

if __name__=='__main__': run()
