"""Read-only staff presentation queries, always scoped to the signed-in user."""
from datetime import date,timedelta
from decimal import Decimal
from django.db.models import Exists,OuterRef,Q,Count,Sum,F,DurationField
from django.utils import timezone
from django.urls import reverse
from .models import Employee,FaceEmbedding,WorkSchedule,Attendance,Payroll,Message,ConversationParticipant
from .rbac import get_role,has_capability

def identity(request):
    if not hasattr(request,'_portal_employee'):
        request._portal_employee=Employee.objects.filter(user=request.user).select_related('position','user','face_profile').annotate(has_face=Exists(FaceEmbedding.objects.filter(profile__employee_id=OuterRef('pk')))).first()
    return request._portal_employee

def unread_counts(user):
    participation=ConversationParticipant.objects.filter(user=user,conversation_id=OuterRef('conversation_id')).filter(Q(last_read_at__isnull=True)|Q(last_read_at__lt=OuterRef('created_at')))
    return dict(Message.objects.exclude(sender=user).filter(Exists(participation)).values('conversation_id').annotate(n=Count('pk')).values_list('conversation_id','n'))

def staff_context(request):
    role=get_role(request.user)
    if role not in ('STAFF','ADMIN','MANAGER'):return {'management_base':'index.html','personal_base':'customer/base.html'}
    staff=role=='STAFF';employee=identity(request)
    name=request.user.get_full_name() or (employee.full_name if employee and not employee.employee_code.upper().startswith('DEMO-') else request.user.username)
    nav=[{'title':title,'url':reverse(route)+suffix,'icon':icon} for title,route,suffix,icon in [('Tổng quan','staff_home','','home'),('Lịch làm','my_work','?tab=schedule','calendar'),('Chấm công','face_attendance','','clock'),('Lương của tôi','my_work','?tab=payroll','money'),('Tin nhắn','chat','','chat')]]
    for title,route,permission,icon in [('Thực đơn quản lý','admin_menu_list','view_menuitem','food'),('Bếp','admin_kitchen','view_orderitem','fire'),('Đơn hàng','admin_orders','view_order','order')]:
        if has_capability(request.user,'customers.'+permission) and (route!='admin_kitchen' or has_capability(request.user,'customers.view_order')):nav.append({'title':title,'url':reverse(route),'icon':icon})
    nav.append({'title':'Tài khoản','url':reverse('customer_profile'),'icon':'user'})
    return {'management_base':'staff/management.html' if staff else 'index.html','personal_base':'staff/base.html' if staff else 'customer/base.html','portal_identity_confirmed':bool(employee and not employee.employee_code.upper().startswith('DEMO-') and not employee.user.username.startswith('demo_m07_')),'portal_employee':employee,'portal_name':name,'portal_initial':name[:1].upper(),'portal_position':employee.position.name if employee else 'Chưa liên kết hồ sơ','staff_nav':nav,'portal_unread':sum(unread_counts(request.user).values()),'portal_today':timezone.localdate()}

def schedule_rows(query):
    now=timezone.now();rows=list(query.select_related('shift','attendance').order_by('start_at'))
    for row in rows:
        row.window_label='Sắp bắt đầu' if now<row.start_at else 'Đã kết thúc' if now>row.end_at else 'Đang trong ca'
        row.window_tone='waiting' if now<row.start_at else 'muted' if now>row.end_at else 'live'
    return rows

def dashboard(request):
    today=timezone.localdate();employee=identity(request)
    schedules=schedule_rows(WorkSchedule.objects.filter(employee__user=request.user,work_date=today).exclude(status='CANCELLED'))
    duration=Attendance.objects.filter(employee__user=request.user,work_date__gte=today.replace(day=1),work_date__lte=today,confirmed_at__isnull=False,check_in_time__isnull=False,check_out_time__isnull=False).aggregate(total=Sum(F('check_out_time')-F('check_in_time'),output_field=DurationField()))['total']
    hours=(Decimal(str(duration.total_seconds()))/Decimal(3600)).quantize(Decimal('.1')) if duration else Decimal(0)
    payroll=Payroll.objects.filter(employee__user=request.user,status__in=['APPROVED','PAID'],period__start_date__lte=today,period__end_date__gte=today).select_related('period').order_by('-period__start_date','-pk').first()
    current=next((row for row in schedules if row.start_at<=timezone.now()<=row.end_at and row.status=='APPROVED'),next((row for row in schedules if row.status=='APPROVED'),None))
    today_duration=sum(((a.check_out_time-a.check_in_time).total_seconds() for row in schedules if (a:=getattr(row,'attendance',None)) and a.confirmed_at and a.check_in_time and a.check_out_time),0)
    today_hours=(Decimal(str(today_duration))/Decimal(3600)).quantize(Decimal('.1'))
    return {'today_hours':today_hours,'today_schedules':schedules,'current_shift':current,'month_hours':hours,'current_payroll':payroll,'staff_page':'overview'}

def week_context(request):
    today=timezone.localdate()
    try:
        selected=date.fromisoformat(request.GET.get('week',''))
        if not 2000<=selected.year<=2100:raise ValueError
    except (ValueError,TypeError):selected=today
    start=selected-timedelta(days=selected.weekday());end=start+timedelta(days=6)
    rows=schedule_rows(WorkSchedule.objects.filter(employee__user=request.user,work_date__range=(start,end)))
    return {'week_start':start,'week_end':end,'previous_week':(start-timedelta(days=7)).isoformat(),'next_week':(start+timedelta(days=7)).isoformat(),'week_days':[{'date':start+timedelta(days=index),'rows':[row for row in rows if row.work_date==start+timedelta(days=index)]} for index in range(7)]}
