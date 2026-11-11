from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect
from django.utils import timezone
from .models import RestaurantTable, WorkSchedule, TableServiceAssignment
from .table_assignment_service import enabled, can_assign, active_assignments, assign_table
from .employee_identity import operational_employees


class AssignmentForm(forms.Form):
    table=forms.ModelChoiceField(queryset=RestaurantTable.objects.none(),label='Bàn')
    schedule=forms.ModelChoiceField(queryset=WorkSchedule.objects.none(),label='Nhân viên · Ca đã duyệt')
    start_at=forms.DateTimeField(required=False,label='Bắt đầu (bỏ trống: bây giờ/đầu ca)',widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    end_at=forms.DateTimeField(required=False,label='Kết thúc (bỏ trống: cuối ca)',widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    replace=forms.BooleanField(required=False,label='Thay thế phân công trùng từ thời điểm bắt đầu mới; không tự khôi phục phân công cũ')

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['table'].queryset=RestaurantTable.objects.select_related('area').filter(is_active=True,area__is_active=True).exclude(status='MAINTENANCE').order_by('area__name','code')
        self.fields['schedule'].queryset=WorkSchedule.objects.select_related('employee','shift').filter(status='APPROVED',shift__is_active=True,end_at__gt=timezone.now(),employee__in=operational_employees()).order_by('start_at','employee__full_name')
        self.fields['schedule'].label_from_instance=lambda s:f'{s.employee.full_name} · {s.shift.name} · {timezone.localtime(s.start_at):%d/%m/%Y %H:%M}–{timezone.localtime(s.end_at):%H:%M}'


@login_required
def assignments(request):
    if not can_assign(request.user):raise PermissionDenied
    form=AssignmentForm(request.POST if request.method=='POST' else None) if enabled() else None
    if request.method=='POST' and form and form.is_valid():
        data=form.cleaned_data
        try:assign_table(actor=request.user,table_id=data['table'].pk,schedule_id=data['schedule'].pk,start_at=data['start_at'],end_at=data['end_at'],replace=data['replace'])
        except ValidationError as error:form.add_error(None,error)
        else:
            messages.success(request,'Đã lưu phân công và nhật ký.');return redirect('table_assignments')
    current={a.table_id:a for a in active_assignments().select_related('work_schedule__employee','work_schedule__shift')} if enabled() else {}
    tables=list(RestaurantTable.objects.select_related('area').order_by('area__name','code'))
    for table in tables:table.service_assignment=current.get(table.pk)
    history=list(TableServiceAssignment.objects.select_related('table__area','work_schedule__employee','work_schedule__shift','assigned_by').order_by('-created_at','-pk')[:100]) if enabled() else []
    return render(request,'admin/restaurant/table_assignments.html',{'form':form,'assignment_tables':tables,'assignment_history':history,'assignments_enabled':enabled(),'admin_page':'tables'},status=400 if request.method=='POST' else 200)
