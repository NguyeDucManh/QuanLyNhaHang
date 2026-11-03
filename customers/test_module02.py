from datetime import datetime, time, timedelta
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock
import importlib
from django.apps import apps
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, connections, IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.utils import timezone
from django.urls import reverse
from .models import Area, RestaurantTable, Booking, MenuItem, Category
from .forms import AreaForm, RestaurantTableForm
from .rbac import assign_role
from .booking_service import create_booking, booking_window, overlaps, transition_booking, save_table, NO_TABLE_MESSAGE


class BookingFixtures:
    @classmethod
    def create_test_data(cls):
        call_command('seed_rbac', stdout=StringIO())
        cls.customer = User.objects.create_user('booking-customer')
        assign_role(cls.customer, 'CUSTOMER')
        cls.area = Area.objects.create(name='Test Area')
        cls.small = RestaurantTable.objects.create(area=cls.area, code='T02', capacity=2)
        cls.medium = RestaurantTable.objects.create(area=cls.area, code='T04', capacity=4)
        cls.large = RestaurantTable.objects.create(area=cls.area, code='T08', capacity=8)
        cls.day = timezone.localdate()+timedelta(days=1)

    def reserve(self, hour=18, guests=2, **kwargs):
        data = dict(user=self.customer, name='Khách', phone='0912345678', date=self.day, time=time(hour), guests=guests)
        data.update(kwargs)
        return create_booking(**data)

    def reserve_pending(self, *args, **kwargs):
        # Legacy pending fixture: new customer bookings now confirm immediately.
        booking = self.reserve(*args, **kwargs)
        Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.PENDING)
        booking.refresh_from_db()
        return booking

    def only_small(self):
        RestaurantTable.objects.exclude(pk=self.small.pk).delete()


