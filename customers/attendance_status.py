"""Own-account attendance readiness; same time window as personnel_service.punch."""
from django.utils import timezone
from .employee_identity import operational_employees
from .models import WorkSchedule


def attendance_context(user):
    now = timezone.now()
    employee = operational_employees().select_related('face_profile', 'position').filter(user=user).first()
    schedules = []
    reason, code = 'Tài khoản chưa liên kết hồ sơ nhân viên đang hoạt động.', 'NO_EMPLOYEE'
    if employee:
        own = WorkSchedule.objects.filter(employee=employee)
        schedules = list(own.filter(status='APPROVED', start_at__lte=now+timezone.timedelta(hours=1),
            end_at__gte=now-timezone.timedelta(hours=4)).select_related('shift').order_by('start_at')[:20])
        if schedules:
            reason, code = 'Có ca đã duyệt trong thời gian cho phép chấm công.', 'AVAILABLE'
        elif own.filter(status='DRAFT', start_at__lte=now+timezone.timedelta(hours=1), end_at__gte=now-timezone.timedelta(hours=4)).exists():
            reason, code = 'Ca làm trong thời gian này đang ở trạng thái nháp, chưa được quản lý duyệt.', 'UNAPPROVED'
        elif own.filter(status='APPROVED').exists():
            reason, code = 'Có ca đã duyệt nhưng ngoài thời gian chấm công (từ 1 giờ trước đến 4 giờ sau ca).', 'OUTSIDE_WINDOW'
        elif own.filter(status='DRAFT').exists():
            reason, code = 'Ca làm đang ở trạng thái nháp, chưa được quản lý duyệt.', 'UNAPPROVED'
        elif own.exists():
            reason, code = 'Các ca hiện có đã hủy; chưa có ca được duyệt để chấm công.', 'CANCELLED'
        else:
            reason, code = 'Bạn chưa được xếp ca làm. Liên hệ quản lý tạo và duyệt ca.', 'NO_SCHEDULE'
    return {'employee': employee, 'schedules': schedules, 'schedule_reason': reason, 'schedule_status': code}
