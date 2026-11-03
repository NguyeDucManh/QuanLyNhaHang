"""Financial snapshot, ownership, demo receipt, concurrency and real ASGI tests."""
import json,uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User,Group,Permission
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,connections,IntegrityError
from django.db import connection
from django.test import TestCase,TransactionTestCase,Client,RequestFactory
from django.urls import reverse
from django.utils import timezone
from .test_module03 import OrderFixtures
from .models import Invoice,Payment,Order,OrderItem
from .order_service import create_order,transition_order
from .kitchen_service import transition_kitchen_item
from .payment_service import issue_invoice,create_payment,report_customer_payment,confirm_payment
from .payment_demo import qr_payload
from .context_processors import business_dashboard
from restaurant_system.asgi import application


class FinancialFixtures(OrderFixtures):
    def invoice(self):
        order=create_order(actor=self.staff,customer=self.customer,order_type='TAKEAWAY',table=None,
            items=[{'menu_item':self.menu,'quantity':2}],discount_amount='1.25',request_key=uuid.uuid4())
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        item=order.items.get()
        transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
        transition_kitchen_item(order.pk,item.pk,'READY',actor=self.staff)
        transition_order(order.pk,'COMPLETED',actor=self.staff)
        return issue_invoice(order.pk,actor=self.staff)

    def attempt(self,invoice=None,method='CASH',actor=None,**kwargs):
        return create_payment(invoice_id=(invoice or self.inv).pk,actor=actor or self.customer,
            customer_initiated=True,payment_method=method,request_key=uuid.uuid4(),**kwargs)


