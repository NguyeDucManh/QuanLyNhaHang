from .ai.face.runtime import face_api
import json
from collections import Counter
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.utils import timezone
from .rbac import role_required,get_role
from .models import Employee,FaceProfile,FaceAudit,FaceEmbedding,AIConversation,AIMessage,IngredientSupplyPolicy,Ingredient,Supplier,WorkSchedule
from .ai.artifacts import latest,read_json

def metadata(kind):
    try: return read_json(latest(kind)/'metadata.json')
    except (ValueError,FileNotFoundError): return None

@role_required('ADMIN','MANAGER')
def dashboard(request):
    from .rbac import has_capability
    from .employee_identity import operational_employees
    employees=operational_employees()
    can_faces=has_capability(request.user,'customers.change_employee')
    profiles=FaceProfile.objects.filter(employee__in=employees)
    return render(request,'admin/ai/operational_dashboard.html',{'admin_page':'ai-dashboard',
        'profiles':profiles.count() if can_faces else 0,
        'embeddings':FaceEmbedding.objects.filter(profile__in=profiles).count() if can_faces else 0,
        'calibrated':profiles.filter(threshold__isnull=False).count() if can_faces else 0,'can_faces':can_faces,
        'can_schedule_ai':all(has_capability(request.user,'customers.'+key) for key in ('view_workschedule','add_workschedule','change_workschedule'))})

@role_required('ADMIN','MANAGER')
def forecast(request):
    from .ai.availability import operational_forecast_metadata
    meta,error=operational_forecast_metadata()
    if not meta: return render(request,'admin/ai/forecast.html',{'admin_page':'ai-forecast','result':None,'summary':None,'error':error})
    from .ai.forecast_service import predict
    error=''; result=None
    try: result=predict(int(request.GET.get('days','7')))
    except (ValueError,FileNotFoundError) as exc: error=str(exc)
    summary=result['metadata']['series']['revenue'] if result else None
    return render(request,'admin/ai/forecast.html',{'admin_page':'ai-forecast','result':result,'summary':summary,'error':error})

@role_required('ADMIN','MANAGER')
def inventory(request):
    from .ai.availability import operational_forecast_metadata
    meta,error=operational_forecast_metadata()
    if not meta: return render(request,'admin/ai/inventory.html',{'admin_page':'ai-inventory','rows':[],'error':error,'counts':{},'suppliers':Supplier.objects.filter(is_active=True)})
    from .ai.forecast_service import predict
    from .ai.inventory_ai_service import calculate
    error=''; rows=[]; result=None
    try:
        days=int(request.GET.get('days','7')); safety=int(request.GET.get('safety','3')); increase=int(request.GET.get('increase','0'))
        result=predict(days); rows=calculate(result,days=days,safety_days=safety,demand_increase=increase)
    except (ValueError,FileNotFoundError) as exc: error=str(exc)
    return render(request,'admin/ai/inventory.html',{'admin_page':'ai-inventory','rows':rows,'forecast_metadata':result['metadata'] if result else None,'error':error,'counts':dict(Counter(r['risk'] for r in rows)),'suppliers':Supplier.objects.filter(is_active=True)})

@role_required('ADMIN','MANAGER')
@require_POST
def supply_policy(request):
    from .rbac import has_capability
    if not has_capability(request.user,'customers.change_ingredient'): raise PermissionDenied
    try:
        ingredient=get_object_or_404(Ingredient,pk=int(request.POST['ingredient']))
        supplier=get_object_or_404(Supplier,pk=int(request.POST['supplier']),is_active=True) if request.POST.get('supplier') else None
        policy=IngredientSupplyPolicy.objects.filter(ingredient=ingredient).first() or IngredientSupplyPolicy(ingredient=ingredient)
        policy.supplier=supplier; policy.lead_time_days=int(request.POST['lead']); policy.safety_days=int(request.POST['safety']); policy.full_clean(); policy.save()
    except (ValueError,KeyError,ValidationError) as exc: return JsonResponse({'error':str(exc)},status=400)
    return redirect('ai_inventory')

@role_required('ADMIN','MANAGER')
def faces(request):
    from .ai.face.face_enrollment_service import require_management
    require_management(request.user)
    from django.db.models import Max
    from .employee_identity import operational_employees,account_audit
    from .ai.face.policy import effective_threshold
    employees=list(operational_employees().select_related('position','user','face_profile').prefetch_related('face_profile__samples').annotate(last_verification=Max('faceaudit__created_at')))
    for employee in employees:
        if hasattr(employee,'face_profile'): employee.face_threshold,employee.threshold_type=effective_threshold(employee.face_profile)
    accounts=[a for a in account_audit()['accounts'] if a['active'] and a['role'] in ('ADMIN','MANAGER','STAFF') and not a['seed_account'] and (not a['employee_code'] or a['employee_code'].upper().startswith('DEMO-'))]
    return render(request,'admin/ai/faces.html',{'admin_page':'ai-faces','employees':employees,'link_accounts':accounts,'audits':FaceAudit.objects.filter(employee__in=operational_employees()).select_related('employee').order_by('-created_at')[:30]})

