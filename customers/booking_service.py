"""Booking intervals and table mutations share PostgreSQL row locks.

Lock order: Area rows (pk), table rows, then Booking rows. Area locks serialize
allocation/configuration within this restaurant; no external locks or fake tables.
"""
from .audit_service import with_actor
from datetime import datetime, timedelta
import re
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Area, RestaurantTable, Booking, BookingItem, MenuItem
from .menu_service import validated_cart_quantities
from decimal import Decimal

BLOCKING_STATUSES = (Booking.Status.PENDING, Booking.Status.CONFIRMED,Booking.Status.PENDING_DEPOSIT)
TRANSITIONS = {
    Booking.Status.PENDING_DEPOSIT:(Booking.Status.CANCELLED,),
    Booking.Status.PENDING: (Booking.Status.CONFIRMED, Booking.Status.CANCELLED),
    Booking.Status.CONFIRMED: (Booking.Status.COMPLETED, Booking.Status.CANCELLED),
    Booking.Status.CANCELLED: (), Booking.Status.COMPLETED: (),
}
NO_TABLE_MESSAGE = 'Không còn bàn phù hợp trong khung giờ đã chọn.'


def booking_window(date, time, *, require_future=True):
    start = timezone.make_aware(datetime.combine(date, time), timezone.get_default_timezone())
    duration = settings.DEFAULT_BOOKING_DURATION_MINUTES
    if not isinstance(duration, int) or duration <= 0:
        raise ValidationError('Thời lượng đặt bàn phải lớn hơn 0.')
    end = start + timedelta(minutes=duration)
    if require_future and start <= timezone.now():
        raise ValidationError('Vui lòng chọn thời gian đặt bàn trong tương lai.')
    return start, end


def validate_window(start, end):
    if not start or not end or timezone.is_naive(start) or timezone.is_naive(end) or end <= start:
        raise ValidationError('Khoảng thời gian đặt bàn không hợp lệ.')


def overlaps(table_id, start, end, exclude_booking=None):
    validate_window(start, end)
    bookings = Booking.objects.filter(table_id=table_id,start_time__lt=end,end_time__gt=start).filter(
        Q(status__in=['PENDING','CONFIRMED'])|Q(status='PENDING_DEPOSIT',deposit__expires_at__gt=timezone.now(),deposit__status__in=['PENDING','FAILED']))
    if exclude_booking:
        bookings = bookings.exclude(pk=exclude_booking)
    return bookings.exists()


def lock_areas():
    # Allocation and every Area/Table editor take these same locks before tables.
    return {area.pk: area for area in Area.objects.select_for_update().order_by('pk')}


def table_eligible(table, area, guests):
    return area.is_active and table.is_active and table.status != RestaurantTable.Status.MAINTENANCE and table.capacity >= guests


def find_available_table(start, end, guests, areas, *, exclude_booking=None, area_id=None):
    # OCCUPIED describes now, not future reservation availability.
    candidates = RestaurantTable.objects.filter(is_active=True, capacity__gte=guests).exclude(
        status=RestaurantTable.Status.MAINTENANCE).order_by('capacity', 'pk')
    if area_id is not None:candidates=candidates.filter(area_id=area_id)
    for table in candidates.select_for_update():
        area = areas.get(table.area_id)
        if area and table_eligible(table, area, guests) and not overlaps(table.pk, start, end, exclude_booking):
            return table
    raise ValidationError(NO_TABLE_MESSAGE)


@with_actor
@transaction.atomic
def create_booking(*, user, name, phone, date, time, guests, note='', food_cart=None, topping_cart=None, combo_cart=None, promotion_code='', online=False, area=None, preferred_area=None):
    if not user.is_authenticated or not user.is_active:
        raise ValidationError('Vui lòng đăng nhập tài khoản đang hoạt động.')
    if isinstance(guests, bool) or not isinstance(guests, int) or not 1 <= guests <= 20:
        raise ValidationError('Vui lòng chọn từ 1 đến 20 khách.')
    if not re.fullmatch(r'\+?[0-9\s().-]{9,20}', phone.strip()):
        raise ValidationError('Vui lòng nhập số điện thoại hợp lệ.')
    start, end = booking_window(date, time)
    areas = lock_areas()
    # Recheck clock after waiting for another request's lock.
    if start <= timezone.now():
        raise ValidationError('Vui lòng chọn thời gian đặt bàn trong tương lai.')
    area=preferred_area if preferred_area is not None else area
    area_id=getattr(area,'pk',None)
    if area is not None and (area_id not in areas or not areas[area_id].is_active):
        raise ValidationError('Khu vực không còn phục vụ.')
    table = find_available_table(start, end, guests, areas, area_id=area_id)
    needs_deposit=online and settings.BOOKING_DEPOSIT_REQUIRED
    booking = Booking(user=user, name=name, phone=phone.strip(), date=date, time=time, guests=guests,
                      note=note, table=table, status='PENDING_DEPOSIT' if needs_deposit else Booking.Status.CONFIRMED, start_time=start, end_time=end)
    booking.full_clean()
    booking.save()
    quantities = validated_cart_quantities({} if food_cart is None else food_cart)
    menus = {item.pk: item for item in MenuItem.objects.select_for_update(of=('self',)).select_related('category').filter(pk__in=quantities).order_by('pk')}
    if len(menus) != len(quantities):
        raise ValidationError('Có món không còn tồn tại. Vui lòng kiểm tra giỏ món.')
    subtotal = Decimal('0')
    for pk, quantity in quantities.items():
        item = menus[pk]
        if not item.is_available or not item.category.is_active:
            raise ValidationError(f'{item.name} đang ngừng phục vụ; vui lòng bỏ món khỏi giỏ.')
        if item.price is None:
            raise ValidationError(f'{item.name} chưa niêm yết giá; vui lòng bỏ món hoặc liên hệ nhà hàng trước khi đặt món.')
        line = BookingItem(booking=booking, menu_item=item, item_name=item.name, quantity=quantity,
                           unit_price=item.price, line_total=item.price * quantity)
        line.full_clean()
        line.save()
        subtotal += line.line_total
    booking.food_subtotal = subtotal
    booking.full_clean()
    booking.save(update_fields=['food_subtotal'])
    if topping_cart or combo_cart:
        from .commerce_service import snapshot_booking_extras
        snapshot_booking_extras(booking,topping_cart or {},combo_cart or {})
    if promotion_code:
        booking.promotion_code=promotion_code.strip().upper()[:40]
        booking.save(update_fields=['promotion_code'])
    if needs_deposit:
        from .deposit_service import create_deposit
        create_deposit(booking)
    return booking


