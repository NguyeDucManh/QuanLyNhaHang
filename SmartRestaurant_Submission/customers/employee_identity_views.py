from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction,IntegrityError
from django.core.exceptions import ValidationError
from django.shortcuts import render,redirect,get_object_or_404
from .rbac import role_required,capability_required,get_role
from .models import Employee
from .module07_forms import EmployeeForm
from .module07_views import save_resource

class OperationalEmployeeForm(EmployeeForm):
    confirmed=forms.BooleanField(label='Tôi xác nhận tài khoản, họ tên và mã là hồ sơ nhân viên thật; đã kiểm tra các dữ liệu liên quan.')
    def clean_employee_code(self):
        value=self.cleaned_data['employee_code'].strip()
        if value.upper().startswith('DEMO-'): raise forms.ValidationError('Nhập mã nhân viên thật, không dùng prefix DEMO-.')
        return value

@role_required('ADMIN','MANAGER')
@capability_required('customers.change_employee')
def employee_link(request,user_id):
    user=get_object_or_404(get_user_model(),pk=user_id,is_active=True)
    if get_role(user) not in ('ADMIN','MANAGER','STAFF') or user.username.startswith('demo_m07_'):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Không dùng tài khoản khách hoặc tài khoản seed cho hồ sơ vận hành.')
    employee=Employee.objects.filter(user=user).first()
    if not employee:
        from .rbac import has_capability
        from django.core.exceptions import PermissionDenied
        if not has_capability(request.user,'customers.add_employee'): raise PermissionDenied
    initial={'user':user.pk,'full_name':user.get_full_name() or user.username}
    form=OperationalEmployeeForm(request.POST if request.method=='POST' else None,instance=employee,initial=initial)
    form.fields['user'].queryset=get_user_model().objects.filter(pk=user.pk)
    form.fields['user'].disabled=True
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=user.pk)
                if not employee and Employee.objects.filter(user=user).exists(): raise ValidationError('Tài khoản vừa được liên kết; tải lại trang.')
                save_resource(form,'employee',request.user)
        except (ValidationError,IntegrityError) as exc:
            form.add_error(None,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Mã nhân viên/tài khoản đã được sử dụng.')
        else:
            messages.success(request,'Đã xác nhận hồ sơ nhân viên. Các ID và tham chiếu lịch/chấm công/lương/FaceID được giữ nguyên.')
            return redirect('ai_faces')
    return render(request,'admin/ai/employee_link.html',{'admin_page':'ai-faces','form':form,'target_user':user,'employee':employee})
