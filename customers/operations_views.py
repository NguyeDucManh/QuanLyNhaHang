from . import service_scope as service_scope
"""Small server-rendered additions to the approved management/customer shells."""
import uuid
from datetime import timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q, F
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.utils.dateparse import parse_date as parse_date_value
from django.utils import timezone
from django.conf import settings
from .models import PurchaseOrder, PurchaseOrderItem, Supplier, Ingredient, AuditLog, CustomerLoyalty, LoyaltyTransaction, BookingWaitlist, Booking, Order, RestaurantTable, Category, Invoice, StockReceiptItem
from .rbac import capability_required, has_capability
from . import purchasing_service as purchasing
from . import booking_advanced_service as advanced


def parse_date(value):
    try: return parse_date_value(value)
    except (ValueError,TypeError): return None


def paginate(request, rows): return Paginator(rows,25).get_page(request.GET.get('page'))


def page(request, title, **context):
    section=context.pop('section',{'form':'purchase-orders','prices':'transactions','booking-ops':'bookings','table-history':'tables'}.get(context.get('kind'),'operations'))
    return render(request,'admin/operations/workspace.html',dict(title=title,admin_page=section,**context))


class POForm(forms.Form):
    supplier = forms.ModelChoiceField(Supplier.objects.filter(is_active=True), label='Nhà cung cấp')
    expected_date = forms.DateField(required=False,label='Ngày dự kiến',widget=forms.DateInput(attrs={'type':'date'}))
    note = forms.CharField(required=False,max_length=1000,label='Ghi chú',widget=forms.Textarea(attrs={'rows':2}))
    request_key = forms.UUIDField(widget=forms.HiddenInput)


class POLineForm(forms.Form):
    ingredient = forms.ModelChoiceField(Ingredient.objects.filter(is_active=True),label='Nguyên liệu')
    quantity = forms.DecimalField(min_value=.001,max_digits=12,decimal_places=3,label='Số đặt (đơn vị kho)')
    unit_price = forms.DecimalField(min_value=0,max_digits=12,decimal_places=2,label='Đơn giá / đơn vị kho')


@capability_required('customers.view_purchaseorder')
def purchase_orders(request):
    rows=PurchaseOrder.objects.select_related('supplier','created_by').annotate(ordered_lines=Count('items'),received_lines=Count('items',filter=Q(items__quantity_received=F('items__quantity_ordered')))).order_by('-created_at','-pk')
    if request.GET.get('status') in PurchaseOrder.Status.values: rows=rows.filter(status=request.GET['status'])
    if request.GET.get('q'): rows=rows.filter(code__icontains=request.GET['q'])
    return page(request,'Đơn mua hàng',section='purchase-orders',kind='po-list',pagination=paginate(request,rows),statuses=PurchaseOrder.Status.choices,can_add=has_capability(request.user,'customers.add_purchaseorder'))


@capability_required('customers.add_purchaseorder')
def purchase_add(request):
    LineSet=forms.formset_factory(POLineForm,extra=5,max_num=50,validate_max=True,min_num=1,validate_min=True)
    form=POForm(request.POST or None,initial={'request_key':uuid.uuid4()})
    lines=LineSet(request.POST or None)
    if request.method=='POST' and form.is_valid() and lines.is_valid():
        try: po=purchasing.create_purchase_order(actor=request.user,items=[i.cleaned_data for i in lines if i.cleaned_data],**form.cleaned_data)
        except ValidationError as exc: form.add_error(None,exc)
        else: return redirect('purchase_order_detail',pk=po.pk)
    return page(request,'Tạo đơn mua hàng',kind='form',form=form,formset=lines)


@capability_required('customers.view_purchaseorder')
def purchase_detail(request,pk):
    po=get_object_or_404(PurchaseOrder.objects.select_related('supplier','created_by','approved_by'),pk=pk)
    rows=list(po.items.select_related('ingredient'))
    return page(request,po.code,section='purchase-orders',kind='po-detail',po=po,lines=rows,receivings=po.receivings.select_related('receipt','created_by').prefetch_related('receipt__items__ingredient'),request_key=uuid.uuid4(),can_change=has_capability(request.user,'customers.change_purchaseorder'),can_approve=has_capability(request.user,'customers.approve_purchaseorder'),can_receive=all(has_capability(request.user,'customers.'+p) for p in ['receive_purchaseorder','add_stockreceipt','change_stockreceipt']))


@require_POST
@capability_required('customers.view_purchaseorder')
def purchase_action(request,pk):
    get_object_or_404(PurchaseOrder,pk=pk)
    try:
        if request.POST.get('action')=='receive':
            date=parse_date(request.POST.get('date',''))
            if date is None: raise ValidationError('Ngày nhận không hợp lệ.')
            items=[]
            for row in PurchaseOrderItem.objects.filter(purchase_order_id=pk):
                quantity=request.POST.get(f'quantity_{row.pk}','').strip()
                if quantity and quantity!='0': items.append({'item_id':row.pk,'quantity':quantity,'unit_price':request.POST.get(f'price_{row.pk}') or None})
            purchasing.receive_purchase_order(pk,actor=request.user,items=items,date=date,request_key=request.POST.get('request_key'),note=request.POST.get('note',''))
        else: purchasing.transition_purchase_order(pk,request.POST.get('action'),actor=request.user)
    except ValidationError as exc: messages.error(request,'; '.join(exc.messages))
    else: messages.success(request,'Đã cập nhật đơn mua hàng.')
    return redirect('purchase_order_detail',pk=pk)


