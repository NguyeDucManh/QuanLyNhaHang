"""Existing Admin shell, real ORM lists and forms, explicit permission on every mutation."""
from django.contrib import messages
from django.core.exceptions import ValidationError,PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError,transaction
from django.db.models import Q,F,Count
from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import Category,MenuItem,Supplier,Ingredient,RecipeIngredient,Order,OrderItem,Booking,Invoice,Payment,StockMovement,StockReceipt,StockIssue,Combo
from .business_forms import CategoryForm,SupplierForm,IngredientForm,RecipeForm,OrderForm,OrderLineForm,OrderLines,PaymentForm,ReceiptForm,IssueForm,DocumentForm,ReceiptLines,IssueLines
from .rbac import capability_required,has_capability
from .management_views import edit_resource
from .inventory_service import create_document,confirm_document,save_recipe,delete_recipe,save_ingredient
from .order_service import create_order,transition_order,open_order_from_booking,add_order_item,update_order_item,remove_order_item,TRANSITIONS,TRANSITION_LABELS,ACTIVE_ORDER_STATUSES
from .kitchen_service import send_order_to_kitchen, transition_kitchen_item
from .templatetags.money import money
from .payment_service import issue_invoice,create_payment,confirm_payment


def allowed(request,codename):
    return has_capability(request.user,'customers.'+codename)


def action(request,codename,label,url,*,post=False,data=None):
    return {'label':label,'url':url,'post':post,'data':data or {}} if allowed(request,codename) else None


def list_page(request,*,page,title,headers,queryset,cells,actions=None,tools=None,description='',filters=None,extra_context=None):
    pagination=Paginator(queryset,30).get_page(request.GET.get('page'))
    rows=[{'cells':cells(obj),'actions':[a for a in (actions(obj) if actions else []) if a]} for obj in pagination]
    return render(request,'admin/business/list.html',dict(admin_page=page,title=title,headers=headers,rows=rows,
        pagination=pagination,query=request.GET.get('q',''),tools=[t for t in (tools or []) if t],description=description,filters=filters,**(extra_context or {})))


@transaction.atomic
def save_master(form):
    return form.save()


RESOURCES={
    'category':(Category,CategoryForm,'menu','Danh mục','admin_categories',save_master),
    'supplier':(Supplier,SupplierForm,'suppliers','Nhà cung cấp','admin_suppliers',save_master),
    'ingredient':(Ingredient,IngredientForm,'ingredients','Nguyên liệu','admin_ingredients',save_ingredient),
    'recipeingredient':(RecipeIngredient,RecipeForm,'recipes','Công thức món','admin_recipes',save_recipe),
}


def resource_edit(request,resource,pk=None):
    if resource not in RESOURCES:
        raise PermissionDenied
    model,form,page,title,destination,save=RESOURCES[resource]
    permission='customers.'+('change_' if pk else 'add_')+resource
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    return edit_resource(request,model=model,form_class=form,save=save,pk=pk,permission=permission,page=page,
        title=('Sửa ' if pk else 'Thêm ')+title,destination=destination)


@capability_required('customers.view_category')
def categories(request):
    return list_page(request,page='menu',title='Danh mục thực đơn',headers=['Tên','Slug','Hoạt động'],
        queryset=Category.objects.filter(name__icontains=request.GET.get('q','')),
        cells=lambda x:[x.name,x.slug,'Có' if x.is_active else 'Không'],
        actions=lambda x:[action(request,'change_category','Sửa',reverse('business_edit',args=['category',x.pk]))],
        tools=[action(request,'add_category','Thêm danh mục',reverse('business_add',args=['category'])),action(request,'view_menuitem','Thực đơn',reverse('admin_menu_list'))])


