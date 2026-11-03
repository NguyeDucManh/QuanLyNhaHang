"""Read-only table workspace. No table, booking or order state is changed here."""
from django.utils import timezone
from .models import RestaurantTable, Booking, Order
from .rbac import has_capability


def workspace(request):
    can_tables = has_capability(request.user, 'customers.view_restauranttable')
    can_menu = has_capability(request.user, 'customers.view_menuitem')
    can_orders = has_capability(request.user, 'customers.view_order')
    if not any((can_tables, can_menu, can_orders)):
        return {}
    now = timezone.now()
    tables = list(RestaurantTable.objects.select_related('area').all()) if can_tables else []
    orders = list(Order.objects.exclude(status__in=['COMPLETED', 'CANCELLED'])
                  .select_related('customer', 'booking', 'table').prefetch_related('items__menu_item')) if can_orders else []
    bookings = {b.table_id: b for b in Booking.objects.filter(
        status='CONFIRMED', start_time__lte=now, end_time__gt=now).order_by('start_time')} if can_tables and has_capability(request.user, 'customers.view_booking') else {}
    counts = dict.fromkeys(['AVAILABLE', 'OCCUPIED', 'RESERVED', 'MAINTENANCE', 'INACTIVE'], 0)
    for table in tables:
        table.live_order = next((o for o in orders if o.table_id == table.pk), None)
        table.live_booking = bookings.get(table.pk)
        table.visual_status = ('INACTIVE' if not table.is_active or not table.area.is_active else
                               'MAINTENANCE' if table.status == 'MAINTENANCE' else
                               'OCCUPIED' if table.live_order or table.status == 'OCCUPIED' else
                               'RESERVED' if table.live_booking else 'AVAILABLE')
        counts[table.visual_status] += 1
        table.visual_label = {'AVAILABLE': 'Trống', 'OCCUPIED': 'Đang phục vụ', 'RESERVED': 'Đã đặt', 'MAINTENANCE': 'Bảo trì', 'INACTIVE': 'Ngừng hoạt động'}[table.visual_status]
        table.current_guests = table.live_booking.guests if table.live_booking else None
        table.service_elapsed = ''
        if table.live_order:
            seconds = max(0, int((now-table.live_order.created_at).total_seconds()))
            table.service_elapsed = f'{seconds//3600:02}:{seconds%3600//60:02}'
    preferred = next((t for t in tables if t.live_order), tables[0] if tables else None)
    selected = next((t for t in tables if str(t.pk) == request.GET.get('table')), preferred)
    from .menu_service import get_dishes
    catalog = get_dishes() if can_menu else []
    categories = list({d['category']: {'slug': d['category'], 'name': d['category_label']} for d in catalog}.values())
    kitchen = [item for order in orders for item in order.items.all() if item.kitchen_status in ('QUEUED', 'PREPARING', 'READY')] if has_capability(request.user, 'customers.view_orderitem') else []
    kitchen_orders = []
    if has_capability(request.user, 'customers.view_orderitem'):
        for order in orders:
            lines = [item for item in order.items.all() if item.kitchen_status in ('QUEUED', 'PREPARING', 'READY')]
            if lines:
                kitchen_orders.append({'order': order, 'items': lines, 'states': ' '.join(sorted({item.kitchen_status for item in lines}))})
    kitchen_orders = kitchen_orders[:8]
    kitchen_counts = {state: sum(state in group['states'].split() for group in kitchen_orders) for state in ('QUEUED', 'PREPARING', 'READY')}
    return {'pos_enabled': can_tables, 'pos_tables': tables, 'pos_counts': counts, 'pos_selected': selected,
            'pos_kitchen_orders': kitchen_orders, 'pos_kitchen_counts': kitchen_counts,
            'pos_dishes': catalog, 'pos_categories': categories, 'pos_kitchen': kitchen[:8],
            'pos_recent': list(Order.objects.select_related('table').prefetch_related('items').order_by('-created_at')[:4]) if can_orders else [],
            'pos_areas': list({t.area_id: t.area for t in tables}.values()),
            'pos_orders': orders[:6], 'pos_can_orders': can_orders,
            'pos_can_items': has_capability(request.user, 'customers.view_orderitem'),
            'pos_can_transfer': has_capability(request.user, 'customers.transfer_table'),
            'pos_can_waitlist': has_capability(request.user, 'customers.view_bookingwaitlist'),
            'pos_can_add_item': has_capability(request.user, 'customers.add_orderitem') and has_capability(request.user, 'customers.change_order'),
            'pos_can_checkout': has_capability(request.user, 'customers.add_invoice') or has_capability(request.user, 'customers.view_invoice'),
            'pos_can_add': has_capability(request.user, 'customers.add_order')}
