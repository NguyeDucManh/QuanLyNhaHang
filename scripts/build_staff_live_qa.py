"""Create a scoped QA runner using the established disposable DB/browser harness."""
from pathlib import Path
root=Path(__file__).resolve().parent.parent
source=(root/'scripts/face_live_e2e.py').read_text(encoding='utf-8')
source=source.replace('127.0.0.1:8790','127.0.0.1:8791').replace('9339','9340').replace("ROOT/'qa_face'","ROOT/'qa_staff'").replace("'sr_face_qa_'","'sr_staff_qa_'")
fixture='''
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
'''
source=source.replace("        env={**os.environ",fixture+"        env={**os.environ",1)
source=source.replace("('STAFF',['/work/faceid/'])","('STAFF',['/staff/','/work/?tab=schedule','/work/faceid/','/payroll/'+str(payroll.pk)+'/', '/chat/'+str(conversation.pk)+'/', '/account/', '/management/menu/', '/management/kitchen/', '/management/orders/'])")
source=source.replace("('MANAGER',paths)","('MANAGER',paths+['/management/','/management/menu/','/management/orders/','/management/kitchen/','/management/module07/employee/','/management/payroll/'])")
source=source.replace('assert not Attendance.objects.exists()','assert Attendance.objects.count()==1')
source=source.replace('Attendance.objects.filter(employee=employee,check_', 'Attendance.objects.filter(employee=employee,work_schedule=schedule,check_')
source=source.replace("            js('document.querySelector(\"[data-punch=out]\").click();true')", "            for _ in range(100):\n                if js('!document.querySelector(\"[data-punch=out]\").disabled'):break\n                time.sleep(.1)\n            js('document.querySelector(\"[data-punch=out]\").click();true')")
# Restore attendance as the final active page before existing GPS UI checks.
source=source.replace("            assert js('!document.querySelector(\"[data-location-map]\")')", "            navigate('/work/faceid/')\n            assert js('!document.querySelector(\"[data-location-map]\")')",1)
source=source.replace("[(1366,768),(1920,1080),(390,844)]","[(1366,768),(1920,1080),(768,1024),(390,844)]")
extra='''
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
            assert js('document.querySelector(".staff-stats").textContent.includes("Kỳ lương QA")')
            for width,height in [(1366,768),(1920,1080),(768,1024),(390,844)]:
                cdp('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<700});time.sleep(.2)
                assert not js('document.documentElement.scrollWidth>innerWidth')
                (OUT/f'staff-dashboard-{width}.png').write_bytes(base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data']))
            cookies('CUSTOMER')
            for path in ['/','/menu/','/booking/','/account/','/chat/']:
                navigate(path)
                assert not js('document.body.classList.contains("staff-portal")')
                assert not js('document.documentElement.scrollWidth>innerWidth')
            result['checks'].append({'kind':'customer_navigation_footer_isolated','result':'PASS'})
'''
source=source.replace("            ws.close();ws=None",extra+"            ws.close();ws=None",1)
source=source.replace('from customers.models import Position,Employee,RestaurantInfo,AttendanceLocationPolicy,Shift,WorkSchedule,Attendance,AttendanceLocationEvent,FaceProfile','from customers.models import Position,Employee,RestaurantInfo,AttendanceLocationPolicy,Shift,WorkSchedule,Attendance,AttendanceLocationEvent,FaceProfile,Message')
(root/'scripts/staff_live_e2e.py').write_text(source,encoding='utf-8')