@capability_required('customers.view_menuitem')
def menu(request):
    queryset=MenuItem.objects.select_related('category').filter(name__icontains=request.GET.get('q',''))
    category=request.GET.get('category','')
    if category.isdigit():
        queryset=queryset.filter(category_id=category)
    active=request.GET.get('active','')
    if active in ('1','0'):
        queryset=queryset.filter(is_available=active=='1')
    pagination=Paginator(queryset,30).get_page(request.GET.get('page'))
    return render(request,'admin/restaurant/menu.html',dict(admin_page='menu',pagination=pagination,query=request.GET.get('q',''),categories=Category.objects.all(),selected_category=category,active=active,
        can_add=allowed(request,'add_menuitem'),can_change=allowed(request,'change_menuitem'),can_categories=allowed(request,'view_category')))


@capability_required('customers.view_supplier')
def suppliers(request):
    return list_page(request,page='suppliers',title='Nhà cung cấp',headers=['Mã','Tên','Người liên hệ','Điện thoại','Email','Địa chỉ','Hoạt động'],
        queryset=Supplier.objects.filter(Q(code__icontains=request.GET.get('q',''))|Q(name__icontains=request.GET.get('q',''))),
        cells=lambda x:[x.code,x.name,x.contact_name,x.phone,x.email,x.address,'Có' if x.is_active else 'Không'],
        actions=lambda x:[action(request,'change_supplier','Sửa',reverse('business_edit',args=['supplier',x.pk]))],
        tools=[action(request,'add_supplier','Thêm nhà cung cấp',reverse('business_add',args=['supplier']))])


@capability_required('customers.view_ingredient')
def ingredients(request):
    return list_page(request,page='ingredients',title='Nguyên liệu',headers=['Mã','Tên','Đơn vị','Tồn hiện tại','Tồn tối thiểu','Hoạt động'],
        queryset=Ingredient.objects.filter(Q(code__icontains=request.GET.get('q',''))|Q(name__icontains=request.GET.get('q',''))),
        cells=lambda x:[x.code,x.name,x.get_unit_display(),x.current_stock,x.minimum_stock,'Có' if x.is_active else 'Không'],
        description='Tồn kho thay đổi qua phiếu nhập/xuất. Không sửa tồn trực tiếp.',
        actions=lambda x:[action(request,'change_ingredient','Sửa',reverse('business_edit',args=['ingredient',x.pk]))],
        tools=[action(request,'add_ingredient','Thêm nguyên liệu',reverse('business_add',args=['ingredient']))])


@capability_required('customers.view_ingredient')
def alerts(request):
    state=request.GET.get('state','low')
    queryset=Ingredient.objects.filter(is_active=True,name__icontains=request.GET.get('q',''))
    if state=='low': queryset=queryset.filter(current_stock__lte=F('minimum_stock'))
    elif state=='out': queryset=queryset.filter(current_stock=0)
    return list_page(request,page='stock-alerts',title='Tồn kho & Cảnh báo',headers=['Mã','Nguyên liệu','Đơn vị','Tồn hiện tại','Tồn tối thiểu','Trạng thái'],
        queryset=queryset,
        cells=lambda x:[x.code,x.name,x.get_unit_display(),x.current_stock,x.minimum_stock,'HẾT HÀNG' if x.current_stock==0 else 'TỒN THẤP' if x.current_stock<=x.minimum_stock else 'ĐỦ TỒN'],
        description='LOW STOCK khi tồn hiện tại ≤ tồn tối thiểu; chỉ nguyên liệu đang hoạt động.',filters={'name':'state','choices':[('low','Tồn thấp'),('out','Hết hàng')],'selected':state})


