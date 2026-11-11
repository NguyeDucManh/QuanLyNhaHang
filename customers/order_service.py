from .audit_service import with_actor
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from .models import Order, OrderItem, MenuItem, RestaurantTable, Booking
from .business_service import decimal_value, lock_request, existing_request, save_validated
from .rbac import has_capability
from django.core.exceptions import PermissionDenied
from .realtime import notify_order_changed


def require_actor(actor, permission):
    if not has_capability(actor, 'customers.' + permission):
        raise PermissionDenied('Bạn chưa được cấp quyền thao tác đơn hàng.')

TRANSITIONS={
    Order.Status.PENDING:(Order.Status.CONFIRMED,Order.Status.CANCELLED),
    Order.Status.CONFIRMED:(Order.Status.PREPARING,Order.Status.CANCELLED),
    Order.Status.PREPARING:(Order.Status.COMPLETED,),
    Order.Status.COMPLETED:(),Order.Status.CANCELLED:(),
}
TRANSITION_LABELS = {'CONFIRMED':'Xác nhận đơn','PREPARING':'Chuyển sang chuẩn bị','COMPLETED':'Hoàn thành','CANCELLED':'Hủy đơn'}
ACTIVE_ORDER_STATUSES = (Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING)


@with_actor
@transaction.atomic
def create_order(*, actor, items, request_key, customer=None, table=None, order_type=Order.Type.TAKEAWAY, discount_amount=0, note=''):
    require_actor(actor, 'add_order')
    require_actor(actor, 'add_orderitem')
    key=lock_request('order',request_key)
    existing=existing_request(Order,key,actor)
    if existing:
        return existing
    if not items:
        raise ValidationError('Đơn phải có ít nhất một món.')
    if customer and not customer.is_active:
        raise ValidationError('Tài khoản khách hàng đã bị khóa.')
    if order_type not in Order.Type.values:
        raise ValidationError('Hình thức đặt món không hợp lệ.')
    if order_type==Order.Type.DINE_IN:
        table=RestaurantTable.objects.select_for_update(of=('self',)).select_related('area').filter(pk=getattr(table,'pk',None)).first()
        if not table or not table.is_active or not table.area.is_active or table.status==RestaurantTable.Status.MAINTENANCE:
            raise ValidationError('Bàn không phù hợp để tạo đơn.')
    elif table is not None:
        raise ValidationError('Đơn mang đi không gán bàn.')
    requested={}
    for item in items:
        pk=item['menu_item'].pk
        quantity=item['quantity']
        if isinstance(quantity,bool) or not isinstance(quantity,int) or not 1<=quantity<=1000:
            raise ValidationError('Số lượng món phải từ 1 đến 1000.')
        if pk in requested:
            raise ValidationError('Món bị trùng trong đơn; hãy gộp số lượng.')
        requested[pk]=item
    menus={m.pk:m for m in MenuItem.objects.select_for_update().select_related('category').filter(pk__in=requested).order_by('pk')}
    if len(menus)!=len(requested):
        raise ValidationError('Món không tồn tại.')
    from .models import Topping
    from .commerce_service import identifiers
    top_ids=set()
    for item in requested.values(): top_ids.update(identifiers([getattr(t,'pk',t) for t in item.get('toppings',[])]))
    list(Topping.objects.select_for_update().filter(pk__in=top_ids).order_by('pk'))
    subtotal=Decimal('0')
    lines=[]
    for pk,item in requested.items():
        menu=menus[pk]
        if not menu.is_available or not menu.category.is_active or menu.price is None:
            raise ValidationError(f'{menu.name}: món ngừng phục vụ hoặc chưa có giá. Hãy cập nhật giá trước khi tạo đơn.')
        from .commerce_service import topping_snapshot
        tops=topping_snapshot(menu,[getattr(t,'pk',t) for t in item.get('toppings',[])])
        price=decimal_value(menu.price,2)+sum((Decimal(t['price']) for t in tops),Decimal(0))
        line_total=price*item['quantity']
        subtotal+=line_total
        lines.append(OrderItem(menu_item=menu,item_name=menu.name,quantity=item['quantity'],unit_price=price,line_total=line_total,note=item.get('note',''),extras={'toppings':tops} if tops else {}))
    discount=decimal_value(discount_amount,2)
    if discount>subtotal:
        raise ValidationError('Giảm giá không được vượt tổng tiền món.')
    order=save_validated(Order(created_by=actor,customer=customer,table=table,order_type=order_type,request_key=key,
        subtotal=subtotal,discount_amount=discount,total_amount=subtotal-discount,note=note))
    for line in lines:
        line.order=order
        save_validated(line)
    notify_order_changed(order.pk)
    return order


