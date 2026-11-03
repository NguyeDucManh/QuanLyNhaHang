"""Real Edge workflow checks on a disposable Django test DB, never operating data."""
import os, sys, uuid, json, subprocess, time, urllib.request
from pathlib import Path
from datetime import timedelta
from decimal import Decimal
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.core.management import call_command
from django.test.runner import DiscoverRunner
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from customers.models import *
from customers.rbac import assign_role
from customers.purchasing_service import create_purchase_order
from customers.booking_service import create_booking
from customers.booking_advanced_service import join_waitlist
from customers.inventory_service import create_document, confirm_document
from customers.order_service import create_order, transition_order
from customers.kitchen_service import transition_kitchen_item
from customers.payment_service import issue_invoice, create_payment, confirm_payment

name='test_operations_browser_'+uuid.uuid4().hex[:12]
settings.DATABASES['default']['TEST']['NAME']=name
runner=DiscoverRunner(verbosity=0,interactive=False)
old=None;server=None
try:
    old=runner.setup_databases()
    assert connection.settings_dict['NAME']==name
    admin=User.objects.create_superuser('qa-operations-admin',password=uuid.uuid4().hex)
    customer=User.objects.create_user('qa-operations-customer')
    category=Category.objects.create(name='Danh mục QA',slug='qa-operations')
    menu=MenuItem.objects.create(name='Món kiểm tra nghiệp vụ',category=category,price=200000,image='ui/images/garden-restaurant-hero.png')
    supplier=Supplier.objects.create(code='QA',name='Nhà cung cấp kiểm tra')
    ingredient=Ingredient.objects.create(code='QA',name='Nguyên liệu kiểm tra',unit='kg')
    RecipeIngredient.objects.create(menu_item=menu,ingredient=ingredient,quantity_required=Decimal('.25'))
    area=Area.objects.create(name='Khu kiểm tra')
    source=RestaurantTable.objects.create(area=area,code='QA01',capacity=4)
    dest=RestaurantTable.objects.create(area=area,code='QA02',capacity=4)
    third=RestaurantTable.objects.create(area=area,code='QA03',capacity=4)
    po=create_purchase_order(actor=admin,supplier=supplier,items=[{'ingredient':ingredient,'quantity':100,'unit_price':50000}],request_key=uuid.uuid4())
    now=timezone.localtime();future=now+timedelta(days=1)
    def booking(): return create_booking(user=customer,name='Khách kiểm tra',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None),guests=4)
    b=booking();Booking.objects.filter(pk=b.pk).update(start_time=now-timedelta(minutes=3),end_time=now+timedelta(hours=1))
    ns=booking();Booking.objects.filter(pk=ns.pk).update(start_time=now-timedelta(minutes=20),end_time=now+timedelta(hours=1))
    RestaurantTable.objects.update(status='MAINTENANCE')
    wait=join_waitlist(customer=customer,name='Khách chờ kiểm tra',phone='0912345678',date=future.date(),time=(future+timedelta(hours=3)).time().replace(tzinfo=None),guests=4,consent=True,request_key=uuid.uuid4())
    RestaurantTable.objects.update(status='AVAILABLE')
    receipt=create_document(actor=admin,kind='receipt',date=now.date(),supplier=supplier,items=[{'ingredient':ingredient,'quantity':2,'unit_price':50000}],request_key=uuid.uuid4())
    confirm_document(receipt.pk,kind='receipt',actor=admin)
    order=create_order(actor=admin,customer=customer,items=[{'menu_item':menu,'quantity':1}],request_key=uuid.uuid4())
    transition_order(order.pk,'CONFIRMED',actor=admin);transition_order(order.pk,'PREPARING',actor=admin)
    line=order.items.get();transition_kitchen_item(order.pk,line.pk,'PREPARING',actor=admin);transition_kitchen_item(order.pk,line.pk,'READY',actor=admin)
    transition_order(order.pk,'COMPLETED',actor=admin)
    invoice=issue_invoice(order.pk,actor=admin)
    payment=create_payment(invoice_id=invoice.pk,actor=admin,payment_method='CASH',request_key=uuid.uuid4());confirm_payment(payment.pk,actor=admin)
    routes=[('po-list',reverse('purchase_orders'),'ADMIN'),('po-create-form',reverse('purchase_add'),'ADMIN')]
    routes += [(label,reverse('purchase_order_detail',args=[po.pk]),'ADMIN') for label in ('po-submit','po-approve','po-partial','po-complete')]
    routes += [('food-cost',reverse('food_cost'),'ADMIN'),('recipe',reverse('admin_recipes'),'ADMIN'),('loyalty-manager',reverse('loyalty_management'),'ADMIN'),('loyalty-customer',reverse('loyalty_customer'),'CUSTOMER'),('audit',reverse('audit_logs'),'ADMIN'),('waitlist',reverse('waitlist_management'),'ADMIN'),('waitlist-customer',reverse('waitlist_customer'),'CUSTOMER')]
    routes += [('booking-checkin',reverse('booking_operations',args=[b.pk]),'ADMIN'),('booking-transfer',reverse('booking_operations',args=[b.pk]),'ADMIN'),('booking-noshow',reverse('booking_operations',args=[ns.pk]),'ADMIN'),('waitlist-convert',reverse('waitlist_management'),'ADMIN'),('pos',reverse('staff_home'),'ADMIN'),('inventory',reverse('admin_ingredients'),'ADMIN'),('table-history',reverse('table_history',args=[dest.pk]),'ADMIN')]
    env=os.environ.copy();env.update(DB_NAME=name,REFERENCE_QA_BASE='http://127.0.0.1:8019',REFERENCE_QA_WIDTHS='1366',REFERENCE_QA_OUTPUT='operations-browser',REFERENCE_QA_SCREENSHOTS_ONLY='1',OPERATIONS_QA_ROUTES=json.dumps(routes),OPERATIONS_DESTINATION=str(dest.pk),OPERATIONS_DESTINATION_CODE=dest.code)
    env.pop('REFERENCE_QA_STAFF_USERNAME',None)
    logdir=ROOT/'artifacts'/'operations-browser';logdir.mkdir(exist_ok=True)
    with (logdir/'server.log').open('w',encoding='utf-8') as log:
        server=subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8019','--noreload'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:8019/',timeout=2);break
            except Exception: time.sleep(.2)
        subprocess.run([sys.executable,'-u','scripts/reference_browser_qa.py'],cwd=ROOT,env=env,check=True)
        mobile_routes=[('po-mobile',reverse('purchase_order_detail',args=[po.pk]),'ADMIN'),('cost-mobile',reverse('food_cost'),'ADMIN'),('audit-mobile',reverse('audit_logs'),'ADMIN'),('loyalty-mobile',reverse('loyalty_customer'),'CUSTOMER'),('booking-mobile',reverse('booking_operations',args=[b.pk]),'ADMIN'),('pos-mobile',reverse('staff_home'),'ADMIN')]
        env.update(REFERENCE_QA_WIDTHS='390',OPERATIONS_QA_ROUTES=json.dumps(mobile_routes))
        subprocess.run([sys.executable,'-u','scripts/reference_browser_qa.py'],cwd=ROOT,env=env,check=True)
    po.refresh_from_db();ingredient.refresh_from_db();b.refresh_from_db();ns.refresh_from_db();wait.refresh_from_db()
    assert po.status=='RECEIVED' and po.items.get().quantity_received==100
    assert po.receivings.count()==2 and ingredient.current_stock==Decimal('101.750')
    assert b.visit.state=='CHECKED_IN' and b.table_id==dest.pk
    assert ns.visit.state=='NO_SHOW' and ns.status=='CANCELLED'
    assert wait.status=='CONVERTED' and wait.booking_id
    assert customer.loyalty.points_balance==20
    print('Browser business workflow assertions: PASS (disposable test database)')
finally:
    if server:
        server.terminate();server.wait(timeout=20)
    if old is not None:
        assert connection.settings_dict['NAME'].startswith('test_operations_browser_')
        runner.teardown_databases(old)