@capability_required('customers.view_recipeingredient')
def recipes(request):
    missing=list(MenuItem.objects.filter(recipe_lines__isnull=True).order_by('pk'))
    queryset=RecipeIngredient.objects.select_related('menu_item','ingredient').filter(menu_item__name__icontains=request.GET.get('q',''))
    menu_id=request.GET.get('menu','')
    if menu_id.isdigit(): queryset=queryset.filter(menu_item_id=menu_id)
    return list_page(request,page='recipes',title='Công thức món',headers=['Món','Nguyên liệu','Lượng cho một món','Đơn vị'],
        queryset=queryset,
        cells=lambda x:[x.menu_item.name,x.ingredient.name,x.quantity_required,x.ingredient.get_unit_display()],
        description=f'{len(missing)} món chưa có công thức. Trừ kho một lần khi từng món PREPARING → READY. Món không công thức được ghi cảnh báo, không trừ đoán. Không quy đổi đơn vị tự động.',extra_context={'missing_recipe_items':missing,'recipe_menus':MenuItem.objects.all(),'selected_menu':menu_id},
        actions=lambda x:[action(request,'change_recipeingredient','Sửa',reverse('business_edit',args=['recipeingredient',x.pk])),action(request,'delete_recipeingredient','Bỏ dòng',reverse('admin_recipe_delete',args=[x.pk]),post=True)],
        tools=[action(request,'add_recipeingredient','Thêm dòng công thức',reverse('business_add',args=['recipeingredient'])),action(request,'view_recipeingredient','Giá vốn từ công thức',reverse('food_cost'))])


@capability_required('customers.delete_recipeingredient')
@require_POST
def recipe_delete(request,pk):
    get_object_or_404(RecipeIngredient,pk=pk)
    delete_recipe(pk)
    return redirect('admin_recipes')


@capability_required('customers.view_order')
def orders(request):
    query=request.GET.get('q','').strip()
    queryset=Order.objects.select_related('customer','table','booking').annotate(item_count=Count('items')).filter(Q(order_number__icontains=query)|Q(customer__username__icontains=query)|Q(customer__first_name__icontains=query)|Q(booking__name__icontains=query)|Q(table__code__icontains=query)).order_by('-created_at','-pk')
    status=request.GET.get('status','')
    if status in Order.Status.values:
        queryset=queryset.filter(status=status)
    return list_page(request,page='orders',title='Đơn hàng',headers=['Mã đơn','Khách','Bàn','Booking','Số loại món','Tổng tiền','Trạng thái','Ngày'],queryset=queryset,
        cells=lambda x:[x.order_number,x.booking.name if x.booking else x.customer.username if x.customer else 'Khách vãng lai',x.table.code if x.table else '—',f'#{x.booking_id}' if x.booking_id else '—',x.item_count,money(x.total_amount),x.get_status_display(),x.created_at],
        actions=lambda x:[action(request,'view_order','Chi tiết',reverse('admin_order_detail',args=[x.pk]))],
        tools=[action(request,'add_order','Mở đơn từ Booking',reverse('admin_order_bookings')),action(request,'add_order','Tạo đơn trực tiếp',reverse('admin_order_add'))],filters={'name':'status','choices':Order.Status.choices,'selected':status})


def entry_form(request,*,form_class,lines_class,title,page,submit,destination):
    form=form_class(request.POST if request.method=='POST' else None)
    lines=lines_class(request.POST if request.method=='POST' else None,prefix='items')
    if request.method=='POST':
        valid=form.is_valid()
        lines_valid=lines.is_valid()
        if valid and lines_valid:
            try:
                obj=submit(form.cleaned_data,[line for line in lines.cleaned_data if line])
            except ValidationError as exc:
                form.add_error(None,exc)
            except IntegrityError:
                form.add_error(None,'Dữ liệu trùng hoặc đã thay đổi. Hãy tải lại và thử lại.')
            else:
                messages.success(request,'Đã lưu dữ liệu.')
                return redirect(destination(obj))
    return render(request,'admin/business/entry.html',dict(form=form,lines=lines,title=title,admin_page=page))


@capability_required('customers.add_order')
def order_add(request):
    return entry_form(request,form_class=OrderForm,lines_class=OrderLines,title='Tạo đơn hàng',page='orders',
        submit=lambda data,items:create_order(actor=request.user,items=items,**data),destination=lambda x:reverse('admin_order_detail',args=[x.pk]))


