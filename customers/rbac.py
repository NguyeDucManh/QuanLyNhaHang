"""Business roles live in Django Group; is_staff is never a business role."""
from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.contrib.auth.models import Group

ROLES = ('ADMIN', 'MANAGER', 'STAFF', 'CUSTOMER')
STAFF_ORDER_PERMISSIONS = {'view_order','add_order','change_order','view_orderitem','add_orderitem','change_orderitem'}
STAFF_PAYMENT_PERMISSIONS = {'view_invoice','add_invoice','view_payment','add_payment','change_payment'}
BUSINESS_VIEW_PERMISSIONS=('view_menuitem','view_category','view_area','view_restauranttable','view_booking','view_order','view_invoice','view_ingredient','view_supplier','view_recipeingredient','view_stockmovement')
BUSINESS_VIEW_PERMISSIONS += ('view_purchaseorder','view_customerloyalty','view_auditlog','view_bookingwaitlist')
MANAGER_PERMISSIONS={
    'view_orderitem','add_orderitem','change_orderitem',
    'view_menuitem','add_menuitem','change_menuitem','view_category','add_category','change_category',
    'view_area','add_area','change_area','view_restauranttable','add_restauranttable','change_restauranttable','view_booking','change_booking',
    'view_order','add_order','change_order','view_invoice','add_invoice','view_payment','add_payment','change_payment',
    'view_supplier','add_supplier','change_supplier','view_ingredient','add_ingredient','change_ingredient',
    'view_recipeingredient','add_recipeingredient','change_recipeingredient','delete_recipeingredient',
    'view_stockreceipt','add_stockreceipt','change_stockreceipt','view_stockissue','add_stockissue','change_stockissue','view_stockmovement',
}

MODULE07_MODELS=('topping','combo','comboitem','promotion','review','restaurantinfo','position','employee','shift','workschedule','attendance','payrollperiod','payroll')
MANAGER_PERMISSIONS.update(f'{action}_{model}' for model in MODULE07_MODELS for action in ('view','add','change'))
MANAGER_PERMISSIONS.add('delete_comboitem')


def get_assigned_role(user):
    if user.is_superuser:
        return 'ADMIN'
    roles = list(user.groups.filter(name__in=ROLES).values_list('name', flat=True))
    return (roles[0] if len(roles) == 1 else None) if roles else 'CUSTOMER'


def get_role(user):
    if not user.is_authenticated or not user.is_active:
        return None
    return get_assigned_role(user)


def is_admin(user):
    return get_role(user) == 'ADMIN'


def has_capability(user, permission):
    role = get_role(user)
    return role == 'ADMIN' or (role in ('MANAGER', 'STAFF') and user.has_perm(permission))


def can_manage(user):
    return get_role(user) in ('ADMIN', 'MANAGER') or (get_role(user) == 'STAFF' and any(has_capability(user,'customers.'+permission) for permission in BUSINESS_VIEW_PERMISSIONS))


def role_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if get_role(request.user) not in roles:
                raise PermissionDenied('Bạn không có vai trò phù hợp.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def capability_required(permission):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not has_capability(request.user, permission):
                raise PermissionDenied('Bạn chưa được cấp quyền cho chức năng này.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


@transaction.atomic
def assign_role(user, role):
    if role not in ROLES or (user.is_superuser and role != 'ADMIN'):
        raise ValidationError('Vai trò không hợp lệ.')
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.remove(*user.groups.filter(name__in=ROLES))
    user.groups.add(group)
    user.is_staff = user.is_superuser or role == 'ADMIN'
    user.save(update_fields=['is_staff'])
    for cache in ('_perm_cache', '_group_perm_cache', '_user_perm_cache'):
        user.__dict__.pop(cache, None)


def management_access(user):
    role=get_role(user)
    def cap(permission):
        return role=='ADMIN' or (role in ('MANAGER','STAFF') and user.has_perm(permission))
    access = {
        'role': role, 'is_admin': (role=='ADMIN'),
        'view_menu': cap( 'customers.view_menuitem'),
        'add_menu': cap( 'customers.add_menuitem'),
        'change_menu': cap( 'customers.change_menuitem'),
        'view_areas': cap( 'customers.view_area'),
        'view_tables': cap( 'customers.view_restauranttable'),
        'view_bookings': cap( 'customers.view_booking'),
        'view_orders':cap('customers.view_order'),
        'view_kitchen':cap('customers.view_order') and cap('customers.view_orderitem'),
        'view_payments':cap('customers.view_invoice'),
        'view_ingredients':cap('customers.view_ingredient'),
        'view_suppliers':cap('customers.view_supplier'),
        'view_recipes':cap('customers.view_recipeingredient'),
        'view_transactions':cap('customers.view_stockmovement'),
        'view_stock_alerts':cap('customers.view_ingredient'),
    }
    access.update({key:cap('customers.view_'+model) for key,model in {'toppings':'topping','combos':'combo','combo-items':'comboitem','promotions':'promotion','reviews':'review','restaurant-info':'restaurantinfo','employees':'employee','positions':'position','shifts':'shift','schedules':'workschedule','attendance':'attendance','payroll':'payroll','periods':'payrollperiod'}.items()})
    access.update({key:cap('customers.'+permission) for key,permission in {'purchase-orders':'view_purchaseorder','food-cost':'view_recipeingredient','loyalty':'view_customerloyalty','audit-log':'view_auditlog','waitlist':'view_bookingwaitlist','booking-operations':'view_booking','transfer-table':'transfer_table'}.items()})
    access['loyalty']=access['loyalty'] and role in ('ADMIN','MANAGER')
    access['messages']=role in ('ADMIN','MANAGER','STAFF')
    access['reports']=role in ('ADMIN','MANAGER')
    access['ai-schedule']=role in ('ADMIN','MANAGER') and all(cap('customers.'+p) for p in ('view_workschedule','add_workschedule','change_workschedule'))
    for page in ['ai-dashboard','ai-forecast','ai-inventory','ai-faces']:
        access[page]=role in ('ADMIN','MANAGER')
    return access
