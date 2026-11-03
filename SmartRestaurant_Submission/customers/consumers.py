from types import SimpleNamespace
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user
from django.contrib.sessions.backends.db import SessionStore
from .models import Order, Invoice
from .rbac import has_capability
from .realtime import KITCHEN_GROUP, order_group, PAYMENTS_GROUP, invoice_group


class ManagementUpdatesConsumer(AsyncJsonWebsocketConsumer):
    @database_sync_to_async
    def authorized(self):
        # Reload session and User on every event: logout, lock and role/permission
        # changes revoke an already-connected socket before sending more data.
        key=self.scope.get('session').session_key if self.scope.get('session') is not None else None
        if not key:
            return False
        user=get_user(SimpleNamespace(session=SessionStore(session_key=key)))
        if not has_capability(user,'customers.view_order') or not has_capability(user,'customers.view_orderitem'):
            return False
        return self.stream=='kitchen' or Order.objects.filter(pk=self.order_id).exists()

    async def connect(self):
        self.stream=self.scope['url_route']['kwargs']['stream']
        self.order_id=self.scope['url_route']['kwargs'].get('order_id')
        self.group=KITCHEN_GROUP if self.stream=='kitchen' else order_group(self.order_id)
        if not await self.authorized():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group,self.channel_name)
        if not await self.authorized():
            await self.channel_layer.group_discard(self.group,self.channel_name)
            await self.close(code=4403)
            return
        await self.accept()

    async def disconnect(self,code):
        if hasattr(self,'group'):
            await self.channel_layer.group_discard(self.group,self.channel_name)

    async def receive(self,text_data=None,bytes_data=None):
        # No client command, subscription change, mutation or arbitrary group selection.
        await self.close(code=4400)

    async def realtime_changed(self,event):
        if not await self.authorized():
            await self.close(code=4403)
            return
        await self.send_json(event['payload'])


class FinancialUpdatesConsumer(ManagementUpdatesConsumer):
    @database_sync_to_async
    def authorized(self):
        key=self.scope.get('session').session_key if self.scope.get('session') is not None else None
        if not key:
            return False
        user=get_user(SimpleNamespace(session=SessionStore(session_key=key)))
        if self.stream=='customer_invoice':
            return user.is_authenticated and user.is_active and Invoice.objects.filter(pk=self.invoice_id,order__customer=user).exists()
        if not has_capability(user,'customers.view_invoice') or not has_capability(user,'customers.view_payment'):
            return False
        return self.stream=='payments' or Invoice.objects.filter(pk=self.invoice_id).exists()

    async def connect(self):
        self.stream=self.scope['url_route']['kwargs']['stream']
        self.invoice_id=self.scope['url_route']['kwargs'].get('invoice_id')
        self.group=PAYMENTS_GROUP if self.stream=='payments' else invoice_group(self.invoice_id)
        if not await self.authorized():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group,self.channel_name)
        if not await self.authorized():
            await self.channel_layer.group_discard(self.group,self.channel_name)
            await self.close(code=4403)
            return
        await self.accept()


class ChatUpdatesConsumer(ManagementUpdatesConsumer):
    @database_sync_to_async
    def authorized(self):
        from .models import Conversation
        from .chat_service import chat_allowed
        key=self.scope.get('session').session_key if self.scope.get('session') is not None else None
        if not key: return False
        user=get_user(SimpleNamespace(session=SessionStore(session_key=key)))
        obj=Conversation.objects.filter(pk=self.conversation_id).first()
        return bool(obj and chat_allowed(user,obj))

    async def connect(self):
        self.conversation_id=self.scope['url_route']['kwargs']['conversation_id']
        self.group=f'chat.{self.conversation_id}'
        if not await self.authorized():
            await self.close(code=4403); return
        await self.channel_layer.group_add(self.group,self.channel_name)
        if not await self.authorized():
            await self.channel_layer.group_discard(self.group,self.channel_name)
            await self.close(code=4403); return
        await self.accept()