@with_actor
@transaction.atomic
def transition_order(order_id,new_status,*,actor):
    require_actor(actor, 'change_order')
    snapshot=Order.objects.get(pk=order_id)
    table=None;booking=None
    if snapshot.table_id:
        from .booking_service import lock_areas
        lock_areas()
        table=RestaurantTable.objects.select_for_update().get(pk=snapshot.table_id)
    if snapshot.booking_id:booking=Booking.objects.select_for_update().get(pk=snapshot.booking_id)
    order=Order.objects.select_for_update().get(pk=order_id)
    if order.table_id!=snapshot.table_id or order.booking_id!=snapshot.booking_id:
        raise ValidationError('Đơn vừa thay đổi bàn/booking. Vui lòng tải lại trước khi chuyển trạng thái.')
    if new_status not in TRANSITIONS.get(order.status,()):
        raise ValidationError('Không được chuyển trạng thái đơn hàng như yêu cầu.')
    from .kitchen_service import queue_drafts, change_item_state
    if new_status == Order.Status.CONFIRMED:
        require_actor(actor, 'change_orderitem')
        queue_drafts(order)
    elif new_status == Order.Status.CANCELLED:
        require_actor(actor, 'change_orderitem')
        lines = list(order.items.select_for_update().order_by('pk'))
        if any(line.kitchen_status in (OrderItem.KitchenStatus.PREPARING, OrderItem.KitchenStatus.READY) for line in lines):
            raise ValidationError('Không thể hủy đơn có món đang chế biến hoặc đã làm xong.')
        for line in lines:
            if line.kitchen_status != OrderItem.KitchenStatus.CANCELLED:
                change_item_state(line, OrderItem.KitchenStatus.CANCELLED)
        order.discount_amount = Decimal('0')
        order.status = Order.Status.CANCELLED
        recalculate_totals(order)
    elif new_status == Order.Status.COMPLETED:
        active = list(order.items.exclude(kitchen_status=OrderItem.KitchenStatus.CANCELLED).select_for_update().order_by('pk'))
        if not active or any(line.kitchen_status != OrderItem.KitchenStatus.READY for line in active):
            raise ValidationError('Chỉ hoàn thành đơn có ít nhất một món và tất cả món chưa hủy đã làm xong.')
    order.status=new_status
    save_validated(order)
    if new_status==Order.Status.COMPLETED:
        if booking and booking.status==Booking.Status.CONFIRMED:
            booking.status=Booking.Status.COMPLETED;booking.save(update_fields=['status'])
        if table and table.status==RestaurantTable.Status.OCCUPIED and not Order.objects.filter(table=table,status__in=ACTIVE_ORDER_STATUSES).exists():
            table.status=RestaurantTable.Status.AVAILABLE;table.save(update_fields=['status'])
    notify_order_changed(order.pk)
    return order


@with_actor
@transaction.atomic
def open_order_from_booking(booking_id, *, actor):
    require_actor(actor, 'add_order')
    require_actor(actor, 'add_orderitem')
    # Same lock order as allocation/cancellation: Area -> Table -> Booking -> Order.
    from .booking_service import lock_areas
    areas = lock_areas()
    snapshot = Booking.objects.get(pk=booking_id)
    table = RestaurantTable.objects.select_for_update().get(pk=snapshot.table_id) if snapshot.table_id else None
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    existing = Order.objects.filter(booking=booking).first()
    from .table_assignment_service import staff_table_ids
    scoped=staff_table_ids(actor)
    if scoped is not None and booking.table_id not in scoped:
        raise PermissionDenied('Bạn chưa được giao bàn này trong ca hiện tại.')
    if scoped is not None:
        from django.utils import timezone
        if not booking.start_time-timezone.timedelta(hours=1)<=timezone.now()<booking.end_time:
            raise PermissionDenied('Booking chưa đến khung giờ phục vụ hoặc đã kết thúc.')
    if existing:
        return existing
    if booking.status != Booking.Status.CONFIRMED:
        raise ValidationError('Chỉ mở đơn cho Booking đã xác nhận.')
    if getattr(booking,'deposit',None) is not None and booking.deposit.status!='SUCCEEDED':
        raise ValidationError('Tiền cọc bắt buộc chưa được xác nhận.')
    if table is None or not table.is_active or not areas[table.area_id].is_active or table.status == RestaurantTable.Status.MAINTENANCE:
        raise ValidationError('Booking cần có bàn và khu vực đang phục vụ.')
    if table.capacity < booking.guests:
        raise ValidationError('Bàn không đủ sức chứa cho Booking.')
    if Order.objects.filter(table=table,status__in=ACTIVE_ORDER_STATUSES).filter(
            Q(booking__isnull=True)|Q(booking__start_time__lt=booking.end_time,booking__end_time__gt=booking.start_time)).exists():
        raise ValidationError('Bàn đang có đơn phục vụ chưa hoàn thành; không mở trùng bàn.')
    order = save_validated(Order(booking=booking, customer_id=booking.user_id, table=table,
                                order_type=Order.Type.DINE_IN, created_by=actor, note=booking.note))
    for item in booking.preorder_items.select_for_update().order_by('pk'):
        save_validated(OrderItem(order=order, menu_item_id=item.menu_item_id, item_name=item.item_name,
                                 source=OrderItem.Source.PREORDER, quantity=item.quantity,
                                 unit_price=item.unit_price, line_total=item.unit_price * item.quantity, extras=item.extras))
    recalculate_totals(order)
    if booking.promotion_code:
        from .commerce_service import apply_voucher
        apply_voucher(order.pk,booking.promotion_code,actor=actor)
        order.refresh_from_db()
    notify_order_changed(order.pk)
    return order