class Module05Tests(FinancialFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def setUp(self): self.inv=self.invoice()

    def test_invoice_requires_completed_and_unique_snapshot(self):
        order=create_order(actor=self.staff,customer=self.customer,order_type='TAKEAWAY',table=None,
            items=[{'menu_item':self.menu,'quantity':1}],request_key=uuid.uuid4())
        with self.assertRaises(ValidationError): issue_invoice(order.pk,actor=self.staff)
        self.assertEqual(issue_invoice(self.inv.order_id,actor=self.manager).pk,self.inv.pk)
        self.assertEqual((self.inv.subtotal,self.inv.discount_amount,self.inv.total_amount),(self.inv.order.subtotal,self.inv.order.discount_amount,self.inv.order.total_amount))
        with self.assertRaises(IntegrityError),transaction.atomic(): Invoice.objects.create(order=self.inv.order,invoice_number='duplicate',subtotal=1,discount_amount=0,total_amount=1)

    def test_cash_and_bank_pending_backend_money_and_qr(self):
        for method in ('CASH','BANK_TRANSFER'):
            inv=self.inv if method=='CASH' else self.invoice()
            payment=self.attempt(inv,method)
            self.assertEqual((payment.status,payment.amount),('PENDING',inv.total_amount))
            self.assertIsNone(payment.customer_confirmed_at); self.assertIsNone(payment.paid_at)
            if method=='BANK_TRANSFER':
                data=json.loads(qr_payload(payment)); self.assertTrue(data['demo'])
                self.assertEqual(data['total_amount'],str(inv.total_amount)); self.assertEqual(data['invoice_number'],inv.invoice_number)
                self.assertEqual(data['payment_number'],payment.payment_number); self.assertTrue(data['reference'].startswith('DEMO-'))

    def test_customer_cannot_see_other_invoice_or_qr_report_start(self):
        payment=self.attempt(method='BANK_TRANSFER'); stranger=User.objects.create_user('other-customer')
        self.client.force_login(stranger)
        for url in (reverse('customer_invoice_detail',args=[self.inv.pk]),reverse('customer_payment_qr',args=[payment.pk])):
            self.assertEqual(self.client.get(url).status_code,404)
        for url in (reverse('customer_payment_start',args=[self.inv.pk]),reverse('customer_payment_report',args=[payment.pk])):
            self.assertEqual(self.client.post(url,{}).status_code,404)
        self.assertNotContains(self.client.get(reverse('customer_invoices')),self.inv.invoice_number)
        with self.assertRaises(PermissionDenied): self.attempt(actor=stranger)
        with self.assertRaises(PermissionDenied): report_customer_payment(payment.pk,actor=stranger)

    def test_client_amount_status_actor_reference_ignored(self):
        self.client.force_login(self.customer)
        payload={'payment_method':'BANK_TRANSFER','request_key':uuid.uuid4(),'amount':'0.01','status':'SUCCEEDED',
            'invoice_status':'PAID','confirmed_by':self.admin.pk,'transaction_reference':'ATTACK'}
        self.client.post(reverse('customer_payment_start',args=[self.inv.pk]),payload)
        p=Payment.objects.get(); self.assertEqual((p.amount,p.status,p.created_by_id),(self.inv.total_amount,'PENDING',self.customer.pk))
        self.assertIsNone(p.confirmed_by); self.assertNotEqual(p.transaction_reference,'ATTACK')
        self.inv.refresh_from_db(); self.assertEqual(self.inv.status,'UNPAID')
        self.client.post(reverse('customer_payment_report',args=[p.pk]),{'status':'SUCCEEDED','amount':1,'paid_at':'2099-01-01'})
        p.refresh_from_db(); self.assertEqual(p.status,'PENDING'); self.assertIsNotNone(p.customer_confirmed_at); self.assertIsNone(p.paid_at)

    def test_report_idempotent_never_marks_paid(self):
        p=self.attempt(); report_customer_payment(p.pk,actor=self.customer)
        p.refresh_from_db(); timestamp=p.customer_confirmed_at
        report_customer_payment(p.pk,actor=self.customer); p.refresh_from_db(); self.inv.refresh_from_db()
        self.assertEqual(p.customer_confirmed_at,timestamp); self.assertEqual((p.status,self.inv.status),('PENDING','UNPAID'))

    def test_confirm_requires_customer_receipt_then_shared_timestamp(self):
        p=self.attempt()
        with self.assertRaises(ValidationError): confirm_payment(p.pk,actor=self.staff)
        report_customer_payment(p.pk,actor=self.customer); confirm_payment(p.pk,actor=self.staff)
        p.refresh_from_db(); self.inv.refresh_from_db()
        self.assertEqual((p.status,self.inv.status),('SUCCEEDED','PAID'))
        self.assertEqual(p.paid_at,self.inv.paid_at); self.assertEqual(p.processed_at,p.paid_at); self.assertEqual(p.confirmed_by,self.staff)
        with self.assertRaises(ValidationError): confirm_payment(p.pk,actor=self.manager)
        with self.assertRaises(ValidationError): self.attempt()

    def test_failed_cancelled_keep_history_allow_new_attempt(self):
        for outcome in ('FAILED','CANCELLED'):
            p=self.attempt(); report_customer_payment(p.pk,actor=self.customer)
            confirm_payment(p.pk,actor=self.manager,outcome=outcome)
            p.refresh_from_db(); self.inv.refresh_from_db()
            self.assertEqual((p.status,self.inv.status),(outcome,'UNPAID')); self.assertIsNone(p.paid_at); self.assertIsNone(self.inv.paid_at)
            self.assertEqual(p.confirmed_by,self.manager); self.assertIsNotNone(p.processed_at)
            with self.assertRaises(ValidationError): confirm_payment(p.pk,actor=self.staff)
        p=self.attempt(); self.assertEqual(Payment.objects.count(),3)
        self.assertEqual(p.status,'PENDING')

    def test_duplicate_pending_customer_click_returns_existing(self):
        p=self.attempt(); self.assertEqual(self.attempt().pk,p.pk)
        with self.assertRaises(ValidationError): self.attempt(method='BANK_TRANSFER')
        self.assertEqual(Payment.objects.count(),1)

    def test_request_key_cannot_cross_invoice(self):
        key=uuid.uuid4()
        create_payment(invoice_id=self.inv.pk,actor=self.customer,customer_initiated=True,payment_method='CASH',request_key=key)
        other=self.invoice()
        with self.assertRaises(ValidationError): create_payment(invoice_id=other.pk,actor=self.customer,customer_initiated=True,payment_method='CASH',request_key=key)
        self.assertEqual(Payment.objects.count(),1)

    def test_tampered_database_amount_cannot_confirm(self):
        p=self.attempt(); report_customer_payment(p.pk,actor=self.customer); Payment.objects.filter(pk=p.pk).update(amount=1)
        with self.assertRaises(ValidationError): confirm_payment(p.pk,actor=self.admin)
        self.inv.refresh_from_db(); self.assertEqual(self.inv.status,'UNPAID')

    def test_paid_cancelled_invoice_blocks_attempt(self):
        Invoice.objects.filter(pk=self.inv.pk).update(status='CANCELLED')
        with self.assertRaises(ValidationError): self.attempt()

    def test_payment_live_unique_constraint_and_number_unique(self):
        p=self.attempt()
        with self.assertRaises(IntegrityError),transaction.atomic(): Payment.objects.create(invoice=self.inv,amount=p.amount,payment_method='CASH',created_by=self.customer)
        other=self.invoice()
        with self.assertRaises(IntegrityError),transaction.atomic(): Payment.objects.create(invoice=other,amount=other.total_amount,payment_method='CASH',created_by=self.customer,payment_number=p.payment_number)

    def test_staff_manager_admin_receipt_and_filter_real_data(self):
        p=self.attempt(); report_customer_payment(p.pk,actor=self.customer)
        for actor in (self.staff,self.manager,self.admin):
            self.client.force_login(actor)
            self.assertContains(self.client.get(reverse('admin_invoices'),{'q':p.payment_number,'receipts':'1'}),p.payment_number)
            self.assertContains(self.client.get(reverse('admin_payment_receipt',args=[p.pk])),'Xác nhận đã nhận tiền')
        self.assertContains(self.client.get(reverse('admin_invoices'),{'payment_status':'FAILED'}),'Chưa có thanh toán phù hợp.')

    def test_customer_and_revoked_staff_cannot_manage_or_confirm(self):
        p=self.attempt(); report_customer_payment(p.pk,actor=self.customer)
        self.client.force_login(self.customer)
        for url in (reverse('admin_invoices'),reverse('admin_payment_receipt',args=[p.pk])): self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.post(reverse('admin_payment_confirm',args=[p.pk]),{'outcome':'success'}).status_code,403)
        with self.assertRaises(PermissionDenied): confirm_payment(p.pk,actor=self.customer)
        Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='change_payment',content_type__app_label='customers'))
        actor=User.objects.get(pk=self.staff.pk)
        with self.assertRaises(PermissionDenied): confirm_payment(p.pk,actor=actor)

    def test_post_csrf_all_mutations_and_no_confirmation_on_get(self):
        p=self.attempt(); protected=Client(enforce_csrf_checks=True); protected.force_login(self.customer)
        for url in (reverse('customer_payment_start',args=[self.inv.pk]),reverse('customer_payment_report',args=[p.pk])):
            self.assertEqual(protected.get(url).status_code,405); self.assertEqual(protected.post(url,{}).status_code,403)
        protected.force_login(self.staff)
        url=reverse('admin_payment_confirm',args=[p.pk]); self.assertEqual(protected.get(url).status_code,405); self.assertEqual(protected.post(url,{'outcome':'success'}).status_code,403)

    def test_management_post_ignores_amount_and_pending_receipt_display(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('admin_payment_add',args=[self.inv.pk]),{'request_key':uuid.uuid4(),'amount':'1','payment_method':'CASH','status':'SUCCEEDED'})
        p=Payment.objects.get(); self.assertEqual((p.amount,p.status),(self.inv.total_amount,'PENDING'))
        self.assertContains(self.client.get(reverse('admin_payment_receipt',args=[p.pk])),'nhân viên ghi nhận trực tiếp')

    def test_customer_invoice_snapshots_and_demo_svg_backend(self):
        p=self.attempt(method='BANK_TRANSFER'); self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse('customer_invoice_detail',args=[self.inv.pk])),'CHUYỂN KHOẢN QR DEMO')
        response=self.client.get(reverse('customer_payment_qr',args=[p.pk])); self.assertEqual(response.status_code,200); self.assertIn(b'<svg',response.content)
        self.assertEqual(response['Cache-Control'],'no-store')

    def test_revenue_only_succeeded_not_completed_unpaid_failed(self):
        pending=self.attempt(); other=self.invoice(); failed=self.attempt(other); confirm_payment(failed.pk,actor=self.admin,outcome='FAILED')
        request=RequestFactory().get('/management/'); request.user=self.admin
        self.assertEqual(business_dashboard(request)['business_summary']['revenue_today'],0)
        report_customer_payment(pending.pk,actor=self.customer); confirm_payment(pending.pk,actor=self.admin)
        self.assertEqual(business_dashboard(request)['business_summary']['revenue_today'],self.inv.total_amount)

    def test_notifications_deferred_and_rollback_silent(self):
        with patch('customers.realtime.broadcast_invoice') as broadcast:
            with self.captureOnCommitCallbacks(execute=True):
                p=self.attempt(); self.assertEqual(broadcast.call_count,0)
            self.assertEqual(broadcast.call_count,1)
            broadcast.reset_mock()
            try:
                with transaction.atomic():
                    report_customer_payment(p.pk,actor=self.customer); raise ValidationError('rollback')
            except ValidationError: pass
            self.assertEqual(broadcast.call_count,0)
            p.refresh_from_db(); self.assertIsNone(p.customer_confirmed_at)