@capability_required('customers.view_order')
def order_detail(request,pk):
    order=get_object_or_404(Order.objects.select_related('customer','table__area','booking','created_by'),pk=pk)
    active=order.status in ACTIVE_ORDER_STATUSES and allowed(request,'change_order')
    items=list(order.items.order_by('created_at','pk'))
    can_edit=active and allowed(request,'change_orderitem')
    for item in items:
        item.can_edit_draft=can_edit and item.kitchen_status=='DRAFT'
        item.can_cancel=can_edit and item.kitchen_status in ('DRAFT','QUEUED')
    serving=[item for item in items if item.kitchen_status!='CANCELLED']
    transitions=list(TRANSITIONS[order.status]) if allowed(request,'change_order') else []
    if not serving or any(item.kitchen_status!='READY' for item in serving):
        transitions=[state for state in transitions if state!='COMPLETED']
    if any(item.kitchen_status in ('PREPARING','READY') for item in items):
        transitions=[state for state in transitions if state!='CANCELLED']
    if not allowed(request,'change_orderitem'):
        transitions=[state for state in transitions if state not in ('CONFIRMED','CANCELLED')]
    template='admin/business/_order_content.html' if request.headers.get('X-Realtime-Partial')=='1' else 'admin/business/order.html'
    response=render(request,template,dict(admin_page='orders',order=order,items=items if allowed(request,'view_orderitem') else [],
        can_view_items=allowed(request,'view_orderitem'),item_form=OrderLineForm(),can_add_item=active and allowed(request,'add_orderitem'),can_edit_item=can_edit,
        combos=Combo.objects.filter(is_active=True),
        can_send=can_edit and order.status in ('CONFIRMED','PREPARING') and any(item.kitchen_status=='DRAFT' for item in items),
        can_view_kitchen=allowed(request,'view_order') and allowed(request,'view_orderitem'),
        transitions=[(status,TRANSITION_LABELS[status]) for status in transitions],can_invoice=allowed(request,'add_invoice') and order.status=='COMPLETED'))
    response['Cache-Control']='no-store'
    response['Vary']='Cookie, X-Realtime-Partial'
    return response


@capability_required('customers.view_order')
@capability_required('customers.view_orderitem')
def kitchen_queue(request):
    queryset=OrderItem.objects.select_related('order__table__area').filter(kitchen_status__in=['QUEUED','PREPARING'],order__status__in=['CONFIRMED','PREPARING'])
    status=request.GET.get('status','')
    if status in ('QUEUED','PREPARING'):
        queryset=queryset.filter(kitchen_status=status)
    from .rbac import get_role
    staff=get_role(request.user)=='STAFF'
    pagination=Paginator(queryset.order_by('queued_at','pk'),30).get_page(request.GET.get('page'))
    template='admin/business/_kitchen_content.html' if request.headers.get('X-Realtime-Partial')=='1' else 'admin/business/kitchen.html'
    if staff and request.headers.get('X-Realtime-Partial')=='1':template='staff/kitchen_board.html'
    rows=list(pagination)
    ready=list(OrderItem.objects.select_related('order__table__area').filter(kitchen_status='READY',order__status__in=['CONFIRMED','PREPARING']).order_by('-ready_at','-pk')[:30]) if staff else []
    response=render(request,template,dict(admin_page='kitchen',pagination=pagination,status=status,kitchen_columns=[{'code':code,'label':label,'items':ready if code=='READY' else [item for item in rows if item.kitchen_status==code]} for code,label in [('QUEUED','Chờ làm'),('PREPARING','Đang làm'),('READY','Sẵn sàng')]],
        can_change=allowed(request,'change_order') and allowed(request,'change_orderitem')))
    response['Cache-Control']='no-store'
    response['Vary']='Cookie, X-Realtime-Partial'
    return response


