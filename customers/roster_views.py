from datetime import date,datetime,timedelta
import json
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,connection
from django.http import HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import Employee,Position,Shift,RosterWeek,ShiftRegistration
from .rbac import role_required
from .ga_service import require_ga
from .roster_service import monday,validate_rules,save_registration,preview_roster,apply_roster


def schema_ready():
    return {'customers_rosterweek','customers_shiftregistration'}.issubset(connection.introspection.table_names())


class RegistrationForm(forms.Form):
    def __init__(self,*args,week,initial_availability=None,**kwargs):
        super().__init__(*args,**kwargs);self.week=week
        for i in range(7):
            day=(week.start_date+timedelta(days=i)).isoformat();label_day=(week.start_date+timedelta(days=i)).strftime('%d/%m/%Y');entry=(initial_availability or {}).get(day,{})
            self.fields['busy_'+str(i)]=forms.BooleanField(required=False,label='Không thể làm '+label_day,initial=entry.get('unavailable',False))
            self.fields['shifts_'+str(i)]=forms.ModelMultipleChoiceField(Shift.objects.filter(is_active=True),required=False,label='Ca mong muốn '+label_day,widget=forms.CheckboxSelectMultiple,initial=entry.get('shifts',[]))
            self.fields['priority_'+str(i)]=forms.TypedChoiceField(choices=[(1,'Ưu tiên cao'),(2,'Bình thường'),(3,'Ưu tiên thấp')],coerce=int,label='Mức ưu tiên '+label_day,initial=entry.get('priority',2))
    def availability(self):
        values={}
        for i in range(7):
            busy=self.cleaned_data['busy_'+str(i)];shifts=list(self.cleaned_data['shifts_'+str(i)].values_list('pk',flat=True))
            if busy and shifts:raise ValidationError('Ngày không thể làm không được chọn ca.')
            values[(self.week.start_date+timedelta(days=i)).isoformat()]={'unavailable':busy,'shifts':shifts,'priority':self.cleaned_data['priority_'+str(i)]}
        return values


class WeekForm(forms.Form):
    min_rest_hours=forms.IntegerField(min_value=11,max_value=48,initial=11,label='Nghỉ tối thiểu giữa hai ca (giờ)')
    max_weekly_hours=forms.IntegerField(min_value=1,max_value=48,initial=48,label='Giờ làm tối đa mỗi tuần')
    max_weekly_shifts=forms.IntegerField(min_value=1,max_value=6,initial=6,label='Số ca tối đa mỗi tuần')
    registration_deadline=forms.DateTimeField(label='Hạn chỉnh sửa đăng ký',widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    def __init__(self,*args,start,**kwargs):
        super().__init__(*args,**kwargs);self.start=start
        self.fields['registration_deadline'].initial=timezone.make_aware(datetime.combine(start-timedelta(days=1),datetime.min.time().replace(hour=18)))
        self.shifts=list(Shift.objects.filter(is_active=True))
        for shift in self.shifts:
            self.fields['positions_'+str(shift.pk)]=forms.ModelMultipleChoiceField(Position.objects.filter(is_active=True),label='Chức vụ phù hợp với '+shift.name,widget=forms.CheckboxSelectMultiple)
    def clean_registration_deadline(self):
        deadline=self.cleaned_data['registration_deadline']
        if not timezone.now()<deadline<timezone.make_aware(datetime.combine(self.start,datetime.min.time())):raise forms.ValidationError('Hạn đăng ký phải ở tương lai và trước đầu tuần.')
        return deadline
    def rules(self):
        return {**{k:self.cleaned_data[k] for k in ('min_rest_hours','max_weekly_hours','max_weekly_shifts')},
            'allowed_positions':{str(s.pk):list(self.cleaned_data['positions_'+str(s.pk)].values_list('pk',flat=True)) for s in self.shifts}}


@role_required('STAFF','MANAGER','ADMIN')
@require_http_methods(['GET','POST'])
def registration(request):
    if not schema_ready():return render(request,'staff/roster_registration.html',{'schema_missing':True},status=503)
    employee=Employee.objects.filter(user=request.user).first()
    if not employee:return render(request,'staff/roster_registration.html',{'no_employee':True},status=403)
    start=monday(timezone.localdate())+timedelta(days=7)
    week=RosterWeek.objects.filter(start_date=start).first()
    if not week:return render(request,'staff/roster_registration.html',{'week_unopened':True,'start':start})
    current=ShiftRegistration.objects.filter(employee=employee,week=week).first()
    form=RegistrationForm(request.POST or None,week=week,initial_availability=current.availability if current else {})
    if request.method=='POST':
        try:
            if request.POST.get('action')=='delete':save_registration(week.pk,employee,{},actor=request.user,delete=True)
            elif form.is_valid():save_registration(week.pk,employee,form.availability(),actor=request.user)
            else:return render(request,'staff/roster_registration.html',{'form':form,'week':week})
        except ValidationError as exc:form.add_error(None,exc)
        else:
            messages.success(request,'Đã cập nhật đăng ký; đây chưa phải lịch chính thức.')
            return redirect('shift_registration')
    return render(request,'staff/roster_registration.html',{'form':form,'week':week,'closed':week.status!='OPEN' or timezone.now()>=week.registration_deadline})


@role_required('ADMIN','MANAGER')
@require_http_methods(['GET','POST'])
def management(request):
    require_ga(request.user)
    if not schema_ready():return render(request,'admin/restaurant/roster.html',{'schema_missing':True,'admin_page':'schedules'},status=503)
    start=monday(timezone.localdate())+timedelta(days=7)
    week=RosterWeek.objects.filter(start_date=start).first();preview=None
    week_form=WeekForm(request.POST if request.POST.get('action')=='open' else None,start=start)
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='open':
                if week:raise ValidationError('Tuần đã mở; không ghi đè chính sách hoặc đăng ký hiện hữu.')
                if not week_form.is_valid():raise ValidationError('Kiểm tra lại hạn đăng ký, giới hạn và chuyên môn theo ca.')
                rules=week_form.rules();deadline=week_form.cleaned_data['registration_deadline']
                with transaction.atomic():
                    week,created=RosterWeek.objects.get_or_create(start_date=start,defaults={'registration_deadline':deadline,'rules':rules,'created_by':request.user})
                    if not created:raise ValidationError('Tuần đã được mở bởi quản lý khác; không ghi đè.')
                    from .audit_service import record
                    record(action='ROSTER_WEEK_OPENED',entity=week,actor=request.user,after={'start_date':start.isoformat(),'deadline':deadline.isoformat()})
                messages.success(request,'Đã mở tuần đăng ký.')
            elif action=='preview':
                if not week:raise ValidationError('Chưa mở tuần đăng ký.')
                preview=preview_roster(start,start+timedelta(days=6),week.rules,week=week)
            elif action=='apply':
                created=apply_roster(request.POST.get('token',''),actor=request.user,approved_digest=request.POST.get('approved_digest',''),approve_current=True)
                messages.success(request,f'Đã duyệt {len(created)} ca; không tạo chấm công.')
                return redirect('roster_management')
            else:raise ValidationError('Thao tác không hợp lệ.')
        except (ValidationError,ValueError,TypeError) as exc:
            messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Dữ liệu JSON không hợp lệ.')
    registrations=list(week.registrations.select_related('employee')) if week else []
    return render(request,'admin/restaurant/roster.html',{'week':week,'registrations':registrations,'preview':preview,'start':start,'week_form':week_form,'admin_page':'schedules'})
