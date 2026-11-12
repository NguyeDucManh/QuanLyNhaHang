import uuid
from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from .test_module07 import Module07Fixtures
from .models import Order, Invoice, Payment, MembershipDiscount, CustomerLoyalty, MembershipPolicy, AuditLog
from . import membership_service as member
from .commerce_service import apply_voucher
from .order_service import recalculate_totals
from .membership_models import default_tiers


@override_settings(MEMBERSHIP_DISCOUNTS_ENABLED=True)
class MembershipDiscountTests(Module07Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()

    def paid(self, amount, customer=None):
        customer = customer or self.customer
        amount = Decimal(str(amount))
        order = Order.objects.create(created_by=self.admin, customer=customer, status='COMPLETED', subtotal=amount, total_amount=amount)
        invoice = Invoice.objects.create(order=order, invoice_number='CI-'+str(uuid.uuid4()), subtotal=amount,
            discount_amount=0, total_amount=amount, status='PAID', paid_at=timezone.now())
        if amount:
            Payment.objects.create(invoice=invoice, created_by=self.admin, confirmed_by=self.admin,
                status='SUCCEEDED', payment_method='CASH', amount=amount, paid_at=timezone.now())
        return invoice

    def test_exact_tier_boundaries_use_real_settled_invoice_amounts(self):
        for amount, tier, rate in [(0,'MEMBER',0),(1999999,'MEMBER',0),(2000000,'SILVER',3),(5000000,'GOLD',5),(15000000,'VIP',5)]:
            with self.subTest(amount=amount):
                user = User.objects.create_user('boundary-'+str(amount))
                self.paid(amount,user)
                status = member.status(user.pk)
                self.assertEqual((status['spend'],status['tier'],status['percent']),(Decimal(amount),tier,Decimal(rate)))

    def test_multiple_invoices_sum_once_and_unpaid_or_cancelled_never_count(self):
        self.paid(1000000);self.paid(1000000)
        unpaid = self.paid(9000000);unpaid.status='CANCELLED';unpaid.save()
        invoice = self.paid(7000000);invoice.payments.update(status='FAILED',paid_at=None,confirmed_by=None)
        status = member.status(self.customer.pk)
        self.assertEqual(status['spend'],Decimal(2000000));self.assertEqual(status['orders'],2)

    def test_manual_points_never_become_spending(self):
        from .loyalty_service import adjust_points
        adjust_points(self.customer.pk,actor=self.admin,points=1000000,reason='Test only',request_key=uuid.uuid4())
        self.assertEqual(member.status(self.customer.pk)['spend'],0)
        self.assertEqual(member.status(self.customer.pk)['tier'],'MEMBER')

    def gold_order(self):
        self.paid(5000000)
        self.menu.price=Decimal(1000000);self.menu.save()
        return self.order(quantity=1,customer=self.customer)

    def test_gold_discount_applied_by_backend_and_snapshot_is_frozen(self):
        order=self.gold_order()
        self.assertEqual((order.discount_amount,order.total_amount),(Decimal(50000),Decimal(950000)))
        entry=MembershipDiscount.objects.get(order=order)
        self.assertEqual(entry.snapshot['tier'],'GOLD')
        tiers=default_tiers();tiers[2]['percent']='10'
        member.save_policy(tiers,actor=self.admin)
        recalculate_totals(order)
        self.assertEqual(order.total_amount,Decimal(950000))
        self.assertEqual(MembershipDiscount.objects.get(order=order).snapshot,entry.snapshot)

    def test_membership_beats_voucher_without_consuming_usage(self):
        order=self.gold_order();promotion=self.promotion(discount_type='FIXED',discount_value=30000)
        result=apply_voucher(order.pk,promotion.code,actor=self.admin)
        promotion.refresh_from_db()
        self.assertEqual(result.total_amount,Decimal(950000));self.assertIsNone(result.promotion_id)
        self.assertEqual(promotion.used_count,0)

    def test_better_voucher_is_not_stacked_and_retry_consumes_once(self):
        order=self.gold_order();promotion=self.promotion(discount_type='FIXED',discount_value=70000)
        for _ in range(2):result=apply_voucher(order.pk,promotion.code,actor=self.admin)
        promotion.refresh_from_db()
        self.assertEqual(result.total_amount,Decimal(930000));self.assertEqual(promotion.used_count,1)
        self.assertEqual(MembershipDiscount.objects.get(order=order).selected,'VOUCHER')

    def test_order_growth_switches_to_better_membership_and_releases_voucher_once(self):
        from .order_service import update_order_item
        order=self.gold_order();promotion=self.promotion(discount_type='FIXED',discount_value=70000)
        apply_voucher(order.pk,promotion.code,actor=self.admin)
        update_order_item(order.pk,order.items.get().pk,quantity=2,actor=self.admin)
        order.refresh_from_db();promotion.refresh_from_db()
        self.assertEqual((order.subtotal,order.discount_amount,order.total_amount),(Decimal(2000000),Decimal(100000),Decimal(1900000)))
        self.assertIsNone(order.promotion_id);self.assertEqual(promotion.used_count,0)
        recalculate_totals(order);promotion.refresh_from_db();self.assertEqual(promotion.used_count,0)
        self.assertTrue(AuditLog.objects.filter(action='VOUCHER_RELEASED',actor=self.admin).exists())

    def test_customer_order_cancellation_returns_unspent_selected_voucher(self):
        from .order_service import transition_order
        order=self.gold_order();promotion=self.promotion(discount_type='FIXED',discount_value=70000)
        apply_voucher(order.pk,promotion.code,actor=self.admin)
        transition_order(order.pk,'CANCELLED',actor=self.admin)
        order.refresh_from_db();promotion.refresh_from_db()
        self.assertEqual((order.total_amount,order.discount_amount,promotion.used_count),(0,0,0))
        self.assertIsNone(order.promotion_id)

    def test_invalid_or_expired_voucher_does_not_mutate_member_order(self):
        order=self.gold_order();promotion=self.promotion(usage_limit=1,used_count=1)
        with self.assertRaises(ValidationError):apply_voucher(order.pk,promotion.code,actor=self.admin)
        order.refresh_from_db();promotion.refresh_from_db()
        self.assertEqual(order.total_amount,Decimal(950000));self.assertEqual(promotion.used_count,1)

    def test_refund_is_idempotent_reduces_tier_spend_not_original_invoice(self):
        invoice=self.paid(5000000)
        original=(invoice.subtotal,invoice.discount_amount,invoice.total_amount,invoice.status)
        first=member.record_refund(invoice.pk,amount=4000000,reference='test-refund',reason='Test completed refund',actor=self.admin)
        second=member.record_refund(invoice.pk,amount=4000000,reference='test-refund',reason='Test completed refund',actor=self.admin)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(member.status(self.customer.pk)['tier'],'MEMBER')
        self.assertEqual(member.status(self.customer.pk)['spend'],Decimal(1000000))
        with self.assertRaises(ValidationError):member.record_refund(invoice.pk,amount=2000000,reference='excess',reason='Test',actor=self.admin)
        invoice.refresh_from_db();self.assertEqual((invoice.subtotal,invoice.discount_amount,invoice.total_amount,invoice.status),original)

    def test_policy_requires_explicit_manager_permission_and_audit(self):
        for actor in (self.manager,self.staff,self.customer):
            with self.subTest(actor=actor.username):
                with self.assertRaises(PermissionDenied):member.save_policy(default_tiers(),actor=actor)
        self.manager.user_permissions.add(Permission.objects.get(codename='manage_membership_policy'))
        actor=User.objects.get(pk=self.manager.pk)
        member.save_policy(default_tiers(),actor=actor)
        self.assertEqual(MembershipPolicy.objects.count(),1)
        self.assertTrue(AuditLog.objects.filter(action='MEMBERSHIP_POLICY_CHANGED',actor=actor).exists())

    def test_invalid_policy_is_rejected_atomically(self):
        tiers=default_tiers();tiers[1]['minimum']='-1'
        with self.assertRaises(ValidationError):member.save_policy(tiers,actor=self.admin)
        self.assertFalse(MembershipPolicy.objects.exists())

    def test_flag_off_keeps_refund_spend_and_historical_discount_visible(self):
        order=self.gold_order()
        invoice=Invoice.objects.get(order__customer=self.customer)
        member.record_refund(invoice.pk,amount=4000000,reference='rollback-test',reason='Test completed refund',actor=self.admin)
        with override_settings(MEMBERSHIP_DISCOUNTS_ENABLED=False):
            self.assertEqual(member.status(self.customer.pk)['spend'],Decimal(1000000))
            self.assertEqual(member.status(self.customer.pk)['tier'],'MEMBER')
            self.assertEqual(member.discount_context(order).snapshot['tier'],'GOLD')
            new=self.order(quantity=1,customer=self.customer)
            self.assertEqual(new.discount_amount,0)
        self.assertEqual(MembershipDiscount.objects.count(),1)

    def test_management_includes_customers_without_loyalty_or_purchase(self):
        user=User.objects.create_user('zero-spend-customer')
        self.client.force_login(self.admin)
        response=self.client.get('/management/loyalty/')
        self.assertEqual(response.status_code,200);self.assertContains(response,user.username)
        self.assertFalse(CustomerLoyalty.objects.filter(customer=user).exists())
        for actor in (self.staff,self.customer):
            self.client.force_login(actor)
            self.assertEqual(self.client.get('/management/membership/policy/').status_code,403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/membership/').status_code,200)

    @override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=True,TABLE_SERVICE_LIFECYCLE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_unit_fixture',STRIPE_WEBHOOK_SECRET='whsec_unit_fixture',BOOKING_DEPOSIT_REQUIRED=True,
        BOOKING_DEPOSIT_TYPE='FIXED',BOOKING_DEPOSIT_VALUE='200000')
    def test_booking_deposit_assignment_kitchen_discount_payment_release_end_to_end(self):
        from datetime import time
        from unittest.mock import patch
        from .test_deposit import DepositTests
        from .models import RecipeIngredient, Shift, StockMovement, LoyaltyTransaction, TableSession
        from . import personnel_service as hr
        from .table_assignment_service import assign_table
        from .booking_advanced_service import mark_arrival
        from .order_service import open_order_from_booking,transition_order
        from .payment_service import issue_invoice,create_payment,confirm_payment
        from .table_session_service import release
        self.personnel();self.paid(5000000)
        self.menu.price=Decimal(1000000);self.menu.save()
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        self.import_stock(10)
        booking=DepositTests.booking(self,time=time(18),preferred_area=self.area,preferred_table=self.table)
        self.assertEqual(booking.status,'PENDING_DEPOSIT')
        self.assertEqual(booking.deposit.amount,Decimal(200000))
        self.attempt=lambda row:DepositTests.attempt(self,row)
        event=DepositTests.event(self,booking)
        self.assertEqual(DepositTests.webhook(self,event).status_code,200)
        self.assertEqual(DepositTests.webhook(self,event).status_code,200)
        booking.refresh_from_db();self.assertEqual(booking.status,'CONFIRMED')
        shift=Shift.objects.create(name='CI serving shift',start_time=time(18),end_time=time(22),required_staff=1)
        schedule=hr.schedule_state(self.schedule(date=booking.date,shift=shift).pk,'APPROVED',actor=self.admin)
        assign_table(actor=self.admin,table_id=self.table.pk,schedule_id=schedule.pk)
        with patch('django.utils.timezone.now',return_value=booking.start_time+timezone.timedelta(minutes=1)):
            mark_arrival(booking.pk,actor=self.admin,state='CHECKED_IN')
            order=open_order_from_booking(booking.pk,actor=self.staff)
            self.assertEqual(open_order_from_booking(booking.pk,actor=self.staff).pk,order.pk)
            self.assertEqual(order.items.count(),1)
            self.assertEqual((order.subtotal,order.discount_amount,order.total_amount),(Decimal(1000000),Decimal(50000),Decimal(950000)))
            self.client.force_login(self.staff)
            self.assertEqual(self.client.get('/staff/').status_code,200)
            self.prepare(order);transition_order(order.pk,'COMPLETED',actor=self.staff)
            invoice=issue_invoice(order.pk,actor=self.admin)
            self.assertEqual((invoice.deposit_applied_amount,invoice.balance_due),(Decimal(200000),Decimal(750000)))
            self.table.refresh_from_db();self.assertEqual(self.table.status,'OCCUPIED')
            payment=create_payment(invoice_id=invoice.pk,actor=self.admin,payment_method='CASH',request_key=uuid.uuid4())
            confirm_payment(payment.pk,actor=self.admin)
            with self.assertRaises(ValidationError):
                confirm_payment(payment.pk,actor=self.admin)  # Existing retry contract: reject, never pay twice.
            self.assertEqual(LoyaltyTransaction.objects.filter(source_type='INVOICE',source_id=str(invoice.pk)).count(),1)
            self.assertEqual(member.status(self.customer.pk)['spend'],Decimal(5950000))
            self.assertIsNone(TableSession.objects.get(order=order).ended_at)
            release(actor=self.staff,order_id=order.pk,reason='CI guest left and table cleaned',confirm=True)
            self.table.refresh_from_db();self.assertEqual(self.table.status,'AVAILABLE')
            booking.refresh_from_db();self.assertEqual(booking.status,'COMPLETED')
            self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,Decimal('9.75'))
            self.assertEqual(StockMovement.objects.filter(movement_type='ORDER_USAGE',order=order).count(),1)
            self.client.force_login(self.customer)
            self.assertContains(self.client.get(f'/invoices/{invoice.pk}/'),'GOLD')

    @override_settings(STRIPE_SECRET_KEY='sk_test_unit_fixture',STRIPE_WEBHOOK_SECRET='whsec_unit_fixture',
        BOOKING_DEPOSIT_REQUIRED=True,BOOKING_DEPOSIT_TYPE='FIXED',BOOKING_DEPOSIT_VALUE='1000000')
    def test_full_deposit_is_capped_after_discount_and_never_counted_twice(self):
        from datetime import time
        from .test_deposit import DepositTests
        from .models import RecipeIngredient,LoyaltyTransaction
        from .order_service import open_order_from_booking,transition_order
        from .payment_service import issue_invoice
        self.paid(5000000);self.menu.price=Decimal(1000000);self.menu.save()
        RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        self.import_stock(10)
        booking=DepositTests.booking(self,time=time(18))
        self.attempt=lambda row:DepositTests.attempt(self,row)
        event=DepositTests.event(self,booking)
        self.assertEqual(DepositTests.webhook(self,event).status_code,200)
        order=open_order_from_booking(booking.pk,actor=self.admin)
        self.prepare(order);transition_order(order.pk,'COMPLETED',actor=self.admin)
        invoice=issue_invoice(order.pk,actor=self.admin)
        self.assertEqual((invoice.status,invoice.total_amount,invoice.deposit_applied_amount,invoice.balance_due),('PAID',Decimal(950000),Decimal(950000),0))
        self.assertFalse(invoice.payments.exists())
        booking.deposit.refresh_from_db();self.assertEqual(booking.deposit.amount,Decimal(1000000))
        self.assertEqual(member.status(self.customer.pk)['spend'],Decimal(5950000))
        self.assertEqual(DepositTests.webhook(self,event).status_code,200)
        self.assertEqual(LoyaltyTransaction.objects.filter(source_type='INVOICE',source_id=str(invoice.pk)).count(),1)

    def test_admin_area_table_changes_are_live_for_customer_without_hardcoded_names(self):
        from django.urls import reverse
        from .models import Area,RestaurantTable
        self.client.force_login(self.admin)
        name='Khu VIP thử nghiệm riêng'
        response=self.client.post(reverse('admin_area_add'),{'name':name,'description':'CI only','is_active':'on'})
        self.assertEqual(response.status_code,302)
        area=Area.objects.get(name=name)
        response=self.client.post(reverse('admin_table_add'),{'area':area.pk,'code':'CI-VIP-9','capacity':4,'status':'AVAILABLE','is_active':'on'})
        self.assertEqual(response.status_code,302)
        table=RestaurantTable.objects.get(code='CI-VIP-9')
        self.client.force_login(self.customer)
        page=self.client.get('/booking/?view=new');self.assertContains(page,name);self.assertContains(page,table.code)
        self.client.force_login(self.admin)
        response=self.client.post(reverse('admin_area_edit',args=[area.pk]),{'name':name+' đổi tên','description':'CI only','is_active':'on'})
        self.assertEqual(response.status_code,302)
        self.client.force_login(self.customer);self.assertContains(self.client.get('/booking/?view=new'),name+' đổi tên')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('admin_area_edit',args=[area.pk]),{'name':name,'description':'CI only'}).status_code,302)
        self.client.force_login(self.customer)
        self.assertNotContains(self.client.get('/booking/?view=new'),table.code)

    @override_settings(MEMBERSHIP_DISCOUNTS_ENABLED=False)
    def test_flag_off_preserves_legacy_order_amount_and_avoids_new_snapshots(self):
        self.paid(5000000)
        order=self.order(quantity=1,customer=self.customer)
        self.assertEqual(order.discount_amount,0)
        self.assertFalse(MembershipDiscount.objects.exists())
