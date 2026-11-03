"""Read-only invalidation events; schedule only from successful service transactions."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from .models import Order, OrderItem, Invoice

KITCHEN_GROUP = 'management.kitchen'
PAYMENTS_GROUP = 'management.payments'


def invoice_group(invoice_id):
    return f'financial.invoice.{int(invoice_id)}'


def broadcast_invoice(invoice_id, payment_id=None):
    invoice=Invoice.objects.filter(pk=invoice_id).values('status','total_amount').first()
    if not invoice:
        return
    payload={'type':'invoice.updated','invoice_id':invoice_id,'payment_id':payment_id,
             'status':invoice['status'],'total_amount':str(invoice['total_amount'])}
    layer=get_channel_layer()
    async_to_sync(layer.group_send)(invoice_group(invoice_id),{'type':'realtime.changed','payload':payload})
    async_to_sync(layer.group_send)(PAYMENTS_GROUP,{'type':'realtime.changed','payload':{'type':'payment.updated','invoice_id':invoice_id,'payment_id':payment_id}})


def notify_invoice_changed(invoice_id, payment_id=None):
    transaction.on_commit(lambda:broadcast_invoice(invoice_id,payment_id),robust=True)


def order_group(order_id):
    return f'management.order.{int(order_id)}'


def broadcast_order(order_id, item_id=None):
    order=Order.objects.filter(pk=order_id).values('status','subtotal','discount_amount','total_amount').first()
    if not order:
        return
    payload={'type':'order.updated','order_id':order_id,'status':order['status'],
        'subtotal':str(order['subtotal']),'discount_amount':str(order['discount_amount']),'total_amount':str(order['total_amount'])}
    if item_id is not None:
        payload['item_id']=item_id
        payload['kitchen_status']=OrderItem.objects.filter(pk=item_id,order_id=order_id).values_list('kitchen_status',flat=True).first()
    layer=get_channel_layer()
    async_to_sync(layer.group_send)(order_group(order_id),{'type':'realtime.changed','payload':payload})
    async_to_sync(layer.group_send)(KITCHEN_GROUP,{'type':'realtime.changed','payload':{'type':'kitchen.queue_changed','order_id':order_id}})


def notify_order_changed(order_id, item_id=None):
    # robust=True: a transport outage must not turn a committed HTTP operation into an error.
    transaction.on_commit(lambda:broadcast_order(order_id,item_id),robust=True)
