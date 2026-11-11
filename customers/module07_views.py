import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from django.db.models import Q,Avg
from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.core.paginator import Paginator
from .models import (Topping,Combo,ComboItem,Promotion,Review,RestaurantInfo,Position,Employee,Shift,WorkSchedule,Attendance,PayrollPeriod,Payroll,Order,Conversation,ConversationParticipant,MenuItem)
from .module07_forms import (ToppingForm,ComboForm,ComboItemForm,PromotionForm,RestaurantInfoForm,PositionForm,EmployeeForm,ShiftForm,ScheduleForm,AttendanceForm,PeriodForm,PayrollForm,ReviewForm,ChatForm)
from .rbac import has_capability,get_role,role_required,capability_required
from .business_views import list_page
from .business_service import save_validated
from . import personnel_service as hr

RESOURCES={
 'topping':(Topping,ToppingForm,'toppings','Topping',['name','price','is_available']),
 'combo':(Combo,ComboForm,'combos','Combo',['name','price','is_active']),
 'comboitem':(ComboItem,ComboItemForm,'combo-items','Thành phần combo',['combo','menu_item','quantity']),
 'promotion':(Promotion,PromotionForm,'promotions','Khuyến mãi / Voucher',['code','name','discount_type','discount_value','used_count','usage_limit','is_active']),
 'restaurantinfo':(RestaurantInfo,RestaurantInfoForm,'restaurant-info','Thông tin nhà hàng',['name','address','phone','email','is_active']),
 'position':(Position,PositionForm,'positions','Chức vụ',['name','description','is_active']),
 'employee':(Employee,EmployeeForm,'employees','Danh sách nhân viên',['employee_code','full_name','position','base_salary','employment_status','is_active']),
 'shift':(Shift,ShiftForm,'shifts','Ca làm việc',['name','start_time','end_time','required_staff','is_active']),
 'workschedule':(WorkSchedule,ScheduleForm,'schedules','Lịch làm việc',['employee','shift','work_date','start_at','end_at','status']),
 'attendance':(Attendance,AttendanceForm,'attendance','Chấm công',['employee','work_date','check_in_time','check_out_time','status','working_hours','confirmed_at']),
 'payrollperiod':(PayrollPeriod,PeriodForm,'periods','Kỳ lương',['name','start_date','end_date','standard_hours','overtime_multiplier']),
}

def require(user,perm):
    if not has_capability(user,'customers.'+perm): raise PermissionDenied

def nav_action(label,url,data=None): return {'label':label,'url':url,'post':data is not None,'data':data or {}}

@login_required
def resource_list(request,resource):
    if resource not in RESOURCES: raise PermissionDenied
    model,_,page,title,columns=RESOURCES[resource]; require(request.user,'view_'+resource)
    qs=model.objects.all().order_by('pk'); q=request.GET.get('q','').strip()
    if q:
        stringfields=[f.name for f in model._meta.fields if f.get_internal_type() in ('CharField','TextField')]
        query=Q()
        for field in stringfields: query|=Q(**{field+'__icontains':q})
        if stringfields: qs=qs.filter(query)
    def actions(obj):
        out=[]
        if has_capability(request.user,'customers.change_'+resource):
            out.append(nav_action('Sửa',reverse('module07_edit',args=[resource,obj.pk])))
            if resource=='workschedule':
                if obj.status=='DRAFT': out.append(nav_action('Phê duyệt',reverse('module07_state',args=[resource,obj.pk]),{'state':'APPROVED'}))
                if obj.status!='CANCELLED': out.append(nav_action('Hủy lịch',reverse('module07_state',args=[resource,obj.pk]),{'state':'CANCELLED'}))
            if resource=='attendance' and not obj.confirmed_at: out.append(nav_action('Xác nhận',reverse('module07_state',args=[resource,obj.pk]),{}))
        if resource=='combo': out.append(nav_action('Thành phần',reverse('module07_list',args=['comboitem'])+'?combo='+str(obj.pk)))
        if resource=='comboitem' and has_capability(request.user,'customers.delete_comboitem'): out.append(nav_action('Xóa thành phần',reverse('module07_state',args=[resource,obj.pk]),{}))
        return out
    if resource=='comboitem' and request.GET.get('combo','').isdigit(): qs=qs.filter(combo_id=request.GET['combo'])
    tools=[nav_action('Thêm',reverse('module07_add',args=[resource]))] if has_capability(request.user,'customers.add_'+resource) else []
    return list_page(request,page=page,title=title,headers=columns,queryset=qs,cells=lambda obj:[getattr(obj,key) for key in columns],actions=actions,tools=tools)

