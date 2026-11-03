"""Visual-only QA on a disposable DB. Signed fixtures do NOT test Stripe's network."""
import os,sys,uuid,json,time,hmac,hashlib,subprocess,urllib.request
from io import StringIO
from pathlib import Path
from datetime import timedelta
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.test.runner import DiscoverRunner
from django.test import override_settings,Client
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from customers.models import *
from customers.booking_service import create_booking
from customers.deposit_service import metadata,expire_booking

name='test_operations_browser_deposit_'+uuid.uuid4().hex[:8]
settings.DATABASES['default']['TEST']['NAME']=name
runner=DiscoverRunner(verbosity=0,interactive=False);old=None;server=None
try:
    old=runner.setup_databases();assert connection.settings_dict['NAME']==name
    user=User.objects.create_user('deposit-visual-customer',first_name='Khách',last_name='kiểm tra')
    call_command('seed_menu',verbosity=0,stdout=StringIO())
    area=Area.objects.create(name='Khu kiểm tra')
    for n in range(7):RestaurantTable.objects.create(area=area,code=f'VIS{n+1:02}',capacity=4)
    future=timezone.localtime()+timedelta(days=2)
    menus=list(MenuItem.objects.filter(price__isnull=False)[:3]);cart={str(m.pk):1 for m in menus}
    def booking():return create_booking(user=user,name='Khách kiểm tra',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None,microsecond=0),guests=2,food_cart=cart,online=True)
    pending=booking();success=booking();failed=booking();expired=booking()
    def signed_fixture(b,status):
        attempt=StripeCheckoutAttempt.objects.create(deposit=b.deposit,status='OPEN',session_id='cs_test_visual_'+uuid.uuid4().hex,stripe_expires_at=b.deposit.expires_at)
        obj={'id':attempt.session_id,'metadata':metadata(b.deposit,attempt),'currency':'vnd','amount_total':int(b.deposit.amount),'status':'complete','payment_status':'paid' if status=='success' else 'unpaid','payment_intent':'pi_visual_'+uuid.uuid4().hex}
        payload={'id':'evt_visual_'+uuid.uuid4().hex,'type':'checkout.session.completed' if status=='success' else 'checkout.session.async_payment_failed','livemode':False,'data':{'object':obj}}
        body=json.dumps(payload).encode();stamp=int(time.time());secret='whsec_local_visual_fixture_only'
        signature=hmac.new(secret.encode(),str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
        with override_settings(STRIPE_WEBHOOK_SECRET=secret):
            response=Client().post(reverse('stripe_webhook'),body,content_type='application/json',HTTP_HOST='localhost',HTTP_STRIPE_SIGNATURE=f't={stamp},v1={signature}')
        assert response.status_code==200
    signed_fixture(success,'success');signed_fixture(failed,'failed')
    BookingDeposit.objects.filter(booking=expired).update(expires_at=timezone.now()-timedelta(seconds=1));expire_booking(expired.pk)
    routes=[('deposit-pending',reverse('booking_deposit',args=[pending.pk]),'CUSTOMER'),('deposit-success',reverse('booking_deposit_success',args=[success.pk]),'CUSTOMER'),('deposit-failed',reverse('booking_deposit',args=[failed.pk]),'CUSTOMER'),('deposit-expired',reverse('booking_deposit',args=[expired.pk]),'CUSTOMER'),('deposit-cancel',reverse('booking_deposit',args=[pending.pk])+'?cancelled=1','CUSTOMER')]
    # Page navigation QA expects pathname only; cancel state is covered by endpoint tests.
    routes=routes[:-1]
    env=os.environ.copy();env.update(DB_NAME=name,STRIPE_SECRET_KEY='',STRIPE_WEBHOOK_SECRET='',REFERENCE_QA_BASE='http://127.0.0.1:8021',REFERENCE_QA_WIDTHS='1920,1366,1024,768,390',REFERENCE_QA_OUTPUT='booking-deposit-visual',REFERENCE_QA_SCREENSHOTS_ONLY='1',OPERATIONS_QA_ROUTES=json.dumps(routes))
    env.pop('REFERENCE_QA_STAFF_USERNAME',None)
    out=ROOT/'artifacts'/'booking-deposit-visual';out.mkdir(exist_ok=True)
    with (out/'server.log').open('w',encoding='utf-8') as log:
        server=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8021','--noreload'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            try:urllib.request.urlopen('http://127.0.0.1:8021/',timeout=2);break
            except Exception:time.sleep(.2)
        subprocess.run([sys.executable,'-u','scripts/reference_browser_qa.py'],cwd=ROOT,env=env,check=True)
    print('VISUAL QA ONLY: signed local fixtures; no Stripe network payment was performed.')
finally:
    if server:server.terminate();server.wait(timeout=20)
    if old is not None:
        assert connection.settings_dict['NAME'].startswith('test_operations_browser_deposit_')
        runner.teardown_databases(old)
