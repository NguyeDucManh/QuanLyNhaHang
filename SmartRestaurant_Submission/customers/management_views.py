"""Server-rendered Admin Area/Table/Booking pages using the existing Admin shell."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .rbac import capability_required, has_capability
from .models import Area, RestaurantTable, Booking
from .forms import AreaForm, RestaurantTableForm
from .booking_service import save_area, save_table, transition_booking, TRANSITIONS


def page_context(request, queryset):
    return Paginator(queryset, 30).get_page(request.GET.get('page'))


@capability_required('customers.view_area')
def areas(request):
    query = request.GET.get('q', '').strip()
    rows = Area.objects.filter(name__icontains=query)
    return render(request, 'admin/restaurant/areas.html', {
        'pagination': page_context(request, rows), 'query': query, 'admin_page': 'areas',
        'can_add': has_capability(request.user, 'customers.add_area'),
        'can_change': has_capability(request.user, 'customers.change_area'),
    })


@capability_required('customers.view_restauranttable')
def tables(request):
    query = request.GET.get('q', '').strip()
    rows = RestaurantTable.objects.select_related('area').filter(code__icontains=query)
    return render(request, 'admin/restaurant/tables.html', {
        'pagination': page_context(request, rows), 'query': query, 'admin_page': 'tables',
        'can_add': has_capability(request.user, 'customers.add_restauranttable'),
        'can_change': has_capability(request.user, 'customers.change_restauranttable'),
    })


def edit_resource(request, *, model, form_class, save, pk, permission, page, title, destination):
    if not has_capability(request.user, permission):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Bạn chưa có quyền thay đổi dữ liệu này.')
    obj = get_object_or_404(model, pk=pk) if pk is not None else None
    form = form_class(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            save(form)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, 'Tên hoặc mã đã tồn tại. Vui lòng kiểm tra lại.')
        else:
            messages.success(request, 'Đã lưu thay đổi.')
            return redirect(destination)
    return render(request, 'admin/restaurant/resource-form.html', {
        'form': form, 'object': obj, 'title': title, 'admin_page': page, 'back_url_name': destination,
    })


@capability_required('customers.add_area')
def area_add(request):
    return edit_resource(request, model=Area, form_class=AreaForm, save=save_area, pk=None,
                         permission='customers.add_area', page='areas', title='Thêm khu vực', destination='admin_areas')


@capability_required('customers.change_area')
def area_edit(request, pk):
    return edit_resource(request, model=Area, form_class=AreaForm, save=save_area, pk=pk,
                         permission='customers.change_area', page='areas', title='Sửa khu vực', destination='admin_areas')


@capability_required('customers.add_restauranttable')
def table_add(request):
    return edit_resource(request, model=RestaurantTable, form_class=RestaurantTableForm, save=save_table, pk=None,
                         permission='customers.add_restauranttable', page='tables', title='Thêm bàn', destination='admin_tables')


@capability_required('customers.change_restauranttable')
def table_edit(request, pk):
    return edit_resource(request, model=RestaurantTable, form_class=RestaurantTableForm, save=save_table, pk=pk,
                         permission='customers.change_restauranttable', page='tables', title='Sửa bàn', destination='admin_tables')


@capability_required('customers.view_booking')
def bookings(request):
    from .booking_workspace import ManagerBookingForm,booking_panel
    from .booking_service import create_booking
    from django.utils import timezone
    from django.core.exceptions import PermissionDenied
    can_add=has_capability(request.user,'customers.add_booking')
    form=ManagerBookingForm(request.POST if request.method=='POST' else None)
    if request.method=='POST':
        if not can_add:raise PermissionDenied
        if form.is_valid():
            data=form.cleaned_data.copy();customer=data.pop('customer') or request.user
            try:create_booking(user=customer,**data)
            except ValidationError as error:form.add_error(None,error)
            else:
                messages.success(request,'Đã tạo đặt bàn và tự gán bàn phù hợp.')
                return redirect('admin_bookings')
    panel=booking_panel(request,Booking.objects.all())
    upcoming=Booking.objects.select_related('user','table__area','service_order').filter(date__gt=timezone.localdate(),status__in=['PENDING','CONFIRMED']).order_by('date','time')[:5]
    return render(request,'admin/restaurant/bookings.html',{
        **panel,'form':form,'can_add':can_add,'workspace_future':[{'booking':b,'transitions':[]} for b in upcoming],
        'rows':panel['workspace_rows'],'pagination':panel['booking_pagination'],'statuses':Booking.Status.choices,
        'status':request.GET.get('status',''),'admin_page':'bookings','can_change':has_capability(request.user,'customers.change_booking'),
        'can_open_order':has_capability(request.user,'customers.add_order') and has_capability(request.user,'customers.add_orderitem'),
        'can_view_order':has_capability(request.user,'customers.view_order')})


@capability_required('customers.view_booking')
def booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('user','table__area','service_order').prefetch_related('preorder_items'), pk=pk)
    return render(request, 'admin/restaurant/booking-detail.html', {'booking':booking,'admin_page':'bookings',
        'can_open_order':has_capability(request.user,'customers.add_order') and has_capability(request.user,'customers.add_orderitem'),
        'can_view_order':has_capability(request.user,'customers.view_order')})


@capability_required('customers.change_booking')
@require_POST
def booking_status(request, pk):
    get_object_or_404(Booking, pk=pk)
    try:
        transition_booking(pk, request.POST.get('status', ''))
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    else:
        messages.success(request, 'Đã cập nhật trạng thái đặt bàn.')
    return redirect('admin_bookings')