@transaction.atomic
def save_resource(form,resource,actor):
    if resource=='restaurantinfo' and get_role(actor)!='ADMIN':raise PermissionDenied
    model=RESOURCES[resource][0]
    if resource=='workschedule': return hr.save_schedule(form,actor=actor)
    if resource=='attendance': return hr.save_attendance(form,actor=actor)
    if resource=='comboitem':
        combo_id=form.cleaned_data['combo'].pk
        Combo.objects.select_for_update().get(pk=combo_id)
        if form.instance.pk and ComboItem.objects.get(pk=form.instance.pk).combo_id!=combo_id: raise ValidationError('Không đổi combo của dòng; xóa/thêm dòng phù hợp.')
    if form.instance.pk:
        old=model.objects.select_for_update().get(pk=form.instance.pk)
        if resource=='employee' and old.user_id!=form.cleaned_data['user'].pk: raise ValidationError('Không đổi tài khoản của Employee đã liên kết.')
        if resource=='shift' and old.workschedule_set.exclude(status='CANCELLED').exists() and (old.start_time!=form.cleaned_data['start_time'] or old.end_time!=form.cleaned_data['end_time']): raise ValidationError('Ca đã dùng trong lịch; tạo ca mới để đổi giờ.')
        if resource=='payrollperiod' and old.payroll_set.exists(): raise ValidationError('Kỳ đã có bảng lương, không đổi chính sách/ngày.')
        if resource=='promotion' and form.cleaned_data.get('usage_limit') is not None and form.cleaned_data['usage_limit']<old.used_count: raise ValidationError('Giới hạn thấp hơn lượt đã dùng.')
        if resource=='promotion': form.instance.used_count=old.used_count
    obj=form.save(commit=False)
    if resource=='employee':
        if get_role(obj.user) not in ('STAFF','MANAGER','ADMIN') or not obj.position.is_active: raise ValidationError('Chọn tài khoản quản trị/nhân viên và chức vụ đang hoạt động; không đổi Group tự động.')
    obj.full_clean(); obj.save(); form.save_m2m()
    return obj

