import numpy as np
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from customers.models import Employee, FaceProfile, FaceEmbedding, FaceAudit, FaceChallenge, WorkSchedule
from customers.personnel_service import punch, active_employee
from customers.rbac import get_role, has_capability
from .facenet_service import engine
from .liveness_service import validate_sequence

def require_management(actor):
    if get_role(actor) not in ['ADMIN','MANAGER'] or not has_capability(actor,'customers.change_employee'): raise PermissionDenied

@transaction.atomic
def enroll(employee_id,frames,actor):
    require_management(actor)
    employee=Employee.objects.select_for_update().select_related('user').get(pk=employee_id)
    from customers.employee_identity import require_operational
    require_operational(employee)
    if not isinstance(frames,list) or not 10<=len(frames)<=20: raise ValidationError('Cần 10–20 frame khác nhau.')
    net=engine(); processed=[net.process(frame) for frame in frames]
    if len({r[2] for r in processed})!=len(processed): raise ValidationError('Frame đăng ký bị trùng.')
    # Reject mixed-identity enrollment instead of blindly averaging.
    vectors=np.array([r[0] for r in processed]); center=vectors.mean(axis=0); center/=np.linalg.norm(center)
    if np.min(vectors@center)<.75: raise ValidationError('Các frame chưa nhất quán; đăng ký lại một người.')
    profile,_=FaceProfile.objects.get_or_create(employee=employee,defaults={'model_version':net.model_version})
    profile.samples.all().delete(); profile.threshold=None; profile.calibration={}; profile.model_version=net.model_version; profile.save()
    FaceEmbedding.objects.bulk_create([FaceEmbedding(profile=profile,vector=v.tolist(),quality=q,image_hash=d) for v,q,d in processed])
    return profile

def identify(vectors,model_version,*,allow_provisional=False,operational_only=False,aggregate=False):
    vectors=np.asarray(vectors); results=[]
    if vectors.ndim!=2 or not np.isfinite(vectors).all(): raise ValidationError('Embedding không hợp lệ.')
    from .policy import effective_threshold
    profiles=FaceProfile.objects.filter(model_version=model_version,employee__is_active=True,employee__user__is_active=True,employee__employment_status='ACTIVE')
    if not allow_provisional: profiles=profiles.filter(threshold__isnull=False)
    if operational_only:
        from customers.employee_identity import operational_employees
        profiles=profiles.filter(employee__in=operational_employees())
    query=vectors.mean(axis=0)
    norm=np.linalg.norm(query)
    if norm<1e-9: raise ValidationError('Embedding không hợp lệ.')
    query=query/norm
    for profile in profiles.select_related('employee__user','employee__position').prefetch_related('samples'):
        samples=np.asarray([r.vector for r in profile.samples.all()],dtype=float)
        if samples.size==0 or samples.ndim!=2 or samples.shape[1]!=vectors.shape[1]: continue
        center=samples.mean(axis=0); norm=np.linalg.norm(center)
        if not np.isfinite(samples).all() or norm<1e-9: continue
        center/=norm
        # Every frame must support the same identity, reducing sequence substitution.
        score=float(query@center) if aggregate else float(np.min(vectors@center)); results.append((score,profile))
    results.sort(key=lambda r:r[0],reverse=True)
    if not results: raise ValidationError('Chưa đăng ký FaceID cho nhân viên hoạt động.' if allow_provisional else 'Chưa có hồ sơ đã hiệu chỉnh threshold.')
    score,profile=results[0]
    threshold,kind=effective_threshold(profile)
    if score<threshold or (len(results)>1 and score-results[1][0]<.05):
        error=ValidationError('Similarity dưới threshold hoặc không phân biệt rõ nhân viên.')
        error.face_profile=profile; error.similarity=score
        raise error
    return profile,score

def verify_identity(*,actor,challenge_id,frames,require_liveness=True,allow_provisional=False,operational_only=False):
    if not isinstance(frames,list) or not ((8<=len(frames)<=30) if require_liveness else (3<=len(frames)<=5)): raise ValidationError('Cần 8–30 frame liveness.' if require_liveness else 'Cần 3–5 frame nhìn thẳng.')
    with transaction.atomic():
        try: challenge=FaceChallenge.objects.select_for_update().filter(pk=challenge_id,actor=actor,used_at__isnull=True,expires_at__gt=timezone.now()).first()
        except (ValidationError,ValueError,TypeError): challenge=None
        if not challenge: raise ValidationError('Thử thách hết hạn/đã sử dụng.')
        if (require_liveness and challenge.action not in ('blink','left','right')) or (not require_liveness and challenge.action!='straight'): raise ValidationError('Challenge không đúng chế độ server.')
        challenge.used_at=timezone.now(); challenge.save(update_fields=['used_at'])
    net=engine(); processed=[net.process(frame) for frame in frames]
    if len({r[2] for r in processed})!=len(processed): raise ValidationError('Không chấp nhận frame lặp lại.')
    if require_liveness: validate_sequence(challenge.action,[r[1] for r in processed])
    elif any(abs(r[1].get('yaw',1))>.15 for r in processed): raise ValidationError('Pose không phù hợp; nhìn thẳng vào camera.')
    return identify([r[0] for r in processed],net.model_version,allow_provisional=allow_provisional,operational_only=operational_only,aggregate=not require_liveness)

def verify_and_punch(*,actor,challenge_id,frames,schedule_id,action):
    if get_role(actor) not in ['STAFF','MANAGER','ADMIN']: raise PermissionDenied
    profile=None; score=None; live=False
    try:
        profile,score=verify_identity(actor=actor,challenge_id=challenge_id,frames=frames); live=True
        if profile.employee.user_id!=actor.pk: raise PermissionDenied('Khuôn mặt không thuộc tài khoản đang đăng nhập.')
        if not WorkSchedule.objects.filter(pk=schedule_id,employee=profile.employee).exists(): raise PermissionDenied
        result=punch(schedule_id,action,actor=actor)
    except (ValidationError,PermissionDenied) as exc:
        FaceAudit.objects.create(actor=actor,employee=profile.employee if profile else None,similarity=score,threshold=profile.threshold if profile else None,liveness=live,action=action,reason=str(exc)[:250])
        raise
    FaceAudit.objects.create(actor=actor,employee=profile.employee,success=True,similarity=score,threshold=profile.threshold,liveness=True,action=action,reason='Attendance service accepted')
    return result
