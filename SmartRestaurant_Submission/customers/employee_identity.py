"""Operational identity rules; preserve historical seed records and HR references."""
from django.db.models import Q
from .models import Employee
from .rbac import get_role

DEMO_EMPLOYEE = Q(employee_code__istartswith='DEMO-')

def operational_employees():
    return Employee.objects.exclude(DEMO_EMPLOYEE).exclude(user__username__startswith='demo_m07_').filter(is_active=True, user__is_active=True, employment_status='ACTIVE').filter(Q(user__is_superuser=True)|Q(user__groups__name__in=['ADMIN','MANAGER','STAFF'])).distinct()

def require_operational(employee):
    from django.core.exceptions import ValidationError
    from .personnel_service import active_employee
    active_employee(employee)
    if employee.employee_code.upper().startswith('DEMO-') or employee.user.username.startswith('demo_m07_'):
        raise ValidationError('Hồ sơ seed không dùng cho FaceID vận hành. Quản lý cần xác nhận hồ sơ nhân viên thật.')
    if get_role(employee.user) not in ('ADMIN','MANAGER','STAFF'):
        raise ValidationError('Tài khoản không có vai trò nhân viên hợp lệ.')
    return employee

def account_audit():
    from django.contrib.auth import get_user_model
    from .models import FaceProfile, FaceEmbedding
    users=get_user_model().objects.prefetch_related('groups','user_permissions').order_by('pk')
    accounts=[]
    for user in users:
        employee=Employee.objects.filter(user=user).first()
        accounts.append({'id':user.pk,'username':user.username,'name':user.get_full_name(),'active':user.is_active,'role':get_role(user),'groups':list(user.groups.values_list('name',flat=True)),'group_permissions':list(user.groups.values_list('permissions__codename',flat=True).distinct()),'direct_permissions':list(user.user_permissions.values_list('codename',flat=True)),'employee_id':employee.pk if employee else None,'employee_code':employee.employee_code if employee else None,'seed_account':user.username.startswith('demo_m07_')})
    demo=[]
    for employee in Employee.objects.filter(DEMO_EMPLOYEE).select_related('user','position'):
        refs={relation.related_model.__name__:relation.related_model.objects.filter(**{relation.field.name:employee}).count() for relation in Employee._meta.related_objects}
        refs['FaceEmbedding']=FaceEmbedding.objects.filter(profile__employee=employee).count()
        demo.append({'id':employee.pk,'user_id':employee.user_id,'username':employee.user.username,'code':employee.employee_code,'position':employee.position.name,'references':refs})
    return {'total_users':len(accounts),'active_users':sum(a['active'] for a in accounts),'employee_profiles':Employee.objects.count(),'operational_employees':operational_employees().count(),'face_profiles':FaceProfile.objects.count(),'face_embeddings':FaceEmbedding.objects.count(),'accounts':accounts,'users_without_employee':[a['username'] for a in accounts if a['active'] and a['role'] in ('STAFF','MANAGER','ADMIN') and not a['seed_account'] and a['employee_id'] is None],'demo_employees':demo,'employees_without_valid_user':Employee.objects.filter(user__isnull=True).count()}
