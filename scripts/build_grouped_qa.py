from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
s=(ROOT/'scripts/premium_live_e2e.py').read_text(encoding='utf-8').replace('8792','8793').replace('9341','9342').replace("'qa_premium'","'qa_grouped'").replace("'sr_premium_qa_'","'sr_grouped_qa_'")
s=s.replace('document.querySelector(".staff-stats")','document.querySelector(".work-income")')
s=s.replace("'/management/payroll/'","'/management/payroll/','/management/bookings/','/management/tables/'")
s=s.replace("'/booking/','/cart/'","'/booking/','/booking/?tab=history','/booking/?tab=cancelled','/combos/','/offers/','/cart/'")
s=s.replace("                cookies(role)\n                for index", "                cookies(role)\n                for index")
# Add clean-label fixtures without changing operational DB.
needle="        env={**os.environ,'DB_NAME':name"
insert='''        from customers.models import Combo,ComboItem,Booking,Area,RestaurantTable
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
'''
s=s.replace(needle,insert+needle)
# Include visible-text checks, separate from technical attributes and URLs.
needle="                        overflow=js('document.documentElement.scrollWidth>innerWidth')"
s=s.replace(needle,"                        assert not js('/demo/i.test(document.body.innerText)'),(role,path,'visible marker')\n"+needle)
needle="                    assert not js('document.documentElement.scrollWidth>innerWidth'),(path,width)"
s=s.replace(needle,"                    assert not js('/demo/i.test(document.body.innerText)'),(path,'visible marker')\n"+needle)
needle="            cdp('Network.clearBrowserCookies')"
actions='''            cookies('MANAGER');navigate('/management/bookings/')
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
'''
s=s.replace(needle,actions+needle)
(ROOT/'scripts/grouped_live_e2e.py').write_text(s,encoding='utf-8')
print('Grouped QA generated')
