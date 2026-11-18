"""Signed webhook/DB tests; provider fixtures are not actual hosted payments."""
import json,uuid,hashlib,hmac,time
from unittest.mock import MagicMock,patch
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .test_business import BusinessData
from .booking_service import create_booking
from .deposit_service import metadata,checkout,reconcile_checkout
from .models import Booking,BookingDeposit,StripeCheckoutAttempt,StripeWebhookEvent,AuditLog


@override_settings(STRIPE_SECRET_KEY='sk_test_hotfix_fixture',STRIPE_WEBHOOK_SECRET='whsec_hotfix_fixture',STRIPE_PUBLIC_BASE_URL='http://127.0.0.1:8000')
class StripeConfirmationTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        day=timezone.localtime()+timedelta(days=2)
        self.booking=create_booking(user=self.customer,name='Test guest',phone='0912345678',date=day.date(),time=day.time().replace(tzinfo=None,microsecond=0),guests=2,online=True)
        self.attempt=StripeCheckoutAttempt.objects.create(deposit=self.booking.deposit,session_id='cs_test_'+uuid.uuid4().hex,status='OPEN',stripe_expires_at=self.booking.deposit.expires_at,checkout_url='https://checkout.stripe.com/c/pay/cs_test_fixture')
        self.intent='pi_'+uuid.uuid4().hex;self.client.force_login(self.customer)
        self.provider=MagicMock();self.provider.v1.checkout.sessions.retrieve.return_value=self.provider_session(False)
        patcher=patch('customers.deposit_service.stripe_client',return_value=self.provider);patcher.start();self.addCleanup(patcher.stop)
    def provider_session(self,paid=True):
        values=metadata(self.booking.deposit,self.attempt)
        return {'id':self.attempt.session_id,'client_reference_id':str(self.booking.deposit.pk),'livemode':False,'currency':'vnd','amount_total':int(self.booking.deposit.amount),'metadata':values,'status':'complete' if paid else 'open','payment_status':'paid' if paid else 'unpaid','payment_intent':{'id':self.intent,'status':'succeeded','livemode':False,'amount':int(self.booking.deposit.amount),'amount_received':int(self.booking.deposit.amount),'currency':'vnd','metadata':values} if paid else None}
    def event(self,kind='checkout.session.completed',**values):
        obj={'id':self.attempt.session_id,'metadata':metadata(self.booking.deposit,self.attempt),'currency':'vnd','amount_total':int(self.booking.deposit.amount),'status':'complete','payment_status':'paid','payment_intent':self.intent};obj.update(values)
        return {'id':'evt_'+uuid.uuid4().hex,'type':kind,'livemode':False,'data':{'object':obj}}
    def webhook(self,event,*,valid=True):
        body=json.dumps(event).encode();timestamp=str(int(time.time()));digest=hmac.new(b'whsec_hotfix_fixture',timestamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
        return self.client.post(reverse('stripe_webhook'),body,content_type='application/json',HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={digest if valid else "invalid"}')
    def test_return_url_never_confirms_and_has_no_pay_form(self):
        r=self.client.get(reverse('booking_deposit_success',args=[self.booking.pk]),{'session_id':'cs_test_untrusted'})
        self.assertContains(r,'Chờ xác nhận tiền cọc');self.assertNotContains(r,'data-deposit-checkout');self.assertContains(r,'Không thanh toán lại')
        self.booking.refresh_from_db();self.assertEqual(self.booking.status,'PENDING_DEPOSIT');self.assertFalse(StripeWebhookEvent.objects.exists())
    def test_active_session_only_offers_resume_not_new_charge(self):
        r=self.client.get(reverse('booking_deposit',args=[self.booking.pk]));self.assertContains(r,'Kiểm tra / tiếp tục phiên Stripe hiện có');self.assertFalse(r.context['can_pay']);self.assertTrue(r.context['can_resume'])
    def test_completed_provider_session_redirects_to_wait_without_new_session(self):
        client=MagicMock();client.v1.checkout.sessions.retrieve.return_value={**self.event()['data']['object'],'livemode':False}
        with patch('customers.deposit_service.stripe_client',return_value=client):r=self.client.post(reverse('booking_deposit_checkout',args=[self.booking.pk]))
        self.assertRedirects(r,reverse('booking_deposit_success',args=[self.booking.pk]));client.v1.checkout.sessions.create.assert_not_called();self.assertEqual(StripeCheckoutAttempt.objects.count(),1)
        self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'PENDING')
    def test_existing_session_metadata_must_match_before_resume_or_wait(self):
        for field,value in [('id','cs_test_wrong'),('currency','usd'),('amount_total',1),('metadata',{})]:
            with self.subTest(field=field):
                client=MagicMock();session={**self.event()['data']['object'],'livemode':False};session[field]=value;client.v1.checkout.sessions.retrieve.return_value=session
                with patch('customers.deposit_service.stripe_client',return_value=client):
                    self.client.post(reverse('booking_deposit_checkout',args=[self.booking.pk]))
                client.v1.checkout.sessions.create.assert_not_called()
        self.assertEqual(StripeCheckoutAttempt.objects.count(),1)
    def test_delayed_webhook_after_browser_return_confirms_exactly_once(self):
        status=reverse('booking_deposit_status',args=[self.booking.pk])+'?awaiting=1'
        self.assertEqual(self.client.get(status).json()['payment_state'],'AWAITING_WEBHOOK')
        event=self.event();self.assertEqual(self.webhook(event).status_code,200);self.assertEqual(self.webhook(event).json()['outcome'],'DUPLICATE')
        event['id']='evt_'+uuid.uuid4().hex;self.assertEqual(self.webhook(event).status_code,200)
        state=self.client.get(status).json();self.assertTrue(state['confirmed']);self.assertFalse(state['can_pay']);self.assertFalse(state['can_resume'])
        self.assertEqual(AuditLog.objects.filter(action='BOOKING_CONFIRMED_FROM_DEPOSIT').count(),1)
        self.assertContains(self.client.get(reverse('booking_deposit_success',args=[self.booking.pk])),'Đặt bàn của bạn đã được xác nhận')
    def test_async_unpaid_then_success_and_late_failure_do_not_regress(self):
        self.assertEqual(self.webhook(self.event(payment_status='unpaid')).status_code,200);self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'PENDING')
        self.assertEqual(self.webhook(self.event('checkout.session.async_payment_succeeded')).status_code,200)
        self.assertEqual(self.webhook(self.event('checkout.session.async_payment_failed',payment_status='unpaid')).status_code,200)
        self.assertEqual(self.webhook(self.event('checkout.session.expired',status='expired',payment_status='unpaid')).status_code,200)
        self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'SUCCEEDED');self.assertEqual(StripeCheckoutAttempt.objects.get(pk=self.attempt.pk).status,'PAID')
    def test_failed_then_real_success_can_confirm_once(self):
        self.webhook(self.event('checkout.session.async_payment_failed',payment_status='unpaid'));self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'FAILED')
        self.webhook(self.event('checkout.session.async_payment_succeeded'));self.assertEqual(Booking.objects.get(pk=self.booking.pk).status,'CONFIRMED')
    def test_late_payment_after_deadline_is_review_and_never_pay_again(self):
        BookingDeposit.objects.filter(pk=self.booking.deposit.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.webhook(self.event()).status_code,200)
        state=self.client.get(reverse('booking_deposit_status',args=[self.booking.pk])).json();self.assertEqual(state['payment_state'],'RECONCILIATION');self.assertFalse(state['confirmed']);self.assertFalse(state['can_pay'])
        self.assertEqual(Booking.objects.get(pk=self.booking.pk).status,'CANCELLED');self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'SUCCEEDED')
    def test_invalid_signature_and_mismatch_logged_without_secret(self):
        with self.assertLogs('customers.deposit_views',level='WARNING') as logs:
            self.assertEqual(self.webhook(self.event(),valid=False).status_code,400)
            self.assertEqual(self.webhook(self.event(amount_total=1)).status_code,409)
        text=' '.join(logs.output);self.assertIn('status=400',text);self.assertIn('status=409',text);self.assertNotIn('whsec_hotfix_fixture',text);self.assertNotIn('Test guest',text)
        self.assertFalse(StripeWebhookEvent.objects.exists())
    def test_processing_failure_rolls_back_and_retry_succeeds(self):
        event=self.event();self.client.raise_request_exception=False
        with patch('customers.deposit_service.record',side_effect=RuntimeError('test rollback')):
            with self.assertLogs('customers.deposit_views',level='WARNING') as logs:self.assertEqual(self.webhook(event).status_code,500)
        self.assertIn('processing_failed_retry_required',' '.join(logs.output));self.assertFalse(StripeWebhookEvent.objects.exists());self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'PENDING')
        self.assertEqual(self.webhook(event).status_code,200);self.assertEqual(AuditLog.objects.filter(action='BOOKING_CONFIRMED_FROM_DEPOSIT').count(),1)
    def test_wrong_account_live_and_cross_booking_events_do_not_confirm(self):
        event=self.event();event['livemode']=True;self.assertEqual(self.webhook(event).status_code,409)
        event=self.event();event['data']['object']['metadata']['booking_id']='999999';self.assertEqual(self.webhook(event).status_code,409)
        self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'PENDING')
    def test_return_checks_stripe_api_and_confirms_without_listener(self):
        self.provider.v1.checkout.sessions.retrieve.return_value=self.provider_session()
        page=self.client.get(reverse('booking_deposit_success',args=[self.booking.pk]),{'session_id':'cs_test_client_cannot_select'})
        self.assertContains(page,'Đặt bàn của bạn đã được xác nhận')
        self.provider.v1.checkout.sessions.retrieve.assert_called_with(self.attempt.session_id,{'expand':['payment_intent']})
        self.assertEqual(Booking.objects.get(pk=self.booking.pk).status,'CONFIRMED');self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'SUCCEEDED')
        self.assertEqual(AuditLog.objects.filter(action='STRIPE_API_RECONCILED').count(),1);self.assertFalse(StripeWebhookEvent.objects.exists())
        self.client.get(reverse('booking_deposit_success',args=[self.booking.pk]));self.webhook(self.event())
        self.assertEqual(AuditLog.objects.filter(action='BOOKING_CONFIRMED_FROM_DEPOSIT').count(),1)
    def test_api_verification_rejects_wrong_amount_intent_or_metadata(self):
        cases=[('amount_received',1),('status','processing'),('livemode',True),('currency','usd'),('metadata',{})]
        from django.core.exceptions import ValidationError
        for field,value in cases:
            with self.subTest(field=field):
                session=self.provider_session();session['payment_intent'][field]=value;self.provider.v1.checkout.sessions.retrieve.return_value=session
                with self.assertRaises(ValidationError):reconcile_checkout(self.booking.pk,actor=self.customer)
        self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'PENDING')
    def test_api_unavailable_does_not_fake_payment(self):
        import stripe
        self.provider.v1.checkout.sessions.retrieve.side_effect=stripe.APIConnectionError('fixture')
        page=self.client.get(reverse('booking_deposit_success',args=[self.booking.pk]));self.assertContains(page,'Chờ xác nhận tiền cọc')
        self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'PENDING')
    def test_verified_api_payment_after_expiry_is_paid_for_review_only(self):
        BookingDeposit.objects.filter(pk=self.booking.deposit.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.provider.v1.checkout.sessions.retrieve.return_value=self.provider_session()
        self.assertEqual(reconcile_checkout(self.booking.pk,actor=self.customer),'RECONCILIATION_REQUIRED')
        self.assertEqual(BookingDeposit.objects.get(pk=self.booking.deposit.pk).status,'SUCCEEDED');self.assertEqual(Booking.objects.get(pk=self.booking.pk).status,'CANCELLED')
