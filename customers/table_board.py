"""Present current occupancy independently from a read-only reservation timeline."""
from types import SimpleNamespace
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import RestaurantTable, Booking, Order
from .rbac import get_role, has_capability
from .table_assignment_service import enabled, active_assignments, can_assign


def board(request):
    actual_now=timezone.now();now=actual_now;scope=request.GET.get('scope','today');time_error=''
    selected_at=request.GET.get('at','')
    if selected_at:
        try:
            parsed=parse_datetime(selected_at)
            if parsed is None:raise ValueError
            now=timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
        except (ValueError,TypeError,OverflowError):
            time_error='Ngày/giờ không hợp lệ; đang hiển thị hiện tại.';selected_at=''
    today=timezone.localdate(now)
    if scope not in ('today','upcoming','history'):scope='today'
    assignments=list(active_assignments(now).select_related('work_schedule__employee','work_schedule__shift')) if enabled() else []
    ownership=active_assignments(actual_now) if enabled() else []
    own_ids={a.table_id for a in ownership if a.work_schedule.employee.user_id==request.user.pk} if get_role(request.user) in ('ADMIN','MANAGER','STAFF') else set()
    global_tables=has_capability(request.user,'customers.view_restauranttable')
    tables=list(RestaurantTable.objects.select_related('area').order_by('area__name','code')) if global_tables else list(RestaurantTable.objects.select_related('area').filter(pk__in=own_ids).order_by('code'))
    if request.GET.get('assigned')=='mine':tables=[t for t in tables if t.pk in own_ids]
    ids=[t.pk for t in tables]
    can_orders=has_capability(request.user,'customers.view_order')
    from .service_scope import orders as scoped_orders
    order_query=scoped_orders(request.user).exclude(status__in=['COMPLETED','CANCELLED'])
    from .table_session_service import enabled as lifecycle_enabled
    if lifecycle_enabled():order_query=order_query.exclude(table_session__ended_at__isnull=False)
    if not global_tables:order_query=order_query.filter(table_id__in=ids)
    orders=list(order_query.select_related('customer','booking','table').prefetch_related('items__menu_item')) if can_orders else []
    can_details=has_capability(request.user,'customers.view_booking')
    booking_ids=ids  # table visibility permits non-PII availability, never customer detail.
    query=Booking.objects.filter(table_id__in=booking_ids).select_related('deposit').order_by('start_time','pk')
    current=list(query.filter(start_time__lte=now,end_time__gt=now,status__in=['PENDING','PENDING_DEPOSIT','CONFIRMED']))
    upcoming=list(query.filter(start_time__gt=now,start_time__lte=now+timezone.timedelta(days=30)).exclude(status__in=['CANCELLED','COMPLETED'])[:200])
    if selected_at:timeline=list(query.filter(start_time__lt=now+timezone.timedelta(minutes=1),end_time__gt=now)[:200])
    elif scope=='today':timeline=list(query.filter(date=today)[:200])
    elif scope=='upcoming':timeline=upcoming
    else:timeline=list(query.filter(Q(end_time__lte=now)|Q(status__in=['CANCELLED','COMPLETED'])).order_by('-start_time','-pk')[:200])
    def active(b):
        deposit=getattr(b,'deposit',None)
        return b.status in ('PENDING','CONFIRMED') or (b.status=='PENDING_DEPOSIT' and deposit is not None and deposit.status in ('PENDING','FAILED') and deposit.expires_at>actual_now)
    def safe(b):
        if can_details:return b
        return SimpleNamespace(pk=b.pk,name='Khách đặt bàn',note='',guests=b.guests,start_time=b.start_time,end_time=b.end_time,status=b.status)
    counts=dict.fromkeys(['AVAILABLE','UPCOMING','RESERVED','OCCUPIED','MAINTENANCE','INACTIVE'],0)
    by_assignment={a.table_id:a for a in assignments}
    by_order={o.table_id:o for o in reversed(orders) if not selected_at and (not o.booking_id or o.booking.start_time<=now+timezone.timedelta(hours=1))}
    from .table_session_service import enabled as lifecycle_enabled
    sessions={}
    if lifecycle_enabled() and not selected_at:
        from .models import TableSession
        sessions={s.table_id:s for s in TableSession.objects.filter(table_id__in=ids,ended_at__isnull=True).select_related('order')}
        visible_session_orders=set(scoped_orders(request.user).filter(pk__in=[s.order_id for s in sessions.values() if s.order_id]).values_list('pk',flat=True)) if can_orders else set()
        for table_id,session in sessions.items():
            if session.order_id in visible_session_orders:by_order[table_id]=session.order
    rows=[]
    from .models import BookingVisit
    arrived_ids=set(BookingVisit.objects.filter(booking_id__in=[b.pk for b in current],state='CHECKED_IN').values_list('booking_id',flat=True)) if lifecycle_enabled() else None
    for b in timeline:
        deposit=getattr(b,'deposit',None)
        hold='Không yêu cầu cọc' if deposit is None else deposit.get_status_display()
        if b.status=='PENDING_DEPOSIT' and not active(b):hold='Giữ chỗ hết hạn/không còn hiệu lực; không giữ bàn'
        table=next((t for t in tables if t.pk==b.table_id),None)
        allowed_open=has_capability(request.user,'customers.add_order') and has_capability(request.user,'customers.add_orderitem') and (not enabled() or get_role(request.user)!='STAFF' or b.table_id in own_ids)
        rows.append({'booking':safe(b),'table':table,'table_id':b.table_id,'status_label':b.get_status_display(),'deposit_label':hold,'active_hold':active(b) and b.end_time>now,'can_open':not selected_at and (arrived_ids is None or b.pk in arrived_ids) and allowed_open and b.status=='CONFIRMED' and b.start_time<=actual_now<b.end_time})
    for table in tables:
        live=next((b for b in current if b.table_id==table.pk and active(b)),None)
        future=next((b for b in upcoming if b.table_id==table.pk and active(b)),None)
        table.live_order=by_order.get(table.pk);table.live_booking=safe(live) if live else None
        table.upcoming_booking=safe(future) if future else None
        table.service_assignment=by_assignment.get(table.pk)
        arrived=bool(live and live.pk in arrived_ids) if arrived_ids is not None else True
        table.can_open_booking=bool(not selected_at and arrived and live and live.status=='CONFIRMED' and has_capability(request.user,'customers.add_order') and has_capability(request.user,'customers.add_orderitem') and (not enabled() or get_role(request.user)!='STAFF' or table.pk in own_ids))
        table.visual_status=('INACTIVE' if not table.is_active or not table.area.is_active else 'MAINTENANCE' if table.status=='MAINTENANCE' else 'OCCUPIED' if table.live_order or table.pk in sessions or (not selected_at and table.status=='OCCUPIED') else 'RESERVED' if live else 'UPCOMING' if future else 'AVAILABLE')
        table.visual_label={'INACTIVE':'Ngừng hoạt động','MAINTENANCE':'Bảo trì','OCCUPIED':'Đang phục vụ','RESERVED':'Đang giữ/đã đặt trong khung giờ','UPCOMING':'Có đặt trước','AVAILABLE':'Trống hiện tại'}[table.visual_status]
        table.current_guests=live.guests if live else None;table.service_elapsed=''
        reservation=live or future
        table.reservation_label=('Giữ tạm · Chờ cọc' if reservation.status=='PENDING_DEPOSIT' else reservation.get_status_display()) if reservation else ''
        if table.live_order:
            seconds=max(0,int((now-table.live_order.created_at).total_seconds()));table.service_elapsed=f'{seconds//3600:02}:{seconds%3600//60:02}'
        counts[table.visual_status]+=1
    preferred=next((t for t in tables if t.live_order),tables[0] if tables else None)
    selected=next((t for t in tables if str(t.pk)==request.GET.get('table')),preferred)
    return {'tables':tables,'orders':orders,'counts':counts,'selected':selected,'global_tables':global_tables,
        'pos_timeline':rows,'pos_scope':scope,'pos_at':selected_at,'pos_at_error':time_error,'pos_can_booking_details':can_details,'pos_can_assign':can_assign(request.user),
        'pos_assignments_enabled':enabled(),'pos_my_tables':bool(own_ids),'pos_assigned_filter':request.GET.get('assigned')=='mine',
        'pos_permission_message':'Chưa có bàn được giao trong ca hiện tại. Liên hệ quản lý.' if enabled() and get_role(request.user)=='STAFF' else 'Bạn chưa có quyền xem sơ đồ bàn.',
        'pos_timeline_limited':len(timeline)>=200}