def recalculate_totals(order):
    """Caller owns the Order row lock and the enclosing transaction."""
    order.subtotal = sum(order.items.exclude(kitchen_status=OrderItem.KitchenStatus.CANCELLED).values_list('line_total', flat=True), Decimal('0'))
    if order.promotion_id and order.status!='CANCELLED':
        from .commerce_service import discount_for
        order.discount_amount=discount_for(order.promotion_snapshot,order.subtotal)
    if order.discount_amount > order.subtotal:
        raise ValidationError('Tạm tính mới thấp hơn giảm giá đã lưu; không thể sửa món.')
    order.total_amount = order.subtotal - order.discount_amount
    return save_validated(order)


def active_order(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status not in ACTIVE_ORDER_STATUSES:
        raise ValidationError('Đơn đã kết thúc; không thể thay đổi món.')
    return order


def validate_quantity(quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 1000:
        raise ValidationError('Số lượng món phải từ 1 đến 1000.')


@with_actor
@transaction.atomic
def add_order_item(order_id, *, actor, menu_item_id, quantity, note='', toppings=None):
    require_actor(actor, 'change_order')
    require_actor(actor, 'add_orderitem')
    order = active_order(order_id)
    validate_quantity(quantity)
    menu = MenuItem.objects.select_for_update().select_related('category').filter(pk=menu_item_id).first()
    if not menu or not menu.is_available or not menu.category.is_active or menu.price is None:
        raise ValidationError('Món không tồn tại, ngừng phục vụ hoặc chưa niêm yết giá.')
    # Separate lines preserve source, price and note, even for the same menu item.
    from .commerce_service import topping_snapshot
    tops=topping_snapshot(menu,[getattr(t,'pk',t) for t in (toppings or [])])
    price=menu.price+sum((Decimal(t['price']) for t in tops),Decimal(0))
    line = save_validated(OrderItem(order=order, menu_item=menu, item_name=menu.name,
                         quantity=quantity, unit_price=price, line_total=price * quantity, note=note,extras={'toppings':tops} if tops else {}))
    recalculate_totals(order)
    notify_order_changed(order.pk,line.pk)
    return line


@with_actor
@transaction.atomic
def update_order_item(order_id, item_id, *, actor, quantity):
    require_actor(actor, 'change_order')
    require_actor(actor, 'change_orderitem')
    order = active_order(order_id)
    validate_quantity(quantity)
    line = OrderItem.objects.select_for_update().filter(order=order, pk=item_id).first()
    if not line:
        raise ValidationError('Món không thuộc đơn hàng này.')
    if line.kitchen_status != OrderItem.KitchenStatus.DRAFT:
        raise ValidationError('Chỉ sửa món DRAFT chưa gửi bếp.')
    combo=line.extras.get('combo')
    if combo:
        group=list(order.items.select_for_update().filter(extras__combo__selection_id=combo['selection_id']).order_by('pk'))
        if quantity>20 or any(item.kitchen_status!='DRAFT' for item in group): raise ValidationError('Chỉ sửa toàn bộ combo chưa gửi bếp, tối đa 20 combo.')
        for item in group:
            item.quantity=quantity; item.line_total=item.unit_price*quantity; item.extras['combo']['quantity']=quantity; save_validated(item)
        recalculate_totals(order); notify_order_changed(order.pk); return OrderItem.objects.get(pk=line.pk)
    line.quantity = quantity
    line.line_total = line.unit_price * quantity
    save_validated(line)
    recalculate_totals(order)
    notify_order_changed(order.pk,line.pk)
    return line


@with_actor
@transaction.atomic
def remove_order_item(order_id, item_id, *, actor):
    require_actor(actor, 'change_order')
    require_actor(actor, 'change_orderitem')
    order = active_order(order_id)
    line = OrderItem.objects.select_for_update().filter(order=order, pk=item_id).first()
    if not line:
        raise ValidationError('Món không thuộc đơn hàng này.')
    if line.kitchen_status != OrderItem.KitchenStatus.DRAFT:
        raise ValidationError('Chỉ xóa món DRAFT; món đã gửi bếp phải giữ lịch sử.')
    combo=line.extras.get('combo')
    if combo:
        group=list(order.items.select_for_update().filter(extras__combo__selection_id=combo['selection_id']).order_by('pk'))
        if any(item.kitchen_status!='DRAFT' for item in group): raise ValidationError('Chỉ bỏ toàn bộ combo khi chưa gửi bếp.')
        for item in group: item.delete()
        recalculate_totals(order); notify_order_changed(order.pk); return order
    line.delete()
    recalculate_totals(order)
    notify_order_changed(order.pk,item_id)
    return order
