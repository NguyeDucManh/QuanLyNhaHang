"""Bounded presentation queries; reservation allocation stays in booking_service."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone
from .forms import BookingForm
from .models import Booking
from .booking_service import booking_window,lock_areas,find_available_table

class ManagerBookingForm(BookingForm):
    customer=forms.ModelChoiceField(queryset=get_user_model().objects.none(),required=False,label='Tài khoản khách (tùy chọn)')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['customer'].queryset=get_user_model().objects.filter(is_active=True,groups__name='CUSTOMER').distinct().order_by('username')
        self.fields['customer'].empty_label='Khách đến trực tiếp'

def booking_panel(request,queryset,*,customer=False):
    tab=request.GET.get('tab','today' if not customer else 'upcoming')
    valid={'today','upcoming','history','cancelled','completed'}
    if tab not in valid:tab='today' if not customer else 'upcoming'
    today=timezone.localdate()
    queryset=queryset.select_related('user','table__area','service_order__invoice','deposit').prefetch_related('preorder_items', 'service_order__invoice__payments')
    if tab=='today':queryset=queryset.filter(date=today)
    elif tab=='upcoming':queryset=queryset.filter(date__gte=today,status__in=['PENDING','CONFIRMED','PENDING_DEPOSIT'])
    elif tab=='cancelled':queryset=queryset.filter(status='CANCELLED')
    elif tab=='completed':queryset=queryset.filter(status='COMPLETED')
    elif not customer:queryset=queryset.filter(Q(date__lt=today)|Q(status='COMPLETED'))
    status=request.GET.get('status','');query=request.GET.get('q','').strip()[:100]
    if status in Booking.Status.values:queryset=queryset.filter(status=status)
    if query:queryset=queryset.filter(Q(name__icontains=query)|Q(phone__icontains=query))
    for key,lookup in [('from','date__gte'),('to','date__lte')]:
        try:
            value=forms.DateField().clean(request.GET.get(key))
            if value:queryset=queryset.filter(**{lookup:value})
        except ValidationError:pass
    pagination=Paginator(queryset.order_by('date','time','pk') if tab in {'today','upcoming'} else queryset.order_by('-date','-time','-pk'),15).get_page(request.GET.get('page'))
    from .booking_service import TRANSITIONS
    rows=[{'booking':b,'transitions':[(s,Booking.Status(s).label) for s in TRANSITIONS.get(b.status,())]} for b in pagination]
    tabs=[('upcoming','Sắp tới'),('completed','Đã hoàn thành'),('cancelled','Đã hủy'),('history','Lịch sử')] if customer else [('today','Hôm nay'),('upcoming','Sắp tới'),('history','Lịch sử'),('cancelled','Đã hủy')]
    return {'booking_tab':tab,'booking_tabs':tabs,'workspace_rows':rows,'booking_pagination':pagination,'booking_query':query,'booking_status':status,'booking_statuses':Booking.Status.choices}

@login_required
def availability(request):
    try:
        fields=BookingForm().fields
        date=fields['date'].clean(request.GET.get('date'));time=fields['time'].clean(request.GET.get('time'));guests=fields['guests'].clean(request.GET.get('guests'))
        if not 1<=guests<=20:raise ValidationError('Chọn từ 1 đến 20 khách.')
        start,end=booking_window(date,time)
        with transaction.atomic():table=find_available_table(start,end,guests,lock_areas())
        return JsonResponse({'available':True,'message':'Có bàn phù hợp. Hệ thống sẽ tự chọn bàn khi lưu đặt bàn; xem trước không giữ chỗ.'})
    except ValidationError as error:return JsonResponse({'available':False,'message':' '.join(error.messages)},status=400)
