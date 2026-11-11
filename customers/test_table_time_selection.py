from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, RequestFactory
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from .test_business import BusinessData
from .models import RestaurantTable, BookingDeposit, Booking, Order
from .booking_service import create_booking
from .table_availability import table_snapshot
from .table_board import board


class TableTimeSelectionTests(BusinessData, TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def setUp(self):
        self.start=(timezone.localtime()+timedelta(days=3)).replace(hour=12,minute=0,second=0,microsecond=0)
        self.other=RestaurantTable.objects.create(area=self.area,code='B02',capacity=4)

    def reserve(self,start=None,**extra):
        start=start or self.start
        return create_booking(user=self.customer,name='Private person',phone='0901234567',
            date=start.date(),time=start.time(),guests=2,preferred_table=self.table,**extra)

    def test_exact_table_overlap_and_alternatives_without_identity(self):
        b=self.reserve()
        with self.assertRaisesMessage(ValidationError,self.table.code):self.reserve(self.start+timedelta(minutes=30))
        self.client.force_login(self.customer)
        r=self.client.get(reverse('booking_availability'),{'date':self.start.date(),'time':'12:30','guests':2,'preferred_table':self.table.pk})
        self.assertEqual(r.status_code,400)
        self.assertNotIn('Private person',r.content.decode())
        self.assertIn(self.other.pk,r.json()['suggestions'])
        self.assertIn('12:00',r.json()['message']);self.assertIn('14:00',r.json()['message'])
        self.assertEqual(Booking.objects.count(),1)

    def test_adjacent_time_and_other_day_same_table_allowed(self):
        first=self.reserve()
        self.assertEqual(self.reserve(self.start+timedelta(hours=2)).table_id,first.table_id)
        self.assertEqual(self.reserve(self.start+timedelta(days=1)).table_id,first.table_id)

    def test_open_booking_list_hides_identity_without_booking_permission(self):
        self.reserve();self.client.force_login(self.staff)
        response=self.client.get(reverse('admin_order_bookings'))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'Private person')

    def test_hold_expiration_and_unavailable_inventory(self):
        b=self.reserve(online=True)
        if not hasattr(b,'deposit'):
            b.status='PENDING_DEPOSIT';b.save(update_fields=['status'])
            BookingDeposit.objects.create(booking=b,amount=100,currency='vnd',expires_at=timezone.now()+timedelta(minutes=10))
        rows=table_snapshot(self.start,self.start+timedelta(hours=2),2)
        self.assertFalse(next(t for t in rows if t['id']==self.table.pk)['available'])
        BookingDeposit.objects.filter(booking=b).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.reserve().table_id,self.table.pk)
        self.other.status='MAINTENANCE';self.other.save()
        rows=table_snapshot(self.start,self.start+timedelta(hours=2),5)
        self.assertEqual(next(t for t in rows if t['id']==self.other.pk)['state'],'MAINTENANCE')

    def test_overrunning_order_blocks_even_after_booking_interval(self):
        b=self.reserve()
        Order.objects.create(order_type='DINE_IN',table=self.table,booking=b,customer=self.customer,created_by=self.admin)
        with patch('django.utils.timezone.now',return_value=self.start+timedelta(hours=3)):
            with self.assertRaisesMessage(ValidationError,'giải phóng'):self.reserve(self.start+timedelta(hours=4))

    def test_staff_projection_at_chosen_time_and_no_fake_orders(self):
        b=self.reserve()
        r=RequestFactory().get('/staff/',{'at':self.start.isoformat()});r.user=self.admin
        state=board(r)
        self.assertEqual(next(t for t in state['tables'] if t.pk==self.table.pk).visual_status,'RESERVED')
        self.assertEqual([row['booking'].pk for row in state['pos_timeline']],[b.pk])
        self.assertFalse(state['selected'].can_open_booking)
        r.GET=r.GET.copy();r.GET['at']=(self.start+timedelta(days=1)).isoformat()
        self.assertEqual(next(t for t in board(r)['tables'] if t.pk==self.table.pk).visual_status,'AVAILABLE')
        self.assertFalse(Order.objects.exists())
