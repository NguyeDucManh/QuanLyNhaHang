"""Manual schedules, attendance and payroll. Employee row is the common lock."""
from .audit_service import with_actor
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import Employee, Shift, WorkSchedule, Attendance, PayrollPeriod, Payroll
from .rbac import has_capability, get_role
from .business_service import save_validated, decimal_value

def require(actor, permission):
    if not has_capability(actor,'customers.'+permission): raise PermissionDenied

def employee_lock(pk):
    return Employee.objects.select_for_update().select_related('user').get(pk=pk)

def active_employee(e):
    if not e.is_active or not e.user.is_active or e.employment_status!='ACTIVE':
        raise ValidationError('Nhân viên không còn hoạt động.')

def period_frozen(employee_id, day):
    return Payroll.objects.filter(employee_id=employee_id,period__start_date__lte=day,period__end_date__gte=day,status__in=['APPROVED','PAID']).exists()

def check_attendance_overlap(obj):
    if obj.check_in_time and obj.check_out_time and Attendance.objects.filter(employee_id=obj.employee_id,check_in_time__lt=obj.check_out_time,check_out_time__gt=obj.check_in_time).exclude(pk=obj.pk).exists():
        raise ValidationError('Giờ công thực tế trùng với một lượt chấm công khác.')

def attendance_snapshot(rows):
    return [{'id':r.pk,'in':str(r.check_in_time),'out':str(r.check_out_time),'status':r.status,'confirmed_at':str(r.confirmed_at)} for r in rows]

@with_actor
@transaction.atomic
def save_schedule(form, *, actor, source='MANUAL'):
    require(actor,'change_workschedule' if form.instance.pk else 'add_workschedule')
    values=form.cleaned_data
    employee=employee_lock(values['employee'].pk); active_employee(employee)
    shift=Shift.objects.select_for_update().get(pk=values['shift'].pk)
    if not shift.is_active: raise ValidationError('Ca không hoạt động.')
    old=WorkSchedule.objects.select_for_update().get(pk=form.instance.pk) if form.instance.pk else None
    if old and (old.employee_id!=employee.pk or old.status!='DRAFT' or hasattr(old,'attendance')):
        raise ValidationError('Chỉ sửa lịch nháp chưa chấm công; không đổi nhân viên của lịch.')
    if period_frozen(employee.pk,values['work_date']): raise ValidationError('Kỳ lương đã khóa.')
    obj=form.save(commit=False); obj.employee=employee; obj.shift=shift
    if source not in ('MANUAL','AI'):raise ValidationError('Nguồn lịch không hợp lệ.')
    obj.source=old.source if old else source; obj.status='DRAFT'; obj.start_at,obj.end_at=obj.window()
    if WorkSchedule.objects.filter(employee=employee).exclude(status='CANCELLED').exclude(pk=obj.pk).filter(start_at__lt=obj.end_at,end_at__gt=obj.start_at).exists():
        raise ValidationError('Nhân viên đã có ca trùng thời gian (kể cả ca qua ngày).')
    return save_validated(obj)

@with_actor
@transaction.atomic
def schedule_state(pk, state, *, actor):
    require(actor,'change_workschedule')
    snapshot=WorkSchedule.objects.get(pk=pk); employee=employee_lock(snapshot.employee_id)
    obj=WorkSchedule.objects.select_for_update().get(pk=pk)
    if period_frozen(employee.pk,obj.work_date) or hasattr(obj,'attendance'): raise ValidationError('Lịch đã chấm công/kỳ lương khóa.')
    if state not in ('APPROVED','CANCELLED') or obj.status not in ('DRAFT','APPROVED') or state==obj.status: raise ValidationError('Chuyển trạng thái không hợp lệ.')
    if state=='APPROVED':
        active_employee(employee)
        if not obj.shift.is_active: raise ValidationError('Ca không hoạt động.')
        obj.approved_by=actor; obj.approved_at=timezone.now()
    obj.status=state
    return save_validated(obj)

