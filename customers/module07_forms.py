from django import forms
from django.contrib.auth import get_user_model
from .models import (Topping,Combo,ComboItem,Promotion,RestaurantInfo,Position,Employee,Shift,WorkSchedule,Attendance,PayrollPeriod)
from .ui_labels import LABELS,display_label

def model_form(model,fields):
    form=forms.modelform_factory(model,fields=fields,labels={name:LABELS[name] for name in fields if name in LABELS},error_messages={name:{'unique':'Giá trị này đã được sử dụng.'} for name in fields},widgets={f.name:forms.DateInput(attrs={'type':'date'}) if f.get_internal_type()=='DateField' else forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M') if f.get_internal_type()=='DateTimeField' else forms.TimeInput(attrs={'type':'time'}) for f in model._meta.fields if f.get_internal_type() in ('DateField','DateTimeField','TimeField')})
    for field in form.base_fields.values():
        if isinstance(field,forms.ChoiceField) and not isinstance(field,forms.ModelChoiceField):field.choices=[(value,display_label(label)) for value,label in field.choices]
        if isinstance(field,forms.ModelChoiceField) and field.queryset.model is WorkSchedule:
            field.label_from_instance=lambda obj:f'{obj.employee.full_name} · {obj.work_date:%d/%m/%Y} · {obj.shift}'
    return form

ToppingForm=model_form(Topping,['name','price','is_available','menu_items'])
ComboForm=model_form(Combo,['name','description','price','is_active'])
ComboItemForm=model_form(ComboItem,['combo','menu_item','quantity'])
PromotionForm=model_form(Promotion,['code','name','discount_type','discount_value','min_order_amount','max_discount_amount','start_at','end_at','usage_limit','is_active'])
RestaurantInfoForm=model_form(RestaurantInfo,['name','description','address','phone','email','opening_time','closing_time','latitude','longitude','is_active'])
PositionForm=model_form(Position,['name','description','is_active'])
EmployeeForm=model_form(Employee,['user','employee_code','full_name','phone','position','hire_date','employment_status','base_salary','is_active'])
ShiftForm=model_form(Shift,['name','start_time','end_time','required_staff','is_active'])
ScheduleForm=model_form(WorkSchedule,['employee','shift','work_date','note'])
AttendanceForm=model_form(Attendance,['work_schedule','check_in_time','check_out_time','status','note'])
PeriodForm=model_form(PayrollPeriod,['name','start_date','end_date','standard_hours','overtime_multiplier'])

class PayrollForm(forms.Form):
    employee=forms.ModelChoiceField(Employee.objects.all(),label='Nhân viên')
    period=forms.ModelChoiceField(PayrollPeriod.objects.all(),label='Kỳ lương')
    allowance=forms.DecimalField(min_value=0,max_digits=14,decimal_places=2,initial=0,label='Phụ cấp')
    bonus=forms.DecimalField(min_value=0,max_digits=14,decimal_places=2,initial=0,label='Thưởng')
    deduction=forms.DecimalField(min_value=0,max_digits=14,decimal_places=2,initial=0,label='Khấu trừ')

class ReviewForm(forms.Form):
    menu_item=forms.IntegerField(min_value=1)
    rating=forms.IntegerField(min_value=1,max_value=5)
    comment=forms.CharField(max_length=2000,required=False,widget=forms.Textarea)

class ChatForm(forms.Form):
    content=forms.CharField(max_length=2000,widget=forms.Textarea(attrs={'rows':3}))
    request_key=forms.UUIDField(widget=forms.HiddenInput)