class Module05ConcurrencyTests(FinancialFixtures,TransactionTestCase):
    def setUp(self): self.initialize(); self.inv=self.invoice()
    def race(self,callback):
        barrier=Barrier(2)
        def worker(i):
            connections.close_all()
            try:
                barrier.wait(timeout=10); return callback(i)
            except ValidationError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(worker,[0,1]))

    def test_two_staff_confirm_only_one_success(self):
        p=self.attempt(); report_customer_payment(p.pk,actor=self.customer)
        def confirm(i): confirm_payment(p.pk,actor=User.objects.get(pk=[self.staff.pk,self.manager.pk][i])); return 'ok'
        self.assertCountEqual(self.race(confirm),['ok','rejected'])
        self.assertEqual(Payment.objects.filter(invoice=self.inv,status='SUCCEEDED').count(),1)
        self.inv.refresh_from_db(); self.assertEqual(self.inv.status,'PAID')

    def test_concurrent_customer_start_one_pending_attempt(self):
        def start(i): return self.attempt(actor=User.objects.get(pk=self.customer.pk)).pk
        ids=self.race(start); self.assertEqual(ids[0],ids[1]); self.assertEqual(Payment.objects.count(),1)


class Module05SocketTests(FinancialFixtures,TransactionTestCase):
    def setUp(self):
        self.initialize(); self.inv=self.invoice(); self.clients={}
        for role in ('admin','manager','staff','customer'):
            client=Client(); client.force_login(getattr(self,role)); self.clients[role]=client
    def socket(self,path,role='staff'):
        headers=[(b'origin',b'http://localhost')]
        if role: headers.append((b'cookie',('sessionid='+self.clients[role].cookies['sessionid'].value).encode()))
        return WebsocketCommunicator(application,path,headers=headers)

    async def test_financial_management_roles_owner_only_customer_room(self):
        for role in ('admin','manager','staff'):
            s=self.socket('/ws/management/payments/',role); self.assertTrue((await s.connect())[0]); await s.disconnect()
        for role in ('customer',None):
            s=self.socket('/ws/management/payments/',role); self.assertFalse((await s.connect())[0]); await s.disconnect()
        s=self.socket(f'/ws/customer/invoices/{self.inv.pk}/','customer'); self.assertTrue((await s.connect())[0]); await s.disconnect()
        s=self.socket(f'/ws/customer/invoices/{self.inv.pk}/','staff'); self.assertFalse((await s.connect())[0]); await s.disconnect()

    async def test_customer_report_notifies_staff_then_confirm_notifies_customer_paid(self):
        p=await database_sync_to_async(self.attempt)()
        staff=self.socket('/ws/management/payments/'); customer=self.socket(f'/ws/customer/invoices/{self.inv.pk}/','customer')
        self.assertTrue((await staff.connect())[0]); self.assertTrue((await customer.connect())[0])
        await database_sync_to_async(report_customer_payment)(p.pk,actor=self.customer)
        self.assertEqual((await staff.receive_json_from())['payment_id'],p.pk)
        self.assertEqual((await customer.receive_json_from())['status'],'UNPAID')
        await database_sync_to_async(confirm_payment)(p.pk,actor=self.staff)
        self.assertEqual((await customer.receive_json_from())['status'],'PAID')
        self.assertEqual((await staff.receive_json_from())['type'],'payment.updated')
        await staff.disconnect(); await customer.disconnect()

    async def test_revoke_financial_permission_closes_before_next_data(self):
        s=self.socket('/ws/management/payments/'); self.assertTrue((await s.connect())[0])
        @database_sync_to_async
        def revoke(): Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='view_payment',content_type__app_label='customers'))
        await revoke(); await database_sync_to_async(self.attempt)()
        self.assertEqual((await s.receive_output())['code'],4403); await s.disconnect()


