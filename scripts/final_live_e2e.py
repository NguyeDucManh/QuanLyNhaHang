"""Live Django HTTP and browser audit against disposable PostgreSQL only."""
import io,json,os,re,sys,time,tempfile,subprocess,urllib.request,urllib.parse,http.cookiejar,uuid
from datetime import time as daytime
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings');os.environ['PYTHONIOENCODING']='utf-8'
from django.conf import settings
import psycopg
from psycopg import sql
OUTPUT=ROOT/'qa_final';OUTPUT.mkdir(exist_ok=True)
BASE='http://127.0.0.1:8788'

class HTTP:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar();self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def get(self,path):
        with self.client.open(BASE+path,timeout=60) as response:return response.status,response.read().decode('utf-8')
    def post(self,path,data,as_json=False):
        token=next((c.value for c in self.jar if c.name=='csrftoken'),'')
        headers={'X-CSRFToken':token,'Referer':BASE+path}
        if as_json: headers['Content-Type']='application/json';body=json.dumps(data).encode('utf-8')
        else: body=urllib.parse.urlencode({**data,'csrfmiddlewaretoken':token},doseq=True).encode()
        request=urllib.request.Request(BASE+path,data=body,headers=headers)
        try:
            with self.client.open(request,timeout=120) as response:return response.status,response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:return exc.code,exc.read().decode('utf-8')
    def login(self,username):
        self.get('/login/');status,body=self.post('/login/',{'username':username,'password':'LiveDemo_2026!'});assert status==200 and 'name="password"' not in body,'Login failed'

