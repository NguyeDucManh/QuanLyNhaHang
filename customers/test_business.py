from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from decimal import Decimal
from io import StringIO
import uuid
from django.contrib.auth.models import User,Permission,Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError,transaction,connections,connection
from django.test import TestCase,TransactionTestCase,Client
from django.urls import reverse
from django.utils import timezone
from .models import *
from .rbac import assign_role
from .business_forms import IngredientForm,RecipeForm
from .order_service import create_order,transition_order
from .kitchen_service import transition_kitchen_item
from .inventory_service import create_document,confirm_document,save_ingredient,consume_order
from .payment_service import issue_invoice,create_payment,confirm_payment


class BusinessData:
    @classmethod
    def initialize(cls):
        call_command('seed_rbac',stdout=StringIO())
        call_command('seed_menu',stdout=StringIO())
        for role in ('ADMIN','MANAGER','STAFF','CUSTOMER'):
            user=User.objects.create_user('business-'+role.lower()); assign_role(user,role); setattr(cls,role.lower(),user)
        cls.menu=MenuItem.objects.get(pk=1); cls.menu.price=Decimal('100'); cls.menu.save()
        cls.second=MenuItem.objects.get(pk=2); cls.second.price=Decimal('60'); cls.second.save()
        cls.supplier=Supplier.objects.create(code='SUP',name='Supplier')
        cls.fish=Ingredient.objects.create(code='FISH',name='Fish',unit='kg',minimum_stock=1)
        cls.butter=Ingredient.objects.create(code='BUTTER',name='Butter',unit='kg',minimum_stock=1)
        cls.area=Area.objects.create(name='Business Area')
        cls.table=RestaurantTable.objects.create(area=cls.area,code='A01',capacity=4)

    def order(self,quantity=2,**kwargs):
        values=dict(actor=self.admin,items=[{'menu_item':self.menu,'quantity':quantity}],request_key=uuid.uuid4()); values.update(kwargs)
        return create_order(**values)

    def receipt(self,quantity=10,**kwargs):
        values=dict(actor=self.admin,kind='receipt',date=timezone.localdate(),supplier=self.supplier,items=[{'ingredient':self.fish,'quantity':quantity,'unit_price':5}],request_key=uuid.uuid4()); values.update(kwargs)
        return create_document(**values)

    def issue(self,quantity=1,**kwargs):
        values=dict(actor=self.admin,kind='issue',date=timezone.localdate(),items=[{'ingredient':self.fish,'quantity':quantity}],request_key=uuid.uuid4()); values.update(kwargs)
        return create_document(**values)

    def import_stock(self,quantity=10):
        confirm_document(self.receipt(quantity).pk,kind='receipt',actor=self.admin)

    def prepare(self,order):
        transition_order(order.pk,'CONFIRMED',actor=self.admin)
        transition_order(order.pk,'PREPARING',actor=self.admin)
        # Completion fixtures now include the real per-item kitchen lifecycle.
        for item in order.items.all():
            transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.admin)
            transition_kitchen_item(order.pk,item.pk,'READY',actor=self.admin)

    def completed(self):
        self.import_stock()
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        order=self.order(); self.prepare(order)
        return transition_order(order.pk,'COMPLETED',actor=self.admin)


class OrderTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_backend_totals_and_snapshot_prices(self):
        order=self.order(items=[{'menu_item':self.menu,'quantity':2,'unit_price':1,'line_total':1},{'menu_item':self.second,'quantity':3}],discount_amount=20)
        self.assertEqual((order.subtotal,order.discount_amount,order.total_amount),(380,20,360))
        self.menu.price=999; self.menu.save()
        self.assertEqual(order.items.get(menu_item=self.menu).unit_price,100)
        self.assertEqual(order.items.get(menu_item=self.menu).line_total,200)

    def test_invalid_quantities_and_empty_order(self):
        for quantity in (0,-1,1.5,True,1001):
            with self.subTest(quantity=quantity),self.assertRaises(ValidationError): self.order(quantity)
        with self.assertRaises(ValidationError): self.order(items=[])
        self.assertEqual(Order.objects.count(),0)

    def test_unpriced_inactive_menu_and_category(self):
        for attribute,value in [('price',None),('is_available',False)]:
            original=getattr(self.menu,attribute); setattr(self.menu,attribute,value); self.menu.save()
            with self.assertRaises(ValidationError): self.order()
            setattr(self.menu,attribute,original); self.menu.save()
        self.menu.category.is_active=False; self.menu.category.save()
        with self.assertRaises(ValidationError): self.order()
        self.assertEqual(Order.objects.count(),0)

    def test_discount_bounds(self):
        for discount in (-1,201,'NaN','Infinity','1.001'):
            with self.subTest(discount=discount),self.assertRaises(ValidationError): self.order(discount_amount=discount)

    def test_dine_in_and_invalid_table(self):
        self.assertEqual(self.order(order_type='DINE_IN',table=self.table).table_id,self.table.pk)
        with self.assertRaises(ValidationError): self.order(order_type='DINE_IN')
        with self.assertRaises(ValidationError): self.order(table=self.table)
        self.table.status='MAINTENANCE'; self.table.save()
        with self.assertRaises(ValidationError): self.order(order_type='DINE_IN',table=self.table)

    def test_creation_retry_is_idempotent(self):
        key=uuid.uuid4(); self.assertEqual(self.order(request_key=key).pk,self.order(request_key=key).pk)
        self.assertEqual(Order.objects.count(),1)

    def test_valid_and_invalid_state_transitions(self):
        order=self.order()
        with self.assertRaises(ValidationError): transition_order(order.pk,'COMPLETED',actor=self.admin)
        transition_order(order.pk,'CONFIRMED',actor=self.admin); transition_order(order.pk,'CANCELLED',actor=self.admin)
        for status in ('CONFIRMED','PREPARING','PENDING'):
            with self.assertRaises(ValidationError): transition_order(order.pk,status,actor=self.admin)

    def test_completed_terminal_state_and_retry(self):
        order=self.completed()
        for status in ('PENDING','PREPARING','CANCELLED'):
            with self.assertRaises(ValidationError): transition_order(order.pk,status,actor=self.admin)
        with self.assertRaises(ValidationError): transition_order(order.pk,'COMPLETED',actor=self.admin)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('9.5'))
        self.assertEqual(StockMovement.objects.filter(order=order).count(),1)

    def test_database_rejects_inconsistent_amounts(self):
        order=self.order()
        with self.assertRaises(IntegrityError),transaction.atomic(): Order.objects.filter(pk=order.pk).update(total_amount=1)
        with self.assertRaises(IntegrityError),transaction.atomic(): OrderItem.objects.filter(order=order).update(quantity=0)


class InventoryTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_receipt_draft_then_confirmation_and_retry(self):
        doc=self.receipt(3); self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,0)
        confirm_document(doc.pk,kind='receipt',actor=self.admin); confirm_document(doc.pk,kind='receipt',actor=self.admin)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,3)
        movement=StockMovement.objects.get(receipt=doc)
        self.assertEqual((movement.stock_before,movement.stock_after,movement.quantity),(0,3,3)); self.assertEqual(movement.created_by,self.admin)

    def test_receipt_creation_retry(self):
        key=uuid.uuid4(); self.assertEqual(self.receipt(request_key=key).pk,self.receipt(request_key=key).pk)
        self.assertEqual(StockReceipt.objects.count(),1)

    def test_issue_decreases_stock_once(self):
        self.import_stock(5); doc=self.issue(2)
        confirm_document(doc.pk,kind='issue',actor=self.admin); confirm_document(doc.pk,kind='issue',actor=self.admin)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,3)
        self.assertEqual(StockMovement.objects.filter(issue=doc).count(),1)

    def test_issue_overstock_is_atomic(self):
        self.import_stock(5); doc=self.issue(items=[{'ingredient':self.fish,'quantity':2},{'ingredient':self.butter,'quantity':1}])
        with self.assertRaises(ValidationError): confirm_document(doc.pk,kind='issue',actor=self.admin)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,5)
        doc.refresh_from_db(); self.assertEqual(doc.status,'DRAFT'); self.assertFalse(StockMovement.objects.filter(issue=doc).exists())

    def test_quantity_supplier_and_date_validation(self):
        for quantity in (0,-1,'0.0001','NaN'):
            with self.assertRaises(ValidationError): self.receipt(quantity)
        self.supplier.is_active=False; self.supplier.save()
        with self.assertRaises(ValidationError): self.receipt()
        with self.assertRaises(ValidationError): self.issue(date=timezone.localdate()+timedelta(days=1))

    def test_ingredient_stock_cannot_be_edited_through_form(self):
        self.import_stock(4)
        form=IngredientForm({'code':self.fish.code,'name':'Updated','unit':'kg','minimum_stock':2,'is_active':'on','current_stock':999},instance=self.fish)
        self.assertTrue(form.is_valid()); save_ingredient(form)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,4)

    def test_unit_cannot_change_after_stock_or_recipe(self):
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=1)
        form=IngredientForm({'code':self.fish.code,'name':'Fish','unit':'g','minimum_stock':0,'is_active':'on'},instance=self.fish)
        self.assertTrue(form.is_valid())
        with self.assertRaises(ValidationError): save_ingredient(form)

    def test_recipe_validation_and_duplicate(self):
        for quantity in (0,-1): self.assertFalse(RecipeForm({'menu_item':self.menu.pk,'ingredient':self.fish.pk,'quantity_required':quantity}).is_valid())
        form=RecipeForm({'menu_item':self.menu.pk,'ingredient':self.fish.pk,'quantity_required':'.25'})
        self.assertTrue(form.is_valid()); line=form.save()
        self.assertEqual(line.menu_item,self.menu); self.assertEqual(line.ingredient,self.fish)
        self.assertFalse(RecipeForm({'menu_item':self.menu.pk,'ingredient':self.fish.pk,'quantity_required':'.5'}).is_valid())

    def test_ready_consumption_aggregates_recipe_quantities(self):
        self.import_stock(2)
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        RecipeIngredient.objects.create(menu_item=self.second,ingredient=self.fish,quantity_required=Decimal('.10'))
        order=self.order(items=[{'menu_item':self.menu,'quantity':2},{'menu_item':self.second,'quantity':3}]); self.prepare(order)
        with self.assertRaises(ValidationError): consume_order(order,self.admin)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('1.2'))
        self.assertEqual(sum(StockMovement.objects.filter(order=order).values_list('quantity',flat=True)),Decimal('.8'))
        self.assertEqual(StockMovement.objects.filter(order=order).count(),2)

    def test_missing_recipe_ready_warns_and_does_not_deduct(self):
        order=self.order(); self.prepare(order)
        self.assertEqual(order.items.get().inventory_status,'NO_RECIPE')
        with self.assertRaises(ValidationError): consume_order(order,self.admin)
        order.refresh_from_db(); self.assertEqual(order.status,'PREPARING'); self.assertFalse(StockMovement.objects.filter(order=order).exists())

    def test_insufficient_recipe_stock_rolls_back_everything(self):
        self.import_stock(1)
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.butter,quantity_required=Decimal('.02'))
        order=self.order()
        with self.assertRaises(ValidationError): self.prepare(order)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,1)
        order.refresh_from_db(); self.assertEqual(order.status,'PREPARING'); self.assertFalse(StockMovement.objects.filter(order=order).exists())

    def test_inactive_ingredient_blocks_explicit_consumption(self):
        self.import_stock(1); RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required='.25')
        self.fish.is_active=False; self.fish.save(); order=self.order()
        with self.assertRaises(ValidationError): self.prepare(order)

    def test_nonnegative_stock_and_minimum_database_constraints(self):
        for fields in ({'current_stock':-1},{'minimum_stock':-1}):
            with self.assertRaises(IntegrityError),transaction.atomic(): Ingredient.objects.filter(pk=self.fish.pk).update(**fields)

    def test_low_stock_includes_equal_threshold(self):
        self.import_stock(1); self.client.force_login(self.admin)
        self.assertEqual(len(self.client.get('/management/stock-alerts/').context['rows']),2)
        self.import_stock(1); self.assertEqual(len(self.client.get('/management/stock-alerts/').context['rows']),1)


class PaymentTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def invoice(self): return issue_invoice(self.completed().pk)
    def pay(self,invoice,**kwargs):
        values=dict(invoice_id=invoice.pk,actor=self.admin,amount=invoice.total_amount,payment_method='CASH',request_key=uuid.uuid4()); values.update(kwargs)
        return create_payment(**values)

    def test_invoice_once_and_backend_amounts(self):
        order=self.completed(); invoice=issue_invoice(order.pk)
        self.assertEqual(invoice.pk,issue_invoice(order.pk).pk)
        self.assertEqual((invoice.subtotal,invoice.discount_amount,invoice.total_amount),(order.subtotal,order.discount_amount,order.total_amount))
        self.assertEqual(Invoice.objects.count(),1)

    def test_invoice_requires_completed_order(self):
        with self.assertRaises(ValidationError): issue_invoice(self.order().pk)

    def test_payment_starts_pending_then_paid_once(self):
        invoice=self.invoice(); payment=self.pay(invoice); self.assertEqual(payment.status,'PENDING')
        invoice.refresh_from_db(); self.assertEqual(invoice.status,'UNPAID')
        confirm_payment(payment.pk,actor=self.manager)
        with self.assertRaises(ValidationError): confirm_payment(payment.pk,actor=self.manager)
        payment.refresh_from_db(); invoice.refresh_from_db()
        self.assertEqual(payment.status,'SUCCEEDED'); self.assertEqual(invoice.status,'PAID')
        self.assertEqual(payment.confirmed_by,self.manager); self.assertIsNotNone(payment.paid_at)
        with self.assertRaises(ValidationError): self.pay(invoice)

    def test_payment_amount_method_and_reference_validation(self):
        invoice=self.invoice()
        for data in ({'amount':1},{'amount':-1},{'payment_method':'CARD'},{'payment_method':'BANK_TRANSFER'}):
            with self.subTest(data=data),self.assertRaises(ValidationError): self.pay(invoice,**data)
        self.assertEqual(Payment.objects.count(),0)
        self.pay(invoice,payment_method='BANK_TRANSFER',transaction_reference='BANK-01')

    def test_duplicate_pending_payment_and_request_retry(self):
        invoice=self.invoice(); key=uuid.uuid4(); payment=self.pay(invoice,request_key=key)
        self.assertEqual(payment.pk,self.pay(invoice,request_key=key).pk)
        with self.assertRaises(ValidationError): self.pay(invoice)
        self.assertEqual(Payment.objects.count(),1)

    def test_failed_payment_then_retry(self):
        invoice=self.invoice(); payment=self.pay(invoice); confirm_payment(payment.pk,actor=self.admin,successful=False)
        invoice.refresh_from_db(); self.assertEqual(invoice.status,'UNPAID')
        with self.assertRaises(ValidationError): confirm_payment(payment.pk,actor=self.admin)
        confirm_payment(self.pay(invoice).pk,actor=self.admin); invoice.refresh_from_db(); self.assertEqual(invoice.status,'PAID')

    def test_tampered_payment_amount_cannot_mark_invoice_paid(self):
        invoice=self.invoice(); payment=self.pay(invoice); Payment.objects.filter(pk=payment.pk).update(amount=1)
        with self.assertRaises(ValidationError): confirm_payment(payment.pk,actor=self.admin)
        invoice.refresh_from_db(); self.assertEqual(invoice.status,'UNPAID')

    def test_bank_reference_cannot_pay_two_invoices(self):
        first=self.invoice()
        order=self.order(); self.prepare(order); transition_order(order.pk,'COMPLETED',actor=self.admin)
        second=issue_invoice(order.pk)
        self.pay(first,payment_method='BANK_TRANSFER',transaction_reference='BANK-UNIQUE')
        with self.assertRaisesMessage(ValidationError,'đã được sử dụng'):
            self.pay(second,payment_method='BANK_TRANSFER',transaction_reference='BANK-UNIQUE')
        self.assertEqual(Payment.objects.count(),1)


class BusinessAccessTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_admin_manager_lists_and_crud_permissions(self):
        urls=['/management/menu/','/management/categories/','/management/orders/','/management/payments/','/management/ingredients/','/management/suppliers/','/management/recipes/','/management/stock-alerts/','/management/transactions/','/management/stock/receipt/','/management/stock/issue/','/management/orders/add/','/management/stock/receipt/add/','/management/stock/issue/add/']
        for user in (self.admin,self.manager):
            self.client.force_login(user)
            for url in urls:
                with self.subTest(user=user.username,url=url): self.assertEqual(self.client.get(url).status_code,200)
            self.assertEqual(self.client.post(reverse('business_add',args=['supplier']),{'code':'S-'+user.username,'name':'New','is_active':'on'}).status_code,302)

    def test_staff_customer_denied_get_and_post(self):
        # A STAFF account with all operational grants revoked must fail closed.
        Group.objects.get(name='STAFF').permissions.clear()
        order=self.order(); receipt=self.receipt()
        for user in (self.staff,self.customer):
            self.client.force_login(user)
            for url in ['/management/orders/','/management/payments/','/management/transactions/','/management/ingredients/','/management/suppliers/','/management/recipes/']: self.assertEqual(self.client.get(url).status_code,403)
            for url in [reverse('admin_order_status',args=[order.pk]),reverse('admin_stock_confirm',args=['receipt',receipt.pk]),reverse('business_add',args=['ingredient'])]:
                self.assertEqual(self.client.post(url,{'status':'COMPLETED','current_stock':999}).status_code,403)
        order.refresh_from_db(); self.assertEqual(order.status,'PENDING'); self.assertFalse(StockMovement.objects.exists())

    def test_staff_explicit_view_does_not_grant_change(self):
        Group.objects.get(name='STAFF').permissions.clear()
        self.staff.user_permissions.add(Permission.objects.get(codename='view_order',content_type__app_label='customers')); self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/management/').status_code,200)
        self.assertEqual(self.client.get('/management/orders/').status_code,200)
        self.assertEqual(self.client.get('/management/orders/add/').status_code,403)

    def test_order_post_ignores_client_money_and_status(self):
        self.client.force_login(self.manager)
        payload={'request_key':str(uuid.uuid4()),'order_type':'TAKEAWAY','discount_amount':'10','items-TOTAL_FORMS':'1','items-INITIAL_FORMS':'0','items-0-menu_item':self.menu.pk,'items-0-quantity':'2','subtotal':'1','total_amount':'1','status':'COMPLETED','items-0-unit_price':'1'}
        self.assertEqual(self.client.post('/management/orders/add/',payload).status_code,302)
        order=Order.objects.get(); self.assertEqual(order.total_amount,200); self.assertEqual(order.status,'PENDING')

    def test_detail_pages_and_payment_post_ignore_frontend_status(self):
        invoice=issue_invoice(self.completed().pk); self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('admin_order_detail',args=[invoice.order_id])).status_code,200)
        self.assertEqual(self.client.get(reverse('admin_invoice_detail',args=[invoice.pk])).status_code,200)
        self.client.post(reverse('admin_payment_add',args=[invoice.pk]),{'request_key':str(uuid.uuid4()),'amount':invoice.total_amount,'payment_method':'CASH','status':'SUCCEEDED','paid_at':'2099-01-01'})
        self.assertEqual(Payment.objects.get().status,'PENDING')
        self.assertEqual(self.client.get(reverse('admin_stock_detail',args=['receipt',self.receipt().pk])).status_code,200)

    def test_mutations_post_only_and_csrf(self):
        order=self.order(); self.client.force_login(self.admin); url=reverse('admin_order_status',args=[order.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        client=Client(enforce_csrf_checks=True); client.force_login(self.admin)
        self.assertEqual(client.post(url,{'status':'CONFIRMED'}).status_code,403)

    def test_menu_search_category_filter_and_account_preservation(self):
        self.client.force_login(self.manager)
        response=self.client.get('/management/menu/',{'q':self.menu.name,'category':self.menu.category_id})
        self.assertEqual(len(response.context['pagination']),1)
        self.assertEqual(MenuItem.objects.count(),45); self.assertEqual(Category.objects.count(),19)
        self.assertEqual(self.client.get('/management/accounts/').status_code,403)

    def test_stock_entry_and_invalid_empty_formset(self):
        self.client.force_login(self.manager)
        payload={'request_key':str(uuid.uuid4()),'date':timezone.localdate().isoformat(),'supplier':self.supplier.pk,'items-TOTAL_FORMS':'1','items-INITIAL_FORMS':'0','items-0-ingredient':self.fish.pk,'items-0-quantity':'2','items-0-unit_price':'3','status':'CONFIRMED'}
        self.assertEqual(self.client.post('/management/stock/receipt/add/',payload).status_code,302)
        doc=StockReceipt.objects.get(); self.assertEqual(doc.status,'DRAFT')
        self.client.post(reverse('admin_stock_confirm',args=['receipt',doc.pk])); self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,2)
        payload['request_key']=str(uuid.uuid4()); payload['items-TOTAL_FORMS']='0'
        self.assertEqual(self.client.post('/management/stock/receipt/add/',payload).status_code,200); self.assertEqual(StockReceipt.objects.count(),1)


class BusinessSeedTests(TestCase):
    def test_seed_idempotent_preserves_user_data_and_creates_no_financial_data(self):
        call_command('seed_restaurant',stdout=StringIO())
        self.assertEqual((Area.objects.count(),RestaurantTable.objects.count(),Supplier.objects.count(),Ingredient.objects.count()),(4,20,3,18))
        ingredient=Ingredient.objects.get(code='NL001'); ingredient.name='Edited'; ingredient.save()
        table=RestaurantTable.objects.get(code='B01'); table.capacity=10; table.save()
        call_command('seed_restaurant',stdout=StringIO()); ingredient.refresh_from_db(); table.refresh_from_db()
        self.assertEqual(ingredient.name,'Edited'); self.assertEqual(table.capacity,10)
        self.assertEqual((Order.objects.count(),Invoice.objects.count(),Payment.objects.count(),RecipeIngredient.objects.count(),StockMovement.objects.count()),(0,0,0,0,0))
        self.assertEqual(Ingredient.objects.filter(current_stock=0).count(),18)


class InventoryConcurrencyTests(BusinessData,TransactionTestCase):
    def setUp(self): self.initialize()
    def race(self,callback):
        barrier=Barrier(2)
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10); actor=User.objects.get(pk=self.admin.pk); callback(index,actor); return 'ok'
            except ValidationError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor: return list(executor.map(worker,[0,1]))

    def test_concurrent_issues_cannot_overdraw(self):
        self.assertEqual(connection.vendor,'postgresql'); self.import_stock(1); docs=[self.issue(1),self.issue(1)]
        self.assertCountEqual(self.race(lambda index,actor:confirm_document(docs[index].pk,kind='issue',actor=actor)),['ok','rejected'])
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,0)
        self.assertEqual(StockMovement.objects.filter(movement_type='EXPORT').count(),1)

    def test_concurrent_completion_is_terminal_without_consumption(self):
        self.import_stock(1); RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required='.25')
        order=self.order(); self.prepare(order)
        self.assertCountEqual(self.race(lambda index,actor:transition_order(order.pk,'COMPLETED',actor=actor)),['ok','rejected'])
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('.5')); self.assertEqual(StockMovement.objects.filter(order=order).count(),1)

    def test_concurrent_invoice_and_payment_once(self):
        order=self.completed(); self.assertEqual(self.race(lambda index,actor:issue_invoice(order.pk)),['ok','ok']); invoice=Invoice.objects.get(); key=uuid.uuid4()
        self.assertEqual(self.race(lambda index,actor:create_payment(invoice_id=invoice.pk,actor=actor,amount=invoice.total_amount,payment_method='CASH',request_key=key)),['ok','ok'])
        self.assertEqual(Payment.objects.count(),1)
