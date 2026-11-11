from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings, RequestFactory
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.urls import reverse
from .test_module07 import Module07Fixtures
from .models import RestaurantTable,Area,Booking,BookingDeposit,Order,TableServiceAssignment,AuditLog,WorkSchedule,Employee
from .booking_service import create_booking
from .order_service import open_order_from_booking,transition_order
from .kitchen_service import transition_kitchen_item
from .table_assignment_service import assign_table,active_assignments
from .table_board import board


@override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=True)
class ServiceAssignmentTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        self.personnel();self.schedule=self.approved_schedule();self.now=self.schedule.start_at+timedelta(minutes=30)
        clock=patch('django.utils.timezone.now',return_value=self.now);clock.start();self.addCleanup(clock.stop)
        self.other=RestaurantTable.objects.create(code='OTHER',area=self.area,capacity=4)
    def request(self,user=None,**query):
        r=RequestFactory().get('/staff/',query);r.user=user or self.admin;r.session={};return r
    def booking(self,**extra):
        at=self.now+timedelta(minutes=10)
        data=dict(user=self.customer,name='Private guest',phone='0912345678',date=timezone.localtime(at).date(),time=timezone.localtime(at).time().replace(tzinfo=None),guests=2,food_cart={str(self.menu.pk):1})
        data.update(extra);return create_booking(**data)
    def assign(self,**extra):
        data=dict(actor=self.manager,table_id=self.table.pk,schedule_id=self.schedule.pk);data.update(extra);return assign_table(**data)
    def test_only_active_approved_in_window_and_authorized_assignment(self):
        with self.assertRaises(PermissionDenied):self.assign(actor=self.staff)
        with self.assertRaises(ValidationError):self.assign(start_at=self.schedule.start_at-timedelta(minutes=1))
        with self.assertRaises(ValidationError):self.assign(end_at=self.schedule.end_at+timedelta(minutes=1))
        WorkSchedule.objects.filter(pk=self.schedule.pk).update(status='DRAFT')
        with self.assertRaises(ValidationError):self.assign()
        self.assertFalse(TableServiceAssignment.objects.exists())
    def test_idempotency_and_audit(self):
        a=self.assign();again=self.assign()
        self.assertEqual(a.pk,again.pk);self.assertEqual(TableServiceAssignment.objects.count(),1)
        self.assertEqual(AuditLog.objects.filter(action='TABLE_ASSIGNED').count(),1)
    def test_replacement_retains_history_and_records_actor(self):
        old=self.assign()
        other=Employee.objects.create(user=self.manager,employee_code='MANAGER2',full_name='Other employee',position=self.position,hire_date=self.day)
        schedule=WorkSchedule.objects.create(employee=other,shift=self.shift,work_date=self.day,start_at=self.schedule.start_at,end_at=self.schedule.end_at,status='APPROVED',approved_by=self.admin,approved_at=self.now)
        with self.assertRaises(ValidationError):self.assign(schedule_id=schedule.pk)
        later=self.now+timedelta(minutes=5)
        with patch('django.utils.timezone.now',return_value=later):
            new=self.assign(schedule_id=schedule.pk,replace=True)
        old.refresh_from_db();self.assertEqual(old.revoked_at,later)
        self.assertEqual(TableServiceAssignment.objects.count(),2)
        self.assertEqual(active_assignments(self.now).get().pk,old.pk)
        self.assertEqual(active_assignments(later).get().pk,new.pk)
        self.assertEqual(AuditLog.objects.get(action='TABLE_ASSIGNMENT_REPLACED').actor_id,self.manager.pk)
    def test_staff_sees_only_assigned_table_and_no_customer_pii(self):
        b=self.booking();self.assign()
        data=board(self.request(self.staff,scope='upcoming'))
        self.assertEqual([t.pk for t in data['tables']],[self.table.pk])
        self.assertEqual(data['pos_timeline'][0]['booking'].pk,b.pk)
        self.assertNotIn('Private guest',str(data['pos_timeline']))
        self.assertNotIn('0912345678',str(data['pos_timeline']))
        self.client.force_login(self.staff);response=self.client.get(reverse('staff_home'),{'scope':'upcoming'})
        self.assertEqual(response.status_code,200);self.assertNotContains(response,'Private guest');self.assertNotContains(response,'0912345678')
    def test_expired_or_cancelled_shift_does_not_grant_access(self):
        self.assign();WorkSchedule.objects.filter(pk=self.schedule.pk).update(status='CANCELLED')
        self.assertFalse(active_assignments().exists());self.assertEqual(board(self.request(self.staff))['tables'],[])
    def test_pending_deposit_live_then_expired_is_not_occupied(self):
        b=self.booking(online=True)
        # Requires no payment mutation on production; test-only fixture.
        if not hasattr(b,'deposit'):
            Booking.objects.filter(pk=b.pk).update(status='PENDING_DEPOSIT')
            BookingDeposit.objects.create(booking=b,customer=self.customer,amount=200000,expires_at=b.end_time)
        BookingDeposit.objects.filter(booking=b).update(expires_at=b.end_time)
        with patch('django.utils.timezone.now',return_value=b.start_time+timedelta(minutes=1)):
            table=next(t for t in board(self.request())['tables'] if t.pk==b.table_id)
            self.assertEqual(table.visual_status,'RESERVED')
            BookingDeposit.objects.filter(booking=b).update(expires_at=self.now-timedelta(seconds=1))
            table=next(t for t in board(self.request())['tables'] if t.pk==b.table_id)
            self.assertEqual(table.visual_status,'AVAILABLE')
    def test_future_and_historical_bookings_are_not_serving(self):
        b=self.booking();future=board(self.request(scope='upcoming'))
        self.assertEqual(next(t for t in future['tables'] if t.pk==b.table_id).visual_status,'UPCOMING')
        with patch('django.utils.timezone.now',return_value=b.end_time+timedelta(minutes=1)):
            data=board(self.request(scope='history'))
            self.assertEqual(next(t for t in data['tables'] if t.pk==b.table_id).visual_status,'AVAILABLE')
            self.assertEqual(len(data['pos_timeline']),1);self.assertFalse(data['pos_timeline'][0]['active_hold'])
            self.assertFalse(Order.objects.exists())
    def test_area_preference_and_capacity_no_fallback_to_other_area(self):
        area=Area.objects.create(name='Preferred');table=RestaurantTable.objects.create(code='P',area=area,capacity=2)
        b=self.booking(area=area);self.assertEqual(b.table_id,table.pk)
        with self.assertRaises(ValidationError):self.booking(area=area)
        self.assertEqual(Booking.objects.count(),1)
    def test_preferred_area_survives_menu_navigation_and_invalid_area_cannot_book(self):
        self.client.force_login(self.customer)
        response=self.client.post(reverse('customer_booking'),{'intent':'menu','preferred_area':str(self.area.pk)})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.session['customer_booking_draft']['fields']['preferred_area'],str(self.area.pk))
        at=timezone.localtime(self.now+timedelta(minutes=10))
        response=self.client.post(reverse('customer_booking'),{'name':'Customer','phone':'0912345678','date':str(at.date()),'time':at.strftime('%H:%M'),'guests':2,'preferred_area':999999})
        self.assertEqual(response.status_code,200)
        self.assertIn('preferred_area',response.context['form'].errors)
        self.assertFalse(Booking.objects.exists())
    def test_booking_cannot_open_without_deposit_confirmation(self):
        b=self.booking()
        BookingDeposit.objects.create(booking=b,customer=self.customer,amount=200000,expires_at=b.end_time)
        with self.assertRaises(ValidationError):open_order_from_booking(b.pk,actor=self.admin)
        self.assertFalse(Order.objects.exists())
    def test_unassigned_staff_cannot_open_another_table(self):
        b=self.booking()
        with self.assertRaises(PermissionDenied):open_order_from_booking(b.pk,actor=self.staff)
    def test_assignment_management_permission_and_csrf(self):
        from django.test import Client
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('table_assignments')).status_code,403)
        protected=Client(enforce_csrf_checks=True);protected.force_login(self.manager)
        self.assertEqual(protected.post(reverse('table_assignments'),{'table':self.table.pk,'schedule':self.schedule.pk}).status_code,403)
        self.assertFalse(TableServiceAssignment.objects.exists())
        self.client.force_login(self.manager)
        response=self.client.post(reverse('table_assignments'),{'table':self.table.pk,'schedule':self.schedule.pk})
        self.assertEqual(response.status_code,302)
        self.assertEqual(TableServiceAssignment.objects.count(),1)
    def test_full_service_flow_and_release(self):
        b=self.booking();self.assign()
        with patch('django.utils.timezone.now',return_value=b.start_time+timedelta(minutes=1)):
            order=open_order_from_booking(b.pk,actor=self.staff)
            self.assertEqual(open_order_from_booking(b.pk,actor=self.staff).pk,order.pk)
            self.assertEqual(order.items.get().item_name,self.menu.name)
            self.assertEqual(next(t for t in board(self.request(self.staff))['tables'] if t.pk==b.table_id).visual_status,'OCCUPIED')
            transition_order(order.pk,'CONFIRMED',actor=self.staff)
            for item in order.items.all():
                transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
                transition_kitchen_item(order.pk,item.pk,'READY',actor=self.manager)
            transition_order(order.pk,'COMPLETED',actor=self.staff)
            b.refresh_from_db();self.assertEqual(b.status,'COMPLETED')
            self.assertEqual(next(t for t in board(self.request(self.staff))['tables'] if t.pk==b.table_id).visual_status,'AVAILABLE')
            self.assertEqual(Order.objects.count(),1)
    @override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=False)
    def test_feature_flag_rejects_writes_and_existing_views_still_render(self):
        with self.assertRaises(ValidationError):self.assign()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('table_assignments')),'migration')
