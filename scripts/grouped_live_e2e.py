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
BASE='http://127.0.0.1:8793';transport.BASE=BASE
OUT=ROOT/'qa_grouped';OUT.mkdir(exist_ok=True)

def main():
    db=settings.DATABASES['default'].copy();name='sr_grouped_qa_'+uuid.uuid4().hex[:10]
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
        from customers.models import MenuItem
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
        from customers.models import Combo,ComboItem,Booking,Area,RestaurantTable
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
        process=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8793','--noreload'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(process)
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
            browser=subprocess.Popen(['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','--headless=new','--no-first-run','--no-default-browser-check','--no-proxy-server','--disable-extensions','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--remote-debugging-port=9342','--user-data-dir='+profile,'about:blank'],stdout=browser_log,stderr=browser_log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(browser)
            for _ in range(100):
                try:targets=json.load(urllib.request.urlopen('http://127.0.0.1:9342/json',timeout=2));break
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
            for role,routes in [('MANAGER',paths+['/management/','/management/menu/','/management/orders/','/management/kitchen/','/management/module07/employee/','/management/payroll/','/management/bookings/','/management/tables/']),('STAFF',['/staff/','/work/?tab=schedule','/work/faceid/','/payroll/'+str(payroll.pk)+'/', '/chat/'+str(conversation.pk)+'/', '/account/', '/management/menu/', '/management/kitchen/', '/management/orders/'])]:
                cookies(role)
                for index,path in enumerate(routes):
                    navigate(path)
                    for width,height in [(1366,768),(1920,1080),(768,1024),(390,844)]:
                        cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.15)
                        assert not js('/demo/i.test(document.body.innerText)'),(role,path,'visible marker')
                        overflow=js('document.documentElement.scrollWidth>innerWidth');assert not overflow,(path,width)
                        result['pages'].append({'role':role,'path':path,'width':width,'height':height,'horizontal_overflow':overflow})
                        if path.endswith('/test/'):
                            geometry=js('(()=>{const v=document.querySelector(".face-camera-viewport").getBoundingClientRect(),g=document.querySelector(".face-guide").getBoundingClientRect(),c=document.querySelector(".face-guide-caption").getBoundingClientRect(),h=document.querySelector(".face-hud-bottom").getBoundingClientRect();return {width_ratio:g.width/v.width,height_ratio:g.height/v.height,caption_below_oval:c.top>=g.bottom,hud_below_oval:h.top>=g.bottom};})()')
                            assert .70<=geometry['width_ratio']<=.78 if width<600 else .45<=geometry['width_ratio']<=.55,geometry
                            assert .55<=geometry['height_ratio']<=.65 if width<600 else .60<=geometry['height_ratio']<=.70,geometry
                            assert geometry['caption_below_oval'] and geometry['hud_below_oval'],geometry
                            result['pages'][-1]['face_guide_geometry']=geometry
                        (OUT/f'{role.lower()}-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
                        if path=='/management/' and width==1366:
                            size=cdp('Page.getLayoutMetrics')['cssContentSize'];(OUT/'manager-dashboard-full-1366.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})['data']))
            navigate('/work/faceid/')
            assert js('!document.querySelector("[data-location-map]")'),'Attendance mini map must be absent'
            assert js('!!document.querySelector(".face-guide") && !!document.querySelector("[data-live-time]")')
            before=AttendanceLocationEvent.objects.count()
            cdp('Browser.grantPermissions',{'permissions':['geolocation'],'origin':BASE});cdp('Emulation.setGeolocationOverride',{'latitude':10,'longitude':106,'accuracy':5})
            js('document.querySelector("[data-location-start]").click();true')
            for _ in range(100):
                if js('document.querySelector(".geo-status").textContent.includes("Trong phạm vi")'):break
                time.sleep(.1)
            assert js('!document.querySelector("[data-punch=in]").disabled')
            assert AttendanceLocationEvent.objects.count()==before,'watch must not log movement'
            result['checks'].append({'kind':'watchPosition_HUD_no_DB_writes','result':'PASS','evidence':'AUTOMATED GPS MOCK'})
            js('document.querySelector("[data-punch=in]").click();true')
            for _ in range(100):
                if js('document.querySelector("[data-face-result]").textContent.includes("CHẤM CÔNG THÀNH CÔNG")'):break
                time.sleep(.1)
            assert Attendance.objects.filter(employee=employee,work_schedule=schedule,check_in_time__isnull=False).exists()
            for _ in range(100):
                if js('!document.querySelector("[data-punch=out]").disabled'):break
                time.sleep(.1)
            js('document.querySelector("[data-punch=out]").click();true')
            for _ in range(100):
                if Attendance.objects.filter(employee=employee,work_schedule=schedule,check_out_time__isnull=False).exists():break
                time.sleep(.1)
            assert Attendance.objects.filter(employee=employee,work_schedule=schedule,check_out_time__isnull=False).exists()
            result['checks'].append({'kind':'GPS_ONLY_checkin_checkout_UI_existing_service','result':'PASS','evidence':'AUTOMATED GPS MOCK'})
            policy=AttendanceLocationPolicy.objects.get(restaurant=restaurant);policy.mode='FACE_AND_GPS';policy.save()
            navigate('/work/faceid/')
            for width,height in [(1366,768),(1920,1080),(768,1024),(390,844)]:
                cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                assert js('!document.querySelector(".face-guide").hidden && !document.querySelector("[data-location-map]")')
                assert not js('document.documentElement.scrollWidth>innerWidth')
                (OUT/f'attendance-face-gps-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            # Mock device is synthetic color bars, not a person's biometric data.
            cookies('MANAGER');navigate('/management/ai/faces/test/')
            assert js('!document.querySelector("script[src*=leaflet]") && !document.querySelector("link[href*=leaflet]")'),'No Leaflet on camera page'
            before_events=AttendanceLocationEvent.objects.count()
            before_attendance=Attendance.objects.count()
            before_checks=len([url for url in request_urls.values() if '/work/location/check/' in url])
            # Far outside the restaurant: display-only test GPS cannot gate recognition.
            cdp('Emulation.setGeolocationOverride',{'latitude':11,'longitude':107,'accuracy':25})
            js('document.querySelector("[data-location-start]").click();true')
            for _ in range(100):
                if js('document.querySelector("[data-location-text]").textContent.includes("11.000000")'):break
                time.sleep(.1)
            assert js('document.querySelector("[data-location-text]").textContent.includes("Vĩ độ: 11.000000") && !document.querySelector("[data-recognize]").disabled')
            assert AttendanceLocationEvent.objects.count()==before_events
            assert len([url for url in request_urls.values() if '/work/location/check/' in url])==before_checks
            result['checks'].append({'kind':'test_GPS_HUD_display_only_no_server_polling','result':'PASS','evidence':'AUTOMATED GPS MOCK'})
            js('document.querySelector("[data-recognize]").click();true')
            for _ in range(200):
                if js('document.querySelector("video").srcObject?.active===true'):break
                time.sleep(.1)
            assert js('document.querySelector("video").srcObject?.active===true'),'Mock camera start'
            (OUT/'camera-mock-live.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            js('window.qaTracks=document.querySelector("video").srcObject.getTracks();document.querySelector("[data-stop]").click();true')
            assert js('window.qaTracks.every(track=>track.readyState==="ended") && document.querySelector("video").srcObject===null')
            result['checks'].append({'kind':'camera_start_stop','result':'PASS','evidence':'AUTOMATED SYNTHETIC CAMERA; no face recognition claim'})
            cdp('Browser.setPermission',{'permission':{'name':'geolocation'},'setting':'denied','origin':BASE})
            js('document.querySelector("[data-location-start]").click();true')
            for _ in range(100):
                if js('document.querySelector(".geo-status").textContent.includes("Không lấy được vị trí")'):break
                time.sleep(.1)
            assert js('document.querySelector(".geo-status").textContent.includes("Vui lòng cấp quyền vị trí")')
            result['checks'].append({'kind':'GPS_permission_denied_Vietnamese_UI','result':'PASS','evidence':'AUTOMATED BROWSER PERMISSION'})
            assert js('FaceUI.label("PROVISIONAL")==="Ngưỡng tạm thời" && FaceUI.timestamp("2026-10-14T03:19:14Z").includes("10:19:14")')
            for relative in ['static/ai/face-ui-vi.js','static/ai/face-realtime.js','static/ai/face-flow.js']:
                assert js('(()=>{new Function('+json.dumps((ROOT/relative).read_text(encoding='utf-8'))+');return true;})()')
            assert not result['exceptions'],result['exceptions']
            assert Attendance.objects.count()==before_attendance,'Face test cannot create attendance'
            assert FaceProfile.objects.count()==0,'No synthetic biometric enrollment created'

            cookies('STAFF');navigate('/staff/')
            assert js('document.body.classList.contains("staff-portal") && !!document.querySelector(".staff-sidebar")')
            assert js('!document.querySelector(".site-footer") && !document.querySelector("video")')
            cdp('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            js('document.querySelector("[data-staff-toggle]").click();true')
            assert js('document.body.classList.contains("staff-nav-open")')
            js('document.querySelector("[data-staff-close]").click();true')
            assert js('!document.body.classList.contains("staff-nav-open") && getComputedStyle(document.querySelector(".staff-bottom-nav")).display!=="none"')
            result['checks'].append({'kind':'staff_sidebar_bottom_nav','result':'PASS'})
            js('document.querySelector("dialog").showModal();true')
            assert js('document.querySelector("dialog").getBoundingClientRect().width<=innerWidth')
            js('document.querySelector("dialog").close();true')
            result['checks'].append({'kind':'mobile_confirmation_dialog','result':'PASS'})
            navigate('/account/')
            js('document.querySelector("[name=first_name]").value="Nhân viên QA";document.querySelector("[name=first_name]").closest("form").requestSubmit();true')
            for _ in range(100):
                users['STAFF'].refresh_from_db()
                if users['STAFF'].first_name=='Nhân viên QA':break
                time.sleep(.1)
            assert users['STAFF'].first_name=='Nhân viên QA' and not users['STAFF'].is_superuser
            result['checks'].append({'kind':'self_profile_form_UI','result':'PASS'})
            navigate('/chat/'+str(conversation.pk)+'/')
            for _ in range(100):
                if js('document.querySelector("#chat-state")?.textContent.includes("Đã kết nối")'):break
                time.sleep(.1)
            assert js('!!document.querySelector(".human-message-bubble")')
            js('document.querySelector("#id_content").value="Tin nhắn QA qua giao diện";document.querySelector("#chat-send").requestSubmit();true')
            for _ in range(100):
                if Message.objects.filter(conversation=conversation,content='Tin nhắn QA qua giao diện').exists():break
                time.sleep(.1)
            assert Message.objects.filter(conversation=conversation,content='Tin nhắn QA qua giao diện').exists()
            result['checks'].append({'kind':'staff_chat_live_fetch_WebSocket','result':'PASS'})
            hr.payroll_state(payroll.pk,'APPROVED',actor=users['MANAGER'])
            navigate('/staff/')
            assert js('document.querySelector(".work-income").textContent.includes("Kỳ lương QA")')
            for width,height in [(1366,768),(1920,1080),(768,1024),(390,844)]:
                cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                assert not js('document.documentElement.scrollWidth>innerWidth')
                (OUT/f'staff-dashboard-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            cookies('CUSTOMER')
            for index,path in enumerate(['/','/menu/','/booking/','/booking/?tab=history','/booking/?tab=cancelled','/combos/','/offers/','/cart/','/ai/chat/','/account/','/chat/']):
                navigate(path)
                assert not js('document.body.classList.contains("staff-portal")')
                for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                    cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                    assert not js('/demo/i.test(document.body.innerText)'),(path,'visible marker')
                    assert not js('document.documentElement.scrollWidth>innerWidth'),(path,width)
                    result['pages'].append({'role':'CUSTOMER','path':path,'width':width,'height':height,'horizontal_overflow':False})
                    (OUT/f'customer-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
                    if path=='/' and width==1366:
                        size=cdp('Page.getLayoutMetrics')['cssContentSize'];(OUT/'customer-home-full-1366.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})['data']))
            result['checks'].append({'kind':'customer_navigation_footer_isolated','result':'PASS'})
            cookies('MANAGER');navigate('/management/bookings/')
            assert js('document.querySelector("[data-booking-preview]")!==null')
            tomorrow=(timezone.localdate()+timezone.timedelta(days=2)).isoformat()
            js('document.querySelector("[name=name]").value="Khách tạo qua giao diện";document.querySelector("[name=phone]").value="0912345678";document.querySelector("[name=date]").value='+json.dumps(tomorrow)+';document.querySelector("[name=time]").value="19:00";document.querySelector("[name=guests]").value="2";document.querySelector("[name=guests]").dispatchEvent(new Event("input",{bubbles:true}))')
            for _ in range(80):
                if js('document.querySelector("[data-booking-availability]").dataset.state==="available"'):break
                time.sleep(.1)
            assert js('document.querySelector("[data-booking-availability]").dataset.state==="available"')
            before=Booking.objects.count();js('document.querySelector("[data-booking-preview]").requestSubmit()')
            for _ in range(80):
                if Booking.objects.filter(name='Khách tạo qua giao diện').exists():break
                time.sleep(.1)
            assert Booking.objects.count()==before+1
            result['checks'].append({'kind':'manager_booking_preview_and_create_existing_service','result':'PASS'})
            for tab in ['today','upcoming','history','cancelled']:
                navigate('/management/bookings/?tab='+tab)
                assert js('document.querySelector(".booking-tabs [aria-current]").getAttribute("href").includes('+json.dumps(tab)+')')
            for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});navigate('/management/bookings/?tab=upcoming')
                assert not js('document.documentElement.scrollWidth>innerWidth')
                geometry=js('Array.from(document.querySelectorAll("[data-booking-preview] .field input,[data-booking-preview] .field select,[data-booking-preview] .field textarea")).map(el=>{const r=el.getBoundingClientRect(),p=el.closest(".field").getBoundingClientRect();return r.left>=p.left-1 && r.right<=p.right+1;})')
                assert all(geometry),('input outside field',width,geometry)
                (OUT/f'booking-workspace-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
                size=cdp('Page.getLayoutMetrics')['cssContentSize'];(OUT/f'booking-workspace-full-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})['data']))
            result['checks'].append({'kind':'booking_tabs_and_responsive','result':'PASS'})
            cookies('ADMIN')
            for path in ['/management/','/management/module07/combo/','/management/module07/employee/','/management/module07/restaurantinfo/','/management/ai/faces/','/management/bookings/']:
                navigate(path);assert not js('/demo/i.test(document.body.innerText)'),(path,'ADMIN marker')
            result['checks'].append({'kind':'all_roles_visible_labels_no_demo','result':'PASS'})
            cdp('Network.clearBrowserCookies')
            for index,path in enumerate(['/login/','/register/']):
                navigate(path)
                assert js('document.querySelector(".auth-photo").naturalWidth>0')
                assert js('document.querySelector("input[type=password]")!==null')
                js('document.querySelector(".password-toggle").click()')
                assert js('document.querySelector(".password-toggle").getAttribute("aria-pressed")==="true"')
                js('document.querySelector(".password-toggle").click()')
                for width,height in [(1920,1080),(1366,768),(768,1024),(390,844)]:
                    cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                    assert not js('/demo/i.test(document.body.innerText)'),(path,'visible marker')
                    assert not js('document.documentElement.scrollWidth>innerWidth'),(path,width)
                    result['pages'].append({'role':'ANONYMOUS','path':path,'width':width,'height':height,'horizontal_overflow':False})
                    (OUT/f'auth-{index}-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            result['checks'].append({'kind':'auth_photo_password_toggle','result':'PASS'})
            assert not result['exceptions'],result['exceptions']
            assert not [e for e in result['http_errors'] if '/static/' in e['url']],result['http_errors']
            ws.close();ws=None
        result['success']=True
    except Exception as exc:
        result['error']=str(exc);result['success']=False
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
