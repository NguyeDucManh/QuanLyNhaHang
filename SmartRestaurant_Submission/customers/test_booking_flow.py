from datetime import time
from django.core.exceptions import PermissionDenied
from django.test import TestCase,Client
from django.urls import reverse
from .test_module02 import BookingFixtures
from .models import Booking,RestaurantTable
from .booking_service import transition_booking,NO_TABLE_MESSAGE


class CustomerBookingFlowTests(BookingFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.create_test_data()

    def test_auto_confirm_and_cancel_releases_same_table(self):
        self.only_small()
        self.client.force_login(self.customer)
        payload={'name':'Khách','phone':'0912345678','date':self.day.isoformat(),'time':'18:00','guests':2}
        response=self.client.post('/booking/',payload,follow=True)
        booking=Booking.objects.get()
        self.assertEqual(booking.status,'CONFIRMED')
        self.assertEqual(booking.table_id,self.small.pk)
        self.assertContains(response,'Đặt bàn thành công')
        self.assertContains(response,'Hủy đặt bàn')
        self.assertContains(self.client.post('/booking/',payload),NO_TABLE_MESSAGE)
        self.assertEqual(Booking.objects.count(),1)
        url=reverse('customer_booking_cancel',args=[booking.pk])
        self.assertRedirects(self.client.post(url,{'status':'COMPLETED','user':999}),'/booking/')
        booking.refresh_from_db(); self.assertEqual(booking.status,'CANCELLED')
        # Keep the original table in history; availability is interval-based.
        self.assertEqual(booking.table_id,self.small.pk)
        self.client.post('/booking/',payload)
        self.assertEqual(Booking.objects.filter(status='CONFIRMED').get().table_id,self.small.pk)

    def test_cannot_cancel_other_customers_booking(self):
        from django.contrib.auth.models import User
        other=User.objects.create_user('other-booking-owner')
        booking=self.reserve(user=other)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(reverse('customer_booking_cancel',args=[booking.pk])).status_code,404)
        with self.assertRaises(PermissionDenied):
            transition_booking(booking.pk,'CANCELLED',owner=self.customer)
        booking.refresh_from_db(); self.assertEqual(booking.status,'CONFIRMED')

    def test_cancel_requires_login_post_and_csrf(self):
        booking=self.reserve(); url=reverse('customer_booking_cancel',args=[booking.pk])
        self.assertEqual(self.client.post(url).status_code,302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code,405)
        protected=Client(enforce_csrf_checks=True); protected.force_login(self.customer)
        self.assertEqual(protected.post(url).status_code,403)
        booking.refresh_from_db(); self.assertEqual(booking.status,'CONFIRMED')

    def test_cancel_retry_is_safe_and_button_disappears(self):
        booking=self.reserve(); self.client.force_login(self.customer)
        url=reverse('customer_booking_cancel',args=[booking.pk])
        self.client.post(url)
        response=self.client.post(url,follow=True)
        self.assertNotContains(response,'Hủy đặt bàn</button>')
        self.assertEqual(Booking.objects.count(),1)
        self.assertEqual(Booking.objects.get().status,'CANCELLED')

    def test_cannot_cancel_completed_or_set_other_status(self):
        booking=self.reserve()
        with self.assertRaises(PermissionDenied): transition_booking(booking.pk,'COMPLETED',owner=self.customer)
        transition_booking(booking.pk,'COMPLETED')
        self.client.force_login(self.customer)
        response=self.client.post(reverse('customer_booking_cancel',args=[booking.pk]),follow=True)
        booking.refresh_from_db(); self.assertEqual(booking.status,'COMPLETED')
        self.assertContains(response,'Không được chuyển trạng thái')

    def test_cancel_keeps_other_slots_and_operational_status(self):
        self.only_small()
        self.small.status=RestaurantTable.Status.OCCUPIED; self.small.save()
        first=self.reserve(18); second=self.reserve(20)
        transition_booking(first.pk,'CANCELLED',owner=self.customer)
        self.small.refresh_from_db(); self.assertEqual(self.small.status,'OCCUPIED')
        second.refresh_from_db(); self.assertEqual(second.status,'CONFIRMED')
        self.assertEqual(self.reserve(18).table_id,self.small.pk)
