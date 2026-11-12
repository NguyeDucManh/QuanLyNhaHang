"""No seed or automatic assignments. Table row locks serialize competing changes."""
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from .models import TableServiceAssignment, RestaurantTable, WorkSchedule, Employee
from .rbac import get_role, has_capability
from .employee_identity import require_operational, operational_employees
from .audit_service import record


def enabled():
    return getattr(settings,'TABLE_SERVICE_ASSIGNMENTS_ENABLED',False)


def can_assign(user):
    return get_role(user) in ('ADMIN','MANAGER') and all(has_capability(user,'customers.'+p)
        for p in ('view_restauranttable','change_restauranttable','view_workschedule','view_employee'))


def active_assignments(at=None):
    at=at or timezone.now()
    return TableServiceAssignment.objects.filter(start_at__lte=at,end_at__gt=at,
        work_schedule__employee__in=operational_employees(),
        work_schedule__status='APPROVED',work_schedule__shift__is_active=True,
        work_schedule__start_at__lte=at,work_schedule__end_at__gt=at,
        work_schedule__employee__is_active=True,work_schedule__employee__user__is_active=True,
        work_schedule__employee__employment_status='ACTIVE').filter(Q(revoked_at__isnull=True)|Q(revoked_at__gt=at))


def staff_table_ids(user):
    if not enabled() or get_role(user)!='STAFF':return None
    return active_assignments().filter(work_schedule__employee__user=user).values_list('table_id',flat=True)


@transaction.atomic
def assign_table(*,actor,table_id,schedule_id,start_at=None,end_at=None,replace=False):
    if not enabled():raise ValidationError('Phân công bàn chưa được bật; cần duyệt migration/cấu hình trước.')
    if not can_assign(actor):raise PermissionDenied
    snapshot=WorkSchedule.objects.get(pk=schedule_id)
    # Same employee -> schedule order as personnel_service, then table.
    employee=Employee.objects.select_for_update(of=('self',)).select_related('user').get(pk=snapshot.employee_id)
    require_operational(employee)
    schedule=WorkSchedule.objects.select_for_update(of=('self',)).select_related('shift').get(pk=schedule_id)
    table=RestaurantTable.objects.select_for_update(of=('self',)).select_related('area').get(pk=table_id)
    now=timezone.now();start_at=start_at or max(now,schedule.start_at);end_at=end_at or schedule.end_at
    if schedule.status!='APPROVED' or not schedule.shift.is_active:raise ValidationError('Chỉ phân công ca đang hoạt động và đã duyệt.')
    if not table.is_active or not table.area.is_active or table.status=='MAINTENANCE':raise ValidationError('Bàn/khu vực không phục vụ.')
    if any(timezone.is_naive(v) for v in (start_at,end_at)) or not schedule.start_at<=start_at<end_at<=schedule.end_at or end_at<=now:
        raise ValidationError('Khoảng phân công phải nằm trong ca hợp lệ, chưa kết thúc.')
    if start_at < now-timezone.timedelta(seconds=2):raise ValidationError('Không phân công hồi tố.')
    overlaps=list(TableServiceAssignment.objects.select_for_update(of=('self',)).filter(table=table,
        work_schedule__status='APPROVED',work_schedule__shift__is_active=True,work_schedule__employee__in=operational_employees(),
        start_at__lt=end_at,end_at__gt=start_at).filter(Q(revoked_at__isnull=True)|Q(revoked_at__gt=start_at)).filter(Q(revoked_at__isnull=True)|Q(revoked_at__gt=F('start_at'))))
    if len(overlaps)==1 and overlaps[0].work_schedule_id==schedule.pk and overlaps[0].start_at<=start_at and overlaps[0].end_at>=end_at and (overlaps[0].revoked_at is None or overlaps[0].revoked_at>=end_at):
        return overlaps[0]
    if overlaps and not replace:raise ValidationError('Bàn đã có người phụ trách trong khoảng này; cần xác nhận thay thế.')
    for old in overlaps:
        old.revoked_at=start_at;old.save(update_fields=['revoked_at'])
        record(actor=actor,action='TABLE_ASSIGNMENT_REPLACED',entity=old,
            before={'schedule_id':old.work_schedule_id,'table_id':table.pk},after={'effective_at':start_at.isoformat(),'replacement_schedule_id':schedule.pk})
    assignment=TableServiceAssignment(table=table,work_schedule=schedule,start_at=start_at,end_at=end_at,assigned_by=actor)
    assignment.full_clean();assignment.save()
    record(actor=actor,action='TABLE_ASSIGNED',entity=assignment,after={'table_id':table.pk,'schedule_id':schedule.pk,'employee_id':employee.pk,'start_at':start_at.isoformat(),'end_at':end_at.isoformat()})
    return assignment