@capability_required('customers.change_order')
@capability_required('customers.change_orderitem')
@require_POST
def order_send_kitchen(request,pk):
    get_object_or_404(Order,pk=pk)
    try:
        count=send_order_to_kitchen(pk,actor=request.user)
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
    else:
        messages.success(request,f'Đã gửi {count} món mới vào bếp.' if count else 'Không có món DRAFT mới để gửi bếp.')
    return redirect('admin_order_detail',pk=pk)


@capability_required('customers.change_order')
@capability_required('customers.change_orderitem')
@require_POST
def kitchen_item_status(request,pk,item_id):
    get_object_or_404(OrderItem,pk=item_id,order_id=pk)
    service_message(request,lambda:transition_kitchen_item(pk,item_id,request.POST.get('status',''),actor=request.user))
    if request.POST.get('return_to')=='kitchen' and allowed(request,'view_order') and allowed(request,'view_orderitem'):
        return redirect('admin_kitchen')
    return redirect('admin_order_detail',pk=pk)


def service_message(request,callback):
    try:
        callback()
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
    else:
        messages.success(request,'Đã xử lý yêu cầu.')


@capability_required('customers.change_order')
@require_POST
def order_status(request,pk):
    get_object_or_404(Order,pk=pk)
    service_message(request,lambda:transition_order(pk,request.POST.get('status',''),actor=request.user))
    return redirect('admin_order_detail',pk=pk)


@capability_required('customers.add_order')
def order_bookings(request):
    from .table_assignment_service import staff_table_ids
    scoped=staff_table_ids(request.user)
    bookings=Booking.objects.filter(status=Booking.Status.CONFIRMED,table__isnull=False,service_order__isnull=True)
    if scoped is not None:bookings=bookings.filter(table_id__in=scoped)
    return list_page(request,page='orders',title='Mở đơn từ Booking',headers=['Booking','Khách','Bàn','Bắt đầu','Kết thúc'],
        queryset=bookings.select_related('table').order_by('start_time','pk'),
        cells=lambda b:[f'#{b.pk}',b.name if has_capability(request.user,'customers.view_booking') else 'Khách đặt bàn',b.table.code,b.start_time,b.end_time],
        actions=lambda b:[action(request,'add_order','Mở đơn hàng',reverse('admin_booking_open_order',args=[b.pk]),post=True)],
        description='Chỉ mở đơn khi khách đến. Món đặt trước được sao chép theo tên và giá đã lưu.')


@capability_required('customers.add_order')
@capability_required('customers.add_orderitem')
@require_POST
def booking_open_order(request,pk):
    get_object_or_404(Booking,pk=pk)
    try:
        order=open_order_from_booking(pk,actor=request.user)
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
        return redirect('admin_order_bookings')
    except IntegrityError:
        messages.error(request,'Dữ liệu đã thay đổi. Hãy tải lại và thử lại.')
        return redirect('admin_order_bookings')
    return redirect('admin_order_detail',pk=order.pk)


@capability_required('customers.change_order')
@capability_required('customers.add_orderitem')
@require_POST
def order_item_add(request,pk):
    get_object_or_404(Order,pk=pk)
    form=OrderLineForm(request.POST)
    if form.is_valid():
        data=form.cleaned_data
        service_message(request,lambda:add_order_item(pk,actor=request.user,menu_item_id=data['menu_item'].pk,quantity=data['quantity'],note=data['note'],toppings=data['toppings']))
    else:
        messages.error(request,' '.join(str(e) for errors in form.errors.values() for e in errors))
    return redirect('admin_order_detail',pk=pk)


