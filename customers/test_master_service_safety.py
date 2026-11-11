import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from django.urls import reverse
from .test_module07 import Module07Fixtures
from .models import Order,RestaurantTable,TableSession,Invoice,Booking,BookingVisit,RestaurantInfo,BookingDeposit,Payment
from .order_service import create_order,transition_order,add_order_item,open_order_from_booking
from .booking_service import create_booking
from .table_session_service import release
from . import service_scope


@override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=True,TABLE_SERVICE_LIFECYCLE_ENABLED=True)
class MasterServiceSafetyTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        self.personnel();self.schedule_row=self.approved_schedule()
        self.clock=patch('django.utils.timezone.now',return_value=self.schedule_row.start_at+timedelta(minutes=30));self.clock.start();self.addCleanup(self.clock.stop)
        from .table_assignment_service import assign_table
        assign_table(actor=self.manager,table_id=self.table.pk,schedule_id=self.schedule_row.pk)
        self.other_table=RestaurantTable.objects.create(code='PRIVATE-B',area=self.area,capacity=4)
    def dine(self,table=None,actor=None):
        return create_order(actor=actor or self.manager,items=[{'menu_item':self.menu,'quantity':1}],request_key=uuid.uuid4(),table=table or self.table,order_type='DINE_IN')
    def test_cross_table_service_http_and_queries_denied(self):
        foreign=self.dine(self.other_table)
        self.assertFalse(service_scope.orders(self.staff).filter(pk=foreign.pk).exists())
        with self.assertRaises(PermissionDenied):add_order_item(foreign.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin_order_detail',args=[foreign.pk])).status_code,404)
        self.assertFalse(service_scope.invoices(self.staff).exists())
        self.assertTrue(service_scope.orders(self.admin).filter(pk=foreign.pk).exists())
        response=self.client.post(reverse('admin_order_item_add',args=[foreign.pk]),{'menu_item':self.menu.pk,'quantity':1})
        self.assertEqual(response.status_code,404)
    def test_ready_completed_paid_still_occupied_until_explicit_release(self):
        order=self.dine(actor=self.staff)
        self.client.force_login(self.staff)
        page=self.client.get(reverse('admin_order_detail',args=[order.pk]))
        self.assertContains(page,'Chưa thể trả bàn thông thường')
        self.assertContains(page,'<button disabled>Xác nhận trả bàn</button>',html=True)
        self.prepare(order);transition_order(order.pk,'COMPLETED',actor=self.staff)
        self.table.refresh_from_db();self.assertEqual(self.table.status,'OCCUPIED')
        self.assertIsNone(TableSession.objects.get(order=order).ended_at)
        with self.assertRaises(ValidationError):self.dine()
        with self.assertRaises(ValidationError):release(actor=self.staff,order_id=order.pk,reason='Guest has left',confirm=True)
        Invoice.objects.create(order=order,invoice_number='TEST-PAID',subtotal=order.subtotal,discount_amount=0,total_amount=order.total_amount,status='PAID',paid_at=timezone.now())
        with self.assertRaises(ValidationError):release(actor=self.staff,order_id=order.pk,reason='Guest has left')
        with patch('customers.table_session_service.record',side_effect=ValidationError('Audit unavailable')):
            with self.assertRaises(ValidationError):release(actor=self.staff,order_id=order.pk,reason='Guest has left',confirm=True)
        self.assertIsNone(TableSession.objects.get(order=order).ended_at)
        self.table.refresh_from_db();self.assertEqual(self.table.status,'OCCUPIED')
        result=release(actor=self.staff,order_id=order.pk,reason='Guest has left',confirm=True)
        self.assertIsNotNone(result.ended_at);self.table.refresh_from_db();self.assertEqual(self.table.status,'AVAILABLE')
        self.assertEqual(release(actor=self.staff,order_id=order.pk,reason='Repeated release',confirm=True).pk,result.pk)
    def test_board_session_status_does_not_grant_order_details(self):
        from django.test import RequestFactory
        from .table_board import board
        from django.contrib.auth.models import Permission
        order=self.dine(actor=self.staff)
        self.staff.groups.get(name='STAFF').permissions.remove(Permission.objects.get(codename='view_order',content_type__app_label='customers'))
        user=type(self.staff).objects.get(pk=self.staff.pk)
        r=RequestFactory().get('/staff/');r.user=user
        table=next(t for t in board(r)['tables'] if t.pk==self.table.pk)
        self.assertEqual(table.visual_status,'OCCUPIED');self.assertIsNone(table.live_order)

    def test_walkin_cannot_take_live_reservation(self):
        at=timezone.localtime(timezone.now()+timedelta(minutes=10))
        create_booking(user=self.customer,name='Private booking',phone='0901234567',date=at.date(),time=at.time(),guests=2,preferred_table=self.table)
        with self.assertRaises(ValidationError):self.dine()
        self.assertFalse(Order.objects.exists())
    def test_booking_requires_arrival_and_session_survives_overrun(self):
        at=timezone.localtime(timezone.now()+timedelta(minutes=10))
        b=create_booking(user=self.customer,name='Private booking',phone='0901234567',date=at.date(),time=at.time(),guests=2,preferred_table=self.table)
        with self.assertRaises(ValidationError):open_order_from_booking(b.pk,actor=self.manager)
        with patch('django.utils.timezone.now',return_value=b.start_time):
            from .booking_advanced_service import mark_arrival
            mark_arrival(b.pk,actor=self.admin,state='CHECKED_IN')
            order=open_order_from_booking(b.pk,actor=self.manager)
            self.assertEqual(open_order_from_booking(b.pk,actor=self.manager).pk,order.pk)
        with patch('django.utils.timezone.now',return_value=b.end_time+timedelta(hours=1)):
            with self.assertRaises(ValidationError):self.dine()
        self.assertEqual(TableSession.objects.count(),1)
    def test_manager_override_audits_without_changing_financial_state(self):
        order=self.dine()
        with self.assertRaises(PermissionDenied):release(actor=self.staff,order_id=order.pk,reason='End stuck session',confirm=True,override=True)
        release(actor=self.manager,order_id=order.pk,reason='End stuck session after inspection',confirm=True,override=True)
        order.refresh_from_db();self.assertEqual(order.status,'PENDING');self.assertFalse(Invoice.objects.exists())
        replacement=self.dine()
        self.assertNotEqual(replacement.pk,order.pk)
        with self.assertRaises(ValidationError):add_order_item(order.pk,actor=self.manager,menu_item_id=self.menu.pk,quantity=1)
    def test_booking_hours_include_entire_interval_and_keep_form_errors(self):
        from .booking_service import booking_window
        from datetime import time
        RestaurantInfo.objects.create(name='Test hours',address='Test',opening_time='09:00',closing_time='22:00')
        day=timezone.localdate()+timedelta(days=2)
        with self.assertRaises(ValidationError):booking_window(day,time(21))
        with self.assertRaises(ValidationError):booking_window(day,time(8))
        self.assertEqual(timezone.localtime(booking_window(day,time(20))[1]).hour,22)
    def test_financial_report_separates_deposit_cash_topup_and_revenue(self):
        from decimal import Decimal
        from .report_service import report_data
        order=self.dine();now=timezone.now()
        booking=Booking.objects.create(user=self.customer,name='Financial fixture',phone='0901234567',date=timezone.localdate(),time=timezone.localtime().time(),guests=2,table=self.table,start_time=now,end_time=now+timedelta(hours=2),status='CONFIRMED')
        deposit=BookingDeposit.objects.create(booking=booking,customer=self.customer,amount=30,currency='vnd',status='SUCCEEDED',paid_at=now,expires_at=now+timedelta(minutes=10))
        invoice=Invoice.objects.create(order=order,invoice_number='TEST-DEPOSIT',subtotal=100,discount_amount=0,total_amount=100,status='PAID',paid_at=now,booking_deposit=deposit,deposit_applied_amount=30)
        Payment.objects.create(invoice=invoice,amount=70,payment_method='CASH',status='SUCCEEDED',paid_at=now,created_by=self.manager,confirmed_by=self.manager,processed_at=now)
        sections=report_data(self.manager)
        rows=dict(next(rows for title,rows in sections if title=='Đối chiếu thu tiền và doanh thu'))
        self.assertEqual(rows['Tổng tiền thu gộp, chưa trừ hoàn tiền'],Decimal(100))
        self.assertEqual(rows['Doanh thu hóa đơn PAID'],Decimal(100))
        self.assertEqual(rows['Cọc chờ xử lý/hoàn phần dư: không cộng thêm vào doanh thu'],Decimal(0))
    @override_settings(TABLE_SERVICE_LIFECYCLE_ENABLED=False,TABLE_SERVICE_ASSIGNMENTS_ENABLED=False)
    def test_flags_off_skip_new_tables(self):
        with patch.object(TableSession.objects,'filter',side_effect=AssertionError('new table queried')):
            order=self.dine()
        self.assertTrue(service_scope.orders(self.manager).filter(pk=order.pk).exists())


from django.test import TransactionTestCase,Client
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from restaurant_system.asgi import application


@override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=True,TABLE_SERVICE_LIFECYCLE_ENABLED=True)
class MasterSocketScopeTests(Module07Fixtures,TransactionTestCase):
    def setUp(self):
        self.initialize();self.personnel();self.schedule_row=self.approved_schedule()
        clock=patch('django.utils.timezone.now',return_value=self.schedule_row.start_at+timedelta(minutes=30));clock.start();self.addCleanup(clock.stop)
        from .table_assignment_service import assign_table
        assign_table(actor=self.manager,table_id=self.table.pk,schedule_id=self.schedule_row.pk)
        other=RestaurantTable.objects.create(code='SOCKET-OTHER',area=self.area,capacity=4)
        def dine(table,actor):return create_order(actor=actor,items=[{'menu_item':self.menu,'quantity':1}],request_key=uuid.uuid4(),table=table,order_type='DINE_IN')
        self.mine=dine(self.table,self.staff);self.foreign=dine(other,self.manager)
        client=Client();client.force_login(self.staff)
        self.headers=[(b'origin',b'http://localhost'),(b'cookie',('sessionid='+client.cookies['sessionid'].value).encode())]
    async def test_foreign_order_socket_denied_and_kitchen_events_filtered(self):
        wrong=WebsocketCommunicator(application,f'/ws/management/orders/{self.foreign.pk}/',headers=self.headers)
        ok,code=await wrong.connect();self.assertFalse(ok);self.assertEqual(code,4403);await wrong.disconnect()
        board=WebsocketCommunicator(application,'/ws/management/kitchen/',headers=self.headers)
        ok,_=await board.connect();self.assertTrue(ok)
        layer=get_channel_layer()
        await layer.group_send('management.kitchen',{'type':'realtime.changed','payload':{'type':'kitchen.queue_changed','order_id':self.foreign.pk}})
        self.assertTrue(await board.receive_nothing(timeout=.1))
        await layer.group_send('management.kitchen',{'type':'realtime.changed','payload':{'type':'kitchen.queue_changed','order_id':self.mine.pk}})
        self.assertEqual((await board.receive_json_from())['order_id'],self.mine.pk)
        await board.disconnect()
    async def test_cancelled_schedule_revokes_existing_order_socket(self):
        socket=WebsocketCommunicator(application,f'/ws/management/orders/{self.mine.pk}/',headers=self.headers)
        ok,_=await socket.connect();self.assertTrue(ok)
        @database_sync_to_async
        def cancel():
            from .models import WorkSchedule
            WorkSchedule.objects.filter(pk=self.schedule_row.pk).update(status='CANCELLED')
        await cancel()
        await get_channel_layer().group_send(f'management.order.{self.mine.pk}',{'type':'realtime.changed','payload':{'type':'order.updated','order_id':self.mine.pk}})
        event=await socket.receive_output(timeout=2)
        self.assertEqual(event['type'],'websocket.close');self.assertEqual(event['code'],4403)
        await socket.disconnect()
