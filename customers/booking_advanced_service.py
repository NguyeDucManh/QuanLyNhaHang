"""Arrival and transfer reuse booking allocation locks, existing order identity and events."""
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import Booking, BookingVisit, BookingWaitlist, RestaurantTable, Order
from .booking_service import lock_areas, booking_window, find_available_table, create_booking, overlaps, table_eligible, NO_TABLE_MESSAGE
from .order_service import ACTIVE_ORDER_STATUSES
from .business_service import lock_request, save_validated
from .rbac import has_capability
from .audit_service import audit_actor, record
from .realtime import notify_order_changed


def require(actor, permission):
    if not has_capability(actor,'customers.'+permission): raise PermissionDenied('Bạn chưa có quyền thực hiện thao tác này.')


@transaction.atomic
def join_waitlist(*, customer, name, phone, date, time, guests, consent, request_key, note=''):
    import re
    if not customer.is_authenticated or not customer.is_active: raise PermissionDenied
    if consent is not True: raise ValidationError('Cần đồng ý tham gia danh sách chờ.')
    if isinstance(guests,bool) or not isinstance(guests,int) or not 1<=guests<=20: raise ValidationError('Số khách phải từ 1 đến 20.')
    if not re.fullmatch(r'\+?[0-9\s().-]{9,20}',phone.strip()): raise ValidationError('Số điện thoại không hợp lệ.')
    key = lock_request('waitlist',request_key)
    old = BookingWaitlist.objects.filter(request_key=key).first()
    if old:
        if old.customer_id != customer.pk: raise PermissionDenied
        return old
    start,end = booking_window(date,time)
    areas = lock_areas()
    try: find_available_table(start,end,guests,areas)
    except ValidationError as error:
        if error.messages != [NO_TABLE_MESSAGE]: raise
    else: raise ValidationError('Vẫn còn bàn phù hợp; vui lòng dùng đặt bàn thông thường.')
    return save_validated(BookingWaitlist(customer=customer,name=name,phone=phone.strip(),requested_date=date,requested_time=time,guests=guests,note=note,request_key=key))


@transaction.atomic
def convert_waitlist(pk, *, actor):
    require(actor,'convert_bookingwaitlist')
    lock_areas()
    row = BookingWaitlist.objects.select_for_update().select_related('customer').get(pk=pk)
    if row.status == 'CONVERTED': return row.booking
    if row.status not in ('WAITING','OFFERED'): raise ValidationError('Yêu cầu không còn chờ bàn.')
    with audit_actor(actor):
        booking = create_booking(user=row.customer,name=row.name,phone=row.phone,date=row.requested_date,time=row.requested_time,guests=row.guests,note=row.note,online=True)
        row.status='CONVERTED'; row.booking=booking; row.promoted_at=timezone.now()
        save_validated(row)
    notify_floor_changed()
    return booking


@transaction.atomic
def cancel_waitlist(pk, *, actor):
    row = BookingWaitlist.objects.select_for_update().get(pk=pk)
    if row.customer_id != actor.pk: require(actor,'change_bookingwaitlist')
    if row.status == 'CANCELLED': return row
    if row.status not in ('WAITING','OFFERED'): raise ValidationError('Không thể hủy yêu cầu này.')
    row.status='CANCELLED'
    with audit_actor(actor): return save_validated(row)


def notify_floor_changed():
    # Existing kitchen invalidation stream and POS polling; no new socket architecture.
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from .realtime import KITCHEN_GROUP
    transaction.on_commit(lambda:async_to_sync(get_channel_layer().group_send)(KITCHEN_GROUP,{'type':'realtime.changed','payload':{'type':'table.updated'}}),robust=True)


@transaction.atomic
def mark_arrival(pk, *, actor, state):
    if state not in ('CHECKED_IN','NO_SHOW'): raise ValidationError('Trạng thái đến không hợp lệ.')
    require(actor,'checkin_booking' if state=='CHECKED_IN' else 'noshow_booking')
    from .service_scope import require_booking
    require_booking(actor,pk)
    lock_areas()
    snapshot = Booking.objects.get(pk=pk)
    table = RestaurantTable.objects.select_for_update().get(pk=snapshot.table_id) if snapshot.table_id else None
    booking = Booking.objects.select_for_update().get(pk=pk)
    old = BookingVisit.objects.filter(booking=booking).first()
    if old:
        if old.state == state: return old
        raise ValidationError('Khách đã được ghi nhận trạng thái đến.')
    if booking.status != 'CONFIRMED' or not table or not booking.start_time or not booking.end_time: raise ValidationError('Đặt bàn chưa được xác nhận hoặc thiếu bàn/khung giờ.')
    now = timezone.now()
    orders = Order.objects.select_for_update().filter(booking=booking)
    if state=='NO_SHOW':
        if not isinstance(settings.BOOKING_HOLD_MINUTES,int) or settings.BOOKING_HOLD_MINUTES<0: raise ValidationError('Cấu hình thời gian giữ bàn không hợp lệ.')
        if now < booking.start_time+timedelta(minutes=settings.BOOKING_HOLD_MINUTES): raise ValidationError('Chưa quá thời gian giữ bàn.')
        if orders.exclude(status='CANCELLED').exists(): raise ValidationError('Đã có đơn phục vụ; không thể đánh dấu không đến.')
        booking.status='CANCELLED'
    else:
        if not booking.start_time <= now < booking.end_time: raise ValidationError('Check-in trong khung giờ đặt bàn.')
        if not table.is_active or not table.area.is_active or table.status=='MAINTENANCE': raise ValidationError('Bàn không sẵn sàng.')
        if Order.objects.filter(table=table,status__in=ACTIVE_ORDER_STATUSES).exclude(booking=booking).exists(): raise ValidationError('Bàn đang có đơn khác.')
        from .table_session_service import busy, start
        if busy(table,exclude_booking=booking.pk):raise ValidationError('Bàn có khách chưa trả bàn.')
        deposit=getattr(booking,'deposit',None)
        if deposit and deposit.status!='SUCCEEDED':raise ValidationError('Cọc chưa được xác nhận.')
        start(table,booking=booking)
        if table.status!='OCCUPIED':table.status='OCCUPIED';save_validated(table)
    with audit_actor(actor):
        save_validated(booking)
        visit=save_validated(BookingVisit(booking=booking,state=state,actor=actor))
    notify_floor_changed()
    return visit


