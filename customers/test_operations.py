"""Operational regressions run only against Django's isolated test database."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .test_business import BusinessData
from .models import *
from .purchasing_service import create_purchase_order, transition_purchase_order, receive_purchase_order
from .food_cost_service import calculate_food_cost, convert_quantity
from .loyalty_service import earn_payment, adjust_points
from .booking_advanced_service import join_waitlist, convert_waitlist, mark_arrival, transfer_table
from .booking_service import create_booking
from .payment_service import issue_invoice, create_payment, confirm_payment
from .inventory_service import confirm_document


class OperationData(BusinessData):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def po(self,quantity=100):
        return create_purchase_order(actor=self.admin,supplier=self.supplier,items=[{'ingredient':self.fish,'quantity':quantity,'unit_price':5}],request_key=uuid.uuid4())
    def approved(self):
        po=self.po();transition_purchase_order(po.pk,'SUBMITTED',actor=self.admin);return transition_purchase_order(po.pk,'APPROVED',actor=self.admin)
    def receive(self,po,quantity,key=None,**kwargs):
        return receive_purchase_order(po.pk,actor=kwargs.pop('actor',self.admin),items=[{'item_id':po.items.get().pk,'quantity':quantity}],request_key=key or uuid.uuid4(),date=timezone.localdate(),**kwargs)
    def booking(self,guests=4):
        future=timezone.localtime()+timedelta(days=1)
        return create_booking(user=self.customer,name='Guest',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None,microsecond=0),guests=guests)
    def waiting(self):
        RestaurantTable.objects.update(status='MAINTENANCE')
        future=timezone.localtime()+timedelta(days=1)
        return join_waitlist(customer=self.customer,name='Guest',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None,microsecond=0),guests=4,consent=True,request_key=uuid.uuid4())


class PurchaseTests(OperationData,TestCase):
    def test_create_backend_totals(self):
        po=self.po();self.assertEqual(po.subtotal,500);self.assertEqual(po.items.get().unit,'kg')
    def test_create_retry(self):
        key=uuid.uuid4();a=create_purchase_order(actor=self.admin,supplier=self.supplier,items=[{'ingredient':self.fish,'quantity':2,'unit_price':5}],request_key=key)
        b=create_purchase_order(actor=self.admin,supplier=self.supplier,items=[],request_key=key)
        self.assertEqual(a.pk,b.pk)
    def test_workflow_approval(self):
        po=self.approved();self.assertEqual(po.approved_by,self.admin)
    def test_illegal_transition(self):
        po=self.po()
        with self.assertRaises(ValidationError): transition_purchase_order(po.pk,'RECEIVED',actor=self.admin)
        with self.assertRaises(ValidationError): self.receive(po,1)
    def test_partial_then_complete(self):
        po=self.approved();self.receive(po,60);po.refresh_from_db();self.assertEqual(po.status,'PARTIALLY_RECEIVED')
        self.receive(po,40);po.refresh_from_db();self.fish.refresh_from_db()
        self.assertEqual(po.status,'RECEIVED');self.assertEqual(self.fish.current_stock,100)
        self.assertEqual(po.receivings.count(),2)
    def test_receipt_and_movement_linked(self):
        po=self.approved();receipt=self.receive(po,10)
        self.assertEqual(receipt.items.get().quantity,10)
        self.assertEqual(StockMovement.objects.get(receipt=receipt).quantity,10)
        self.assertEqual(po.receivings.get().receipt_id,receipt.pk)
    def test_retry_does_not_increment_stock(self):
        po=self.approved();key=uuid.uuid4();a=self.receive(po,100,key);b=self.receive(po,100,key)
        self.fish.refresh_from_db();self.assertEqual(a.pk,b.pk);self.assertEqual(self.fish.current_stock,100)
    def test_retry_changed_payload_rejected(self):
        po=self.approved();key=uuid.uuid4();self.receive(po,10,key)
        with self.assertRaises(ValidationError): self.receive(po,20,key)
    def test_over_receive_rolls_back(self):
        po=self.approved()
        with self.assertRaises(ValidationError): self.receive(po,101)
        self.assertFalse(StockReceipt.objects.exists());self.assertFalse(StockMovement.objects.exists())
    def test_cancelled_not_receivable(self):
        po=self.approved();transition_purchase_order(po.pk,'CANCELLED',actor=self.admin)
        with self.assertRaises(ValidationError): self.receive(po,1)
    def test_partial_cannot_cancel(self):
        po=self.approved();self.receive(po,1)
        with self.assertRaises(ValidationError): transition_purchase_order(po.pk,'CANCELLED',actor=self.admin)
    def test_atomic_failure_after_stock(self):
        po=self.approved()
        original=PurchaseOrderItem.full_clean
        def fail(instance,*args,**kwargs):
            if instance.quantity_received: raise ValidationError('Injected failure')
            return original(instance,*args,**kwargs)
        with patch.object(PurchaseOrderItem,'full_clean',fail),self.assertRaises(ValidationError): self.receive(po,10)
        self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,0)
        self.assertFalse(StockReceipt.objects.exists());self.assertFalse(PurchaseReceiving.objects.exists());self.assertFalse(StockMovement.objects.exists())
    def test_permissions(self):
        with self.assertRaises(PermissionDenied): self.receive(self.approved(),1,actor=self.staff)
        with self.assertRaises(PermissionDenied): create_purchase_order(actor=self.customer,supplier=self.supplier,items=[],request_key=uuid.uuid4())
    def test_manual_receipt_key_cannot_be_reused(self):
        receipt=self.receipt();po=self.approved()
        with self.assertRaises(ValidationError): self.receive(po,10,receipt.request_key)
    def test_duplicate_ingredients(self):
        with self.assertRaises(ValidationError): create_purchase_order(actor=self.admin,supplier=self.supplier,items=[{'ingredient':self.fish,'quantity':1,'unit_price':5}]*2,request_key=uuid.uuid4())


class FoodCostTests(OperationData,TestCase):
    def recipe(self,ingredient=None,quantity='.25'):
        return RecipeIngredient.objects.create(menu_item=self.menu,ingredient=ingredient or self.fish,quantity_required=Decimal(quantity))
    def test_one_ingredient(self):
        self.recipe();self.import_stock();self.assertEqual(calculate_food_cost(self.menu)['cost'],Decimal('1.25'))
    def test_multiple_ingredients(self):
        self.recipe();self.recipe(self.butter,'.5');self.import_stock()
        receipt=self.receipt(items=[{'ingredient':self.butter,'quantity':10,'unit_price':4}]);confirm_document(receipt.pk,kind='receipt',actor=self.admin)
        self.assertEqual(calculate_food_cost(self.menu)['cost'],Decimal('3.25'))
    def test_mass_conversion(self):
        self.assertEqual(convert_quantity(1,'kg','g'),1000);self.assertEqual(convert_quantity(250,'g','kg'),Decimal('.25'))
    def test_volume_conversion(self): self.assertEqual(convert_quantity(1,'l','ml'),1000)
    def test_piece_and_incompatible(self):
        self.assertEqual(convert_quantity(2,'piece','piece'),2)
        with self.assertRaises(ValidationError): convert_quantity(1,'kg','l')
    def test_missing_cost_is_none(self):
        self.recipe();result=calculate_food_cost(self.menu);self.assertIsNone(result['cost']);self.assertEqual(result['status'],'Chưa đủ dữ liệu')
    def test_draft_does_not_price(self):
        self.recipe();self.receipt();self.assertIsNone(calculate_food_cost(self.menu)['cost'])
    def test_zero_selling_price(self):
        self.recipe();self.import_stock();self.menu.price=0;self.assertIsNone(calculate_food_cost(self.menu)['percentage'])
    def test_recalculate_after_purchase(self):
        self.recipe();self.import_stock();po=self.approved();receive_purchase_order(po.pk,actor=self.admin,items=[{'item_id':po.items.get().pk,'quantity':10,'unit_price':20}],request_key=uuid.uuid4(),date=timezone.localdate())
        self.assertEqual(calculate_food_cost(self.menu)['cost'],5)


class LoyaltyTests(OperationData,TestCase):
    def payment(self):
        order=self.completed();order.customer=self.customer;order.save()
        invoice=issue_invoice(order.pk,actor=self.admin)
        return create_payment(invoice_id=invoice.pk,actor=self.admin,payment_method='CASH',request_key=uuid.uuid4())
    @override_settings(LOYALTY_VND_PER_POINT=100)
    def test_success_and_retry(self):
        payment=self.payment();confirm_payment(payment.pk,actor=self.admin);earn_payment(payment.pk);earn_payment(payment.pk)
        self.assertEqual(self.customer.loyalty.points_balance,2);self.assertEqual(LoyaltyTransaction.objects.count(),1)
    def test_failed_no_points(self):
        payment=self.payment();confirm_payment(payment.pk,actor=self.admin,successful=False);self.assertIsNone(earn_payment(payment.pk));self.assertFalse(CustomerLoyalty.objects.exists())
    def test_cancelled_order_no_points(self):
        payment=self.payment();Order.objects.filter(pk=payment.invoice.order_id).update(status='CANCELLED');confirm_payment(payment.pk,actor=self.admin)
        self.assertFalse(CustomerLoyalty.objects.exists())
    @override_settings(LOYALTY_VND_PER_POINT=1,LOYALTY_TIERS=[('MEMBER',0),('SILVER',100),('GOLD',500),('VIP',1000)])
    def test_tier_upgrade(self):
        confirm_payment(self.payment().pk,actor=self.admin);self.assertEqual(self.customer.loyalty.tier,'SILVER')
    def test_adjust_permission(self):
        with self.assertRaises(PermissionDenied): adjust_points(self.customer.pk,actor=self.staff,points=2,reason='Test',request_key=uuid.uuid4())
    def test_adjust_reason_balance_and_retry(self):
        key=uuid.uuid4();a=adjust_points(self.customer.pk,actor=self.admin,points=5,reason='Correction',request_key=key);b=adjust_points(self.customer.pk,actor=self.admin,points=5,reason='Correction',request_key=key)
        self.assertEqual(a.pk,b.pk);self.assertEqual(self.customer.loyalty.points_balance,5)
        with self.assertRaises(ValidationError): adjust_points(self.customer.pk,actor=self.admin,points=-6,reason='Correction',request_key=uuid.uuid4())
        self.assertTrue(AuditLog.objects.filter(action='LOYALTY_ADJUST',actor=self.admin).exists())
    def test_history_owner_only(self):
        adjust_points(self.customer.pk,actor=self.admin,points=5,reason='Private correction',request_key=uuid.uuid4())
        self.client.force_login(self.staff);self.assertNotContains(self.client.get(reverse('loyalty_customer')),'Private correction')
        self.client.force_login(self.customer);self.assertContains(self.client.get(reverse('loyalty_customer')),'Private correction')


class AdvancedBookingTests(OperationData,TestCase):
    def test_waitlist_requires_consent(self):
        future=timezone.localtime()+timedelta(days=1)
        with self.assertRaises(ValidationError): join_waitlist(customer=self.customer,name='A',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None),guests=2,consent=False,request_key=uuid.uuid4())
    def test_waitlist_and_convert_retry(self):
        row=self.waiting();RestaurantTable.objects.filter(pk=self.table.pk).update(status='AVAILABLE')
        booking=convert_waitlist(row.pk,actor=self.admin);self.assertEqual(convert_waitlist(row.pk,actor=self.admin).pk,booking.pk)
        self.assertEqual(Booking.objects.count(),1);self.assertEqual(booking.table_id,self.table.pk)
    def test_convert_permission(self):
        with self.assertRaises(PermissionDenied): convert_waitlist(self.waiting().pk,actor=self.staff)
    def test_convert_no_table_rolls_back(self):
        row=self.waiting()
        with self.assertRaises(ValidationError): convert_waitlist(row.pk,actor=self.admin)
        row.refresh_from_db();self.assertEqual(row.status,'WAITING');self.assertFalse(Booking.objects.exists())
    def test_checkin(self):
        b=self.booking()
        with patch('customers.booking_advanced_service.timezone.now',return_value=b.start_time+timedelta(minutes=1)):
            first=mark_arrival(b.pk,actor=self.admin,state='CHECKED_IN');self.assertEqual(mark_arrival(b.pk,actor=self.admin,state='CHECKED_IN').pk,first.pk)
        b.table.refresh_from_db();self.assertEqual(b.table.status,'OCCUPIED');self.assertEqual(Booking.objects.get(pk=b.pk).status,'CONFIRMED')
    def test_noshow_only_after_hold(self):
        b=self.booking()
        with self.assertRaises(ValidationError): mark_arrival(b.pk,actor=self.admin,state='NO_SHOW')
        with patch('customers.booking_advanced_service.timezone.now',return_value=b.start_time+timedelta(minutes=16)):
            mark_arrival(b.pk,actor=self.admin,state='NO_SHOW')
        b.refresh_from_db();self.assertEqual(b.status,'CANCELLED');self.assertEqual(b.visit.state,'NO_SHOW')
    def test_checked_in_cannot_noshow(self):
        b=self.booking()
        with patch('customers.booking_advanced_service.timezone.now',return_value=b.start_time+timedelta(minutes=1)):
            mark_arrival(b.pk,actor=self.admin,state='CHECKED_IN')
            with self.assertRaises(ValidationError): mark_arrival(b.pk,actor=self.admin,state='NO_SHOW')
    def destination(self,capacity=4): return RestaurantTable.objects.create(area=self.area,code='DEST',capacity=capacity)
    def test_transfer_identity_and_retry(self):
        b=self.booking();dest=self.destination();old=b.pk
        transfer_table(actor=self.admin,booking_id=b.pk,destination_id=dest.pk);transfer_table(actor=self.admin,booking_id=b.pk,destination_id=dest.pk)
        b.refresh_from_db();self.assertEqual((b.pk,b.table_id),(old,dest.pk));self.assertEqual(Booking.objects.count(),1)
    def test_transfer_capacity(self):
        b=self.booking()
        with self.assertRaises(ValidationError): transfer_table(actor=self.admin,booking_id=b.pk,destination_id=self.destination(2).pk)
    def test_transfer_conflict(self):
        b=self.booking();dest=self.destination();Booking.objects.create(user=self.customer,name='B',phone='0912345678',date=b.date,time=b.time,guests=2,status='CONFIRMED',table=dest,start_time=b.start_time,end_time=b.end_time)
        with self.assertRaises(ValidationError): transfer_table(actor=self.admin,booking_id=b.pk,destination_id=dest.pk)
    def test_transfer_rollback(self):
        b=self.booking();dest=self.destination()
        with patch('customers.booking_advanced_service.record',side_effect=ValidationError('Injected')),self.assertRaises(ValidationError): transfer_table(actor=self.admin,booking_id=b.pk,destination_id=dest.pk)
        b.refresh_from_db();self.assertEqual(b.table_id,self.table.pk)
    def test_realtime_on_commit(self):
        b=self.booking()
        with patch('customers.booking_advanced_service.transaction.on_commit') as callback: transfer_table(actor=self.admin,booking_id=b.pk,destination_id=self.destination().pk)
        self.assertTrue(callback.called)
    def test_completed_visit_releases_table(self):
        from .booking_service import transition_booking
        b=self.booking()
        with patch('customers.booking_advanced_service.timezone.now',return_value=b.start_time+timedelta(minutes=1)): mark_arrival(b.pk,actor=self.admin,state='CHECKED_IN')
        with self.assertRaises(ValidationError):transition_booking(b.pk,'COMPLETED')
        from .table_session_service import release
        release(actor=self.admin,booking_id=b.pk,reason='Khách rời bàn, quản lý kiểm tra',confirm=True,override=True)
        b.table.refresh_from_db();self.assertEqual(b.table.status,'AVAILABLE')


class AuditAndViewsTests(OperationData,TestCase):
    def test_menu_price_actor_and_no_secrets(self):
        from .audit_service import audit_actor
        with audit_actor(self.admin): self.menu.price=123;self.menu.save()
        event=AuditLog.objects.filter(entity_type='MenuItem',entity_id=str(self.menu.pk),action='UPDATE').latest('pk')
        self.assertEqual(event.actor,self.admin);self.assertEqual(Decimal(event.before_data['price']),100);self.assertEqual(Decimal(str(event.after_data['price'])),123)
        with audit_actor(self.admin): self.customer.set_password('NEVER_LOG_THIS');self.customer.save()
        self.assertNotIn('NEVER_LOG_THIS',str(list(AuditLog.objects.values('before_data','after_data'))))
    def test_normal_users_cannot_edit_audit(self):
        self.client.force_login(self.customer);self.assertEqual(self.client.get(reverse('audit_logs')).status_code,403)
        self.client.force_login(self.admin);self.assertEqual(self.client.post(reverse('audit_logs'),{'action':'DELETE'}).status_code,405)
        self.assertFalse(Permission.objects.filter(content_type__model='auditlog',codename__startswith='delete_').exists())
    def test_new_permissions_not_granted(self):
        for code in ('receive_purchaseorder','checkin_booking','transfer_table','adjust_customerloyalty'):
            self.assertFalse(self.staff.has_perm('customers.'+code));self.assertFalse(self.manager.has_perm('customers.'+code))
    def test_management_pages(self):
        self.client.force_login(self.admin)
        po=self.approved();b=self.booking()
        for name,args in [('purchase_orders',[]),('purchase_add',[]),('purchase_order_detail',[po.pk]),('supplier_prices',[]),('food_cost',[]),('audit_logs',[]),('loyalty_management',[]),('waitlist_management',[]),('booking_operations',[b.pk]),('table_history',[self.table.pk]),('staff_home',[])]:
            with self.subTest(name=name): self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200)
        self.assertEqual(self.client.post(reverse('purchase_action',args=[po.pk]),{'action':'receive','date':'2026-02-31'}).status_code,302)
        self.assertEqual(self.client.get(reverse('audit_logs'),{'from':'2026-02-31'}).status_code,200)
    def test_new_pages_denied_without_permissions(self):
        self.client.force_login(self.staff)
        for name in ('purchase_orders','purchase_add','audit_logs','loyalty_management','waitlist_management'):
            with self.subTest(name=name): self.assertEqual(self.client.get(reverse(name)).status_code,403)


class ConcurrentOperationsTests(OperationData,TransactionTestCase):
    def setUp(self): self.initialize()
    def concurrent(self,function):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        barrier=Barrier(2)
        def worker(index):
            try:
                barrier.wait(timeout=10)
                return function(index)
            except ValidationError: return 'REJECTED'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(worker,range(2)))
    def test_same_receipt_retry_concurrent(self):
        po=self.approved();key=uuid.uuid4()
        results=self.concurrent(lambda _:self.receive(po,100,key).pk)
        self.assertEqual(results[0],results[1]);self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,100)
        self.assertEqual(PurchaseReceiving.objects.count(),1)
    def test_two_receivers_cannot_over_receive(self):
        po=self.approved()
        results=self.concurrent(lambda _:self.receive(po,60).pk)
        self.assertEqual(results.count('REJECTED'),1);self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,60)
    def test_waitlist_convert_concurrent(self):
        row=self.waiting();RestaurantTable.objects.filter(pk=self.table.pk).update(status='AVAILABLE')
        results=self.concurrent(lambda _:convert_waitlist(row.pk,actor=self.admin).pk)
        self.assertEqual(results[0],results[1]);self.assertEqual(Booking.objects.count(),1)
    @override_settings(LOYALTY_VND_PER_POINT=100)
    def test_earn_concurrent(self):
        order=self.completed();order.customer=self.customer;order.save()
        invoice=issue_invoice(order.pk,actor=self.admin);payment=create_payment(invoice_id=invoice.pk,actor=self.admin,payment_method='CASH',request_key=uuid.uuid4())
        with patch('customers.loyalty_service.earn_payment'): confirm_payment(payment.pk,actor=self.admin)
        results=self.concurrent(lambda _:earn_payment(payment.pk).pk)
        self.assertEqual(results[0],results[1]);self.assertEqual(CustomerLoyalty.objects.get(customer=self.customer).points_balance,2)
    async def test_inventory_socket_permissions_commit_and_revocation(self):
        from channels.db import database_sync_to_async
        from channels.testing import WebsocketCommunicator
        from restaurant_system.asgi import application
        from django.test import Client
        from django.contrib.auth.models import Group
        @database_sync_to_async
        def cookie(user):
            client=Client();client.force_login(user);return client.cookies['sessionid'].value
        async def socket(user):
            return WebsocketCommunicator(application,'/ws/management/inventory/',headers=[(b'origin',b'http://localhost'),(b'cookie',('sessionid='+await cookie(user)).encode())])
        denied=await socket(self.customer);connected,code=await denied.connect();self.assertFalse(connected);self.assertEqual(code,4403);await denied.disconnect()
        manager=await socket(self.manager);connected,_=await manager.connect();self.assertTrue(connected)
        await database_sync_to_async(self.import_stock)(2)
        self.assertEqual((await manager.receive_json_from())['type'],'inventory.updated')
        @database_sync_to_async
        def revoke():
            Group.objects.get(name='MANAGER').permissions.remove(*Permission.objects.filter(codename__in=['view_ingredient','view_stockmovement','view_purchaseorder']))
        await revoke()
        from customers.realtime import notify_inventory_changed
        await database_sync_to_async(notify_inventory_changed)()
        self.assertEqual((await manager.receive_output())['code'],4403);await manager.disconnect()
