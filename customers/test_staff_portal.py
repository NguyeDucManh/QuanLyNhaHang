from datetime import timedelta
from decimal import Decimal
from django.test import TestCase,RequestFactory
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.db import connection
from .test_module07 import Module07Fixtures
from .models import Employee,Attendance,Payroll,Message,ConversationParticipant
from .staff_portal import dashboard,unread_counts
from .chat_service import create_conversation,send_message
import uuid

class StaffPortalTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):self.personnel();self.client.force_login(self.staff)
    def test_staff_dashboard_is_distinct_shell_and_no_camera(self):
        response=self.client.get(reverse('staff_home'));self.assertContains(response,'staff-sidebar');self.assertContains(response,'Ca làm hôm nay');self.assertNotContains(response,'site-footer');self.assertNotContains(response,'getUserMedia');self.assertNotContains(response,'<video')
    def test_customer_cannot_open_staff_or_work(self):
        self.client.force_login(self.customer)
        for name in ['staff_home','my_work','face_attendance']:self.assertEqual(self.client.get(reverse(name)).status_code,403)
    def test_dashboard_never_shows_other_employee_or_payroll(self):
        other=Employee.objects.create(user=self.manager,employee_code='OTHER',full_name='Private Other Employee',position=self.position,hire_date=self.day)
        response=self.client.get(reverse('staff_home'));self.assertNotContains(response,'Private Other Employee');self.assertIsNone(response.context['current_payroll'])
    def test_month_hours_only_confirmed_closed_own_records(self):
        schedule=self.approved_schedule();attendance=self.manual_attendance(schedule)
        attendance.confirmed_at=timezone.now();attendance.save()
        request=RequestFactory().get('/staff/');request.user=self.staff
        self.assertEqual(dashboard(request)['month_hours'],Decimal('8.0'))
        attendance.confirmed_at=None;attendance.save();self.assertEqual(dashboard(request)['month_hours'],0)
    def test_week_navigation_filters_own_schedules(self):
        own=self.approved_schedule();response=self.client.get(reverse('my_work'),{'week':self.day.isoformat()});self.assertContains(response,'Tuần trước');self.assertContains(response,'Tuần sau');self.assertEqual(sum(len(day['rows']) for day in response.context['week_days']),1)
        response=self.client.get(reverse('my_work'),{'week':(self.day+timedelta(days=30)).isoformat()});self.assertEqual(sum(len(day['rows']) for day in response.context['week_days']),0)
    def test_bad_week_query_falls_back_without_error(self):
        self.assertEqual(self.client.get(reverse('my_work'),{'week':'garbage'}).status_code,200)
    def test_nav_requires_actual_capabilities(self):
        for group in self.staff.groups.all():group.permissions.clear()
        self.staff.user_permissions.clear()
        response=self.client.get(reverse('staff_home'));urls=[item['url'] for item in response.context['staff_nav']];self.assertNotIn(reverse('admin_menu_list'),urls);self.assertNotIn(reverse('admin_kitchen'),urls)
        self.staff.user_permissions.add(Permission.objects.get(codename='view_menuitem',content_type__app_label='customers'))
        response=self.client.get(reverse('staff_home'));self.assertIn(reverse('admin_menu_list'),[item['url'] for item in response.context['staff_nav']]);self.assertContains(self.client.get(reverse('admin_menu_list')),'staff-sidebar')
    def test_backend_still_rejects_no_permission_management(self):
        for group in self.staff.groups.all():group.permissions.clear()
        self.staff.user_permissions.clear();self.assertEqual(self.client.get(reverse('admin_menu_list')).status_code,403);self.assertEqual(self.client.get(reverse('admin_kitchen')).status_code,403)
    def test_staff_profile_cannot_change_roles_or_target_other_user(self):
        oldusername=self.staff.username
        response=self.client.post(reverse('customer_profile'),{'first_name':'Updated','last_name':'Own','email':'own@example.test','is_superuser':'true','user_id':self.manager.pk,'username':'spoof'})
        self.assertEqual(response.status_code,302);self.staff.refresh_from_db();self.assertEqual(self.staff.first_name,'Updated');self.assertFalse(self.staff.is_superuser);self.assertEqual(self.staff.username,oldusername);self.manager.refresh_from_db();self.assertNotEqual(self.manager.first_name,'Updated')
    def test_profile_does_not_expose_embeddings_or_permission_dump(self):
        response=self.client.get(reverse('customer_profile'));self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'FaceEmbedding');self.assertNotContains(response,'user_permissions');self.assertEqual(response.content.decode().count('name="first_name"'),1)
    def test_staff_payroll_restricted_even_with_view_permission(self):
        other=Employee.objects.create(user=self.manager,employee_code='OTHER',full_name='Other',position=self.position,hire_date=self.day)
        payroll=Payroll.objects.create(employee=other,period=self.period,base_salary=100,earned_base=0,overtime_pay=0,allowance=0,bonus=0,deduction=0,gross_salary=0,net_salary=0)
        self.staff.user_permissions.add(Permission.objects.get(codename='view_payroll',content_type__app_label='customers'))
        self.assertEqual(self.client.get(reverse('payroll_detail',args=[payroll.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('payroll_list')),'OTHER')
    def test_own_payroll_has_staff_summary(self):
        payroll=Payroll.objects.create(employee=self.employee,period=self.period,base_salary=100,earned_base=0,overtime_pay=0,allowance=0,bonus=0,deduction=0,gross_salary=0,net_salary=0)
        response=self.client.get(reverse('payroll_detail',args=[payroll.pk]));self.assertContains(response,'Thực nhận');self.assertContains(response,'staff-sidebar')
    def test_chat_unread_and_read_receipt_are_owner_scoped(self):
        conversation=create_conversation(actor=self.manager,recipient_id=self.staff.pk)
        send_message(actor=self.manager,conversation_id=conversation.pk,content='A private message',request_key=uuid.uuid4())
        self.assertEqual(unread_counts(self.staff).get(conversation.pk),1)
        response=self.client.get(reverse('chat_detail',args=[conversation.pk]));self.assertContains(response,'human-message-bubble');self.assertEqual(unread_counts(self.staff).get(conversation.pk,0),0)
        self.client.force_login(self.customer);self.assertEqual(self.client.get(reverse('chat_detail',args=[conversation.pk])).status_code,404)
    def test_dashboard_query_count_does_not_grow_per_shift(self):
        self.approved_schedule()
        request=RequestFactory().get('/staff/');request.user=self.staff
        with CaptureQueriesContext(connection) as queries:dashboard(request)
        self.assertLessEqual(len(queries),5)