@capability_required('customers.change_order')
@capability_required('customers.change_orderitem')
@require_POST
def order_item_quantity(request,pk,item_id):
    get_object_or_404(OrderItem,pk=item_id,order_id=pk)
    from django import forms
    try:
        quantity=forms.IntegerField(min_value=1,max_value=1000).clean(request.POST.get('quantity'))
        service_message(request,lambda:update_order_item(pk,item_id,actor=request.user,quantity=quantity))
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
    return redirect('admin_order_detail',pk=pk)


@capability_required('customers.change_order')
@capability_required('customers.change_orderitem')
@require_POST
def order_item_remove(request,pk,item_id):
    get_object_or_404(OrderItem,pk=item_id,order_id=pk)
    service_message(request,lambda:remove_order_item(pk,item_id,actor=request.user))
    return redirect('admin_order_detail',pk=pk)


@capability_required('customers.view_invoice')
def invoices(request):
    return list_page(request,page='payments',title='Hóa đơn & Thanh toán',headers=['Số hóa đơn','Đơn','Tổng tiền','Trạng thái','Ngày xuất'],
        queryset=Invoice.objects.select_related('order').filter(invoice_number__icontains=request.GET.get('q','')),
        cells=lambda x:[x.invoice_number,f'#{x.order_id}',x.total_amount,x.get_status_display(),x.issued_at],
        description='Xuất hóa đơn từ chi tiết đơn đã hoàn thành. Thanh toán tiền mặt/chuyển khoản được nhà hàng đối soát và xác nhận thủ công.',
        actions=lambda x:[action(request,'view_invoice','Chi tiết / Thanh toán',reverse('admin_invoice_detail',args=[x.pk]))])


@capability_required('customers.add_invoice')
@require_POST
def invoice_issue(request,pk):
    get_object_or_404(Order,pk=pk)
    try:
        invoice=issue_invoice(pk,actor=request.user)
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
        return redirect('admin_order_detail',pk=pk)
    return redirect('admin_invoice_detail',pk=invoice.pk)


@capability_required('customers.view_invoice')
def invoice_detail(request,pk):
    invoice=get_object_or_404(Invoice.objects.select_related('order__customer','order__table'),pk=pk)
    form=PaymentForm()
    can_view_payments=allowed(request,'view_payment')
    from .payment_views import partial
    template='admin/business/_invoice_content.html' if request.headers.get('X-Realtime-Partial')=='1' else 'admin/business/invoice.html'
    return partial(request,template,dict(admin_page='payments',invoice=invoice,form=form,
        payments=invoice.payments.select_related('confirmed_by','created_by').all() if can_view_payments else [],
        can_view_payments=can_view_payments,can_pay=allowed(request,'add_payment') and invoice.status=='UNPAID' and not invoice.payments.filter(status__in=['PENDING','SUCCEEDED']).exists(),can_confirm=allowed(request,'change_payment')))


@capability_required('customers.add_payment')
@require_POST
def payment_add(request,pk):
    invoice=get_object_or_404(Invoice,pk=pk)
    form=PaymentForm(request.POST)
    if form.is_valid():
        service_message(request,lambda:create_payment(invoice_id=pk,actor=request.user,**form.cleaned_data))
    else:
        messages.error(request,' '.join(str(error) for errors in form.errors.values() for error in errors))
    return redirect('admin_invoice_detail',pk=invoice.pk)


@capability_required('customers.change_payment')
@require_POST
def payment_confirm(request,pk):
    payment=get_object_or_404(Payment,pk=pk)
    outcome=request.POST.get('outcome')
    if outcome not in ('success','failed','cancelled'):
        messages.error(request,'Kết quả xác nhận không hợp lệ.')
    else:
        service_message(request,lambda:confirm_payment(pk,actor=request.user,outcome={'success':'SUCCEEDED','failed':'FAILED','cancelled':'CANCELLED'}[outcome]))
    if request.POST.get('return_to')=='receipt':
        return redirect('admin_payment_receipt',pk=payment.pk)
    return redirect('admin_invoice_detail',pk=payment.invoice_id)


