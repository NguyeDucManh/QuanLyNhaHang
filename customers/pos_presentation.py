"""Read-only table workspace. No table, booking or order state is changed here."""
from django.utils import timezone
from .models import RestaurantTable, Booking, Order
from .rbac import has_capability
from .service_scope import orders as scoped_orders


def workspace(request):
    can_tables = has_capability(request.user, 'customers.view_restauranttable')
    can_menu = has_capability(request.user, 'customers.view_menuitem')
    can_orders = has_capability(request.user, 'customers.view_order')
    from .table_board import board
    state=board(request)
    if not any((can_tables,can_menu,can_orders)) and not state['tables']:
        return {}
    tables,orders,counts,selected=state['tables'],state['orders'],state['counts'],state['selected']
    can_tables=bool(tables) or can_tables
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
    return {**{k:v for k,v in state.items() if k.startswith('pos_')}, 'pos_enabled': can_tables, 'pos_tables': tables, 'pos_counts': counts, 'pos_selected': selected,
            'pos_kitchen_orders': kitchen_orders, 'pos_kitchen_counts': kitchen_counts,
            'pos_dishes': catalog, 'pos_categories': categories, 'pos_kitchen': kitchen[:8],
            'pos_recent': list(scoped_orders(request.user).filter(**({} if state['global_tables'] else {'table_id__in':[t.pk for t in tables]})).select_related('table').prefetch_related('items').order_by('-created_at')[:4]) if can_orders else [],
            'pos_areas': list({t.area_id: t.area for t in tables}.values()),
            'pos_orders': orders[:6], 'pos_can_orders': can_orders,
            'pos_can_items': has_capability(request.user, 'customers.view_orderitem'),
            'pos_can_transfer': has_capability(request.user, 'customers.transfer_table'),
            'pos_can_waitlist': has_capability(request.user, 'customers.view_bookingwaitlist'),
            'pos_can_add_item': has_capability(request.user, 'customers.add_orderitem') and has_capability(request.user, 'customers.change_order'),
            'pos_can_checkout': has_capability(request.user, 'customers.add_invoice') or has_capability(request.user, 'customers.view_invoice'),
            'pos_can_add': has_capability(request.user, 'customers.add_order')}