class AreaTableTests(BookingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_test_data()

    def test_valid_area_and_invalid_names(self):
        form = AreaForm({'name':'VIP', 'description':'', 'is_active':'on'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().name, 'VIP')
        for name in ('', '   ', 'Test Area'):
            form = AreaForm({'name':name})
            self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError):
            Area(name='  ').full_clean()

    def test_table_capacity_and_unique_code_and_status(self):
        for capacity in (0,-1):
            with self.subTest(capacity=capacity):
                form = RestaurantTableForm({'area':self.area.pk,'code':'BAD','capacity':capacity,'status':'AVAILABLE','is_active':'on'})
                self.assertFalse(form.is_valid())
        form = RestaurantTableForm({'area':self.area.pk,'code':'NEW','capacity':6,'status':'AVAILABLE','is_active':'on'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().capacity, 6)
        for code,status in [('T02','AVAILABLE'), ('NEW-CODE','RESERVED'), (' ','AVAILABLE')]:
            self.assertFalse(RestaurantTableForm({'area':self.area.pk,'code':code,'capacity':4,'status':status}).is_valid())

    def test_database_constraints(self):
        for values in ({'code':'ZERO','capacity':0}, {'code':'T02','capacity':4}, {'code':'BADSTATUS','capacity':2,'status':'INVALID'}):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                RestaurantTable.objects.create(area=self.area, **values)

    def test_inactive_maintenance_and_inactive_area_not_assigned(self):
        self.small.is_active=False; self.small.save()
        self.medium.status=RestaurantTable.Status.MAINTENANCE; self.medium.save()
        booking=self.reserve()
        self.assertEqual(booking.table_id, self.large.pk)
        self.area.is_active=False; self.area.save()
        with self.assertRaisesMessage(ValidationError, NO_TABLE_MESSAGE):
            self.reserve(hour=21)

    def test_occupied_table_allows_future_booking(self):
        self.small.status=RestaurantTable.Status.OCCUPIED; self.small.save()
        self.assertEqual(self.reserve().table_id, self.small.pk)

    def test_capacity_reduction_rejects_existing_slot(self):
        booking=self.reserve(guests=4)
        form=RestaurantTableForm({'area':self.area.pk,'code':self.medium.code,'capacity':2,'status':'AVAILABLE','is_active':'on'}, instance=self.medium)
        self.assertTrue(form.is_valid())
        with self.assertRaises(ValidationError):
            save_table(form)
        self.assertEqual(RestaurantTable.objects.get(pk=booking.table_id).capacity, 4)


class BookingServiceTests(BookingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_test_data()

    def test_valid_booking_assigns_smallest_table_and_duration(self):
        booking=self.reserve()
        self.assertEqual(booking.table_id, self.small.pk)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(booking.end_time-booking.start_time,timedelta(minutes=120))
        self.assertTrue(timezone.is_aware(booking.start_time))
        self.assertEqual(self.reserve(guests=4).table_id,self.medium.pk)
        self.assertEqual(self.reserve(guests=8).table_id,self.large.pk)

    @override_settings(DEFAULT_BOOKING_DURATION_MINUTES=90)
    def test_duration_comes_from_central_setting(self):
        booking=self.reserve()
        self.assertEqual(booking.end_time-booking.start_time,timedelta(minutes=90))

    def test_past_today_invalid_guests_and_capacity(self):
        self.only_small()
        for data in ({'date':self.day-timedelta(days=2)}, {'guests':0}, {'guests':-1}, {'guests':3}, {'guests':21}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                self.reserve(**data)
        with self.assertRaises(ValidationError):
            self.reserve(date=timezone.localdate(), time=timezone.localtime(timezone.now()-timedelta(minutes=5)).time().replace(tzinfo=None))
        self.assertEqual(Booking.objects.count(),0)

    def test_pending_overlap_and_18_20_vs_19_21(self):
        self.only_small()
        first=self.reserve_pending(18)
        start,end=booking_window(self.day,time(19))
        self.assertTrue(overlaps(first.table_id,start,end))
        with self.assertRaisesMessage(ValidationError, NO_TABLE_MESSAGE):
            self.reserve(19)
        self.assertEqual(Booking.objects.count(),1)

    def test_boundary_18_20_vs_20_22_no_overlap(self):
        self.only_small()
        first=self.reserve(18); second=self.reserve(20)
        self.assertEqual(first.table_id,second.table_id)
        self.assertEqual(first.end_time,second.start_time)

    def test_overlap_falls_back_to_another_table(self):
        first=self.reserve(18); second=self.reserve(19)
        self.assertEqual(first.table_id,self.small.pk)
        self.assertEqual(second.table_id,self.medium.pk)

    def test_confirmed_blocks_and_cancelled_frees_slot(self):
        self.only_small()
        first=self.reserve()
        self.assertEqual(first.status, Booking.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            self.reserve(19)
        transition_booking(first.pk, Booking.Status.CANCELLED)
        self.assertEqual(self.reserve(19).table_id,self.small.pk)

    def test_pending_cancel_and_completed_release_slot_and_terminal_states(self):
        self.only_small()
        first=self.reserve_pending()
        transition_booking(first.pk, Booking.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            transition_booking(first.pk, Booking.Status.CONFIRMED)
        second=self.reserve_pending()
        transition_booking(second.pk, Booking.Status.CONFIRMED)
        transition_booking(second.pk, Booking.Status.COMPLETED)
        with self.assertRaises(ValidationError):
            transition_booking(second.pk, Booking.Status.PENDING)
        third=self.reserve_pending()
        with self.assertRaises(ValidationError):
            transition_booking(third.pk, Booking.Status.COMPLETED)
        self.assertEqual(Booking.objects.get(pk=third.pk).status,Booking.Status.PENDING)

    def test_no_table_and_invalid_window_create_nothing(self):
        RestaurantTable.objects.all().delete()
        with self.assertRaisesMessage(ValidationError,NO_TABLE_MESSAGE):
            self.reserve()
        start,end=booking_window(self.day,time(18))
        with self.assertRaises(ValidationError):
            overlaps(1,end,start)
        self.assertEqual(Booking.objects.count(),0)

    def test_customer_ignores_untrusted_table_user_status_capacity_and_end(self):
        self.client.force_login(self.customer)
        other=User.objects.create_user('other-customer')
        response=self.client.post('/booking/', {'name':'Khách','phone':'0912345678','date':self.day.isoformat(),'time':'18:00','guests':2,
             'user':other.pk,'table':self.large.pk,'status':'CANCELLED','capacity':999,'area':999,'end_time':'2099-01-01T00:00'})
        self.assertRedirects(response,reverse('booking_deposit',args=[Booking.objects.get().pk]))
        booking=Booking.objects.get()
        self.assertEqual(booking.user_id,self.customer.pk)
        self.assertEqual(booking.table_id,self.small.pk)
        self.assertEqual(booking.status,'PENDING_DEPOSIT')
        self.assertEqual(booking.end_time-booking.start_time,timedelta(minutes=120))

    def test_customer_no_table_error_and_scoped_history(self):
        RestaurantTable.objects.all().delete()
        self.client.force_login(self.customer)
        response=self.client.post('/booking/', {'name':'Khách','phone':'0912345678','date':self.day.isoformat(),'time':'18:00','guests':2})
        self.assertContains(response,NO_TABLE_MESSAGE)
        self.assertEqual(Booking.objects.count(),0)

    def test_legacy_backfill_preserves_fields_and_can_assign_on_confirm(self):
        old=Booking.objects.create(user=self.customer,name='Legacy',phone='0912345678',date=self.day,time=time(18),guests=2,note='Preserve')
        original=(old.user_id,old.name,old.phone,old.date,old.time,old.guests,old.note,old.created_at)
        migration=importlib.import_module('customers.migrations.0004_legacy_booking_windows')
        migration.fill_legacy_windows(apps,Mock(connection=connection))
        old.refresh_from_db()
        self.assertEqual((old.user_id,old.name,old.phone,old.date,old.time,old.guests,old.note,old.created_at),original)
        self.assertIsNone(old.table_id)
        self.assertEqual(old.end_time-old.start_time,timedelta(minutes=120))
        confirmed=transition_booking(old.pk,'CONFIRMED')
        self.assertEqual(confirmed.table_id,self.small.pk)


class Module02AccessTests(BookingFixtures,TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_test_data()
        call_command('seed_menu',stdout=StringIO())
        cls.admin=User.objects.create_user('area-admin'); assign_role(cls.admin,'ADMIN')
        cls.manager=User.objects.create_user('area-manager'); assign_role(cls.manager,'MANAGER')
        cls.staff=User.objects.create_user('area-staff'); assign_role(cls.staff,'STAFF')

    def test_admin_manager_crud_and_booking_state(self):
        for user in (self.admin,self.manager):
            self.client.force_login(user)
            for url in ('/management/areas/','/management/tables/','/management/bookings/'):
                self.assertEqual(self.client.get(url).status_code,200)
            area_name='Area '+user.username
            self.assertRedirects(self.client.post('/management/areas/add/',{'name':area_name,'is_active':'on'}),'/management/areas/')
            area=Area.objects.get(name=area_name)
            self.assertRedirects(self.client.post('/management/tables/add/',{'area':area.pk,'code':user.username,'capacity':4,'status':'AVAILABLE','is_active':'on'}),'/management/tables/')
        booking=self.reserve_pending()
        self.assertRedirects(self.client.post(reverse('admin_booking_status',args=[booking.pk]),{'status':'CONFIRMED'}),'/management/bookings/')
        self.assertEqual(Booking.objects.get(pk=booking.pk).status,'CONFIRMED')

    def test_staff_customer_forbidden_no_mutation(self):
        for user in (self.staff,self.customer):
            self.client.force_login(user)
            for url in ('/management/areas/','/management/tables/','/management/bookings/','/management/accounts/'):
                self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post('/management/areas/add/',{'name':'Denied'}).status_code,403)
            self.assertEqual(self.client.post('/management/tables/add/',{'area':self.area.pk,'code':'DENIED','capacity':4,'status':'AVAILABLE'}).status_code,403)
        self.assertFalse(Area.objects.filter(name='Denied').exists())
        self.assertFalse(RestaurantTable.objects.filter(code='DENIED').exists())

    def test_shared_account_layout_active_page_and_role_change(self):
        self.client.force_login(self.admin)
        for url in ('/management/accounts/',reverse('admin_account_edit',args=[self.customer.pk])):
            response=self.client.get(url)
            self.assertContains(response,'data-admin-page="accounts"')
            self.assertContains(response,'id="server-content"')
            self.assertContains(response,'id="admin-routes"')
            self.assertEqual(response.context['admin_page'],'accounts')
        response=self.client.post(reverse('admin_account_edit',args=[self.customer.pk]),{'role':'STAFF','is_active':'on'})
        self.assertRedirects(response,'/management/accounts/')
        self.customer.refresh_from_db()
        self.assertEqual(list(self.customer.groups.values_list('name',flat=True)),['STAFF'])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/management/accounts/').status_code,403)
        self.assertFalse(self.client.get('/management/').context['rbac_access']['is_admin'])

    def test_booking_post_csrf_and_invalid_transition_unchanged(self):
        self.client.force_login(self.admin)
        booking=self.reserve_pending()
        url=reverse('admin_booking_status',args=[booking.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        protected=Client(enforce_csrf_checks=True); protected.force_login(self.admin)
        self.assertEqual(protected.post(url,{'status':'CANCELLED'}).status_code,403)
        self.client.post(url,{'status':'COMPLETED'})
        self.assertEqual(Booking.objects.get(pk=booking.pk).status,'PENDING')
        self.client.post(url,{'status':'CANCELLED'})
        self.client.post(url,{'status':'CONFIRMED'})
        self.assertEqual(Booking.objects.get(pk=booking.pk).status,'CANCELLED')

    def test_resource_edits_status_disable_and_database_counts(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('admin_table_edit',args=[self.small.pk]),{'area':self.area.pk,'code':self.small.code,'capacity':2,'status':'MAINTENANCE'})
        self.small.refresh_from_db()
        self.assertFalse(self.small.is_active)
        self.assertEqual(self.small.status,'MAINTENANCE')
        self.client.post(reverse('admin_area_edit',args=[self.area.pk]),{'name':self.area.name,'description':'Updated'})
        self.assertFalse(Area.objects.get(pk=self.area.pk).is_active)
        self.assertEqual(MenuItem.objects.count(),45)
        self.assertEqual(Category.objects.count(),19)


class BookingConcurrencyTests(BookingFixtures,TransactionTestCase):
    def setUp(self):
        self.create_test_data()
        RestaurantTable.objects.exclude(pk=self.small.pk).delete()

    def test_two_requests_cannot_book_same_table_overlapping(self):
        self.assertEqual(connection.vendor,'postgresql')
        barrier=Barrier(2)
        user_id=self.customer.pk
        day=self.day
        def worker():
            connections.close_all()
            try:
                user=User.objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    booking=create_booking(user=user,name='Concurrent',phone='0912345678',date=day,time=time(18),guests=2)
                    return 'created',booking.pk
                except ValidationError:
                    return 'unavailable',None
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            a=executor.submit(worker); b=executor.submit(worker)
            results=[a.result(timeout=15),b.result(timeout=15)]
        self.assertEqual(sorted(r[0] for r in results),['created','unavailable'])
        self.assertEqual(Booking.objects.count(),1)