@capability_required('customers.view_stockmovement')
def transactions(request):
    return list_page(request,page='transactions',title='Nhập / Xuất kho — Lịch sử',headers=['Ngày','Nguyên liệu','Loại','Số lượng','Trước','Sau','Nguồn','Tham chiếu','Người thực hiện'],
        queryset=StockMovement.objects.select_related('ingredient','created_by','order_item').filter(Q(reference__icontains=request.GET.get('q',''))|Q(ingredient__name__icontains=request.GET.get('q',''))),
        cells=lambda x:[x.created_at,x.ingredient.name+' ('+x.ingredient.get_unit_display()+')',x.get_movement_type_display(),x.quantity,x.stock_before,x.stock_after,x.reference_type,x.reference,x.created_by.username],
        tools=[action(request,'view_stockreceipt','Phiếu nhập',reverse('admin_stock_list',args=['receipt'])),action(request,'view_stockissue','Phiếu xuất',reverse('admin_stock_list',args=['issue']))],description='Lịch sử bất biến; chỉ tạo qua nghiệp vụ đã xác nhận, không sửa/xóa trên giao diện.')


def document_model(kind):
    if kind=='receipt':
        return StockReceipt,'stockreceipt'
    if kind=='issue':
        return StockIssue,'stockissue'
    from django.http import Http404
    raise Http404


def require_document_permission(request,kind,verb):
    model,codename=document_model(kind)
    if not allowed(request,verb+'_'+codename):
        raise PermissionDenied('Bạn chưa được cấp quyền thao tác phiếu kho.')
    return model,codename


@capability_required('customers.view_stockmovement')
def stock_list(request,kind):
    model,codename=require_document_permission(request,kind,'view')
    return list_page(request,page='transactions',title='Phiếu nhập' if kind=='receipt' else 'Phiếu xuất',headers=['Mã','Ngày','Trạng thái','Nhà cung cấp','Người tạo'],
        queryset=model.objects.select_related('created_by',*(['supplier'] if kind=='receipt' else [])).filter(code__icontains=request.GET.get('q','')),cells=lambda x:[x.code,x.date,x.get_status_display(),x.supplier.name if kind=='receipt' else '—',x.created_by.username],
        actions=lambda x:[action(request,'view_'+codename,'Chi tiết',reverse('admin_stock_detail',args=[kind,x.pk]))],
        tools=[action(request,'add_'+codename,'Tạo phiếu',reverse('admin_stock_add',args=[kind])),action(request,'view_stockmovement','Lịch sử',reverse('admin_transactions'))])


@capability_required('customers.view_stockmovement')
def stock_add(request,kind):
    require_document_permission(request,kind,'add')
    return entry_form(request,form_class=ReceiptForm if kind=='receipt' else IssueForm,lines_class=ReceiptLines if kind=='receipt' else IssueLines,
        title='Tạo phiếu nhập' if kind=='receipt' else 'Tạo phiếu xuất',page='transactions',
        submit=lambda data,items:create_document(actor=request.user,kind=kind,items=items,**data),destination=lambda x:reverse('admin_stock_detail',args=[kind,x.pk]))


@capability_required('customers.view_stockmovement')
def stock_detail(request,kind,pk):
    model,codename=require_document_permission(request,kind,'view')
    document=get_object_or_404(model,pk=pk)
    return render(request,'admin/business/stock.html',dict(admin_page='transactions',document=document,kind=kind,items=document.items.select_related('ingredient'),can_confirm=allowed(request,'change_'+codename) and document.status=='DRAFT'))


@capability_required('customers.view_stockmovement')
@require_POST
def stock_confirm(request,kind,pk):
    model,_=require_document_permission(request,kind,'change')
    get_object_or_404(model,pk=pk)
    service_message(request,lambda:confirm_document(pk,kind=kind,actor=request.user))
    return redirect('admin_stock_detail',kind=kind,pk=pk)