@login_required
def resource_edit(request,resource,pk=None):
    if resource=='restaurantinfo' and get_role(request.user)!='ADMIN':raise PermissionDenied
    if resource not in RESOURCES: raise PermissionDenied
    model,Form,page,title,_=RESOURCES[resource]
    require(request.user,('change_' if pk else 'add_')+resource)
    obj=get_object_or_404(model,pk=pk) if pk else None
    form=Form(request.POST if request.method=='POST' else None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try: save_resource(form,resource,request.user)
        except (ValidationError,IntegrityError) as exc: form.add_error(None,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Dữ liệu trùng hoặc vi phạm ràng buộc.')
        else:
            messages.success(request,'Đã lưu.'); return redirect('module07_list',resource=resource)
    return render(request,'admin/module07/form.html',{'admin_page':page,'title':title,'form':form,'back':reverse('module07_list',args=[resource])})

@login_required
@require_POST
def resource_state(request,resource,pk):
    try:
        if resource=='workschedule': hr.schedule_state(pk,request.POST.get('state'),actor=request.user)
        elif resource=='attendance': hr.confirm_attendance(pk,actor=request.user)
        elif resource=='comboitem':
            require(request.user,'delete_comboitem')
            with transaction.atomic():
                obj=get_object_or_404(ComboItem,pk=pk); Combo.objects.select_for_update().get(pk=obj.combo_id); obj.delete()
        else: raise PermissionDenied
    except ValidationError as exc: messages.error(request,' '.join(exc.messages))
    else: messages.success(request,'Đã cập nhật.')
    return redirect('module07_list',resource=resource)

@role_required('STAFF','MANAGER','ADMIN')
def my_work(request):
    from .staff_portal import week_context
    schedules=WorkSchedule.objects.filter(employee__user=request.user).select_related('shift','employee').order_by('-work_date')[:100]
    attendance=Attendance.objects.filter(employee__user=request.user).select_related('employee','work_schedule').order_by('-work_date')[:100]
    payroll=Payroll.objects.filter(employee__user=request.user).select_related('period','employee').order_by('-period__start_date')[:100]
    return render(request,'staff/work.html',{'employee':Employee.objects.filter(user=request.user).first(),'schedules':schedules,'attendance':attendance,'payrolls':payroll,'staff_page':'work',**week_context(request)})

@login_required
@require_POST
def punch(request,pk):
    get_object_or_404(WorkSchedule,pk=pk,employee__user=request.user)
    messages.info(request,'Vui lòng dùng trang chấm công để xác thực theo chính sách FaceID/GPS.')
    return redirect('face_attendance')

@capability_required('customers.view_payroll')
def payroll_list(request):
    qs=Payroll.objects.select_related('employee','period').order_by('-pk')
    staff=get_role(request.user)=='STAFF'
    if staff:qs=qs.filter(employee__user=request.user)
    def actions(x):
        out=[nav_action('Chi tiết',reverse('payroll_detail',args=[x.pk]))]
        if not staff and has_capability(request.user,'customers.change_payroll'):
            if x.status=='DRAFT': out.append(nav_action('Duyệt',reverse('payroll_state',args=[x.pk]),{'state':'APPROVED'}))
            if x.status=='APPROVED': out.append(nav_action('Ghi nhận đã trả (thủ công)',reverse('payroll_state',args=[x.pk]),{'state':'PAID'}))
        return out
    tools=[]
    if not staff and has_capability(request.user,'customers.add_payroll'): tools.append(nav_action('Tính / tính lại',reverse('payroll_calculate')))
    if not staff and has_capability(request.user,'customers.view_payrollperiod'): tools.append(nav_action('Kỳ lương',reverse('module07_list',args=['payrollperiod'])))
    return list_page(request,page='payroll',title='Bảng lương',headers=['Nhân viên','Kỳ','Giờ','Tăng ca','Tổng','Thực nhận','Trạng thái'],queryset=qs,cells=lambda x:[x.employee,x.period,x.working_hours,x.overtime_hours,x.gross_salary,x.net_salary,x.status],actions=actions,tools=tools)

@capability_required('customers.add_payroll')
@role_required('ADMIN','MANAGER')
def payroll_calculate(request):
    form=PayrollForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        try: obj=hr.calculate_payroll(data.pop('employee').pk,data.pop('period').pk,actor=request.user,**data)
        except ValidationError as exc: form.add_error(None,exc)
        else: return redirect('payroll_detail',pk=obj.pk)
    return render(request,'admin/module07/form.html',{'admin_page':'payroll','title':'Tính lương theo giờ công đã xác nhận','form':form,'back':reverse('payroll_list')})

@login_required
def payroll_detail(request,pk):
    qs=Payroll.objects.select_related('employee','period')
    management=get_role(request.user) in ('ADMIN','MANAGER') and has_capability(request.user,'customers.view_payroll')
    if not management: qs=qs.filter(employee__user=request.user)
    obj=get_object_or_404(qs,pk=pk)
    return render(request,'admin/module07/payroll.html' if management else 'staff/payroll.html' if get_role(request.user)=='STAFF' else 'customer/module07/payroll.html',{'payroll':obj,'admin_page':'payroll','staff_page':'payroll'})

@login_required
@require_POST
@role_required('ADMIN','MANAGER')
def payroll_state(request,pk):
    try: hr.payroll_state(pk,request.POST.get('state'),actor=request.user)
    except ValidationError as exc: messages.error(request,' '.join(exc.messages))
    return redirect('payroll_list')

def combos(request):
    from .customer_booking_workspace import menu_context
    return render(request,'customer/module07/combos.html',{'combos':Combo.objects.filter(is_active=True).prefetch_related('items__menu_item'),'page':'combos',**menu_context(request)})

@require_POST
def combo_cart(request,pk):
    from .menu_service import session_cart
    session_cart(request)
    combo=get_object_or_404(Combo,pk=pk,is_active=True)
    cart=request.session.get('combo_cart',{}).copy()
    if request.POST.get('action')=='remove': cart.pop(str(pk),None)
    else: cart[str(pk)]=min(20,cart.get(str(pk),0)+1)
    request.session['combo_cart']=cart
    if request.POST.get('return_to')=='booking_menu': return redirect('/menu/?from=booking')
    if request.POST.get('return_to')=='booking': return redirect('/booking/?view=new')
    return redirect('customer_cart')

@login_required
def history(request,pk=None):
    qs=Order.objects.filter(customer=request.user).select_related('table','invoice').prefetch_related('items','invoice__payments').order_by('-pk')
    if pk:
        order=get_object_or_404(qs,pk=pk)
        return render(request,'customer/module07/history_detail.html',{'order':order,'review_form':ReviewForm(),'page':'history'})
    return render(request,'customer/module07/history.html',{'orders':qs[:100],'page':'history'})

@login_required
@require_POST
def voucher(request,pk):
    get_object_or_404(Order,pk=pk,customer=request.user)
    from .commerce_service import apply_voucher
    try: apply_voucher(pk,request.POST.get('code',''),actor=request.user)
    except ValidationError as exc: messages.error(request,' '.join(exc.messages))
    else: messages.success(request,'Đã áp dụng voucher.')
    return redirect('purchase_detail',pk=pk)

@capability_required('customers.change_order')
@capability_required('customers.add_orderitem')
@require_POST
def order_combo(request,pk):
    from .commerce_service import add_combo_to_order
    try:
        add_combo_to_order(pk,int(request.POST.get('combo','0')),int(request.POST.get('quantity','0')),actor=request.user)
    except (ValueError,ValidationError) as exc: messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Số lượng không hợp lệ.')
    return redirect('admin_order_detail',pk=pk)

@login_required
@require_POST
def review_create(request,pk):
    get_object_or_404(Order,pk=pk,customer=request.user)
    form=ReviewForm(request.POST)
    if form.is_valid():
        from .commerce_service import write_review
        data=form.cleaned_data
        try: write_review(actor=request.user,order_id=pk,menu_item_id=data.pop('menu_item'),**data)
        except (ValidationError,IntegrityError) as exc: messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Bạn đã đánh giá món này.')
        else: messages.success(request,'Đã lưu đánh giá.')
    else: messages.error(request,'Đánh giá không hợp lệ.')
    return redirect('purchase_detail',pk=pk)

@login_required
def reviews(request):
    management=has_capability(request.user,'customers.view_review')
    qs=Review.objects.select_related('customer','menu_item','order').order_by('-pk')
    if not management: qs=qs.filter(customer=request.user)
    rating=request.GET.get('rating','')
    if rating in ('1','2','3','4','5'): qs=qs.filter(rating=rating)
    q=request.GET.get('q',''); qs=qs.filter(Q(menu_item__name__icontains=q)|Q(customer__username__icontains=q))
    if management:
        return list_page(request,page='reviews',title='Đánh giá',headers=['Khách','Đơn','Món','Rating','Bình luận','Hiển thị'],queryset=qs,cells=lambda x:[x.customer,x.order.order_number,x.menu_item,x.rating,x.comment,x.is_visible],actions=lambda x:[nav_action('Ẩn / Hiện',reverse('review_visibility',args=[x.pk]),{})] if has_capability(request.user,'customers.change_review') else [],filters={'name':'rating','choices':[(str(i),str(i)) for i in range(1,6)],'selected':rating})
    return render(request,'customer/module07/reviews.html',{'reviews':qs[:100]})

@capability_required('customers.change_review')
@require_POST
def review_visibility(request,pk):
    with transaction.atomic():
        obj=get_object_or_404(Review.objects.select_for_update(),pk=pk); obj.is_visible=not obj.is_visible; obj.save(update_fields=['is_visible'])
    return redirect('reviews')

def about(request):
    return render(request,'customer/module07/about.html',{'restaurant':RestaurantInfo.objects.filter(is_active=True).first(),'page':'about'})

def offers(request):
    from django.db.models import F
    now=timezone.now()
    qs=Promotion.objects.filter(is_active=True,start_at__lte=now,end_at__gte=now).filter(Q(usage_limit__isnull=True)|Q(used_count__lt=F('usage_limit')))
    return render(request,'customer/module07/promotions.html',{'promotions':qs.order_by('code'),'page':'offers'})

@role_required('ADMIN','MANAGER')
def reports(request):
    from .report_service import report_data
    return render(request,'admin/module07/reports.html',{'sections':report_data(request.user),'admin_page':'reports'})

@login_required
def chat(request,pk=None):
    from .chat_service import chat_allowed,create_conversation,send_message
    if get_role(request.user) is None: raise PermissionDenied
    selected=None
    if pk:
        selected=get_object_or_404(Conversation,pk=pk,participants=request.user)
        if not chat_allowed(request.user,selected): raise PermissionDenied
    form=ChatForm(request.POST if request.method=='POST' and selected else None,initial={'request_key':uuid.uuid4()})
    if request.method=='POST':
        try:
            if selected and form.is_valid(): send_message(actor=request.user,conversation_id=selected.pk,**form.cleaned_data)
            elif not selected:
                recipient_id=int(request.POST.get('recipient','0'))
                selected=create_conversation(actor=request.user,recipient_id=recipient_id)
            else: raise ValidationError('Nội dung không hợp lệ.')
        except (ValidationError,ValueError,get_user_model().DoesNotExist) as exc:
            error=' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Người nhận không hợp lệ.'
            if request.headers.get('Accept')=='application/json': return JsonResponse({'error':error},status=400)
            messages.error(request,error)
        else:
            if request.headers.get('Accept')=='application/json': return JsonResponse({'request_key':str(uuid.uuid4())},status=201)
            return redirect('chat_detail',pk=selected.pk)
    from .staff_portal import unread_counts
    qs=Conversation.objects.filter(participants=request.user).prefetch_related('participants').order_by('-pk')
    unread=unread_counts(request.user)
    if get_role(request.user)=='CUSTOMER': qs=qs.filter(is_support=True)
    recipients=get_user_model().objects.filter(is_active=True).exclude(pk=request.user.pk)
    recipients=recipients.filter(Q(groups__name__in=['ADMIN','MANAGER','STAFF'])|Q(is_superuser=True)).distinct()
    pagination=Paginator(selected.messages.select_related('sender').order_by('-pk'),50).get_page(request.GET.get('page')) if selected else None
    if pagination and request.method=='GET':
        from .models import ConversationParticipant
        latest=max(message.created_at for message in pagination)
        ConversationParticipant.objects.filter(conversation=selected,user=request.user).filter(Q(last_read_at__isnull=True)|Q(last_read_at__lt=latest)).update(last_read_at=latest)
        unread=unread_counts(request.user)
    conversations=list(qs)
    for conversation in conversations:
        people=[user.get_full_name() or user.username for user in conversation.participants.all() if user.pk!=request.user.pk]
        conversation.display_name=', '.join(people) or str(conversation);conversation.unread_count=unread.get(conversation.pk,0)
    context={'conversations':conversations,'selected':selected,'chat_messages':pagination or [],'pagination':pagination,'form':form,'recipients':recipients,'admin_page':'messages'}
    if request.headers.get('X-Realtime-Partial')=='1' and selected:
        response=render(request,'shared/module07/chat_messages.html',context); response['Cache-Control']='no-store'; response['Vary']='Cookie, X-Realtime-Partial'; return response
    return render(request,'staff/chat.html' if get_role(request.user)=='STAFF' else 'admin/module07/chat.html' if get_role(request.user)!='CUSTOMER' else 'customer/module07/chat.html',context)
