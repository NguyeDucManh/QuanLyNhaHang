"""Scoped LIVE HTTP/Edge QA. GPS/camera are mocks; no real biometric enrollment."""
import base64,io,json,os,sys,time,tempfile,subprocess,urllib.request,uuid
from datetime import time as daytime
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
from django.conf import settings
import psycopg
from psycopg import sql
import final_live_e2e as transport
BASE='http://127.0.0.1:8795';transport.BASE=BASE
OUT=ROOT/'qa_customer_booking';OUT.mkdir(exist_ok=True)

def main():
    db=settings.DATABASES['default'].copy();name='sr_booking_qa_'+uuid.uuid4().hex[:10]
    admin=psycopg.connect(host=db['HOST'],port=db['PORT'],user=db['USER'],password=db['PASSWORD'],dbname='postgres',autocommit=True)
    processes=[];handles=[];ws=None;created=False
    result={'label':'ISOLATED QA; mock GPS and mock camera only','real_webcam':'NOT TESTED','real_gps':'NOT TESTED','real_biometric_accuracy':'NOT MEASURED','checks':[],'pages':[],'exceptions':[],'network_failures':[],'http_errors':[]}
    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)));created=True;settings.DATABASES['default']['NAME']=name
        import django;django.setup()
        from django.core.management import call_command
        from django.contrib.auth.models import User
        from django.utils import timezone
        from customers.rbac import assign_role
        from customers.models import Position,Employee,RestaurantInfo,AttendanceLocationPolicy,Shift,WorkSchedule,Attendance,AttendanceLocationEvent,FaceProfile,Message
        call_command('migrate',verbosity=0,stdout=io.StringIO());call_command('seed_rbac',stdout=io.StringIO())
        clients={};users={}
        for role in ['ADMIN','MANAGER','STAFF','CUSTOMER']:
            user=User.objects.create_user('face-qa-'+role.lower(),password='LiveDemo_2026!',first_name='QA',last_name=role);assign_role(user,role);users[role]=user
        position=Position.objects.create(name='QA Fixture Position')
        employee=Employee.objects.create(user=users['STAFF'],employee_code='NV-QA',full_name='QA Fixture Employee',position=position,hire_date=timezone.localdate())
        demo_user=User.objects.create_user('demo_m07_face_qa',password='Unused-QA');assign_role(demo_user,'STAFF')
        demo=Employee.objects.create(user=demo_user,employee_code='DEMO-UQA',full_name='Hidden seed employee',position=position,hire_date=timezone.localdate())
        restaurant=RestaurantInfo.objects.create(name='QA Restaurant',address='QA only, no real location evidence',latitude=10,longitude=106,opening_time='08:00',closing_time='23:00')
        AttendanceLocationPolicy.objects.create(restaurant=restaurant,mode='GPS_ONLY')
        shift=Shift.objects.create(name='QA Shift',start_time=daytime(0),end_time=daytime(23,59))
        schedule=WorkSchedule(employee=employee,shift=shift,work_date=timezone.localdate(),status='APPROVED');schedule.start_at,schedule.end_at=schedule.window();schedule.save()

        from django.contrib.auth.models import Permission
        from customers.models import PayrollPeriod,Payroll,Attendance
        from customers import personnel_service as hr
        from customers.module07_forms import AttendanceForm
        from customers.chat_service import create_conversation,send_message
        call_command('seed_menu',stdout=io.StringIO())
        from customers.models import MenuItem,Order
        from customers.order_service import create_order,transition_order
        from customers.kitchen_service import transition_kitchen_item
        qa_order=create_order(actor=users['MANAGER'],items=[{'menu_item':item,'quantity':index+1} for index,item in enumerate(MenuItem.objects.filter(is_available=True).order_by('pk')[:3])],request_key=uuid.uuid4(),note='SIMULATED QA order only')
        transition_order(qa_order.pk,'CONFIRMED',actor=users['MANAGER'])
        lines=list(qa_order.items.order_by('pk'))
        transition_kitchen_item(qa_order.pk,lines[0].pk,'PREPARING',actor=users['MANAGER']);transition_kitchen_item(qa_order.pk,lines[0].pk,'READY',actor=users['MANAGER'])
        transition_kitchen_item(qa_order.pk,lines[1].pk,'PREPARING',actor=users['MANAGER'])
        users['STAFF'].user_permissions.add(Permission.objects.get(codename='view_menuitem',content_type__app_label='customers'))
        employee.base_salary=9000000;employee.save()
        prior=WorkSchedule(employee=employee,shift=shift,work_date=timezone.localdate()-timezone.timedelta(days=1),status='APPROVED');prior.start_at,prior.end_at=prior.window();prior.save()
        form=AttendanceForm({'work_schedule':prior.pk,'check_in_time':prior.start_at.isoformat(),'check_out_time':(prior.start_at+timezone.timedelta(hours=8)).isoformat(),'status':'PRESENT','note':'SIMULATED QA fixture; not hardware evidence'})
        assert form.is_valid(),form.errors
        attendance=hr.save_attendance(form,actor=users['MANAGER'])
        today=timezone.localdate();period=PayrollPeriod.objects.create(name='Kỳ lương QA',start_date=today.replace(day=1),end_date=today.replace(day=28))
        payroll=hr.calculate_payroll(employee.pk,period.pk,actor=users['MANAGER'])
        conversation=create_conversation(actor=users['MANAGER'],recipient_id=users['STAFF'].pk)
        send_message(actor=users['MANAGER'],conversation_id=conversation.pk,content='Chào bạn, ca hôm nay đã được duyệt.',request_key=uuid.uuid4())
        from customers.models import Combo,ComboItem,Booking,Area,RestaurantTable,Topping
        qa_top=Topping.objects.create(name='QA topping',price=15000)
        qa_top.menu_items.add(MenuItem.objects.order_by('pk').first())
        from customers.booking_service import create_booking
        from django.contrib.auth.models import Permission
        area=Area.objects.create(name='Không gian kiểm tra')
        RestaurantTable.objects.create(code='B01',area=area,capacity=4)
        RestaurantTable.objects.create(code='B02',area=area,capacity=6)
        users['MANAGER'].user_permissions.add(Permission.objects.get(codename='add_booking',content_type__app_label='customers'))
        qa_combo=Combo.objects.create(name='Combo bò DEMO',price=500000)
        ComboItem.objects.create(combo=qa_combo,menu_item=MenuItem.objects.order_by('pk').first(),quantity=2)
        future=create_booking(user=users['CUSTOMER'],name='Khách kiểm tra sắp tới',phone='0912345678',date=timezone.localdate()+timezone.timedelta(days=1),time=daytime(18),guests=2)
        Booking.objects.create(user=users['CUSTOMER'],name='Khách kiểm tra hôm nay',phone='0912345678',date=timezone.localdate(),time=daytime(12),guests=2,status='COMPLETED')
        Booking.objects.create(user=users['CUSTOMER'],name='Khách đã hủy',phone='0912345678',date=timezone.localdate()-timezone.timedelta(days=1),time=daytime(12),guests=2,status='CANCELLED')
        restaurant.address='123 Đường Nhà Hàng DEMO';restaurant.email='demo@restaurant.example';restaurant.phone='0000000000';restaurant.save()
        call_command('clean_operational_demo_labels',apply=True,allow_test_database=True,stdout=io.StringIO())
        env={**os.environ,'DB_NAME':name,'PYTHONIOENCODING':'utf-8','FACEID_REQUIRE_LIVENESS':'false'}
        log=(OUT/'server.log').open('w',encoding='utf-8');handles.append(log)
        process=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8795','--noreload'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(process)
        for _ in range(120):
            try:urllib.request.urlopen(BASE+'/login/',timeout=2).close();break
            except Exception:time.sleep(.25)
        for role in users:
            clients[role]=transport.HTTP();clients[role].login(users[role].username)
        paths=['/management/ai/faces/','/management/ai/faces/test/',f'/management/ai/faces/{employee.pk}/enrollment/','/management/settings/location/']
        for path in paths:
            status,body=clients['MANAGER'].get(path);assert status==200,path
            result['checks'].append({'kind':'manager_HTTP','path':path,'status':status})
        _,body=clients['MANAGER'].get(paths[0]);assert 'DEMO-UQA' not in body and 'NV-QA' in body
        assert Employee.objects.filter(pk=demo.pk).exists()
        result['checks'].append({'kind':'seed_hidden_without_delete','result':'PASS'})
        for role in ['CUSTOMER','STAFF']:
            try:clients[role].get(paths[0]);raise AssertionError('Expected 403')
            except urllib.error.HTTPError as error:assert error.code==403
        point={'latitude':10,'longitude':106,'accuracy':5}
        for data in [{'schedule':schedule.pk,'action':'in','location':{**point,'longitude':107},'inside':True,'verified':True},{'schedule':schedule.pk,'action':'in','location':None,'verified':True}]:
            status,_=clients['STAFF'].post('/work/attendance/verify/',data,True);assert status==400
        assert Attendance.objects.count()==1
        result['checks'].append({'kind':'spoof_and_missing_GPS_denied','result':'PASS'})
        browser_log=(OUT/'browser.log').open('w',encoding='utf-8');handles.append(browser_log)
        with tempfile.TemporaryDirectory(prefix='sr-face-',ignore_cleanup_errors=True) as profile:
            browser=subprocess.Popen(['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','--headless=new','--no-first-run','--no-default-browser-check','--no-proxy-server','--disable-extensions','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--remote-debugging-port=9344','--user-data-dir='+profile,'about:blank'],stdout=browser_log,stderr=browser_log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(browser)
            for _ in range(100):
                try:targets=json.load(urllib.request.urlopen('http://127.0.0.1:9344/json',timeout=2));break
                except Exception:time.sleep(.2)
            import websocket
            ws=websocket.create_connection(next(t for t in targets if t['type']=='page')['webSocketDebuggerUrl'],timeout=30,suppress_origin=True);counter=0;request_urls={}
            def cdp(method,params=None):
                nonlocal counter
                counter+=1;identifier=counter;ws.send(json.dumps({'id':identifier,'method':method,'params':params or {}}))
                while True:
                    response=json.loads(ws.recv())
                    if response.get('method')=='Network.requestWillBeSent':request_urls[response['params']['requestId']]=response['params']['request']['url']
                    if response.get('method')=='Network.responseReceived' and response['params']['response']['status']>=400:
                        result['http_errors'].append({'url':response['params']['response']['url'],'status':response['params']['response']['status']})
                    if response.get('method')=='Runtime.exceptionThrown':result['exceptions'].append(response)
                    if response.get('method')=='Network.loadingFailed':
                        response['url']=request_urls.get(response['params']['requestId'],'unknown');result['network_failures'].append(response)
                    if response.get('id')==identifier:
                        if response.get('error'):raise RuntimeError(response['error'])
                        return response.get('result',{})
            def js(expression):
                response=cdp('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
                if response.get('exceptionDetails'):raise RuntimeError(str(response['exceptionDetails']))
                return response.get('result',{}).get('value')
            def navigate(path):
                cdp('Page.navigate',{'url':BASE+path})
                for _ in range(100):
                    if js('location.href==='+json.dumps(BASE+path)+' && document.readyState==="complete" && !!document.querySelector("h1")'):break
                    time.sleep(.1)
                time.sleep(.15)
            def cookies(role):
                cdp('Page.navigate',{'url':'about:blank'})
                for _ in range(50):
                    if js('location.href==="about:blank" && document.readyState==="complete"'):break
                    time.sleep(.05)
                for cookie in clients[role].jar:cdp('Network.setCookie',{'name':cookie.name,'value':cookie.value,'url':BASE+'/'})
            cdp('Page.enable');cdp('Runtime.enable');cdp('Network.enable')
            cookies('CUSTOMER')
            def wait_for(expression):
                for _ in range(100):
                    if js(expression): return
                    time.sleep(.1)
                raise AssertionError('Browser condition timed out: '+expression)
            def snapshot(label,path=None):
                for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                    cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700})
                    if path: navigate(path)
                    time.sleep(.15)
                    assert not js('document.documentElement.scrollWidth>innerWidth'),(label,width)
                    result['pages'].append({'label':label,'width':width,'height':height,'horizontal_overflow':False})
                    size=cdp('Page.getLayoutMetrics')['cssContentSize']
                    (OUT/f'{label}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})['data']))
            navigate('/booking/?view=new')
            assert js('!!document.querySelector("#booking-form") && !document.querySelector("#booking-list")')
            data={'name':'Khách luồng đặt bàn QA','phone':'0912345678','date':str(timezone.localdate()+timezone.timedelta(days=5)),'time':'19:00','guests':'3','note':'Giữ bàn yên tĩnh, không cay'}
            js('(()=>{const data='+json.dumps(data)+';for(const [k,v] of Object.entries(data)){const el=document.querySelector("#booking-form [name="+k+"]");el.value=v;el.dispatchEvent(new Event("input",{bubbles:true}));}})()')
            snapshot('new-draft')
            before={'booking':Booking.objects.count(),'order':Order.objects.count()}
            js('document.querySelector("button[name=intent][value=menu]").click()')
            wait_for('location.pathname==="/menu/" && location.search==="?from=booking" && !!document.querySelector("[data-booking-menu-bar]")')
            assert Booking.objects.count()==before['booking'] and Order.objects.count()==before['order']
            item=MenuItem.objects.order_by('pk').first()
            navigate('/menu/'+str(item.pk)+'/?from=booking')
            wait_for('!!document.querySelector(".add-form [name=quantity]")')
            js('document.querySelector(".add-form [name=quantity]").value="2";document.querySelector(".add-form [name=toppings]").checked=true;document.querySelector(".add-form button").click()')
            wait_for('document.querySelector("[data-booking-cart-count]").textContent==="2"')
            navigate('/menu/?from=booking')
            js('document.querySelector("form[action*=combos] button").click()')
            wait_for('document.querySelector("[data-booking-cart-count]").textContent==="4"')
            snapshot('menu-booking')
            assert js('getComputedStyle(document.querySelector(".chat-launcher")).display==="none"')
            js('document.querySelector("[data-booking-menu-done]").click()')
            wait_for('location.pathname==="/booking/" && !!document.querySelector("#booking-form")')
            for key,value in data.items():
                assert js('document.querySelector("#booking-form [name='+key+']").value')==value,(key,value)
            assert js('document.querySelectorAll(".booking-food .cart-item").length===1')
            assert js('document.querySelector(".booking-food").innerText.includes("QA topping")')
            assert js('document.querySelector(".booking-food").innerText.includes("Combo")')
            snapshot('restored')
            js('document.querySelector("button[name=intent][value=confirm]").click()')
            wait_for('!!document.querySelector("[data-booking-confirmation]")')
            created_booking=Booking.objects.get(name=data['name'])
            assert created_booking.preorder_items.count()==3, list(created_booking.preorder_items.values('quantity','extras'))
            assert Order.objects.count()==before['order']
            assert js('document.querySelector("[data-payment-state=unavailable] button").disabled')
            assert not js('!!document.querySelector("#booking-form") || !!document.querySelector("#booking-list")')
            snapshot('confirmation')
            result['checks'].append({'kind':'browser_draft_food_quantity_topping_combo_return_confirm_existing_service','result':'PASS','booking_items':created_booking.preorder_items.count(),'order_created':False})
            navigate('/booking/?view=mine')
            assert not js('!!document.querySelector("#booking-form")')
            assert js('document.body.innerText.includes('+json.dumps(data['name'])+')')
            snapshot('mine')
            # Exercise the real order/kitchen/invoice services in the isolated QA DB.
            from customers.order_service import open_order_from_booking
            from customers.payment_service import issue_invoice,create_payment,confirm_payment,report_customer_payment
            order=open_order_from_booking(created_booking.pk,actor=users['MANAGER'])
            transition_order(order.pk,'CONFIRMED',actor=users['MANAGER'])
            transition_order(order.pk,'PREPARING',actor=users['MANAGER'])
            for line in order.items.all():
                transition_kitchen_item(order.pk,line.pk,'PREPARING',actor=users['MANAGER'])
                transition_kitchen_item(order.pk,line.pk,'READY',actor=users['MANAGER'])
            transition_order(order.pk,'COMPLETED',actor=users['MANAGER'])
            invoice=issue_invoice(order.pk,actor=users['MANAGER'])
            snapshot('mine-payable','/booking/?view=mine&tab=history')
            assert js('document.querySelector("[data-payment-state=payable] a").getAttribute("href")')=='/invoices/'+str(invoice.pk)+'/'
            js('document.querySelector("[data-payment-state=payable] a").click()')
            wait_for('location.pathname==="/invoices/'+str(invoice.pk)+'/" && document.readyState==="complete"')
            payment=create_payment(invoice_id=invoice.pk,actor=users['CUSTOMER'],customer_initiated=True,payment_method='CASH',request_key=uuid.uuid4())
            snapshot('mine-pending','/booking/?view=mine&tab=history')
            assert js('!!document.querySelector("[data-payment-state=pending]")')
            report_customer_payment(payment.pk,actor=users['CUSTOMER'])
            confirm_payment(payment.pk,actor=users['MANAGER'])
            snapshot('mine-paid','/booking/?view=mine&tab=history')
            assert js('!!document.querySelector("[data-payment-state=paid]")')
            result['checks'].append({'kind':'real_service_order_kitchen_invoice_payment_lifecycle_QA_only','result':'PASS'})
            snapshot('normal-menu','/menu/')
            assert not js('!!document.querySelector("[data-booking-menu-bar]")')
            for tab in ['upcoming','completed','cancelled','history']:
                navigate('/booking/?view=mine&tab='+tab)
                assert not js('!!document.querySelector("#booking-form")')
            assert not result['exceptions'],result['exceptions']
            assert not result['http_errors'],result['http_errors']
            ws.close();ws=None

        result['success']=True
    except Exception as exc:
        import traceback
        result['error']=str(exc);result['traceback']=traceback.format_exc();result['success']=False
    finally:
        if ws:ws.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for handle in handles:handle.close()
        from django.db import connections
        connections.close_all()
        if created:
            admin.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',(name,));admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        admin.close();result['QA_database_deleted']=created;(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True))
    return 0 if result.get('success') else 1

if __name__=='__main__':sys.exit(main())