@with_actor
@transaction.atomic
def transition_booking(booking_id, new_status, *, owner=None):
    areas = lock_areas()
    snapshot = Booking.objects.get(pk=booking_id)
    table = RestaurantTable.objects.select_for_update().get(pk=snapshot.table_id) if snapshot.table_id else None
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if owner is not None:
        if not owner.is_authenticated or not owner.is_active or booking.user_id != owner.pk or new_status != Booking.Status.CANCELLED:
            raise PermissionDenied('Bạn chỉ được hủy đặt bàn của mình.')
        if booking.status == Booking.Status.CANCELLED:
            return booking  # A repeated cancellation does not alter the table or history.
    if new_status not in TRANSITIONS.get(booking.status, ()):
        raise ValidationError('Không được chuyển trạng thái Booking như yêu cầu.')
    if new_status == Booking.Status.CANCELLED:
        from .models import Order
        service_order = Order.objects.select_for_update().filter(booking=booking).first()
        if service_order and (owner is not None or service_order.status != Order.Status.CANCELLED):
            raise ValidationError('Booking đã mở đơn hàng; không thể tự hủy. Vui lòng liên hệ nhà hàng.')
    if new_status == Booking.Status.CONFIRMED:
        if getattr(booking,'deposit',None) is not None and booking.deposit.status!='SUCCEEDED':
            raise ValidationError('Chưa thể xác nhận booking khi tiền cọc bắt buộc chưa thành công.')
        if booking.start_time is None or booking.end_time is None:
            booking.start_time, booking.end_time = booking_window(booking.date, booking.time)
        validate_window(booking.start_time, booking.end_time)
        if table is None:  # Legacy request: assign safely when administrator confirms it.
            if booking.start_time <= timezone.now():
                raise ValidationError('Yêu cầu cũ đã qua thời gian bắt đầu; hãy hủy yêu cầu.')
            table = find_available_table(booking.start_time, booking.end_time, booking.guests, areas, exclude_booking=booking.pk)
            booking.table = table
        if not table_eligible(table, areas[table.area_id], booking.guests):
            raise ValidationError('Bàn hoặc khu vực không phù hợp để xác nhận Booking.')
        if overlaps(table.pk, booking.start_time, booking.end_time, booking.pk):
            raise ValidationError('Bàn đã có Booking giao nhau trong khung giờ này.')
    booking.status = new_status
    booking.full_clean()
    booking.save(update_fields=['status', 'table', 'start_time', 'end_time'])
    if new_status=='CANCELLED':
        from .models import BookingDeposit
        deposit=BookingDeposit.objects.select_for_update().filter(booking=booking,status__in=['PENDING','FAILED']).first()
        if deposit:
            deposit.status='CANCELLED';deposit.save(update_fields=['status','updated_at'])
            from .audit_service import record
            record(action='DEPOSIT_CANCELLED',entity=deposit,actor=owner,after={'booking_id':booking.pk})
    if new_status in ('COMPLETED','CANCELLED') and table:
        from .models import BookingVisit, Order
        if BookingVisit.objects.filter(booking=booking,state='CHECKED_IN').exists():
            other_visits=BookingVisit.objects.filter(booking__table=table,booking__status='CONFIRMED',booking__end_time__gt=timezone.now(),state='CHECKED_IN').exclude(booking=booking).exists()
            if not other_visits and not Order.objects.filter(table=table,status__in=['PENDING','CONFIRMED','PREPARING']).exists() and table.status=='OCCUPIED':
                table.status='AVAILABLE';table.save(update_fields=['status','updated_at'])
            from .booking_advanced_service import notify_floor_changed
            notify_floor_changed()
    return booking


@with_actor
@transaction.atomic
def save_area(form):
    lock_areas()
    if form.instance.pk:
        Area.objects.select_for_update().get(pk=form.instance.pk)
    return form.save()


@with_actor
@transaction.atomic
def save_table(form):
    lock_areas()
    if form.instance.pk:
        RestaurantTable.objects.select_for_update().get(pk=form.instance.pk)
        # Future bookings cannot become impossible due to reduced capacity/reassigned area.
        future = Booking.objects.filter(table_id=form.instance.pk, status__in=BLOCKING_STATUSES, end_time__gt=timezone.now())
        if future.filter(guests__gt=form.cleaned_data['capacity']).exists():
            raise ValidationError('Sức chứa mới không đủ cho Booking đang giữ chỗ.')
    return form.save()