class Module05MigrationTests(TransactionTestCase):
    def test_multiple_legacy_receipts_unique_backfill_preserves_original_fields(self):
        from django.db.migrations.executor import MigrationExecutor
        old_target=[('customers','0011_legacy_kitchen_states')]
        executor=MigrationExecutor(connection); executor.migrate(old_target)
        try:
            old=executor.loader.project_state(old_target).apps
            user=old.get_model('auth','User').objects.create(username='legacy-payment')
            paid_at=timezone.now(); ids=[]
            for index in range(2):
                order=old.get_model('customers','Order').objects.create(created_by_id=user.pk,status='COMPLETED',subtotal=100,discount_amount=10,total_amount=90)
                invoice=old.get_model('customers','Invoice').objects.create(order=order,invoice_number=f'LEGACY-INV-{index}',subtotal=100,discount_amount=10,total_amount=90,status='PAID')
                payment=old.get_model('customers','Payment').objects.create(invoice=invoice,created_by_id=user.pk,confirmed_by_id=user.pk,payment_method='CASH',status='SUCCEEDED',amount=90,paid_at=paid_at)
                ids.append((invoice.pk,payment.pk))
            executor=MigrationExecutor(connection); executor.migrate(executor.loader.graph.leaf_nodes())
            for invoice_id,payment_id in ids:
                invoice=Invoice.objects.get(pk=invoice_id); payment=Payment.objects.get(pk=payment_id)
                self.assertEqual((invoice.status,invoice.total_amount,payment.status,payment.amount),('PAID',90,'SUCCEEDED',90))
                self.assertEqual(invoice.paid_at,paid_at); self.assertEqual(payment.paid_at,paid_at)
                self.assertEqual(payment.processed_at,paid_at); self.assertIsNone(payment.customer_confirmed_at)
                self.assertFalse(payment.customer_initiated)
            self.assertEqual(Payment.objects.values('payment_number').distinct().count(),2)
        finally:
            restore=MigrationExecutor(connection); restore.migrate(restore.loader.graph.leaf_nodes())