@capability_required('customers.view_stockreceipt')
def prices(request):
    return page(request,'Lịch sử giá mua theo nhà cung cấp',kind='prices',pagination=paginate(request,purchasing.supplier_prices()),history=paginate(request,StockReceiptItem.objects.filter(receipt__status='CONFIRMED').select_related('receipt__supplier','ingredient').order_by('-receipt__date','-pk')))


@capability_required('customers.view_recipeingredient')
def food_cost(request):
    from .food_cost_service import food_cost_report
    category=request.GET.get('category','')
    if category and not category.isdigit(): category=''
    rows=food_cost_report(request.GET.get('q',''),category)
    sorting=request.GET.get('sort','name')
    if sorting in ('cost','percentage','profit'): rows.sort(key=lambda i:(i[sorting] is None,i[sorting] or 0))
    else: rows.sort(key=lambda i:i['menu'].name)
    return page(request,'Giá vốn món từ Recipe',section='food-cost',kind='food-cost',pagination=paginate(request,rows),categories=Category.objects.all())


@require_GET
@capability_required('customers.view_auditlog')
def audit_logs(request):
    rows=AuditLog.objects.select_related('actor')
    for key in ('entity_type','action','entity_id'):
        if request.GET.get(key): rows=rows.filter(**{key:request.GET[key]})
    if request.GET.get('actor'): rows=rows.filter(actor__username__icontains=request.GET['actor'])
    for field,lookup in [('from','created_at__date__gte'),('to','created_at__date__lte')]:
        value=parse_date(request.GET.get(field,''))
        if value: rows=rows.filter(**{lookup:value})
    return page(request,'Nhật ký hệ thống',section='audit-log',kind='audit',pagination=paginate(request,rows))


@capability_required('customers.view_customerloyalty')
def loyalty_management(request):
    accounts=CustomerLoyalty.objects.select_related('customer').order_by('-lifetime_points','pk')
    if request.GET.get('q'): accounts=accounts.filter(customer__username__icontains=request.GET['q'])
    # Separate aggregation avoids multiplying invoices by loyalty ledger rows.
    pagination=paginate(request,accounts)
    customers=[account.customer_id for account in pagination]
    spend={i['order__customer_id']:i for i in service_scope.invoices(request.user).filter(status='PAID',order__status='COMPLETED',order__customer_id__in=customers).values('order__customer_id').annotate(spend=Sum('total_amount'),orders=Count('pk'))}
    for account in pagination: account.summary=spend.get(account.customer_id,{})
    return page(request,'Thành viên khách hàng',section='loyalty',kind='loyalty',pagination=pagination,can_adjust=has_capability(request.user,'customers.adjust_customerloyalty'),request_key=uuid.uuid4())


@require_POST
@capability_required('customers.adjust_customerloyalty')
def loyalty_adjust(request,pk):
    from .loyalty_service import adjust_points
    from django.contrib.auth import get_user_model
    get_object_or_404(get_user_model(),pk=pk)
    try:
        try: points=int(request.POST.get('points',''))
        except ValueError: raise ValidationError('Điểm phải là số nguyên.')
        adjust_points(pk,actor=request.user,points=points,reason=request.POST.get('reason',''),request_key=request.POST.get('request_key'))
    except ValidationError as exc: messages.error(request,'; '.join(exc.messages))
    else: messages.success(request,'Đã điều chỉnh điểm và lưu nhật ký.')
    return redirect('loyalty_management')


@login_required
def loyalty_customer(request):
    from .membership_service import status,enabled,policy
    return render(request,'customer/operations.html',{'page':'membership','kind':'loyalty','member':status(request.user.pk),'membership_enabled':enabled(),'tiers':policy()[0],'account':CustomerLoyalty.objects.filter(customer=request.user).first(),'pagination':paginate(request,LoyaltyTransaction.objects.filter(customer=request.user))})


class WaitlistForm(forms.Form):
    name=forms.CharField(max_length=100,label='Họ tên')
    phone=forms.CharField(max_length=20,label='Điện thoại')
    date=forms.DateField(label='Ngày',widget=forms.DateInput(attrs={'type':'date'}))
    time=forms.TimeField(label='Giờ',widget=forms.TimeInput(attrs={'type':'time'}))
    guests=forms.IntegerField(min_value=1,max_value=20,label='Số khách')
    note=forms.CharField(max_length=500,required=False,label='Ghi chú')
    consent=forms.BooleanField(label='Tôi đồng ý tham gia danh sách chờ khi hết bàn')
    request_key=forms.UUIDField(widget=forms.HiddenInput)


