"""Operational seeding preserves existing data and does not manufacture revenue."""
import json
from io import StringIO
from unittest.mock import patch
from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management import call_command,CommandError
from django.test import TestCase
from .test_business import BusinessData
from .models import *
from .report_service import report_data
from .rbac import assign_role

class OperationalSeedTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.initialize()
        MenuItem.objects.filter(pk=45).update(price=55000)
    def seed(self):
        output=StringIO()
        with patch('customers.management.commands.seed_module07_operational_data.timezone.localdate',return_value=date(2026,10,13)):
            call_command('seed_module07_operational_data',stdout=output)
        return json.loads(output.getvalue())
    def state(self):
        from django.apps import apps
        return {m._meta.label:list(m.objects.order_by('pk').values()) for m in apps.get_models(include_auto_created=True) if m._meta.app_label in ('customers','auth')}
    def test_coverage_packaged_drinks_stock_prices_and_rbac_preserved(self):
        menus=list(MenuItem.objects.order_by('pk').values());users=list(User.objects.order_by('pk').values());groups=list(self.staff.groups.values_list('id',flat=True))
        result=self.seed()
        self.assertEqual(MenuItem.objects.filter(recipe_lines__isnull=False).distinct().count(),35)
        self.assertFalse(RecipeIngredient.objects.filter(menu_item_id__gte=36).exists())
        self.assertEqual(list(MenuItem.objects.order_by('pk').values()),menus)
        self.assertEqual(list(User.objects.filter(pk__in=[u['id'] for u in users]).order_by('pk').values()),users)
        self.assertEqual(list(self.staff.groups.values_list('id',flat=True)),groups)
        self.assertEqual(Employee.objects.filter(user=self.customer).count(),0)
        self.assertFalse(Ingredient.objects.exclude(current_stock=0).exists());self.assertEqual(StockMovement.objects.count(),0);self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(len(result['new_accounts']),2);self.assertTrue(all(name.startswith('demo_m07_') for name in result['new_accounts']))
    def test_rerun_every_field_timestamp_membership_idempotent(self):
        self.seed();before=self.state();result=self.seed()
        self.assertEqual(self.state(),before);self.assertEqual(result['new_accounts'],[])
        self.assertEqual(result['schedules_created'],0);self.assertEqual(result['attendance_created'],0)
    def test_existing_recipe_profile_and_user_edited_demo_data_not_overwritten(self):
        RecipeIngredient.objects.create(menu_item=MenuItem.objects.get(pk=3),ingredient=self.fish,quantity_required='.777')
        profile=RestaurantInfo.objects.create(name='Existing',address='Keep',opening_time='09:00',closing_time='21:00')
        self.seed();combo=Combo.objects.first();combo.price=123;combo.is_active=False;combo.save()
        top=Topping.objects.first();top.price=234;top.is_available=False;top.save();top.menu_items.clear()
        promotion=Promotion.objects.first();promotion.is_active=False;promotion.save()
        self.seed();combo.refresh_from_db();top.refresh_from_db();promotion.refresh_from_db();profile.refresh_from_db()
        self.assertEqual(combo.price,123);self.assertFalse(combo.is_active);self.assertEqual(top.price,234);self.assertFalse(top.is_available);self.assertEqual(top.menu_items.count(),0);self.assertFalse(promotion.is_active)
        self.assertEqual(profile.address,'Keep');self.assertEqual(RestaurantInfo.objects.count(),1)
        self.assertEqual(RecipeIngredient.objects.get(menu_item_id=3).quantity_required,Decimal('.777'))
    def test_atomic_rollback_for_bad_unit_after_partial_work(self):
        Ingredient.objects.create(code='BAD',name='Bột bắp',unit='piece')
        before=self.state()
        with self.assertRaises(CommandError):self.seed()
        self.assertEqual(self.state(),before)
    def test_schedules_attendance_payroll_service_no_overlaps_paid_or_fake_totals(self):
        self.seed()
        self.assertFalse(WorkSchedule.objects.exclude(status='APPROVED',source='MANUAL').exists())
        for schedule in WorkSchedule.objects.all():
            self.assertFalse(WorkSchedule.objects.filter(employee=schedule.employee,start_at__lt=schedule.end_at,end_at__gt=schedule.start_at).exclude(pk=schedule.pk).exists())
        self.assertTrue(Attendance.objects.filter(status='LATE').exists());self.assertTrue(Attendance.objects.filter(status='PRESENT').exists())
        for payroll in Payroll.objects.all():
            self.assertEqual(payroll.status,'DRAFT');self.assertIsNone(payroll.paid_at);self.assertTrue(payroll.calculation_snapshot['attendance'])
            self.assertEqual(payroll.net_salary,payroll.earned_base+payroll.overtime_pay+payroll.allowance+payroll.bonus-payroll.deduction)
            self.assertGreater(payroll.working_hours,0)
        self.assertEqual(Message.objects.count(),0)
    def test_toppings_combo_prices_vouchers_reports_and_no_unpurchased_reviews(self):
        self.seed();self.assertEqual(Topping.objects.count(),5);self.assertEqual(Combo.objects.count(),4);self.assertEqual(Promotion.objects.count(),4);self.assertEqual(Review.objects.count(),0)
        for combo in Combo.objects.all():
            full=sum(part.menu_item.price*part.quantity for part in combo.items.select_related('menu_item'))
            self.assertGreater(combo.price,0);self.assertLess(combo.price,full);self.assertGreater(combo.price,full*Decimal('.80'))
        sections=dict(report_data(self.manager));self.assertEqual(dict(sections['Công thức'])['Món có recipe'],35)
        self.assertEqual(dict(sections['Doanh thu Payment SUCCEEDED'])['Thực thu'],0)
        for title in ('Topping','Combo','Promotion / Voucher','Nhân sự','Chức vụ','Ca làm việc','Lịch làm việc','Chấm công','Payroll'):self.assertIn(title,sections)
    def test_review_only_existing_completed_customer_purchase_once(self):
        order=self.order(customer=self.customer);self.prepare(order)
        from .order_service import transition_order
        transition_order(order.pk,'COMPLETED',actor=self.admin)
        self.seed();self.assertEqual(Review.objects.count(),1)
        review=Review.objects.get();self.assertEqual((review.customer_id,review.order_id,review.menu_item_id),(self.customer.pk,order.pk,self.menu.pk))
        self.seed();self.assertEqual(Review.objects.count(),1);self.assertEqual(Order.objects.count(),1);self.assertEqual(Payment.objects.count(),0)
    def test_existing_staff_cover_all_positions_no_new_accounts(self):
        for name in ('kitchen-existing','cashier-existing'):
            user=User.objects.create_user(name);assign_role(user,'STAFF')
        before=User.objects.count();result=self.seed();self.assertEqual(User.objects.count(),before);self.assertEqual(result['new_accounts'],[])