@with_actor
@transaction.atomic
def punch(schedule_id, action, *, actor):
    snapshot=WorkSchedule.objects.get(pk=schedule_id)
    employee=employee_lock(snapshot.employee_id); active_employee(employee)
    if get_role(actor) not in ('STAFF','MANAGER','ADMIN') or employee.user_id!=actor.pk: raise PermissionDenied
    schedule=WorkSchedule.objects.select_for_update().get(pk=schedule_id)
    now=timezone.now()
    if schedule.status!='APPROVED' or now<schedule.start_at-timezone.timedelta(hours=1) or now>schedule.end_at+timezone.timedelta(hours=4):
        raise ValidationError('Chỉ chấm công cho ca đã duyệt trong cửa sổ từ 1 giờ trước đến 4 giờ sau ca.')
    if period_frozen(employee.pk,schedule.work_date): raise ValidationError('Kỳ lương đã khóa.')
    obj=Attendance.objects.select_for_update().filter(work_schedule=schedule).first()
    if obj and obj.confirmed_at: raise ValidationError('Chấm công đã xác nhận.')
    if action=='in':
        if obj: raise ValidationError('Đã check-in cho ca này.')
        obj=Attendance(employee=employee,work_schedule=schedule,work_date=schedule.work_date,check_in_time=now,status='LATE' if now>schedule.start_at else 'PRESENT')
    elif action=='out':
        if not obj or not obj.check_in_time or obj.check_out_time or now<=obj.check_in_time: raise ValidationError('Chưa check-in hoặc đã check-out.')
        obj.check_out_time=now
        if now<schedule.end_at: obj.status='EARLY_LEAVE'
    else: raise ValidationError('Thao tác không hợp lệ.')
    check_attendance_overlap(obj)
    return save_validated(obj)

@with_actor
@transaction.atomic
def save_attendance(form, *, actor):
    require(actor,'change_attendance' if form.instance.pk else 'add_attendance')
    schedule=form.cleaned_data['work_schedule']
    employee=employee_lock(schedule.employee_id); active_employee(employee)
    schedule=WorkSchedule.objects.select_for_update().get(pk=schedule.pk)
    if form.instance.pk:
        old=Attendance.objects.select_for_update().get(pk=form.instance.pk)
        if old.work_schedule_id!=schedule.pk: raise ValidationError('Không đổi ca của chấm công đã lưu.')
    if schedule.status!='APPROVED' or period_frozen(employee.pk,schedule.work_date): raise ValidationError('Ca chưa duyệt hoặc kỳ lương đã khóa.')
    obj=form.save(commit=False); obj.employee=employee; obj.work_date=schedule.work_date
    if obj.status in ('ABSENT','LEAVE'):
        if obj.check_in_time or obj.check_out_time: raise ValidationError('Vắng/nghỉ phép không có giờ công.')
    elif not obj.check_in_time or not obj.check_out_time: raise ValidationError('Chấm công thủ công cần đủ giờ vào/ra.')
    if obj.check_in_time and (obj.check_in_time<schedule.start_at-timezone.timedelta(hours=4) or obj.check_out_time>schedule.end_at+timezone.timedelta(hours=4)):
        raise ValidationError('Giờ công ngoài giới hạn ca; kiểm tra lại dữ liệu.')
    obj.confirmed_by=actor; obj.confirmed_at=timezone.now()
    check_attendance_overlap(obj)
    return save_validated(obj)

@with_actor
@transaction.atomic
def confirm_attendance(pk, *, actor):
    require(actor,'change_attendance')
    snap=Attendance.objects.get(pk=pk); employee=employee_lock(snap.employee_id); active_employee(employee)
    obj=Attendance.objects.select_for_update().get(pk=pk)
    if period_frozen(employee.pk,obj.work_date): raise ValidationError('Kỳ lương đã khóa.')
    if not obj.check_out_time and obj.status not in ('ABSENT','LEAVE'): raise ValidationError('Chưa đủ giờ vào/ra.')
    if obj.confirmed_at: raise ValidationError('Đã xác nhận.')
    obj.confirmed_by=actor; obj.confirmed_at=timezone.now()
    return save_validated(obj)