@login_required
def waitlist_customer(request):
    form=WaitlistForm(request.POST or None,initial={'name':request.user.get_full_name(),'request_key':uuid.uuid4()})
    if request.method=='POST' and form.is_valid():
        try: advanced.join_waitlist(customer=request.user,**form.cleaned_data)
        except ValidationError as exc: form.add_error(None,exc)
        else: messages.success(request,'Đã ghi nhận yêu cầu chờ bàn.');return redirect('waitlist_customer')
    return render(request,'customer/operations.html',{'kind':'waitlist','form':form,'pagination':paginate(request,BookingWaitlist.objects.filter(customer=request.user).select_related('booking'))})


@capability_required('customers.view_bookingwaitlist')
def waitlist_management(request):
    return page(request,'Danh sách chờ bàn',section='waitlist',kind='waitlist',pagination=paginate(request,BookingWaitlist.objects.select_related('customer','booking')),can_convert=has_capability(request.user,'customers.convert_bookingwaitlist'),can_cancel=has_capability(request.user,'customers.change_bookingwaitlist'))


@require_POST
@login_required
def waitlist_action(request,pk):
    get_object_or_404(BookingWaitlist,pk=pk)
    try:
        if request.POST.get('action')=='convert': advanced.convert_waitlist(pk,actor=request.user)
        elif request.POST.get('action')=='cancel': advanced.cancel_waitlist(pk,actor=request.user)
        else: raise ValidationError('Thao tác không hợp lệ.')
    except ValidationError as exc: messages.error(request,'; '.join(exc.messages))
    else: messages.success(request,'Đã cập nhật danh sách chờ.')
    return redirect('waitlist_management' if has_capability(request.user,'customers.view_bookingwaitlist') else 'waitlist_customer')


@capability_required('customers.view_booking')
def booking_operations(request,pk):
    booking=get_object_or_404(service_scope.bookings(request.user).select_related('table__area','visit','service_order'),pk=pk)
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='transfer':
                try: destination=int(request.POST.get('destination',''))
                except ValueError: raise ValidationError('Chọn bàn đích.')
                advanced.transfer_table(actor=request.user,booking_id=pk,destination_id=destination)
            else: advanced.mark_arrival(pk,actor=request.user,state=action)
        except ValidationError as exc: messages.error(request,'; '.join(exc.messages))
        else: messages.success(request,'Đã cập nhật phục vụ.')
        return redirect('booking_operations',pk=pk)
    visit=getattr(booking,'visit',None);order=getattr(booking,'service_order',None);now=timezone.now()
    pending_arrival=booking.status=='CONFIRMED' and not visit and booking.start_time and booking.end_time
    return page(request,'Phục vụ đặt bàn',kind='booking-ops',booking=booking,tables=service_scope.tables(request.user).filter(is_active=True,area__is_active=True).exclude(status='MAINTENANCE').exclude(pk=booking.table_id).select_related('area'),
        can_checkin=has_capability(request.user,'customers.checkin_booking') and pending_arrival and booking.start_time<=now<booking.end_time,
        can_noshow=has_capability(request.user,'customers.noshow_booking') and pending_arrival and now>=booking.start_time+timedelta(minutes=settings.BOOKING_HOLD_MINUTES) and (not order or order.status=='CANCELLED'),
        can_transfer=has_capability(request.user,'customers.transfer_table') and booking.table_id and booking.status=='CONFIRMED' and (not order or order.status in ('PENDING','CONFIRMED','PREPARING')))


@capability_required('customers.transfer_table')
def order_transfer(request,pk):
    order=get_object_or_404(service_scope.orders(request.user),pk=pk)
    class TransferForm(forms.Form):
        destination=forms.ModelChoiceField(service_scope.tables(request.user).filter(is_active=True).exclude(status='MAINTENANCE'),label='Bàn đích')
        guests=forms.IntegerField(min_value=1,max_value=20,label='Số khách')
    form=TransferForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try: advanced.transfer_table(actor=request.user,order_id=pk,destination_id=form.cleaned_data['destination'].pk,guests=form.cleaned_data['guests'])
        except ValidationError as exc: form.add_error(None,exc)
        else: return redirect('staff_home')
    return page(request,'Chuyển bàn · '+order.order_number,section='orders',kind='form',form=form)


@capability_required('customers.view_restauranttable')
def table_history(request,pk):
    table=get_object_or_404(service_scope.tables(request.user),pk=pk)
    return page(request,'Lịch sử bàn '+table.code,kind='table-history',table=table,
        bookings=table.bookings.select_related('visit').order_by('-created_at')[:30] if has_capability(request.user,'customers.view_booking') else [],
        orders=service_scope.orders(request.user).filter(table=table).order_by('-created_at')[:30] if has_capability(request.user,'customers.view_order') else [],
        events=AuditLog.objects.filter(entity_type='RestaurantTable',entity_id=str(pk)).select_related('actor')[:30] if has_capability(request.user,'customers.view_auditlog') else [])
