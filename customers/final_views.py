from .ai.face.runtime import face_api
from django.shortcuts import render,get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db.models import Count
from .rbac import role_required,capability_required
from .models import Employee,AIMessage,FaceAudit
from .ai_phase_views import payload,metadata
from .ai.face.face_enrollment_service import require_management,verify_identity

@role_required('ADMIN','MANAGER')
@capability_required('customers.change_employee')
def enrollment_page(request,pk):
    from .employee_identity import operational_employees
    employee=get_object_or_404(operational_employees().select_related('position','user'),pk=pk)
    return render(request,'admin/ai/enrollment.html',{'admin_page':'ai-faces','employee':employee})

@role_required('ADMIN','MANAGER')
@capability_required('customers.change_employee')
def test_page(request):
    from django.conf import settings
    return render(request,'admin/ai/face_test.html',{'admin_page':'ai-faces','require_liveness':settings.FACEID_REQUIRE_LIVENESS})

@face_api

@role_required('ADMIN','MANAGER')
@capability_required('customers.change_employee')
@require_POST
def test_face(request):
    from django.utils import timezone
    try:
        from .ai.face.policy import verification_options,face_result,effective_threshold
        data=payload(request); profile,score=verify_identity(actor=request.user,challenge_id=data.get('challenge'),frames=data.get('frames'),**verification_options())
    except (ValidationError,ValueError,TypeError) as exc:
        from .ai.face.policy import effective_threshold
        failed=getattr(exc,'face_profile',None); threshold,kind=effective_threshold(failed) if failed else (None,'')
        FaceAudit.objects.create(actor=request.user,employee=failed.employee if failed else None,similarity=getattr(exc,'similarity',None),threshold=threshold,threshold_type=kind,action='test',reason=str(exc)[:250])
        evidence = {'similarity': getattr(exc, 'similarity', None), 'threshold': threshold, 'threshold_type': kind} if failed else {}
        return JsonResponse({'success':False,'error':str(exc), **evidence},status=400)
    result=face_result(profile,score)
    FaceAudit.objects.create(actor=request.user,employee=profile.employee,success=True,similarity=score,threshold=result['threshold'],threshold_type=result['threshold_type'],liveness=result['liveness'],action='test',reason='Verification only; no Attendance written')
    return JsonResponse({'success':True,**result})

@face_api

@role_required('STAFF','MANAGER','ADMIN')
@require_POST
def self_test_face(request):
    from .employee_identity import operational_employees
    from .ai.face.policy import verification_options,face_result
    from django.core.exceptions import PermissionDenied
    employee=get_object_or_404(operational_employees(),user=request.user)
    profile=None;score=None
    try:
        if not hasattr(employee,'face_profile') or not employee.face_profile.samples.exists(): raise ValidationError('Chưa đăng ký FaceID.')
        data=payload(request)
        profile,score=verify_identity(actor=request.user,challenge_id=data.get('challenge'),frames=data.get('frames'),**verification_options())
        if profile.employee_id!=employee.pk: raise PermissionDenied('Khuôn mặt không thuộc tài khoản đang đăng nhập.')
    except (ValidationError,PermissionDenied) as exc:
        from .ai.face.policy import effective_threshold
        failed=getattr(exc,'face_profile',profile);threshold,kind=effective_threshold(failed) if failed else (None,'')
        FaceAudit.objects.create(actor=request.user,employee=employee,similarity=getattr(exc,'similarity',score),threshold=threshold,threshold_type=kind,action='preview',reason=str(exc)[:250])
        return JsonResponse({'success':False,'error':str(exc)},status=403 if isinstance(exc,PermissionDenied) else 400)
    result=face_result(profile,score)
    FaceAudit.objects.create(actor=request.user,employee=employee,success=True,action='preview',similarity=score,threshold=result['threshold'],threshold_type=result['threshold_type'],liveness=result['liveness'],reason='Self verification only; attendance re-verifies server-side')
    return JsonResponse({'success':True,**result})

@role_required('ADMIN','MANAGER')
def chatbot_management(request):
    from .ai.chatbot.answer_guard import NO_DATA
    total=AIMessage.objects.count(); fallback=AIMessage.objects.filter(answer=NO_DATA).count()
    return render(request,'admin/ai/chatbot_management.html',{'admin_page':'ai-chatbot','total':total,'fallback':fallback,'fallback_rate':fallback/total if total else None,'intents':AIMessage.objects.values('intent').annotate(count=Count('id')).order_by('-count'),'index':metadata('chatbot'),'evaluation':metadata('evaluation')})
