"""Face-only attendance. Historical location tables are retained, never consulted."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Employee, WorkSchedule, FaceAudit
from .personnel_service import punch


def secure_punch(*, actor, schedule_id, action, frames=None, challenge_id=None):
    from .employee_identity import require_operational
    from .ai.face.face_enrollment_service import verify_identity
    from .ai.face.policy import verification_options, effective_threshold, face_result
    employee = Employee.objects.select_related('user').filter(user=actor).first()
    if not employee:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên.')
    require_operational(employee)
    if action not in ('in', 'out'):
        raise ValidationError('Thao tác chấm công không hợp lệ.')
    schedule = WorkSchedule.objects.filter(pk=schedule_id, employee=employee).first()
    if not schedule:
        raise PermissionDenied('Ca làm không thuộc tài khoản đang đăng nhập.')
    now = timezone.now()
    if schedule.status != 'APPROVED' or not schedule.start_at-timezone.timedelta(hours=1) <= now <= schedule.end_at+timezone.timedelta(hours=4):
        raise ValidationError('Chỉ chấm công cho ca đã duyệt trong cửa sổ từ 1 giờ trước đến 4 giờ sau ca.')
    profile = None
    score = None
    try:
        if not hasattr(employee, 'face_profile') or not employee.face_profile.samples.exists():
            raise ValidationError('Chưa đăng ký FaceID.')
        profile, score = verify_identity(actor=actor, challenge_id=challenge_id, frames=frames, **verification_options())
        if profile.employee_id != employee.pk:
            raise PermissionDenied('Khuôn mặt không thuộc tài khoản đang đăng nhập.')
        evidence = face_result(profile, score)
        # punch locks/revalidates employee, schedule, payroll period and duplicates.
        with transaction.atomic():
            result = punch(schedule_id, action, actor=actor)
            FaceAudit.objects.create(actor=actor, employee=employee, success=True,
                similarity=score, threshold=evidence['threshold'], threshold_type=evidence['threshold_type'],
                liveness=evidence['liveness'], action=action, reason='Attendance accepted; FACE_ONLY')
        return result, {'mode': 'FACE_ONLY', 'face': evidence}
    except (ValidationError, PermissionDenied) as error:
        failed = getattr(error, 'face_profile', profile)
        threshold, kind = effective_threshold(failed) if failed else (None, '')
        FaceAudit.objects.create(actor=actor, employee=employee,
            similarity=getattr(error, 'similarity', score), threshold=threshold,
            threshold_type=kind, action=action, reason=str(error)[:250])
        raise
