"""Local contract/security tests. Signed fixtures are NOT a Stripe Test Mode run."""
import hashlib,hmac,json,time,uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch,MagicMock
import stripe
from django.conf import settings
from django.core.exceptions import ValidationError,PermissionDenied,ImproperlyConfigured
from django.test import TestCase,TransactionTestCase,override_settings,Client
from django.urls import reverse
from django.utils import timezone
from .test_business import BusinessData
from .models import *
from .booking_service import create_booking,transition_booking,overlaps
from .deposit_service import checkout,expire_booking,deposit_amount,metadata
from .order_service import open_order_from_booking,transition_order
from .payment_service import issue_invoice,create_payment,confirm_payment


@override_settings(STRIPE_SECRET_KEY='sk_test_unit_fixture',STRIPE_WEBHOOK_SECRET='whsec_unit_fixture')
class DepositTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize();cls.menu.price=1000000;cls.menu.save()
    def booking(self,**kwargs):
        future=timezone.localtime()+timedelta(days=2)
        values=dict(user=self.customer,name='Guest',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None,microsecond=0),guests=4,food_cart={str(self.menu.pk):1},online=True)
        values.update(kwargs);return create_booking(**values)
    def attempt(self,b):
        return StripeCheckoutAttempt.objects.create(deposit=b.deposit,session_id='cs_test_'+uuid.uuid4().hex,status='OPEN',stripe_expires_at=b.deposit.expires_at,checkout_url='https://checkout.stripe.com/c/pay/cs_test_fixture')
    def event(self,b,attempt=None,kind='checkout.session.completed',**updates):
        attempt=attempt or self.attempt(b)
        obj={'id':attempt.session_id,'object':'checkout.session','metadata':metadata(b.deposit,attempt),'currency':'vnd','amount_total':int(b.deposit.amount),'status':'complete','payment_status':'paid','payment_intent':'pi_'+uuid.uuid4().hex}
        obj.update(updates)
        return {'id':'evt_'+uuid.uuid4().hex,'type':kind,'livemode':False,'data':{'object':obj}}
    def webhook(self,event,valid=True):
        body=json.dumps(event,separators=(',',':')).encode();timestamp=int(time.time())
        signature=hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(),str(timestamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
        return self.client.post(reverse('stripe_webhook'),body,content_type='application/json',HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={signature if valid else "invalid"}')
    def paid(self):
        b=self.booking();self.assertEqual(self.webhook(self.event(b)).status_code,200);b.refresh_from_db();return b
    def final_invoice(self,b):
        order=open_order_from_booking(b.pk,actor=self.admin);self.prepare(order);transition_order(order.pk,'COMPLETED',actor=self.admin)
        return issue_invoice(order.pk,actor=self.admin)
    def test_online_pending_and_snapshot(self):
        b=self.booking();self.assertEqual(b.status,'PENDING_DEPOSIT');self.assertEqual(b.deposit.amount,200000);self.assertEqual(b.deposit.remaining_estimated_amount,800000)
    def test_manual_booking_preserved(self): self.assertEqual(self.booking(online=False).status,'CONFIRMED')
    @override_settings(BOOKING_DEPOSIT_REQUIRED=False)
    def test_config_opt_out(self): self.assertEqual(self.booking().status,'CONFIRMED')
    @override_settings(BOOKING_DEPOSIT_TYPE='PERCENT',BOOKING_DEPOSIT_VALUE='20',BOOKING_DEPOSIT_MINIMUM='100000')
    def test_percentage_and_no_preorder(self):
        self.assertEqual(deposit_amount(Decimal('1000000')),200000);self.assertEqual(deposit_amount(0),100000)
    @override_settings(BOOKING_DEPOSIT_TYPE='PERCENT',BOOKING_DEPOSIT_VALUE='101')
    def test_invalid_percentage(self):
        with self.assertRaises(ValidationError):self.booking()
    def test_staff_cannot_confirm_without_deposit(self):
        b=self.booking()
        with self.assertRaises(ValidationError):transition_booking(b.pk,'CONFIRMED')
        b.status='CONFIRMED'
        with self.assertRaises(ValidationError):b.full_clean()
    def test_pending_blocks_availability(self):
        b=self.booking();self.assertTrue(overlaps(b.table_id,b.start_time,b.end_time))
    def test_expired_hold_does_not_block_even_without_cron(self):
        b=self.booking();BookingDeposit.objects.filter(booking=b).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertFalse(overlaps(b.table_id,b.start_time,b.end_time))
    def test_expiration_releases_booking(self):
        b=self.booking();BookingDeposit.objects.filter(booking=b).update(expires_at=timezone.now()-timedelta(seconds=1));expire_booking(b.pk);b.refresh_from_db()
        self.assertEqual(b.status,'CANCELLED');self.assertEqual(b.deposit.status,'EXPIRED')
    def test_signature_required(self):
        b=self.booking();self.assertEqual(self.webhook(self.event(b),False).status_code,400);b.refresh_from_db();self.assertEqual(b.status,'PENDING_DEPOSIT')
    def test_success_confirms_atomic(self):
        b=self.paid();self.assertEqual(b.status,'CONFIRMED');self.assertEqual(b.deposit.status,'SUCCEEDED');self.assertIsNotNone(b.deposit.paid_at)
    def test_duplicate_event_and_session(self):
        b=self.booking();event=self.event(b);self.webhook(event);self.webhook(event)
        event['id']='evt_'+uuid.uuid4().hex;self.webhook(event)
        self.assertEqual(BookingDeposit.objects.count(),1);self.assertEqual(AuditLog.objects.filter(action='BOOKING_CONFIRMED_FROM_DEPOSIT').count(),1)
    def test_webhook_no_stock_or_loyalty(self):
        self.paid();self.assertFalse(StockMovement.objects.exists());self.assertFalse(LoyaltyTransaction.objects.exists())
    def test_wrong_amount(self):
        b=self.booking();self.assertEqual(self.webhook(self.event(b,amount_total=1)).status_code,409);self.assertEqual(Booking.objects.get(pk=b.pk).status,'PENDING_DEPOSIT')
    def test_wrong_currency(self):
        b=self.booking();self.assertEqual(self.webhook(self.event(b,currency='usd')).status_code,409)
    def test_wrong_session(self):
        b=self.booking();self.assertEqual(self.webhook(self.event(b,id='cs_test_wrong')).status_code,409)
    def test_wrong_customer(self):
        b=self.booking();event=self.event(b);event['data']['object']['metadata']['customer_id']=str(self.admin.pk);self.assertEqual(self.webhook(event).status_code,409)
    def test_live_event_rejected(self):
        b=self.booking();event=self.event(b);event['livemode']=True;self.assertEqual(self.webhook(event).status_code,409)
    def test_unpaid_completed_does_not_confirm(self):
        b=self.booking();self.webhook(self.event(b,payment_status='unpaid'));b.refresh_from_db();self.assertEqual(b.status,'PENDING_DEPOSIT')
    def test_failed_payment(self):
        b=self.booking();self.webhook(self.event(b,kind='checkout.session.async_payment_failed',payment_status='unpaid'));b.refresh_from_db();self.assertEqual(b.status,'PENDING_DEPOSIT');self.assertEqual(b.deposit.status,'FAILED')
    def test_expired_session_allows_new_attempt_within_hold(self):
        b=self.booking();self.webhook(self.event(b,kind='checkout.session.expired',status='expired',payment_status='unpaid'));b.refresh_from_db();self.assertEqual(b.status,'PENDING_DEPOSIT');self.assertEqual(b.deposit.attempts.get().status,'EXPIRED')
    def test_late_payment_is_review_not_new_hold(self):
        b=self.booking();event=self.event(b);BookingDeposit.objects.filter(booking=b).update(expires_at=timezone.now()-timedelta(seconds=1));expire_booking(b.pk);self.webhook(event);b.refresh_from_db()
        self.assertEqual(b.status,'CANCELLED');self.assertEqual(b.deposit.status,'SUCCEEDED');self.assertTrue(b.deposit.reconciliation_required)
    def test_cancel_preserves_paid_deposit(self):
        b=self.paid();transition_booking(b.pk,'CANCELLED',owner=self.customer);self.assertEqual(BookingDeposit.objects.get(booking=b).status,'SUCCEEDED')
    def test_cancel_pending(self):
        b=self.booking();transition_booking(b.pk,'CANCELLED',owner=self.customer);self.assertEqual(BookingDeposit.objects.get(booking=b).status,'CANCELLED')
    def test_success_url_is_read_only(self):
        b=self.booking();self.client.force_login(self.customer);r=self.client.get(reverse('booking_deposit_success',args=[b.pk]),{'session_id':'cs_test_fake'})
        self.assertEqual(r.status_code,200);self.assertNotContains(r,'<h1>Thanh toán thành công</h1>',html=True);self.assertEqual(Booking.objects.get(pk=b.pk).status,'PENDING_DEPOSIT')
    def test_other_customer_cannot_view_status_or_pay(self):
        b=self.booking();self.client.force_login(self.staff)
        for name in ('booking_deposit','booking_deposit_success','booking_deposit_status'):self.assertEqual(self.client.get(reverse(name,args=[b.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('booking_deposit_checkout',args=[b.pk])).status_code,404)
        protected=Client(enforce_csrf_checks=True);protected.force_login(self.customer)
        self.assertEqual(protected.post(reverse('booking_deposit_checkout',args=[b.pk])).status_code,403)
    def test_cancel_url_does_not_cancel_booking(self):
        b=self.booking();self.client.force_login(self.customer);self.assertContains(self.client.get(reverse('booking_deposit',args=[b.pk]),{'cancelled':'1'}),'Thanh toán chưa hoàn tất');self.assertEqual(Booking.objects.get(pk=b.pk).status,'PENDING_DEPOSIT')
    def test_final_invoice_deduction(self):
        invoice=self.final_invoice(self.paid());self.assertEqual((invoice.total_amount,invoice.deposit_applied_amount,invoice.balance_due),(1000000,200000,800000))
        payment=create_payment(invoice_id=invoice.pk,actor=self.admin,payment_method='CASH',request_key=uuid.uuid4());self.assertEqual(payment.amount,800000)
        confirm_payment(payment.pk,actor=self.admin);self.assertEqual(self.customer.loyalty.points_balance,100)
    def test_invoice_retry_applies_once(self):
        invoice=self.final_invoice(self.paid());self.assertEqual(issue_invoice(invoice.order_id,actor=self.admin).pk,invoice.pk);self.assertEqual(invoice.balance_due,800000)
    @override_settings(BOOKING_DEPOSIT_VALUE='2000000')
    def test_deposit_exceeding_invoice_has_no_negative_balance(self):
        invoice=self.final_invoice(self.paid());self.assertEqual(invoice.balance_due,0);self.assertEqual(invoice.deposit_applied_amount,1000000);self.assertEqual(invoice.status,'PAID');self.assertFalse(invoice.payments.exists());self.assertEqual(self.customer.loyalty.points_balance,100)
    def test_checkout_vnd_amount_and_retry(self):
        b=self.booking();client=MagicMock()
        def create(params,options):
            obj=stripe.StripeObject.construct_from({'id':'cs_test_contract','livemode':False,'amount_total':200000,'currency':'vnd','metadata':params['metadata'],'url':'https://checkout.stripe.com/c/pay/cs_test_contract','status':'open'},key=None)
            client.v1.checkout.sessions.retrieve.return_value=obj
            return obj
        client.v1.checkout.sessions.create.side_effect=create
        self.client.force_login(self.customer)
        with patch('customers.deposit_service.stripe_client',return_value=client):
            for _ in range(2):self.assertEqual(self.client.post(reverse('booking_deposit_checkout',args=[b.pk]),{'amount':'1','deposit_amount':'1'}).status_code,302)
        params=client.v1.checkout.sessions.create.call_args.args[0];self.assertEqual(params['line_items'][0]['price_data']['unit_amount'],200000)
        self.assertEqual(params['payment_method_types'],['card']);self.assertEqual(StripeCheckoutAttempt.objects.count(),1);self.assertEqual(client.v1.checkout.sessions.create.call_count,1)
    def test_network_retry_reuses_persisted_idempotency_key(self):
        b=self.booking();client=MagicMock();client.v1.checkout.sessions.create.side_effect=stripe.APIConnectionError('Unit fixture')
        with patch('customers.deposit_service.stripe_client',return_value=client):
            for _ in range(2):
                with self.assertRaises(stripe.APIConnectionError):checkout(b.pk,actor=self.customer)
        calls=client.v1.checkout.sessions.create.call_args_list;self.assertEqual(calls[0].kwargs['options'],calls[1].kwargs['options']);self.assertEqual(StripeCheckoutAttempt.objects.count(),1)
    @override_settings(STRIPE_SECRET_KEY='sk_live_forbidden_fixture')
    def test_live_key_is_never_used(self):
        b=self.booking()
        with self.assertRaises(ImproperlyConfigured):checkout(b.pk,actor=self.customer)
    def test_audit_has_no_card_or_secrets(self):
        self.paid();data=str(list(AuditLog.objects.values('before_data','after_data')))
        for value in ('sk_test_unit_fixture','whsec_unit_fixture','card_number','cvc'):self.assertNotIn(value,data)
    def test_payment_page_has_no_card_fields_or_manual_confirm(self):
        b=self.booking();self.client.force_login(self.customer);r=self.client.get(reverse('booking_deposit',args=[b.pk]))
        self.assertContains(r,'Thanh toán an toàn qua Stripe');self.assertNotContains(r,'Tôi đã thanh toán');self.assertNotContains(r,'name="cvc"');self.assertNotContains(r,'name="card_number"')


@override_settings(STRIPE_WEBHOOK_SECRET='whsec_concurrent_contract_fixture')
class DepositConcurrentTests(BusinessData,TransactionTestCase):
    def setUp(self):self.initialize()
    def test_concurrent_duplicate_webhooks_confirm_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        future=timezone.localtime()+timedelta(days=1)
        b=create_booking(user=self.customer,name='Guest',phone='0912345678',date=future.date(),time=future.time().replace(tzinfo=None),guests=4,online=True)
        attempt=StripeCheckoutAttempt.objects.create(deposit=b.deposit,session_id='cs_test_concurrent_fixture',status='OPEN',stripe_expires_at=b.deposit.expires_at)
        event={'id':'evt_concurrent_contract','type':'checkout.session.completed','livemode':False,'data':{'object':{'id':attempt.session_id,'metadata':metadata(b.deposit,attempt),'currency':'vnd','amount_total':int(b.deposit.amount),'status':'complete','payment_status':'paid','payment_intent':'pi_concurrent_fixture'}}}
        body=json.dumps(event).encode();stamp=int(time.time());signature=hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(),str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
        barrier=Barrier(2)
        def worker(_):
            try:
                barrier.wait(timeout=10)
                return Client().post(reverse('stripe_webhook'),body,content_type='application/json',HTTP_STRIPE_SIGNATURE=f't={stamp},v1={signature}').status_code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(worker,range(2))),[200,200])
        self.assertEqual(StripeWebhookEvent.objects.filter(event_id=event['id']).count(),1)
        self.assertEqual(AuditLog.objects.filter(action='BOOKING_CONFIRMED_FROM_DEPOSIT').count(),1)
        self.assertEqual(Booking.objects.get(pk=b.pk).status,'CONFIRMED')
