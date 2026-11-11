from django.http import JsonResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_GET, require_POST
from .ai.face.runtime import face_api
from .rbac import role_required
from .face_attendance_service import secure_punch


def public_config():
    from django.conf import settings
    return {'configured': True, 'mode': 'FACE_ONLY', 'require_liveness': settings.FACEID_REQUIRE_LIVENESS}


@face_api
@role_required('STAFF', 'MANAGER', 'ADMIN')
@require_GET
def attendance_status(request):
    from .attendance_status import attendance_context
    state = attendance_context(request.user)
    response = JsonResponse({'config': public_config(), 'schedule_status': state['schedule_status'],
        'schedule_reason': state['schedule_reason'], 'schedules': [
            {'id': row.pk, 'label': f'{timezone.localtime(row.start_at):%d/%m/%Y %H:%M} · {row.shift.name}'}
            for row in state['schedules']]})
    response['Vary'] = 'Cookie'
    return response


@face_api
@role_required('STAFF', 'MANAGER', 'ADMIN')
@require_POST
def attendance(request):
    from .ai_phase_views import payload
    try:
        data = payload(request)
        if 'location' in data:
            raise ValidationError('Chấm công chỉ nhận khuôn mặt và ca làm; cập nhật lại trang để tiếp tục.')
        result, evidence = secure_punch(actor=request.user, schedule_id=int(data.get('schedule')),
            action=data.get('action'), frames=data.get('frames'), challenge_id=data.get('challenge'))
    except (ValueError, TypeError, ValidationError) as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse({'message': 'Chấm công thành công.', 'attendance_id': result.pk,
        'mode': 'FACE_ONLY', 'face': evidence['face'], 'timestamp': timezone.now().isoformat()})
