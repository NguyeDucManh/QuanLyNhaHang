"""Read existing runtime data; create only temporary login sessions for browser QA."""
import os, sys, json, time, subprocess, urllib.request, tempfile, base64
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurant_system.settings')
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.conf import settings
from django.urls import reverse
from django.contrib.sessions.models import Session
from customers.rbac import get_role, has_capability
import websocket

OUT = ROOT/'artifacts'/os.environ.get('REFERENCE_QA_OUTPUT', 'reference-qa')
OUT.mkdir(exist_ok=True)
BASE = os.environ.get('REFERENCE_QA_BASE', 'http://127.0.0.1:8017')
sessions = []
errors = []
results = []
browser = None
ws = None

def main():
    global browser, ws
    profiles = {}
    for role in ('ADMIN', 'MANAGER', 'STAFF', 'CUSTOMER'):
        candidates = [u for u in User.objects.filter(is_active=True).order_by('pk') if get_role(u) == role]
        if role == 'STAFF':
            candidates.sort(key=lambda u: not has_capability(u, 'customers.view_restauranttable'))
        if role == 'STAFF' and os.environ.get('REFERENCE_QA_STAFF_USERNAME'):
            candidates = [u for u in candidates if u.username == os.environ['REFERENCE_QA_STAFF_USERNAME']]
            assert candidates, 'Requested existing staff user was not found'
        if candidates:
            session = SessionStore()
            session[SESSION_KEY] = str(candidates[0].pk)
            session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
            session[HASH_SESSION_KEY] = candidates[0].get_session_auth_hash()
            session.save()
            key = session.session_key
            sessions.append(key)
            profiles[role] = key
    binary = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    log = (OUT/'browser.log').open('w', encoding='utf-8')
    browser = subprocess.Popen([str(binary), '--headless=new', '--no-first-run', '--disable-extensions', '--disable-gpu', '--no-sandbox',
        '--no-proxy-server', '--remote-debugging-port=9347', '--user-data-dir='+tempfile.mkdtemp(prefix='reference-ui-'),
        'about:blank'], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(80):
        try:
            targets = json.load(urllib.request.urlopen('http://127.0.0.1:9347/json', timeout=2))
            target = next(t for t in targets if t['type'] == 'page')
            break
        except Exception:
            time.sleep(.25)
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
    counter = 0
    def cdp(method, params=None):
        nonlocal counter
        counter += 1
        ws.send(json.dumps({'id': counter, 'method': method, 'params': params or {}}))
        while True:
            reply = json.loads(ws.recv())
            if reply.get('method') == 'Runtime.exceptionThrown':
                errors.append(reply)
            if reply.get('id') == counter:
                if 'error' in reply:
                    raise RuntimeError(reply['error'])
                return reply.get('result', {})
    def js(expression):
        return cdp('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}).get('result', {}).get('value')
    cdp('Page.enable'); cdp('Runtime.enable'); cdp('Network.enable')
    for file in ('static/admin/js/main.js', 'static/ui/pos.js', 'static/location/maps.js'):
        value = js('(()=>{try{new Function('+json.dumps((ROOT/file).read_text(encoding='utf-8'))+');return "PASS"}catch(e){return e.message}})()')
        results.append({'script': file, 'parse': value})
    routes = [('customer', reverse('customer_home'), None)]
    for role in ('ADMIN', 'MANAGER', 'STAFF'):
        if role in profiles:
            routes.append((role.lower(), reverse('staff_home' if role == 'STAFF' else 'admin_home'), profiles[role]))
    if profiles.get('ADMIN'):
        routes += [('pos-admin-permissions', reverse('staff_home'), profiles['ADMIN']),
                   ('face', reverse('ai_faces'), profiles['ADMIN']),
                   ('assistant', reverse('ai_chatbot_management'), profiles['ADMIN'])]
        routes += [('payments', reverse('admin_invoices'), profiles['ADMIN']),
                   ('reports', reverse('admin_reports'), profiles['ADMIN']),
                   ('location', reverse('location_settings'), profiles['ADMIN'])]
    if os.environ.get('REFERENCE_QA_ONLY'):
        routes = [route for route in routes if route[0] in os.environ['REFERENCE_QA_ONLY'].split(',')]
    if os.environ.get('OPERATIONS_QA_ROUTES'):
        routes = [(label,path,profiles[role]) for label,path,role in json.loads(os.environ['OPERATIONS_QA_ROUTES'])]
    for label, path, session in routes:
        cdp('Network.clearBrowserCookies')
        if session:
            cdp('Network.setCookie', {'name': 'sessionid', 'value': session, 'url': BASE})
        widths = [1920, 1366, 1024, 768, 390] if label in ('customer', 'admin', 'manager', 'staff', 'pos-admin-permissions') else [1366, 390]
        if os.environ.get('REFERENCE_QA_DESKTOP'):
            widths = [1920, 1366]
        if os.environ.get('REFERENCE_QA_WIDTHS'):
            widths = [int(value) for value in os.environ['REFERENCE_QA_WIDTHS'].split(',')]
        for width in widths:
            height = 1080 if width == 1920 else 768 if width == 1366 else 1000
            cdp('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            cdp('Page.navigate', {'url': BASE+path})
            time.sleep(.5)
            for _ in range(60):
                if js('document.readyState === "complete" && location.pathname === '+json.dumps(path)+' && document.body.innerText.length > 200 && (!document.getElementById("app") || document.querySelector("#main")?.innerText.length > 50)'):
                    break
                time.sleep(.2)
            time.sleep(.4)
            assert js('location.pathname === '+json.dumps(path)+' && !!document.querySelector("#server-content, #main, .site-header, .staff-main")'), 'Application page did not load: '+BASE+path
            assert not js('!!document.querySelector("#traceback, #summary h1")'), 'Django error page: '+path
            if os.environ.get('OPERATIONS_QA_ROUTES'):
                # Mutations run only on the disposable database created by the harness.
                assert os.environ.get('DB_NAME','').startswith('test_operations_browser_')
                actions = {
                    'po-submit': "document.querySelector('button[value=SUBMITTED]').click()",
                    'po-approve': "document.querySelector('button[value=APPROVED]').click()",
                    'po-partial': "document.querySelector('input[name^=quantity_]').value='60';document.querySelector('input[name^=quantity_]').form.requestSubmit()",
                    'po-complete': "document.querySelector('input[name^=quantity_]').value='40';document.querySelector('input[name^=quantity_]').form.requestSubmit()",
                    'booking-checkin': "document.querySelector('button[value=CHECKED_IN]').click()",
                    'booking-noshow': "document.querySelector('button[value=NO_SHOW]').click()",
                    'booking-transfer': "const s=document.querySelector('select[name=destination]');s.value="+json.dumps(os.environ.get('OPERATIONS_DESTINATION'))+";s.form.requestSubmit()",
                    'waitlist-convert': "document.querySelector('button[value=convert]').click()",
                }
                if label in actions:
                    result=cdp('Runtime.evaluate',{'expression':'(()=>{'+actions[label]+';return true})()','returnByValue':True})
                    assert 'exceptionDetails' not in result, result
                    time.sleep(1)
                    for _ in range(50):
                        if js('document.readyState === "complete" && !!document.querySelector("#main form, #main table")'): break
                        time.sleep(.1)
                    expected={'po-submit':'Chờ duyệt','po-approve':'Đã duyệt','po-partial':'Nhận một phần','po-complete':'Đã nhận đủ','booking-checkin':'Đã đến','booking-noshow':'Không đến','waitlist-convert':'Đã đặt bàn','booking-transfer':os.environ.get('OPERATIONS_DESTINATION_CODE')}
                    assert js('document.body.innerText.includes('+json.dumps(expected[label])+')'), label+' did not reach expected state'
            if label == 'location':
                time.sleep(9)
            data = js('''(()=>({title:document.title,url:location.pathname,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                dashboardRows:document.querySelectorAll('.dashboard-row').length,serverDashboard:!!document.querySelector('[data-dashboard-structure=server-rendered]'),posRows:document.querySelectorAll('.pos-service-row,.pos-catalog-row,.pos-production-row').length,body:document.body.innerText.slice(0,180),tables:document.querySelectorAll('.pos-table').length,
                ai:[...document.querySelectorAll('.sidebar .nav-link')].filter(a=>['ai-faces','ai-chatbot','ai-dashboard','ai-schedule','recommendation-demo','ai-forecast','ai-inventory'].includes(a.dataset.page)).map(a=>a.textContent.trim()),
                brokenImages:[...document.images].filter(i=>!i.complete||i.naturalWidth===0).map(i=>i.getAttribute('src')),
                posCounts:[...document.querySelectorAll('[data-pos-status]')].map(b=>b.textContent)
                ,posGeometry:[...document.querySelectorAll('.pos-floor,.pos-table-grid,.pos-floor-toolbar,.pos-filters,.pos-table-legend,.pos-bill,.pos-menu,.pos-kitchen')].map(e=>({element:e.className,height:e.offsetHeight,scroll:e.scrollHeight,top:Math.round(e.getBoundingClientRect().top)}))
                ,tableOverflow:[...document.querySelectorAll('.table-scroll')].map(t=>({width:t.clientWidth,scroll:t.scrollWidth}))
                ,mapFallback:document.querySelector('.map-unavailable')?.textContent||null
            }))()''')
            data.update(page=label, viewport=width)
            results.append(data)
            if label in ('pos-admin-permissions', 'staff') and width == 1366 and js("!!document.querySelector('.pos-table-grid')"):
                results.append({'posFilterCheck': js('''(()=>{const results=[];for(const b of document.querySelectorAll('[data-pos-status]')){b.click();const visible=[...document.querySelectorAll('.pos-table')].filter(t=>!t.hidden);results.push({status:b.dataset.posStatus,count:visible.length,match:visible.every(t=>!b.dataset.posStatus||t.dataset.status===b.dataset.posStatus)});}document.querySelector('[data-pos-status=""]').click();return results;})()''')})
                results.append({'areaFilterCheck': js('''(()=>{const a=document.querySelector('#pos-area'),r=[];for(const option of a.options){a.value=option.value;a.dispatchEvent(new Event('change',{bubbles:true}));const visible=[...document.querySelectorAll('.pos-table')].filter(t=>!t.hidden);const label=document.querySelector('[data-pos-status=""]').textContent;r.push({area:option.text,count:visible.length,counter:label,match:visible.every(t=>!a.value||t.dataset.area===a.value)&&label.includes('('+visible.length+')')});}a.value='';a.dispatchEvent(new Event('change',{bubbles:true}));return r})()''')})
                results.append({'catalogFilterCheck': js('''(()=>{const input=document.querySelector('#pos-food-search'),buttons=[...document.querySelectorAll('[data-pos-category]')];if(!input)return null;const all=[...document.querySelectorAll('[data-food-category]')];input.value='__qa_no_matching_dish__';input.dispatchEvent(new Event('input',{bubbles:true}));const search=all.every(card=>card.hidden);input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));let category=true;if(buttons[1]){buttons[1].click();category=all.filter(c=>!c.hidden).every(c=>c.dataset.foodCategory===buttons[1].dataset.posCategory);buttons[0].click();}return {search,category,total:all.length,restored:all.every(c=>!c.hidden)};})()''')})
                results.append({'tableSelectionCheck': js('''(async()=>{const links=[...document.querySelectorAll('.pos-table')];if(links.length<2)return null;const expected=links[1].querySelector('strong').textContent,original=links[0].querySelector('strong').textContent;await new Promise(r=>setTimeout(r,400));links[1].click();for(let n=0;n<40;n++){if(document.querySelector('.pos-detail h2')?.textContent.includes(expected))break;await new Promise(r=>setTimeout(r,100));}const matched=document.querySelector('.pos-detail h2')?.textContent.includes(expected);document.querySelector('.pos-table').click();for(let n=0;n<40;n++){if(document.querySelector('.pos-detail h2')?.textContent.includes(original))break;await new Promise(r=>setTimeout(r,100));}return {expected,matched,restored:document.querySelector('.pos-detail h2')?.textContent.includes(original)};})()''')})
            if label == 'customer' and width == 390:
                results.append({'customerMobileNav': js('''(()=>{const b=document.querySelector('#nav-toggle'),nav=document.querySelector('#main-nav');b.click();const open=nav.classList.contains('is-open')&&getComputedStyle(nav).display!=='none';b.click();return {open,closed:!nav.classList.contains('is-open')};})()''')})
            if label in ('staff','pos-admin-permissions') and width == 390:
                results.append({'staffMobileNav': js('''(async()=>{const b=document.querySelector('[data-staff-toggle]');b.click();await new Promise(r=>setTimeout(r,250));const open=document.body.classList.contains('staff-nav-open')&&document.querySelector('.staff-sidebar').getBoundingClientRect().left>=-1;document.querySelector('[data-staff-close]').click();await new Promise(r=>setTimeout(r,250));return {open,closed:!document.body.classList.contains('staff-nav-open')};})()''')})
            image = cdp('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
            (OUT/f'{label}-{width}.png').write_bytes(base64.b64decode(image['data']))
    from customers.models import RestaurantTable
    if not os.environ.get('REFERENCE_QA_SCREENSHOTS_ONLY'):
        (OUT/'results.json').write_text(json.dumps({'database_table_count':RestaurantTable.objects.count(), 'results':results, 'exceptions': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pages':len(results), 'exceptions':len(errors), 'overflow':[{k:r[k] for k in ('page','viewport','scrollWidth')} for r in results if r.get('scrollWidth',0)>r.get('width',0)], 'screenshots':str(OUT), 'structure':[{k:r.get(k) for k in ('page','viewport','dashboardRows','serverDashboard','posRows','tables')} for r in results if r.get('page') in ('admin','pos-admin-permissions')], 'interactions':[r for r in results if any(k in r for k in ('posFilterCheck','areaFilterCheck','catalogFilterCheck','tableSelectionCheck'))]},ensure_ascii=True))

try:
    main()
finally:
    if ws:
        ws.close()
    if browser:
        browser.terminate()
    Session.objects.filter(session_key__in=sessions).delete()
