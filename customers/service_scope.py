"""One object scope for HTTP, services, exports and websocket reauthorization."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import Order, Booking, Invoice, Payment, RestaurantTable
from .rbac import get_role


def management(user):
    return user.is_authenticated and user.is_active and get_role(user) in ('ADMIN','MANAGER')


def assigned_ids(user):
    from .table_assignment_service import enabled, active_assignments
    if not enabled():return None
    return active_assignments().filter(work_schedule__employee__user=user).values_list('table_id',flat=True)


def orders(user, queryset=None):
    queryset=Order.objects.all() if queryset is None else queryset
    if management(user):return queryset
    if not user.is_authenticated or not user.is_active:return queryset.none()
    if get_role(user)=='CUSTOMER':return queryset.filter(customer=user)
    if get_role(user)!='STAFF':return queryset.none()
    ids=assigned_ids(user)
    if ids is None:return queryset
    return queryset.filter(Q(table_id__in=ids)|Q(table__isnull=True,created_by=user))


def bookings(user,queryset=None):
    queryset=Booking.objects.all() if queryset is None else queryset
    if management(user):return queryset
    if not user.is_authenticated or not user.is_active:return queryset.none()
    if get_role(user)=='CUSTOMER':return queryset.filter(user=user)
    if get_role(user)!='STAFF':return queryset.none()
    ids=assigned_ids(user)
    return queryset.filter(table_id__in=ids) if ids is not None else queryset


def invoices(user,queryset=None):
    queryset=Invoice.objects.all() if queryset is None else queryset
    return queryset.filter(order__in=orders(user))


def payments(user,queryset=None):
    queryset=Payment.objects.all() if queryset is None else queryset
    return queryset.filter(invoice__in=invoices(user))


def tables(user,queryset=None):
    queryset=RestaurantTable.objects.all() if queryset is None else queryset
    if management(user):return queryset
    ids=assigned_ids(user) if get_role(user)=='STAFF' else []
    return queryset.filter(pk__in=ids) if ids is not None else queryset


def require_order(user,pk):
    if not orders(user).filter(pk=pk).exists():raise PermissionDenied('Đơn không thuộc phạm vi phục vụ của bạn.')


def require_booking(user,pk):
    if not bookings(user).filter(pk=pk).exists():raise PermissionDenied('Booking không thuộc phạm vi phục vụ của bạn.')


def require_table(user,pk):
    if not tables(user).filter(pk=pk).exists():raise PermissionDenied('Bàn không thuộc phạm vi phục vụ của bạn.')


def require_invoice(user,pk):
    if not invoices(user).filter(pk=pk).exists():raise PermissionDenied('Hóa đơn không thuộc phạm vi phục vụ của bạn.')