@transaction.atomic
def transfer_table(*, actor, destination_id, booking_id=None, order_id=None, guests=None):
    require(actor,'transfer_table')
    from .service_scope import require_order,require_booking,require_table
    if order_id:require_order(actor,order_id)
    if booking_id:require_booking(actor,booking_id)
    require_table(actor,destination_id)
    areas=lock_areas()
    if bool(booking_id)==bool(order_id): raise ValidationError('Chọn một đặt bàn hoặc một đơn hàng.')
    order_snapshot=Order.objects.get(pk=order_id) if order_id else None
    if order_snapshot and order_snapshot.booking_id: booking_id=order_snapshot.booking_id
    booking_snapshot=Booking.objects.get(pk=booking_id) if booking_id else None
    source_id=booking_snapshot.table_id if booking_snapshot else order_snapshot.table_id
    tables={t.pk:t for t in RestaurantTable.objects.select_for_update().filter(pk__in=[source_id,destination_id]).order_by('pk')}
    source, dest=tables.get(source_id), tables.get(destination_id)
    booking=Booking.objects.select_for_update().get(pk=booking_id) if booking_id else None
    order=Order.objects.select_for_update().filter(booking=booking).first() if booking else Order.objects.select_for_update().get(pk=order_id)
    if not source or not dest: raise ValidationError('Bàn không tồn tại.')
    if booking and booking.table_id != source_id or order and order.table_id != source_id: raise ValidationError('Bàn vừa thay đổi; hãy tải lại.')
    if booking and booking.status!='CONFIRMED' or order and order.status not in ACTIVE_ORDER_STATUSES: raise ValidationError('Phiên phục vụ đã kết thúc.')
    if source.pk==dest.pk: return booking or order
    from .table_session_service import busy,enabled
    if busy(dest):raise ValidationError('Bàn đích có khách chưa trả bàn.')
    count=booking.guests if booking else guests
    if isinstance(count,bool) or not isinstance(count,int) or count<1: raise ValidationError('Cần số khách thực tế.')
    if not table_eligible(dest,areas[dest.area_id],count) or dest.status=='OCCUPIED': raise ValidationError('Bàn đích không phù hợp hoặc đang sử dụng.')
    start,end=(booking.start_time,booking.end_time) if booking else (timezone.now(),timezone.now()+timedelta(minutes=settings.DEFAULT_BOOKING_DURATION_MINUTES))
    if overlaps(dest.pk,start,end,booking.pk if booking else None): raise ValidationError('Bàn đích trùng lịch.')
    if Order.objects.filter(table=dest,status__in=ACTIVE_ORDER_STATUSES).exists(): raise ValidationError('Bàn đích đang có đơn.')
    with audit_actor(actor):
        if booking: booking.table=dest;save_validated(booking)
        if order: order.table=dest;save_validated(order);notify_order_changed(order.pk)
        in_service=bool(order) or bool(booking and BookingVisit.objects.filter(booking=booking,state='CHECKED_IN').exists())
        if in_service:
            if enabled():
                from .models import TableSession
                session=TableSession.objects.select_for_update().filter(table=source,ended_at__isnull=True).first()
                if session:
                    session.table=dest;session.save(update_fields=['table'])
            dest.status='OCCUPIED';save_validated(dest)
            other_order=Order.objects.filter(table=source,status__in=ACTIVE_ORDER_STATUSES).exists()
            other_visit=BookingVisit.objects.filter(booking__table=source,booking__status='CONFIRMED',state='CHECKED_IN').exists()
            if not other_order and not other_visit and source.status=='OCCUPIED': source.status='AVAILABLE';save_validated(source)
        record(actor=actor,action='TABLE_TRANSFER',entity=booking or order,before={'table_id':source.pk},after={'table_id':dest.pk})
        record(actor=actor,action='TRANSFER_OUT',entity=source,after={'destination_id':dest.pk})
        record(actor=actor,action='TRANSFER_IN',entity=dest,after={'source_id':source.pk})
    notify_floor_changed()
    return booking or order
