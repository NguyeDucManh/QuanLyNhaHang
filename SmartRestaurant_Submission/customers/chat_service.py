"""Human chat: HTTP POST persists; socket only invalidates DB history."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Conversation, ConversationParticipant, Message
from .rbac import get_role
from .business_service import lock_request, save_validated

def chat_allowed(user, conversation):
    role=get_role(user)
    if role is None: return False
    if role=='CUSTOMER' and not conversation.is_support: return False
    return conversation.participants.filter(pk=user.pk).exists()

@transaction.atomic
def create_conversation(*,actor,recipient_id):
    if get_role(actor) is None: raise PermissionDenied
    users={u.pk:u for u in get_user_model().objects.select_for_update().filter(pk__in=[actor.pk,recipient_id],is_active=True).order_by('pk')}
    if actor.pk not in users or recipient_id not in users: raise ValidationError('Tài khoản không hoạt động.')
    other=users[recipient_id]
    role=get_role(other)
    if other.pk==actor.pk or role is None: raise ValidationError('Người nhận không phù hợp.')
    support=get_role(actor)=='CUSTOMER' or role=='CUSTOMER'
    if support and (get_role(actor) not in ('ADMIN','MANAGER','STAFF') and role not in ('ADMIN','MANAGER','STAFF')): raise PermissionDenied
    # Actor row serializes repeated creations for the same pair.
    existing=Conversation.objects.filter(participants=actor,is_support=support).filter(participants=other).first()
    if existing: return existing
    obj=Conversation.objects.create(created_by=actor,is_support=support)
    ConversationParticipant.objects.bulk_create([ConversationParticipant(conversation=obj,user=u) for u in (actor,other)])
    return obj

def broadcast(conversation_id):
    async_to_sync(get_channel_layer().group_send)(f'chat.{conversation_id}',{'type':'realtime.changed','payload':{'type':'chat.updated','conversation_id':conversation_id}})

@transaction.atomic
def send_message(*,actor,conversation_id,content,request_key):
    obj=Conversation.objects.select_for_update().get(pk=conversation_id)
    if not chat_allowed(actor,obj): raise PermissionDenied
    key=lock_request('chat',request_key)
    prior=Message.objects.filter(request_key=key).first()
    if prior:
        if prior.sender_id!=actor.pk or prior.conversation_id!=obj.pk: raise PermissionDenied
        return prior
    text=content.strip()
    if not text or len(text)>2000: raise ValidationError('Tin nhắn cần 1–2000 ký tự.')
    message=save_validated(Message(conversation=obj,sender=actor,content=text,request_key=key))
    ConversationParticipant.objects.filter(conversation=obj,user=actor).update(last_read_at=timezone.now())
    transaction.on_commit(lambda:broadcast(obj.pk),robust=True)
    return message