def main():
    db=settings.DATABASES['default'].copy();name='smart_restaurant_final_e2e_'+uuid.uuid4().hex[:8]
    admin=psycopg.connect(host=db['HOST'],port=db['PORT'],user=db['USER'],password=db['PASSWORD'],dbname='postgres',autocommit=True)
    processes=[];handles=[];created=False;ws=None;results={'label':'ISOLATED live HTTP / browser audit; all fixtures are simulated QA data','checks':[],'browser':{},'webcam':'NOT TESTED REAL','gps':'AUTOMATED MOCK ONLY','real_face_enrollment':0}
    def record(kind,detail):results['checks'].append({'kind':kind,**detail});(OUTPUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)));created=True;settings.DATABASES['default']['NAME']=name
        import django;django.setup()
        from django.core.management import call_command
        from django.contrib.auth.models import User
        from customers.rbac import assign_role
        from customers.models import Area,RestaurantTable,RestaurantInfo,Employee,Position,Shift,WorkSchedule,AttendanceLocationPolicy,Combo,ComboItem,Promotion,Supplier,Booking,Order,Invoice,Payment,Review,Conversation,Message,MenuItem
        from django.utils import timezone
        call_command('migrate',verbosity=0,stdout=io.StringIO());call_command('seed_rbac',stdout=io.StringIO());call_command('seed_menu',stdout=io.StringIO());call_command('seed_module07_recipes',stdout=io.StringIO())
        for role in ['ADMIN','MANAGER','STAFF','CUSTOMER']:
            user=User.objects.create_user('e2e-'+role.lower(),password='LiveDemo_2026!');assign_role(user,role)
        area=Area.objects.create(name='QA only');RestaurantTable.objects.create(area=area,code='QA01',capacity=8)
        Supplier.objects.create(code='QA-SUP',name='QA Supplier');call_command('seed_initial_inventory',stdout=io.StringIO())
        for guests,price in [(2,600000),(4,1100000)]:
            combo=Combo.objects.create(name=f'Combo {guests} người QA',price=price,description='Simulated QA fixture only');ComboItem.objects.create(combo=combo,menu_item_id=1,quantity=guests)
        Promotion.objects.create(code='QA10',name='QA promotion only',discount_type='PERCENT',discount_value=10,start_at=timezone.now()-timezone.timedelta(days=1),end_at=timezone.now()+timezone.timedelta(days=7))
        info=RestaurantInfo.objects.create(name='QA Restaurant',opening_time='08:00',closing_time='23:00',latitude=10.7769,longitude=106.7009)
        AttendanceLocationPolicy.objects.create(restaurant=info,mode='GPS_ONLY')
        staff=User.objects.get(username='e2e-staff');position=Position.objects.create(name='QA Staff');employee=Employee.objects.create(user=staff,employee_code='QA-EMP',full_name='QA Employee',position=position,hire_date=timezone.localdate())
        shift=Shift.objects.create(name='QA shift',start_time=daytime(0),end_time=daytime(23,59));schedule=WorkSchedule(employee=employee,shift=shift,work_date=timezone.localdate(),status='APPROVED');schedule.start_at,schedule.end_at=schedule.window();schedule.save()
        env={**os.environ,'DB_NAME':name,'PYTHONIOENCODING':'utf-8'};log=(OUTPUT/'server.log').open('w',encoding='utf-8');handles.append(log)
        server=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8788','--noreload'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(server)
        for _ in range(120):
            try:urllib.request.urlopen(BASE+'/menu/',timeout=2).close();break
            except Exception:time.sleep(.25)
        manager=HTTP();manager.login('e2e-manager');customer=HTTP();customer.login('e2e-customer');employee_http=HTTP();employee_http.login('e2e-staff')
        routes=['/management/','/management/menu/','/management/categories/','/management/suppliers/','/management/ingredients/','/management/recipes/','/management/stock-alerts/','/management/bookings/','/management/orders/','/management/kitchen/','/management/payments/','/management/stock/receipt/','/management/stock/issue/','/management/areas/','/management/tables/','/management/reports/','/management/ai/','/management/ai/forecast/','/management/ai/inventory/','/management/ai/faces/','/management/ai/chatbot/','/management/ai/faces/test/','/management/settings/location/']
        routes += ['/management/module07/'+resource+'/' for resource in ['employee','position','shift','workschedule','attendance','promotion','combo','topping','restaurantinfo']]+['/reviews/','/management/payroll/']
        for route in routes:
            status,body=manager.get(route);assert status==200 and 'Exception Type:' not in body,route;record('manager_http',{'route':route,'status':status})
        for route in ['/','/menu/','/menu/?max_price=500000&sort=price_asc','/menu/1/','/combos/','/cart/','/booking/','/purchases/','/invoices/','/reviews/','/ai/chat/','/chat/','/about/','/offers/','/account/']:
            status,body=customer.get(route);assert status==200 and 'Exception Type:' not in body,route;record('customer_http',{'route':route,'status':status})
        # Auth + cart + booking on actual HTTP, prices always resolved by services.
        customer.post('/cart/1/',{'quantity':2});status,body=customer.get('/cart/');assert status==200;record('cart_http',{'quantity':2,'status':status})
        future=timezone.localdate()+timezone.timedelta(days=4)
        status,body=customer.post('/booking/',{'name':'QA Customer','phone':'0912345678','date':str(future),'time':'19:00','guests':'4','note':'Isolated E2E'});assert status==200 and 'errorlist' not in body,'booking';record('booking_http',{'status':status,'future_date':str(future)})
        booking=Booking.objects.get(user__username='e2e-customer');manager.post(f'/management/bookings/{booking.pk}/open-order/',{});order=Order.objects.get(booking=booking)
        customer.post(f'/purchases/{order.pk}/voucher/',{'code':'QA10'});order.refresh_from_db();assert order.promotion_id is not None;record('voucher_http',{'discount':str(order.discount_amount),'label':'QA FIXTURE'})
        manager.post(f'/management/orders/{order.pk}/status/',{'status':'CONFIRMED'})
        for line in order.items.all():
            for state in ['PREPARING','READY']:manager.post(f'/management/orders/{order.pk}/items/{line.pk}/kitchen/',{'status':state})
        manager.post(f'/management/orders/{order.pk}/status/',{'status':'PREPARING'});manager.post(f'/management/orders/{order.pk}/status/',{'status':'COMPLETED'});order.refresh_from_db();assert order.status=='COMPLETED';record('order_kitchen_http',{'status':order.status})
        manager.post(f'/management/orders/{order.pk}/invoice/',{});invoice=Invoice.objects.get(order=order);customer.get(f'/invoices/{invoice.pk}/');customer.post(f'/invoices/{invoice.pk}/payments/start/',{'payment_method':'BANK_TRANSFER','request_key':str(uuid.uuid4())});payment=Payment.objects.get(invoice=invoice);customer.post(f'/payments/{payment.pk}/report/',{});manager.post(f'/management/payments/{payment.pk}/confirm/',{'outcome':'success'});invoice.refresh_from_db();assert invoice.status=='PAID';record('invoice_payment_demo_http',{'status':invoice.status,'label':'QA PAYMENT DEMO; no real money'})
        customer.post(f'/purchases/{order.pk}/review/',{'menu_item':'1','rating':'5','comment':'Isolated HTTP review'});assert Review.objects.filter(order=order).exists();record('review_http',{'created':True})
        customer.post('/chat/',{'recipient':User.objects.get(username='e2e-manager').pk});conversation=Conversation.objects.get(is_support=True);customer.post(f'/chat/{conversation.pk}/',{'content':'QA human support HTTP message','request_key':str(uuid.uuid4())});assert Message.objects.filter(conversation=conversation).exists();record('human_chat_http',{'created':True})
        import websocket
        manager_cookie='; '.join(c.name+'='+c.value for c in manager.jar)
        chat_socket=websocket.create_connection(BASE.replace('http://','ws://')+f'/ws/chat/{conversation.pk}/',cookie=manager_cookie,origin=BASE,timeout=15)
        customer.post(f'/chat/{conversation.pk}/',{'content':'QA real WebSocket event','request_key':str(uuid.uuid4())});event=json.loads(chat_socket.recv());chat_socket.close();assert event['type']=='chat.updated';record('human_chat_websocket',{'event_type':event['type'],'transport':'LIVE WebSocket'})
        registration=HTTP();registration.get('/register/');status,raw=registration.post('/register/',{'first_name':'QA Registered','username':'qa-new-user','email':'qa@example.test','password1':'Demo_Register_2026!','password2':'Demo_Register_2026!'});assert User.objects.filter(username='qa-new-user').exists();record('register_http',{'status':status});registration.post('/logout/',{});registration.get('/login/');status,raw=registration.post('/login/',{'username':'qa-new-user','password':'Demo_Register_2026!'});assert status==200;record('logout_login_http',{'status':status})
        # Independent query corpus on live server. Fresh conversations avoid cross-query slot carryover.
        corpus=json.loads((ROOT/'docs/chatbot_realistic_queries.json').read_text(encoding='utf-8'));outcomes=[]
        for expected,queries in corpus['groups'].items():
            for query in queries:
                http=HTTP();http.get('/ai/chat/');status,raw=http.post('/ai/chat/message/',{'message':query},True)
                result=json.loads(raw) if raw.startswith('{') else {'error':'Non-JSON response'}
                tool_names={'MENU_SEARCH':'search_menu','MENU_PRICE':'get_menu_price','MENU_RECOMMENDATION':'recommend_for_current_user','COMBO_INFO':'get_combo_info','BOOKING_AVAILABILITY':'check_booking_availability','MY_ORDER_STATUS':'get_my_order_status','MY_PAYMENT_STATUS':'get_my_payment_status','OPENING_HOURS':'get_restaurant_info','CART_VIEW':'get_my_cart','PROMOTION_INFO':'get_current_promotions','REFUSAL':'input_guard','OUT_OF_SCOPE':'input_guard','UNKNOWN':'rag_retrieval'}
                entity_expected=corpus.get('price_expectations',{}).get(query)
                entity_passed=all(result.get('entities',{}).get(k)==v for k,v in entity_expected.items()) if entity_expected else None
                grounded=None
                if expected=='MENU_PRICE' and result.get('menu_ids'):
                    from customers.menu_service import format_money
                    current=MenuItem.objects.get(pk=result['menu_ids'][0]);grounded=current.name in result.get('answer','') and format_money(current.price) in result.get('answer','')
                if entity_expected and result.get('menu_ids'):
                    selected=list(MenuItem.objects.filter(pk__in=result['menu_ids']))
                    grounded=all(item.is_available and (entity_expected.get('min_price',0)<=item.price<=entity_expected.get('max_price',float('inf'))) for item in selected)
                outcomes.append({'query':query,'expected_intent':expected,'http_status':status,'result':result,'intent_correct':result.get('intent')==expected,'tool_correct':result.get('tool')==tool_names.get(expected),'entity_assertion_passed':entity_passed,'grounding_assertion_passed':grounded})
        conversations=[]
        for conversation in corpus['conversations']:
            http=HTTP();http.get('/ai/chat/');responses=[]
            for query in conversation['turns']:
                status,raw=http.post('/ai/chat/message/',{'message':query},True);responses.append(json.loads(raw))
            slots=conversation.get('expected_slots');tool=conversation.get('expected_tool')
            passed=all(responses[-1].get('entities',{}).get(k)==v for k,v in slots.items()) if slots else responses[-1].get('tool')==tool
            conversations.append({**conversation,'responses':responses,'context_assertion_passed':passed})
        (OUTPUT/'chatbot_live_results.json').write_text(json.dumps({'queries':outcomes,'conversations':conversations},ensure_ascii=False,indent=2),encoding='utf-8')
        fallback=sum('chưa có đủ thông tin' in o['result'].get('answer','') for o in outcomes);incorrect=sum('chưa có đủ thông tin' in o['result'].get('answer','') and o['expected_intent'] not in ['UNKNOWN','OUT_OF_SCOPE','REFUSAL'] for o in outcomes)
        entity_scored=[o for o in outcomes if o['entity_assertion_passed'] is not None]
        grounded_scored=[o for o in outcomes if o['grounding_assertion_passed'] is not None]
        results['chatbot']={'query_count':len(outcomes),'conversation_count':len(conversations),'intent_accuracy':sum(o['intent_correct'] for o in outcomes)/len(outcomes),'tool_accuracy':sum(o['tool_correct'] for o in outcomes)/len(outcomes),'price_entity_accuracy':sum(o['entity_assertion_passed'] for o in entity_scored)/len(entity_scored),'context_slot_accuracy':sum(c['context_assertion_passed'] for c in conversations)/len(conversations),'fallback_rate':fallback/len(outcomes),'incorrect_fallback_rate':incorrect/len(outcomes),'http_errors':sum(o['http_status']!=200 for o in outcomes),'method':'Independent authored acceptance corpus, actual HTTP against isolated DB; assertion proxy, not human accuracy.'}
        results['chatbot']['grounding_assertion_count']=len(grounded_scored);results['chatbot']['grounding_assertion_accuracy']=sum(o['grounding_assertion_passed'] for o in grounded_scored)/len(grounded_scored) if grounded_scored else None
        # Actual HTTP with simulated position; no real GPS evidence claimed.
        point={'latitude':10.7769,'longitude':106.7009,'accuracy':10};status,raw=employee_http.post('/work/location/check/',{'location':point},True);assert status==200 and json.loads(raw)['geo_status']=='ALLOWED';record('gps_mock_http',{'status':status,'geo_status':'ALLOWED','evidence':'AUTOMATED MOCK'})
        # Browser attempt: installed Edge, ASCII cache path, no document injection.
        chrome_log=(OUTPUT/'browser.log').open('w',encoding='utf-8');handles.append(chrome_log)
        with tempfile.TemporaryDirectory(prefix='sr-live-',ignore_cleanup_errors=True) as profile:
            binary=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
            browser=subprocess.Popen([str(binary),'--headless=new','--no-first-run','--no-default-browser-check','--no-proxy-server','--disable-extensions','--remote-debugging-port=9338','--user-data-dir='+profile,'about:blank'],stdout=chrome_log,stderr=chrome_log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(browser)
            for _ in range(100):
                try:targets=json.load(urllib.request.urlopen('http://127.0.0.1:9338/json',timeout=2));break
                except Exception:time.sleep(.2)
            import websocket;target=next(t for t in targets if t['type']=='page');ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=20,suppress_origin=True);counter=0;errors=[]
            def cdp(method,params=None):
                nonlocal counter
                counter+=1;identifier=counter;ws.send(json.dumps({'id':identifier,'method':method,'params':params or {}}))
                while True:
                    response=json.loads(ws.recv())
                    if response.get('method') in ['Runtime.exceptionThrown','Network.loadingFailed']:errors.append(response)
                    if response.get('id')==identifier:
                        if response.get('error'):raise RuntimeError(response['error'])
                        return response.get('result',{})
            def js(expression):return cdp('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True}).get('result',{}).get('value')
            cdp('Page.enable');cdp('Runtime.enable');cdp('Network.enable');navigation=cdp('Page.navigate',{'url':BASE+'/menu/'})
            if navigation.get('errorText'):raise RuntimeError('Browser live navigation '+navigation['errorText'])
            for _ in range(100):
                if js('document.readyState === "complete" && !!document.querySelector(".dish-card")'):break
                time.sleep(.2)
            assert js('location.href').startswith(BASE),'Browser did not navigate live';assert js('document.querySelectorAll(".dish-card").length')>0
            checks=[]
            for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.3)
                checks.append({'width':width,'height':height,'horizontal_overflow':js('document.documentElement.scrollWidth > innerWidth')})
                try:shot=cdp('Page.captureScreenshot',{'format':'png'});(OUTPUT/f'menu-{width}.png').write_bytes(__import__('base64').b64decode(shot['data']))
                except Exception as exc:results['screenshot_error']=str(exc);break
            # Real browser navigation across critical management/customer pages.
            pages=[]
            for role,http,paths in [('manager',manager,['/management/','/management/menu/','/management/ai/','/management/ai/faces/','/management/ai/faces/test/','/management/ai/faces/'+str(employee.pk)+'/enrollment/','/management/settings/location/','/management/reports/']),('customer',customer,['/','/ai/chat/','/cart/','/booking/','/purchases/']),('staff',employee_http,['/work/faceid/'])]:
                for cookie in http.jar:
                    cdp('Network.setCookie',{'name':cookie.name,'value':cookie.value,'url':BASE+'/'})
                for page_index,path in enumerate(paths):
                    navigation=cdp('Page.navigate',{'url':BASE+path});assert not navigation.get('errorText'),navigation
                    for _ in range(120):
                        if js('document.readyState === "complete" && !!document.querySelector("h1")'):break
                        time.sleep(.1)
                    if not js('!!document.querySelector("h1")'): raise RuntimeError('Missing rendered content on '+path+'; inspect console/static scripts')
                    for width,height in [(1366,768),(768,1024),(390,844)]:
                        cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.15)
                        page_result={'role':role,'path':path,'width':width,'horizontal_overflow':js('document.documentElement.scrollWidth > innerWidth'),'heading':js('document.querySelector("h1")?.textContent'),'method':'LIVE HTTP'}
                        pages.append(page_result)
                        shot=cdp('Page.captureScreenshot',{'format':'png'});(OUTPUT/f'{role}-{page_index}-{width}.png').write_bytes(__import__('base64').b64decode(shot['data']))
            # UI geolocation uses a DevTools override: explicitly MOCK evidence.
            cdp('Browser.grantPermissions',{'permissions':['geolocation'],'origin':BASE})
            cdp('Emulation.setGeolocationOverride',{'latitude':10.7769,'longitude':106.7009,'accuracy':10})
            js('document.querySelector("[data-location-start]").click(); true')
            for _ in range(120):
                if js('document.querySelector(".geo-status").textContent.includes("trong phạm vi")'):break
                time.sleep(.1)
            assert js('document.querySelector(".geo-status").textContent.includes("trong phạm vi")'),'GPS UI mock result'
            js('document.querySelector("[data-punch=in]").click(); true')
            for _ in range(120):
                if js('document.querySelector("[data-face-result]").textContent.includes("Chấm công thành công")'):break
                time.sleep(.1)
            assert js('document.querySelector("[data-face-result]").textContent.includes("Chấm công thành công")'),'GPS_ONLY attendance UI'
            record('browser_gps_attendance',{'result':'PASS','policy':'GPS_ONLY','evidence':'DEVTOOLS GPS AUTOMATED MOCK; no FaceID or real GPS claim'})
            for cookie in customer.jar:cdp('Network.setCookie',{'name':cookie.name,'value':cookie.value,'url':BASE+'/'})
            cdp('Page.navigate',{'url':BASE+'/ai/chat/'})
            for _ in range(100):
                if js('!!document.querySelector(".assistant-page [data-ai-chat]")'):break
                time.sleep(.1)
            js('(()=>{const f=document.querySelector(".assistant-page [data-ai-chat]");f.querySelector("textarea").value="món dưới 500k";f.requestSubmit();return true;})()')
            for _ in range(120):
                if js('document.querySelectorAll(".assistant-page .chat-message.assistant").length >= 2 && !document.querySelector(".assistant-page [aria-busy=true]")'):break
                time.sleep(.1)
            assert js('document.querySelector(".assistant-page .assistant-messages").textContent.includes("289.000")'),'AI bubble live result'
            record('browser_chat_bubbles',{'result':'PASS','transport':'LIVE fetch + CSRF'})
            cdp('Page.navigate',{'url':BASE+'/menu/'})
            for _ in range(100):
                if js('!!document.querySelector(".menu-filters input[name=max_price]")'):break
                time.sleep(.1)
            js('document.querySelector(".menu-filters input[name=max_price]").value="500000";document.querySelector(".menu-filters").requestSubmit();true')
            for _ in range(100):
                if js('location.search.includes("max_price=500000") && document.readyState === "complete"'):break
                time.sleep(.1)
            assert js('location.search.includes("max_price=500000")'),'Browser menu price filter'
            js('document.querySelector(".dish-card .add-form").requestSubmit();true')
            for _ in range(100):
                if js('Number(document.querySelector(".cart-count").textContent)>0'):break
                time.sleep(.1)
            assert js('Number(document.querySelector(".cart-count").textContent)>0'),'Browser cart add'
            record('browser_menu_filter_cart',{'result':'PASS','transport':'GET filter + POST fetch/CSRF'})
            results['browser']={'mode':'LIVE HTTP EDGE','checks':checks,'pages':pages,'console_errors':errors}
            ws.close();ws=None;browser.terminate();browser.wait(timeout=15);processes.remove(browser)
    except Exception as exc:
        results['error']=str(exc);print(str(exc),flush=True)
    finally:
        if ws:ws.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for handle in handles:handle.close()
        from django.db import connections
        connections.close_all()
        if created:admin.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',(name,));admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        admin.close();results['temporary_database_deleted']=created;(OUTPUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(results,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
