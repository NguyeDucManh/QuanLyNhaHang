from io import StringIO
from datetime import timedelta,time
from django.test import TestCase,RequestFactory
from django.core.management import call_command,CommandError
from django.utils import timezone
from django.urls import reverse
from django.utils.html import strip_tags
from django.db import connection
from django.test.utils import CaptureQueriesContext
from .test_module07 import Module07Fixtures
from .models import Combo,ComboItem,RestaurantInfo,Booking,Employee,Attendance
from .booking_workspace import booking_panel
from .employee_identity import operational_employees
from .operational_labels import operational_text

class GroupedWorkspaceTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):self.personnel()
    def test_cleanup_default_dry_run_preserves_values(self):
        combo=Combo.objects.create(name='Combo bò DEMO',price=100)
        call_command('clean_operational_demo_labels',stdout=StringIO());combo.refresh_from_db();self.assertEqual(combo.name,'Combo bò DEMO')
    def test_cleanup_apply_is_idempotent_and_preserves_relations(self):
        combo=Combo.objects.create(name='Combo bò DEMO',price=100);line=ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=2)
        for _ in range(2):call_command('clean_operational_demo_labels',apply=True,allow_test_database=True,stdout=StringIO())
        combo.refresh_from_db();line.refresh_from_db();self.assertEqual(combo.name,'Combo bò');self.assertEqual((line.combo_id,line.menu_item_id,line.quantity),(combo.pk,self.menu.pk,2));self.assertEqual(Combo.objects.count(),1)
    def test_collision_is_not_renamed_or_deleted(self):
        combo=Combo.objects.create(name='Combo bò DEMO',price=100);Combo.objects.create(name='Combo bò',price=100)
        call_command('clean_operational_demo_labels',apply=True,allow_test_database=True,stdout=StringIO());combo.refresh_from_db();self.assertEqual(combo.name,'Combo bò DEMO');self.assertEqual(Combo.objects.count(),2)
    def test_ordinary_apply_skips_test_database(self):
        with self.assertRaises(CommandError):call_command('clean_operational_demo_labels',apply=True,stdout=StringIO())
    def test_employee_identity_is_not_inferred_or_mutated(self):
        self.employee.employee_code='DEMO-U0001';self.employee.full_name='Nhân viên DEMO';self.employee.save()
        call_command('clean_operational_demo_labels',apply=True,allow_test_database=True,stdout=StringIO());self.employee.refresh_from_db();self.assertEqual(self.employee.employee_code,'DEMO-U0001');self.assertFalse(operational_employees().filter(pk=self.employee.pk).exists())
        self.client.force_login(self.staff);text=strip_tags(self.client.get(reverse('staff_home')).content.decode());self.assertNotIn('DEMO',text);self.assertIn('Hồ sơ cần xác nhận',text)
    def test_customer_combo_label_does_not_show_marker(self):
        Combo.objects.create(name='Combo bò DEMO',price=100);self.assertNotIn('DEMO',strip_tags(self.client.get(reverse('customer_combos')).content.decode()))
    def test_placeholder_contacts_are_hidden_without_fabrication(self):
        RestaurantInfo.objects.create(name='Nhà hàng DEMO',address='123 Đường DEMO',phone='0000000000',email='demo@restaurant.example',opening_time=time(8),closing_time=time(23))
        text=strip_tags(self.client.get('/').content.decode());self.assertNotIn('DEMO',text);self.assertNotIn('0000000000',text);self.assertNotIn('demo@',text);self.assertIn('Chưa cập nhật',text)
    def test_simulated_provenance_is_not_removed(self):
        self.assertEqual(operational_text('Dữ liệu mô phỏng'),'Dữ liệu mô phỏng');self.assertEqual(operational_text('Chỉ số kiểm tra gián tiếp'),'Chỉ số kiểm tra gián tiếp')
    def test_confirmed_employee_identity_remains_real(self):
        self.client.force_login(self.staff);text=strip_tags(self.client.get(reverse('staff_home')).content.decode());self.assertIn('EMP1',text);self.assertNotIn('DEMO',text)
    def test_staff_sections_are_grouped_without_duplicate_all_actions(self):
        self.client.force_login(self.staff);r=self.client.get(reverse('staff_home'))
        for label in ['Ca làm &amp; chấm công','Công việc','Cá nhân &amp; thu nhập']:self.assertContains(r,label)
        self.assertNotContains(r,'staff-stats');self.assertNotContains(r,'getUserMedia')
    def test_booking_tabs_are_owned(self):
        own=self.reserve();other=self.reserve(user=self.manager,time=time(21),name='Private Other Booking')
        self.client.force_login(self.customer);r=self.client.get(reverse('customer_booking'));self.assertNotContains(r,'Private Other Booking');self.assertEqual([row['booking'].pk for row in r.context['workspace_rows']],[own.pk])
    def test_customer_cannot_create_manager_booking(self):
        self.client.force_login(self.customer);self.assertEqual(self.client.post(reverse('admin_bookings'),{}).status_code,403)
    def test_manager_booking_uses_existing_autoassignment(self):
        from django.contrib.auth.models import Permission
        self.manager.user_permissions.add(Permission.objects.get(codename='add_booking',content_type__app_label='customers'))
        self.client.force_login(self.manager);date=timezone.localdate()+timedelta(days=5)
        r=self.client.post(reverse('admin_bookings'),{'customer':self.customer.pk,'name':'New reservation','phone':'0912345678','date':str(date),'time':'19:00','guests':2,'note':''});self.assertEqual(r.status_code,302)
        b=Booking.objects.get(name='New reservation');self.assertEqual(b.user_id,self.customer.pk);self.assertIsNotNone(b.table_id);self.assertEqual(b.status,'CONFIRMED')
    def test_availability_does_not_reserve_or_mutate(self):
        self.client.force_login(self.customer);date=timezone.localdate()+timedelta(days=4);before=Booking.objects.count()
        r=self.client.get(reverse('booking_availability'),{'date':str(date),'time':'18:00','guests':2});self.assertEqual(r.status_code,200);self.assertTrue(r.json()['available']);self.assertEqual(Booking.objects.count(),before)
        self.assertEqual(self.client.get(reverse('booking_availability'),{'date':str(date),'time':'18:00','guests':21}).status_code,400)
    def test_booking_query_budget_does_not_grow_per_row(self):
        for i in range(5):Booking.objects.create(user=self.customer,name='Owned',phone='0912345678',date=timezone.localdate(),time=time(18),guests=2)
        request=RequestFactory().get('/management/bookings/');request.user=self.manager
        with CaptureQueriesContext(connection) as queries:panel=booking_panel(request,Booking.objects.all())
        self.assertEqual(len(panel['workspace_rows']),5);self.assertLessEqual(len(queries),4)
    def test_history_dates_and_pagination_are_bounded(self):
        for i in range(20):Booking.objects.create(user=self.customer,name='Past',phone='0912345678',date=timezone.localdate()-timedelta(days=1),time=time(18),guests=2,status='COMPLETED')
        request=RequestFactory().get('/booking/',{'tab':'history','page':2});request.user=self.customer
        panel=booking_panel(request,self.customer.booking_set.all(),customer=True);self.assertEqual(len(panel['workspace_rows']),5);self.assertEqual(panel['booking_pagination'].paginator.count,20)
