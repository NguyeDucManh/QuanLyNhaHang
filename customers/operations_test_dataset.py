"""Rich test data over a copied catalog. Never permitted on an operational DB."""
from datetime import timedelta
from decimal import Decimal
from collections import defaultdict
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection,transaction
from django.utils import timezone
from . import models as m
from .rbac import get_role
from .audit_service import record
from .operational_catalog import menu_snapshot,natural

def fixture_database_allowed(name,host,on_render,enabled):
    return enabled and not on_render and host in ('127.0.0.1','localhost','::1') and (name.startswith('test_issue10_') or name.startswith('test_restaurant_ci'))

def require_test_database():
    db=connection.settings_dict
    if not fixture_database_allowed(db['NAME'],db['HOST'],settings.ON_RENDER,getattr(settings,'ISSUE10_TEST_FIXTURES_ENABLED',False)):
        raise ValidationError('Chỉ được tạo fixture trên DB test Issue10 riêng đã cho phép; không được dùng local gốc hoặc Render.')

def counts():
    from django.apps import apps
    return {model._meta.db_table:model.objects.count() for model in apps.get_models() if model._meta.managed}

@transaction.atomic
def build_dataset(*,actor):
    require_test_database()
    if get_role(actor)!='ADMIN':raise ValidationError('Cần ADMIN của bản sao test.')
    with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(8410182027)')
    if m.AuditLog.objects.filter(action='ISSUE10_TEST_DATASET',after_data__batch='operations-v1').exists():return {'created':False,'idempotent':True,'counts':counts()}
    before=counts();catalog=menu_snapshot()
    menus=list(m.MenuItem.objects.filter(is_available=True).order_by('pk')[:4])
    customer=get_user_model().objects.filter(is_active=True,groups__name='CUSTOMER').first()
    if not menus or not customer or not m.Employee.objects.exists():raise ValidationError('Cần bản sao thực đơn/tài khoản/nhân sự đã có; không seed_menu hoặc tạo tài khoản thay thế.')
    names=['Thịt vịt','Cá hồi','Nấm đùi gà','Rau cải','Bí đỏ','Đậu phụ','Khoai lang','Bắp cải']
    existing={natural(v) for v in m.Ingredient.objects.values_list('name',flat=True)}
    for i,name in enumerate(names):
        if m.Ingredient.objects.count()>=80:break
        if natural(name) not in existing:m.Ingredient.objects.create(code='FIX-ING-'+str(i),name=name,unit='kg',minimum_stock=2)
    for i,name in enumerate(['Nhà cung cấp Thực phẩm An Bình','Nhà cung cấp Hải sản Đông Phương','Nhà cung cấp Nông sản Xanh','Nhà cung cấp Gia vị Việt','Nhà cung cấp Rau sạch Thành Phố']):
        if not m.Supplier.objects.filter(code='FIX-SUP-'+str(i)).exists():m.Supplier.objects.create(code='FIX-SUP-'+str(i),name=name)
    supplier=m.Supplier.objects.filter(is_active=True).first()
    for ingredient in m.Ingredient.objects.order_by('pk')[:6]:
        m.IngredientSupplyPolicy.objects.get_or_create(ingredient=ingredient,defaults={'supplier':supplier,'lead_time_days':2,'safety_days':3})
    from .inventory_service import create_document,confirm_document
    ingredients=list(m.Ingredient.objects.filter(recipeingredient__menu_item__in=menus).distinct())
    needed=defaultdict(Decimal)
    for line in m.RecipeIngredient.objects.filter(menu_item__in=menus):needed[line.ingredient_id]+=line.quantity_required
    if ingredients:
        receipt=create_document(actor=actor,kind='receipt',date=timezone.localdate(),supplier=supplier,
            items=[{'ingredient':i,'quantity':max(Decimal(100),needed[i.pk]+10),'unit_price':50000} for i in ingredients],request_key=uuid.uuid4(),note='Dữ liệu kiểm thử trên database tách biệt, không phải nhập kho thực tế')
        confirm_document(receipt.pk,kind='receipt',actor=actor)
    from .purchasing_service import create_purchase_order,transition_purchase_order
    ingredient=m.Ingredient.objects.first()
    for state in ('DRAFT','SUBMITTED','APPROVED'):
        po=create_purchase_order(actor=actor,supplier=supplier,items=[{'ingredient':ingredient,'quantity':10,'unit_price':50000}],request_key=uuid.uuid4(),note='Kiểm thử nội bộ, không gửi nhà cung cấp')
        if state!='DRAFT':transition_purchase_order(po.pk,'SUBMITTED',actor=actor)
        if state=='APPROVED':transition_purchase_order(po.pk,'APPROVED',actor=actor)
    from .order_service import create_order,transition_order
    from .kitchen_service import transition_kitchen_item
    from .payment_service import issue_invoice,create_payment,confirm_payment
    for index,menu in enumerate(menus):
        order=create_order(actor=actor,customer=customer,items=[{'menu_item':menu,'quantity':1}],request_key=uuid.uuid4(),note='Giao dịch kiểm thử trên database tách biệt, không phải doanh thu thực tế')
        transition_order(order.pk,'CONFIRMED',actor=actor)
        if index==0:continue
        transition_order(order.pk,'PREPARING',actor=actor)
        for item in order.items.all():
            transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=actor)
            if index>=2:transition_kitchen_item(order.pk,item.pk,'READY',actor=actor)
        if index>=2:
            transition_order(order.pk,'COMPLETED',actor=actor);invoice=issue_invoice(order.pk,actor=actor)
            payment=create_payment(invoice_id=invoice.pk,actor=actor,payment_method='CASH',request_key=uuid.uuid4())
            if index==3:
                confirm_payment(payment.pk,actor=actor)
                m.Review.objects.create(customer=customer,order=order,menu_item=menu,rating=5,comment='Đánh giá kiểm thử nội bộ, không phải phản hồi khách hàng thực tế',is_visible=False)
    now=timezone.now()
    m.Promotion.objects.create(code='FIXTURE10',name='Ưu đãi thành viên',discount_type='PERCENT',discount_value=5,min_order_amount=100000,max_discount_amount=50000,start_at=now,end_at=now+timedelta(days=7),usage_limit=100)
    if menu_snapshot()!=catalog:raise ValidationError('Thực đơn thay đổi: rollback toàn bộ fixture.')
    record(action='ISSUE10_TEST_DATASET',entity=actor,actor=actor,after={'batch':'operations-v1','test_only':True,'menu_preserved':True})
    return {'created':True,'test_only':True,'before':before,'after':counts(),'menu_before':catalog,'menu_after':menu_snapshot(),'attendance_added':False,'users_added':False}
