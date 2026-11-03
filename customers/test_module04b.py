"""Real ASGI session authentication, commit notifications and read-only sockets."""
from unittest.mock import patch
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TransactionTestCase, Client
from .test_module03 import OrderFixtures
from .models import Order,OrderItem
from .order_service import transition_order,add_order_item,update_order_item,remove_order_item
from .kitchen_service import send_order_to_kitchen,transition_kitchen_item
from .realtime import KITCHEN_GROUP,order_group
from restaurant_system.asgi import application


class Module04BTests(OrderFixtures,TransactionTestCase):
    def setUp(self):
        self.initialize()
        self.order=self.open()
        self.clients={}
        for role in ('admin','manager','staff','customer'):
            client=Client(); client.force_login(getattr(self,role)); self.clients[role]=client

    def socket(self,path,role='staff',origin='http://localhost'):
        headers=[(b'origin',origin.encode())]
        if role:
            headers.append((b'cookie',('sessionid='+self.clients[role].cookies['sessionid'].value).encode()))
        return WebsocketCommunicator(application,path,headers=headers)

    async def opened(self,path,role='staff'):
        socket=self.socket(path,role); connected,_=await socket.connect(); self.assertTrue(connected)
        return socket

    async def events(self,socket):
        result=[await socket.receive_json_from()]
        while not await socket.receive_nothing(timeout=.05): result.append(await socket.receive_json_from())
        return result

    async def test_admin_manager_staff_authenticate_kitchen_and_order(self):
        for role in ('admin','manager','staff'):
            for path in ('/ws/management/kitchen/',f'/ws/management/orders/{self.order.pk}/'):
                socket=await self.opened(path,role); await socket.disconnect()

    async def test_customer_and_anonymous_denied_both_streams(self):
        for role in ('customer',None):
            for path in ('/ws/management/kitchen/',f'/ws/management/orders/{self.order.pk}/'):
                socket=self.socket(path,role); connected,code=await socket.connect()
                self.assertFalse(connected); self.assertEqual(code,4403); await socket.disconnect()

    async def test_bad_origin_rejected(self):
        socket=self.socket('/ws/management/kitchen/',origin='https://attacker.example')
        connected,_=await socket.connect(); self.assertFalse(connected); await socket.disconnect()

    async def test_missing_order_and_missing_permission_denied(self):
        socket=self.socket('/ws/management/orders/999999/')
        connected,code=await socket.connect(); self.assertFalse(connected); self.assertEqual(code,4403); await socket.disconnect()
        @database_sync_to_async
        def revoke():
            Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='view_order',content_type__app_label='customers'))
        await revoke()
        socket=self.socket(f'/ws/management/orders/{self.order.pk}/')
        connected,_=await socket.connect(); self.assertFalse(connected); await socket.disconnect()

    async def test_confirm_notifies_kitchen_and_order_only_after_commit(self):
        kitchen=await self.opened('/ws/management/kitchen/'); order=await self.opened(f'/ws/management/orders/{self.order.pk}/')
        @database_sync_to_async
        def confirm():
            with patch('customers.realtime.broadcast_order',wraps=__import__('customers.realtime',fromlist=['broadcast_order']).broadcast_order) as notify:
                with transaction.atomic():
                    transition_order(self.order.pk,'CONFIRMED',actor=self.staff)
                    self.assertEqual(notify.call_count,0)
                self.assertEqual(notify.call_count,1)
        await confirm()
        event=await order.receive_json_from(); self.assertEqual(event['status'],'CONFIRMED'); self.assertEqual(event['total_amount'],'987001.00')
        self.assertEqual((await kitchen.receive_json_from())['type'],'kitchen.queue_changed')
        await order.disconnect(); await kitchen.disconnect()

    async def test_rollback_no_notifications_or_state_changes(self):
        socket=await self.opened('/ws/management/kitchen/')
        @database_sync_to_async
        def rollback():
            try:
                with transaction.atomic():
                    transition_order(self.order.pk,'CONFIRMED',actor=self.staff)
                    raise ValidationError('rollback')
            except ValidationError: pass
            self.assertEqual(Order.objects.get(pk=self.order.pk).status,'PENDING')
            self.assertEqual(self.order.items.filter(kitchen_status='DRAFT').count(),2)
        await rollback(); self.assertTrue(await socket.receive_nothing(timeout=.15)); await socket.disconnect()

    async def test_two_clients_same_group_receive_change_other_order_does_not(self):
        first=await self.opened(f'/ws/management/orders/{self.order.pk}/'); second=await self.opened(f'/ws/management/orders/{self.order.pk}/','manager')
        other_id=await database_sync_to_async(lambda:Order.objects.create(created_by=self.admin).pk)()
        other=await self.opened(f'/ws/management/orders/{other_id}/')
        await database_sync_to_async(transition_order)(self.order.pk,'CONFIRMED',actor=self.staff)
        self.assertEqual(await first.receive_json_from(),await second.receive_json_from())
        self.assertTrue(await other.receive_nothing(timeout=.1))
        await first.disconnect(); await second.disconnect(); await other.disconnect()

    async def test_kitchen_start_ready_cancel_events_and_official_totals(self):
        await database_sync_to_async(transition_order)(self.order.pk,'CONFIRMED',actor=self.staff)
        socket=await self.opened(f'/ws/management/orders/{self.order.pk}/')
        item_id=await database_sync_to_async(lambda:self.order.items.get(menu_item=self.menu).pk)()
        for status in ('PREPARING','READY'):
            await database_sync_to_async(transition_kitchen_item)(self.order.pk,item_id,status,actor=self.staff)
            # Starting the first dish also transitions the Order, emitting two
            # committed invalidations. Consume both before the next operation.
            events=[await socket.receive_json_from() for _ in range(2 if status=='PREPARING' else 1)]
            self.assertTrue(any(event.get('kitchen_status')==status for event in events))
            self.assertTrue(all(event['status']=='PREPARING' for event in events))
        second_id=await database_sync_to_async(lambda:self.order.items.get(menu_item=self.second).pk)()
        await database_sync_to_async(transition_kitchen_item)(self.order.pk,second_id,'CANCELLED',actor=self.staff)
        event=await socket.receive_json_from(); self.assertEqual((event['kitchen_status'],event['total_amount']),('CANCELLED','698001.00'))
        await socket.disconnect()

    async def test_add_quantity_remove_send_events(self):
        await database_sync_to_async(transition_order)(self.order.pk,'CONFIRMED',actor=self.staff)
        order=await self.opened(f'/ws/management/orders/{self.order.pk}/'); kitchen=await self.opened('/ws/management/kitchen/')
        item=await database_sync_to_async(add_order_item)(self.order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        self.assertEqual((await order.receive_json_from())['kitchen_status'],'DRAFT'); await kitchen.receive_json_from()
        await database_sync_to_async(update_order_item)(self.order.pk,item.pk,actor=self.staff,quantity=2)
        self.assertEqual((await order.receive_json_from())['total_amount'],'1685002.00'); await kitchen.receive_json_from()
        await database_sync_to_async(send_order_to_kitchen)(self.order.pk,actor=self.staff)
        self.assertEqual((await order.receive_json_from())['type'],'order.updated'); await kitchen.receive_json_from()
        draft=await database_sync_to_async(add_order_item)(self.order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        await order.receive_json_from(); await kitchen.receive_json_from()
        await database_sync_to_async(remove_order_item)(self.order.pk,draft.pk,actor=self.staff)
        event=await order.receive_json_from(); self.assertEqual(event['item_id'],draft.pk); self.assertIsNone(event['kitchen_status'])
        await kitchen.receive_json_from(); await order.disconnect(); await kitchen.disconnect()

    async def test_socket_commands_cannot_mutate(self):
        socket=await self.opened(f'/ws/management/orders/{self.order.pk}/')
        await socket.send_json_to({'type':'order.updated','status':'COMPLETED','order_id':self.order.pk})
        self.assertEqual((await socket.receive_output())['code'],4400)
        self.assertEqual(await database_sync_to_async(lambda:Order.objects.get(pk=self.order.pk).status)(),'PENDING')
        await socket.disconnect()

    async def test_permission_revocation_closes_connected_socket_before_data(self):
        socket=await self.opened(f'/ws/management/orders/{self.order.pk}/')
        @database_sync_to_async
        def revoke(): Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='view_orderitem',content_type__app_label='customers'))
        await revoke()
        await get_channel_layer().group_send(order_group(self.order.pk),{'type':'realtime.changed','payload':{'type':'order.updated','total_amount':'secret'}})
        output=await socket.receive_output(); self.assertEqual((output['type'],output['code']),('websocket.close',4403))
        await socket.disconnect()

    async def test_logout_revokes_socket_and_disconnect_does_not_break_http(self):
        socket=await self.opened('/ws/management/kitchen/')
        await database_sync_to_async(self.clients['staff'].logout)()
        await get_channel_layer().group_send(KITCHEN_GROUP,{'type':'realtime.changed','payload':{'type':'kitchen.queue_changed'}})
        self.assertEqual((await socket.receive_output())['code'],4403); await socket.disconnect()
        await database_sync_to_async(transition_order)(self.order.pk,'CONFIRMED',actor=self.manager)
        self.assertEqual(await database_sync_to_async(lambda:Order.objects.get(pk=self.order.pk).status)(),'CONFIRMED')

    def test_transport_failure_does_not_undo_commit(self):
        with patch('customers.realtime.broadcast_order',side_effect=RuntimeError('transport down')),self.assertLogs('django.db.backends.base',level='ERROR'):
            transition_order(self.order.pk,'CONFIRMED',actor=self.staff)
        self.assertEqual(Order.objects.get(pk=self.order.pk).status,'CONFIRMED')

    def test_partial_html_permission_cache_and_scripts(self):
        for path in ('/management/kitchen/',f'/management/orders/{self.order.pk}/'):
            response=self.clients['staff'].get(path,headers={'X-Realtime-Partial':'1'})
            self.assertEqual(response.status_code,200); self.assertNotContains(response,'<html'); self.assertEqual(response['Cache-Control'],'no-store')
            self.assertEqual(self.clients['customer'].get(path,headers={'X-Realtime-Partial':'1'}).status_code,403)
            self.assertContains(self.clients['staff'].get(path),'data-realtime-socket')
