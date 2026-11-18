from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command,CommandError
from django.test import TestCase,override_settings,Client
from django.utils import timezone
from .test_business import BusinessData
from .booking_service import create_booking
from .stripe_configuration import configuration_errors,payment_readiness


@override_settings(STRIPE_SECRET_KEY='sk_test_fixture',STRIPE_WEBHOOK_SECRET='whsec_fixture',STRIPE_PUBLIC_BASE_URL='http://127.0.0.1:8000',ON_RENDER=False)
class CheckoutReadinessTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()

    def booking(self):
        day=timezone.localtime()+timedelta(days=2)
        return create_booking(user=self.customer,name='Khách kiểm thử',phone='0912345678',date=day.date(),time=day.time().replace(tzinfo=None,microsecond=0),guests=2,online=True)

    def test_valid_configuration_is_not_a_provider_delivery_claim(self):
        output=StringIO();call_command('check_stripe_config',stdout=output)
        self.assertIn('"ready": true',output.getvalue())
        self.assertIn('"delivery_verified": false',output.getvalue())
        self.assertNotIn('sk_test_fixture',output.getvalue())

    def test_missing_key_and_bad_webhook_are_reported_without_secret(self):
        with override_settings(STRIPE_SECRET_KEY='',STRIPE_WEBHOOK_SECRET='bad-secret-value'):
            output=StringIO()
            with self.assertRaises(CommandError):call_command('check_stripe_config',stdout=output)
            self.assertNotIn('bad-secret-value',output.getvalue())
            self.assertEqual(len(configuration_errors()),2)

    def test_render_rejects_localhost_origin_and_path_or_credentials(self):
        for origin in ('http://127.0.0.1:8000','https://smart-restaurant-demo.onrender.com/path','https://user:password@smart-restaurant-demo.onrender.com'):
            with self.subTest(origin=origin),override_settings(ON_RENDER=True,STRIPE_PUBLIC_BASE_URL=origin):
                self.assertTrue(configuration_errors())

    def test_whitespace_and_live_keys_are_not_accepted(self):
        for key in ('sk_test_fixture ','sk_live_fixture'):
            with override_settings(STRIPE_SECRET_KEY=key):self.assertTrue(configuration_errors())

    def test_expiry_is_distinct_from_configuration(self):
        booking=self.booking();deposit=booking.deposit
        with override_settings(STRIPE_SECRET_KEY=''):
            self.assertEqual(payment_readiness(booking,deposit,deposit.expires_at)[0],'EXPIRED')
            self.assertEqual(payment_readiness(booking,deposit,timezone.now())[0],'CONFIGURATION')

    def test_page_explains_disabled_checkout_and_rejects_post(self):
        booking=self.booking();self.client.force_login(self.customer)
        with override_settings(STRIPE_WEBHOOK_SECRET='invalid'),patch('customers.deposit_service.checkout') as checkout:
            page=self.client.get(f'/booking/{booking.pk}/deposit/')
            self.assertContains(page,'data-payment-blocker="CONFIGURATION"')
            self.assertContains(page,'data-checkout-submit disabled')
            self.client.post(f'/booking/{booking.pk}/deposit/checkout/')
            checkout.assert_not_called()
        booking.refresh_from_db();self.assertEqual(booking.status,'PENDING_DEPOSIT')

    def test_checkout_still_requires_csrf_and_ownership(self):
        booking=self.booking();client=Client(enforce_csrf_checks=True);client.force_login(self.customer)
        response=client.post(f'/booking/{booking.pk}/deposit/checkout/')
        self.assertEqual(response.status_code,403)

    def test_vietnamese_source_scan_is_clean(self):
        from scripts.check_vietnamese_text import audit
        self.assertEqual(audit(),[])

    def test_admin_faceid_shortcut_points_to_existing_route(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/management/'),'Quét mặt chấm công')
