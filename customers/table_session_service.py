"""Payment and kitchen completion never imply departure. Caller locks Area/Table first."""
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import TableSession, RestaurantTable, Booking, BookingVisit, Order, Invoice
from .audit_service import record
from .rbac import has_capability
from . import service_scope as scope


def enabled():return getattr(settings,'TABLE_SERVICE_LIFECYCLE_ENABLED',False)


def busy(table, *, exclude_booking=None, exclude_order=None):
    sessions=TableSession.objects.filter(table=table,ended_at__isnull=True) if enabled() else None
    orders=Order.objects.filter(table=table,status__in=['PENDING','CONFIRMED','PREPARING'])
    if enabled():orders=orders.exclude(table_session__ended_at__isnull=False)
    visits=BookingVisit.objects.filter(booking__table=table,booking__status='CONFIRMED',state='CHECKED_IN')
    if exclude_booking is not None:
        orders=orders.exclude(booking_id=exclude_booking);visits=visits.exclude(booking_id=exclude_booking)
        if sessions is not None:sessions=sessions.exclude(booking_id=exclude_booking)
    if exclude_order is not None:
        orders=orders.exclude(pk=exclude_order)
        if sessions is not None:sessions=sessions.exclude(order_id=exclude_order)
    if sessions is not None and sessions.exists():return True
    if orders.exists() or visits.exists():return True
    # A persisted occupied flag is a legacy physical fact, not a booking forecast.
    own_visit=exclude_booking and BookingVisit.objects.filter(booking_id=exclude_booking,state='CHECKED_IN').exists()
    return table.status=='OCCUPIED' and not own_visit


def start(table, *, booking=None, order=None):
    if enabled():
        session=TableSession.objects.select_for_update().filter(table=table,ended_at__isnull=True).first()
        if session:
            if session.booking_id!=getattr(booking,'pk',None) or session.order_id not in (None,getattr(order,'pk',None)):
                raise ValidationError('Bàn đang có phiên phục vụ khác chưa trả bàn.')
            if order and session.order_id is None:session.order=order;session.save(update_fields=['order'])
        else:
            session=TableSession.objects.create(table=table,booking=booking,order=order,started_at=timezone.now())
    if enabled() and table.status!='OCCUPIED':table.status='OCCUPIED';table.save(update_fields=['status','updated_at'])


@transaction.atomic
def release(*,actor,order_id=None,booking_id=None,reason='',override=False,confirm=False):
    if not has_capability(actor,'customers.change_order'):raise PermissionDenied
    if not confirm:raise ValidationError('Cần xác nhận khách đã rời và bàn đã được trả.')
    if not isinstance(reason,str) or not 5<=len(reason.strip())<=1000:raise ValidationError('Nhập lý do trả bàn từ 5 đến 1000 ký tự.')
    if bool(order_id)==bool(booking_id):raise ValidationError('Chọn đúng một đơn hoặc lượt đến.')
    from .booking_service import lock_areas
    lock_areas()
    snapshot=Order.objects.get(pk=order_id) if order_id else Booking.objects.get(pk=booking_id)
    if order_id:scope.require_order(actor,order_id)
    else:scope.require_booking(actor,booking_id)
    if snapshot.table_id is None:raise ValidationError('Không có bàn để trả.')
    table=RestaurantTable.objects.select_for_update().get(pk=snapshot.table_id)
    booking_pk=snapshot.booking_id if order_id else snapshot.pk
    booking=Booking.objects.select_for_update().filter(pk=booking_pk).first()
    order=Order.objects.select_for_update().filter(pk=order_id).first() if order_id else Order.objects.select_for_update().filter(booking=booking).first()
    if (order and order.table_id!=table.pk) or (booking and booking.table_id!=table.pk):raise ValidationError('Bàn vừa thay đổi. Tải lại trước khi trả bàn.')
    session=TableSession.objects.select_for_update().filter(order=order).first() if enabled() and order else TableSession.objects.select_for_update().filter(booking=booking).first() if enabled() and booking else None
    if session and session.ended_at:return session
    if enabled() and TableSession.objects.filter(table=table,ended_at__isnull=True).exclude(pk=getattr(session,'pk',None)).exists():raise ValidationError('Bàn thuộc phiên phục vụ khác.')
    if Order.objects.filter(table=table,status__in=['PENDING','CONFIRMED','PREPARING']).exclude(pk=getattr(order,'pk',None)).exists():raise ValidationError('Bàn có đơn khác đang phục vụ.')
    if override:
        if not scope.management(actor):raise PermissionDenied('Chỉ quản lý được kết thúc phiên treo có lý do.')
    else:
        if not order or order.status!='COMPLETED' or not Invoice.objects.filter(order=order,status='PAID').exists():raise ValidationError('Hoàn thành đơn và xác nhận thanh toán trước khi trả bàn.')
        if enabled() and session is None:raise ValidationError('Phiên cũ chưa liên kết; quản lý cần kiểm tra và kết thúc có lý do.')
    if table.status!='OCCUPIED' and session is None and (booking is None or booking.status!='CONFIRMED'):return None
    now=timezone.now()
    if session:
        session.ended_at=now;session.ended_by=actor;session.end_reason=reason.strip();session.save(update_fields=['ended_at','ended_by','end_reason'])
    if booking and booking.status=='CONFIRMED':booking.status='COMPLETED';booking.save(update_fields=['status'])
    table.status='AVAILABLE';table.save(update_fields=['status','updated_at'])
    record(actor=actor,action='TABLE_SERVICE_RELEASED_OVERRIDE' if override else 'TABLE_SERVICE_RELEASED',entity=order or booking,
           after={'table_id':table.pk,'session_id':getattr(session,'pk',None),'reason':reason.strip(),'financial_state_unchanged':True})
    from .booking_advanced_service import notify_floor_changed
    notify_floor_changed()
    return session