def money(n): return n.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

@with_actor
@transaction.atomic
def calculate_payroll(employee_id, period_id, *, actor, allowance=0, bonus=0, deduction=0):
    require(actor,'add_payroll'); require(actor,'change_payroll')
    employee=employee_lock(employee_id)
    period=PayrollPeriod.objects.select_for_update().get(pk=period_id)
    payroll=Payroll.objects.select_for_update().filter(employee=employee,period=period).first()
    if Payroll.objects.filter(employee=employee,period__start_date__lte=period.end_date,period__end_date__gte=period.start_date).exclude(period=period).exists():
        raise ValidationError('Nhân viên đã có bảng lương cho kỳ chồng lấn.')
    if payroll and payroll.status!='DRAFT': raise ValidationError('Bảng lương đã duyệt/ghi nhận trả, không thể tính lại.')
    rows=list(Attendance.objects.select_for_update(of=('self',)).select_related('work_schedule').filter(employee=employee,work_date__range=(period.start_date,period.end_date),confirmed_at__isnull=False).order_by('pk'))
    hours=Decimal(0); overtime=Decimal(0)
    for row in rows:
        if not row.check_in_time or not row.check_out_time or row.status in ('ABSENT','LEAVE'): continue
        seconds=max(0,(min(row.check_out_time,row.work_schedule.end_at)-max(row.check_in_time,row.work_schedule.start_at)).total_seconds())
        regular=Decimal(str(seconds))/Decimal(3600)
        hours+=regular; overtime+=max(Decimal(0),row.working_hours-regular)
    rate=employee.base_salary/period.standard_hours
    earned=money(rate*min(hours,period.standard_hours)); overtime_pay=money(rate*overtime*period.overtime_multiplier)
    allowance=decimal_value(allowance,2); bonus=decimal_value(bonus,2); deduction=decimal_value(deduction,2)
    gross=earned+overtime_pay+allowance+bonus
    if deduction>gross: raise ValidationError('Khấu trừ vượt lương tổng.')
    obj=payroll or Payroll(employee=employee,period=period)
    obj.base_salary=employee.base_salary; obj.working_hours=money(hours); obj.overtime_hours=money(overtime)
    obj.earned_base=earned; obj.overtime_pay=overtime_pay; obj.allowance=allowance; obj.bonus=bonus; obj.deduction=deduction
    obj.gross_salary=gross; obj.net_salary=gross-deduction
    obj.calculation_snapshot={'standard_hours':str(period.standard_hours),'overtime_multiplier':str(period.overtime_multiplier),'attendance':attendance_snapshot(rows)}
    return save_validated(obj)

@with_actor
@transaction.atomic
def payroll_state(pk,state,*,actor):
    require(actor,'change_payroll')
    snap=Payroll.objects.get(pk=pk); employee=employee_lock(snap.employee_id)
    obj=Payroll.objects.select_for_update().get(pk=pk)
    if state=='APPROVED' and obj.status=='DRAFT':
        rows=list(Attendance.objects.filter(employee=employee,work_date__range=(obj.period.start_date,obj.period.end_date),confirmed_at__isnull=False).order_by('pk'))
        if obj.base_salary!=employee.base_salary or obj.calculation_snapshot['attendance']!=attendance_snapshot(rows):
            raise ValidationError('Lương cơ sở/giờ công đã đổi; tính lại trước khi duyệt.')
        obj.approved_by=actor; obj.approved_at=timezone.now()
    elif state=='PAID' and obj.status=='APPROVED': obj.paid_at=timezone.now()
    else: raise ValidationError('Bảng lương không cho phép chuyển trạng thái này.')
    obj.status=state
    return save_validated(obj)
