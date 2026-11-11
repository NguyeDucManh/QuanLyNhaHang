"""Read-only availability shared by customer preview and allocation errors.

No customer identity is included. Preview never holds a table.
"""
from django.db.models import Q
from django.utils import timezone
from .models import RestaurantTable, Booking, Order


def effective_bookings(start, end, *, now=None):
    now = now or timezone.now()
    return Booking.objects.filter(start_time__lt=end, end_time__gt=start).filter(
        Q(status__in=['PENDING', 'CONFIRMED']) |
        Q(status='PENDING_DEPOSIT', deposit__expires_at__gt=now,
          deposit__status__in=['PENDING', 'FAILED']))


def blocking_orders(start, end, *, now=None):
    now = now or timezone.now()
    # A booked order can be prepared in advance. Only its interval blocks until
    # overdue; an overdue still-open order must be released before another arrival.
    from .table_session_service import enabled
    predicate=Q(status__in=['PENDING','CONFIRMED','PREPARING']) & (
        Q(booking__isnull=True) |
        Q(booking__start_time__lt=end, booking__end_time__gt=start) |
        Q(booking__end_time__lte=now))
    if enabled():predicate |= Q(table_session__ended_at__isnull=True,table_session__isnull=False)
    rows=Order.objects.filter(predicate)
    if enabled():rows=rows.exclude(table_session__ended_at__isnull=False)
    return rows


def conflict_message(table, booking):
    start, end = timezone.localtime(booking.start_time), timezone.localtime(booking.end_time)
    return (f'Bàn {table.code} đã được đặt từ {start:%H:%M} đến {end:%H:%M} '
            f'ngày {start:%d/%m/%Y}. Vui lòng chọn bàn khác hoặc thời gian khác.')


def table_snapshot(start, end, guests, area_id=None):
    now = timezone.now()
    bookings = {}
    for booking in effective_bookings(start, end, now=now).order_by('start_time', 'pk'):
        bookings.setdefault(booking.table_id, booking)
    occupied = set(blocking_orders(start, end, now=now).values_list('table_id', flat=True))
    from .table_session_service import enabled
    if enabled():
        from .models import TableSession
        occupied.update(TableSession.objects.filter(ended_at__isnull=True).values_list('table_id',flat=True))
    rows = []
    for table in RestaurantTable.objects.select_related('area').order_by('area__name', 'code'):
        conflict = bookings.get(table.pk)
        if not table.is_active or not table.area.is_active:
            state, reason = 'INACTIVE', 'Bàn hoặc khu vực ngừng hoạt động.'
        elif table.status == 'MAINTENANCE':
            state, reason = 'MAINTENANCE', 'Bàn đang bảo trì.'
        elif table.pk in occupied or (table.status == 'OCCUPIED' and start <= now < end):
            state, reason = 'OCCUPIED', 'Bàn chưa được giải phóng khỏi lượt phục vụ hiện tại.'
        elif conflict:
            state, reason = 'RESERVED', conflict_message(table, conflict)
        elif table.capacity < guests:
            state, reason = 'TOO_SMALL', 'Bàn không đủ sức chứa.'
        elif area_id and table.area_id != area_id:
            state, reason = 'OTHER_AREA', 'Bàn thuộc khu vực khác đã chọn.'
        else:
            state, reason = 'AVAILABLE', 'Có thể đặt trong khoảng đã chọn.'
        rows.append({'id': table.pk, 'code': table.code, 'area': table.area.name,
                     'area_id': table.area_id, 'capacity': table.capacity,
                     'state': state, 'available': state == 'AVAILABLE', 'reason': reason,
                     'start': start.isoformat(), 'end': end.isoformat()})
    return rows
