"""Kitchen transitions share Order -> OrderItem locks with every order mutation."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem
from .business_service import save_validated
from .order_service import require_actor, recalculate_totals, ACTIVE_ORDER_STATUSES
from .realtime import notify_order_changed

TRANSITIONS = {
    'DRAFT': ('QUEUED', 'CANCELLED'),
    'QUEUED': ('PREPARING', 'CANCELLED'),
    'PREPARING': ('READY',),
    'READY': (), 'CANCELLED': (),
}


def change_item_state(item, status, *, now=None):
    """Internal primitive: caller owns Order and item locks in an atomic transaction."""
    if status not in TRANSITIONS.get(item.kitchen_status, ()):
        raise ValidationError('Không được chuyển trạng thái bếp của món như yêu cầu.')
    now = now or timezone.now()
    if status == OrderItem.KitchenStatus.QUEUED:
        item.queued_at = now
    elif status == OrderItem.KitchenStatus.PREPARING:
        item.preparing_at = now
    elif status == OrderItem.KitchenStatus.READY:
        item.ready_at = now
    item.kitchen_status = status
    return save_validated(item)


def queue_drafts(order):
    """Called inside confirmation/send transactions; retries do not overwrite timestamps."""
    now = timezone.now()
    lines = list(order.items.select_for_update().filter(kitchen_status='DRAFT').order_by('pk'))
    for line in lines:
        change_item_state(line, OrderItem.KitchenStatus.QUEUED, now=now)
    return len(lines)


@transaction.atomic
def send_order_to_kitchen(order_id, *, actor):
    require_actor(actor, 'change_order')
    require_actor(actor, 'change_orderitem')
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status not in (Order.Status.CONFIRMED, Order.Status.PREPARING):
        raise ValidationError('Xác nhận đơn trước khi gửi món mới vào bếp; đơn kết thúc không thể gửi.')
    count=queue_drafts(order)
    if count:
        notify_order_changed(order.pk)
    return count


@transaction.atomic
def transition_kitchen_item(order_id, item_id, status, *, actor):
    require_actor(actor, 'change_order')
    require_actor(actor, 'change_orderitem')
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status not in ACTIVE_ORDER_STATUSES:
        raise ValidationError('Đơn đã kết thúc; không thể thao tác bếp.')
    item = OrderItem.objects.select_for_update().filter(pk=item_id, order=order).first()
    if not item:
        raise ValidationError('Món không thuộc đơn hàng này.')
    if status in ('QUEUED','PREPARING','READY') and order.status == Order.Status.PENDING:
        raise ValidationError('Cần xác nhận đơn trước khi gửi hoặc chế biến món.')
    now=timezone.now()
    if status==OrderItem.KitchenStatus.READY:
        if item.kitchen_status!=OrderItem.KitchenStatus.PREPARING:
            raise ValidationError('Chỉ món đang chế biến mới được làm xong.')
        from .inventory_service import consume_order_item
        consume_order_item(item,actor,now=now)
    change_item_state(item, status, now=now)
    if status == OrderItem.KitchenStatus.PREPARING and order.status == Order.Status.CONFIRMED:
        from .order_service import transition_order
        transition_order(order.pk, Order.Status.PREPARING, actor=actor)
    if status == OrderItem.KitchenStatus.CANCELLED:
        recalculate_totals(order)
    notify_order_changed(order.pk,item.pk)
    return item