def payload(request):
    if len(request.body)>35*1024*1024: raise ValidationError('Yêu cầu quá lớn.')
    try: data=json.loads(request.body)
    except (ValueError,UnicodeDecodeError): raise ValidationError('JSON không hợp lệ.')
    if not isinstance(data,dict): raise ValidationError('JSON phải là object.')
    return data

@face_api

@role_required('ADMIN','MANAGER')
@require_POST
def enrollment(request,pk):
    from .ai.face.face_enrollment_service import enroll
    from .employee_identity import operational_employees
    from django.shortcuts import get_object_or_404
    get_object_or_404(operational_employees(),pk=pk)
    try:
        data=payload(request)
        if data.get('consent') is not True: raise ValidationError('Cần xác nhận consent của người được đăng ký.')
        profile=enroll(pk,data.get('frames'),request.user)
    except (ValidationError,ValueError) as exc: return JsonResponse({'error':str(exc)},status=400)
    from .ai.face.policy import effective_threshold
    threshold,kind=effective_threshold(profile)
    return JsonResponse({'samples':profile.samples.count(),'threshold':threshold,'threshold_type':kind,'message':'Đã đăng ký. Ngưỡng tạm thời — chưa hiệu chỉnh bằng dữ liệu validation thật.'})

@face_api

@role_required('ADMIN','MANAGER','STAFF')
@require_POST
def face_quality(request):
    from .ai.face.face_enrollment_service import require_management
    from .ai.face.facenet_service import engine
    if get_role(request.user)=='STAFF':
        from .employee_identity import operational_employees
        from django.shortcuts import get_object_or_404
        get_object_or_404(operational_employees(),user=request.user)
    else: require_management(request.user)
    try:
        _,quality,_=engine().process(payload(request).get('frame'))
    except (ValueError,ValidationError) as exc: return JsonResponse({'error':str(exc)},status=400)
    return JsonResponse({'accepted':True,'quality':quality})

@role_required('ADMIN','MANAGER')
@require_POST
def face_delete(request,pk):
    from .ai.face.face_enrollment_service import require_management
    from .employee_identity import operational_employees
    from django.shortcuts import get_object_or_404
    require_management(request.user); employee=get_object_or_404(operational_employees(),pk=pk); FaceProfile.objects.filter(employee=employee).delete()
    return redirect('ai_faces')

@role_required('STAFF','ADMIN','MANAGER')
def face_attendance(request):
    from .face_attendance_views import public_config
    from .employee_identity import operational_employees
    from .ai.face.policy import effective_threshold
    from django.conf import settings
    from .attendance_status import attendance_context
    state=attendance_context(request.user)
    config=public_config(); config['require_liveness']=settings.FACEID_REQUIRE_LIVENESS
    return render(request,'customer/ai/face_attendance.html',{**state,'attendance_config':config,'require_liveness':settings.FACEID_REQUIRE_LIVENESS})

@face_api

@role_required('STAFF','ADMIN','MANAGER')
@require_POST
def challenge(request):
    from .ai.face.liveness_service import issue
    from django.conf import settings
    return JsonResponse(issue(request.user,require_liveness=settings.FACEID_REQUIRE_LIVENESS))

def verify(request):
    # The canonical view owns auth, method and inference capacity guards.
    # Wrapping it twice would make this request compete with itself (429).
    from .face_attendance_views import attendance
    return attendance(request)

def chat_page(request):
    return render(request,'customer/ai/chat.html',{})

@require_GET
def chat_history(request):
    user=request.user if request.user.is_authenticated else None
    conversation=AIConversation.objects.filter(session_key=request.session.session_key or '',user=user).order_by('-pk').first()
    rows=list(conversation.messages.order_by('-pk')[:30]) if conversation else []
    response=JsonResponse({'messages':[{'question':row.question,'answer':row.answer,'created_at':row.created_at.isoformat()} for row in reversed(rows)]})
    response['Cache-Control']='no-store';response['Vary']='Cookie'
    return response

@require_POST
def chat_message(request):
    from .ai.chatbot.assistant_service import respond
    from django.core.cache import cache
    if not request.session.session_key: request.session.create()
    now=int(timezone.now().timestamp()/60); rate_key=f'ai-chat:{request.session.session_key}:{now}'
    count=cache.get(rate_key,0)
    if count>=20: return JsonResponse({'error':'Vui lòng chờ một phút trước khi gửi tiếp.'},status=429)
    cache.set(rate_key,count+1,timeout=65)
    try:
        data=payload(request)
        with transaction.atomic():
            user=request.user if request.user.is_authenticated else None
            qs=AIConversation.objects.select_for_update().filter(session_key=request.session.session_key,user=user)
            conversation=qs.order_by('-pk').first() or AIConversation.objects.create(session_key=request.session.session_key,user=user)
            memory=conversation.memory
            result=respond(data.get('message'),memory,request)
            conversation.memory=memory; conversation.save(update_fields=['memory'])
            AIMessage.objects.create(conversation=conversation,question=data['message'],answer=result['answer'],intent=result['intent'],tool=result.get('tool',''),sources=result.get('sources',[]))
    except (ValueError,TypeError,ValidationError) as exc: return JsonResponse({'error':str(exc)},status=400)
    return JsonResponse(result)
