import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.conf import settings
from django.utils import timezone
from .test_business import BusinessData
from .models import Order,Invoice,Payment


@override_settings(MEMBERSHIP_DISCOUNTS_ENABLED=True)
class FinalCleanupContracts(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()

    def test_access_map_has_constant_role_queries_and_honors_revocation(self):
        from .rbac import management_access
        user=User.objects.get(pk=self.manager.pk)
        with CaptureQueriesContext(connection) as queries:
            access=management_access(user)
        self.assertEqual(access['role'],'MANAGER')
        self.assertLessEqual(len(queries),5)
        user.groups.clear()
        access=management_access(User.objects.get(pk=user.pk))
        self.assertEqual(access['role'],'CUSTOMER');self.assertFalse(access['view_orders'])

    def test_spending_aggregation_uses_one_query_for_many_invoices(self):
        from .membership_service import spend_summaries
        for _ in range(20):
            order=Order.objects.create(created_by=self.admin,customer=self.customer,status='COMPLETED',subtotal=100,total_amount=100)
            invoice=Invoice.objects.create(order=order,invoice_number='query-'+uuid.uuid4().hex,subtotal=100,discount_amount=0,total_amount=100,status='PAID',paid_at=timezone.now())
            Payment.objects.create(invoice=invoice,created_by=self.admin,confirmed_by=self.admin,status='SUCCEEDED',payment_method='CASH',amount=100,paid_at=timezone.now())
        with CaptureQueriesContext(connection) as queries:
            result=spend_summaries([self.customer.pk])
        self.assertEqual(result[self.customer.pk]['spend'],Decimal(2000))
        self.assertEqual(result[self.customer.pk]['orders'],20)
        self.assertEqual(len(queries),1)

    def test_live_recommendations_never_load_research_or_heavy_runtime(self):
        from .ai.hybrid_service import recommend
        with (
            patch('customers.ai.hybrid_service.latest',side_effect=AssertionError('Research artifact must not drive production')),
            patch('customers.ai.hybrid_service._offline_dependencies',side_effect=AssertionError('Heavy research imports forbidden')),
        ):
            result=recommend(None,n=4)
        self.assertEqual(result['provenance'],'REAL_LIVE')
        self.assertEqual(len(result['recommendations']),4)

    def test_missing_embedding_is_checked_before_importing_torch_stack(self):
        from .ai.chatbot.rag_service import embedder
        embedder.cache_clear()
        with patch('customers.ai.chatbot.rag_service.read_json',return_value={'embedding':{'local_path':'/not-a-real-ci-model'}}),patch('pathlib.Path.exists',return_value=False),patch.dict('sys.modules',{'sentence_transformers':None}):
            with self.assertRaises(ValueError):embedder()

    def test_grounded_fallback_uses_code_policy_and_unknown_stays_unknown(self):
        from .ai.chatbot.rag_service import grounded_fallback
        from .ai.chatbot.answer_guard import NO_DATA
        result=grounded_fallback('chính sách đặt bàn','BOOKING_POLICY')
        self.assertEqual(result['tool'],'grounded_policy_fallback');self.assertFalse(result['semantic_ready'])
        self.assertIn('đăng nhập',result['answer'])
        self.assertEqual(result['sources'][0]['source_id'],'booking-window')
        self.assertEqual(grounded_fallback('chuyện không có nguồn','UNKNOWN')['answer'],NO_DATA)

    def test_research_forecast_is_not_shown_as_operational_revenue(self):
        self.client.force_login(self.manager)
        metadata={'data_provenance':{'real_days':1,'synthetic_days':69}}
        with patch('customers.ai.availability.latest',return_value=Path('/ci')),patch('customers.ai.availability.read_json',return_value=metadata):
            response=self.client.get('/management/ai/forecast/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'nghiên cứu')
        self.assertIsNone(response.context['result'])

    def test_camera_ui_has_no_location_access_and_admin_identity_is_dynamic(self):
        source=(Path(settings.BASE_DIR)/'static/ai/face-realtime.js').read_text(encoding='utf-8')
        self.assertNotIn('geolocation',source)
        enrollment=(Path(settings.BASE_DIR)/'static/ai/face-flow.js').read_text(encoding='utf-8')
        self.assertNotIn('geolocation',enrollment)
        self.assertNotIn('GPS_ONLY',enrollment)
        self.assertIn('video.videoWidth',enrollment)
        admin=(Path(settings.BASE_DIR)/'static/admin/js/main.js').read_text(encoding='utf-8')
        self.assertNotIn('Nguyễn Đức Mạnh',admin)
        self.assertIn('adminName()',admin)

    def test_ci_fixture_rejects_non_ci_database_before_migrating(self):
        import runpy
        config={**settings.DATABASES['default'],'NAME':'must_never_modify_this_database'}
        with override_settings(DATABASES={'default':config}),patch('django.core.management.call_command') as migrate:
            with self.assertRaises(AssertionError):runpy.run_path(str(Path(settings.BASE_DIR)/'scripts/render512_fixture.py'))
            migrate.assert_not_called()
