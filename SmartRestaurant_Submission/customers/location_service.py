"""Event-only geofence checks. Browser coordinates are claims, never distances/proofs."""
import math
from decimal import Decimal
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import RestaurantInfo,AttendanceLocationPolicy,AttendanceLocationEvent,Employee
from .personnel_service import active_employee,punch

def coordinate(value,lower,upper,label):
    if isinstance(value,bool) or not isinstance(value,(int,float,str,Decimal)): raise ValidationError(f'{label} không hợp lệ.')
    try: number=float(value)
    except (ValueError,TypeError): raise ValidationError(f'{label} không hợp lệ.')
    if not math.isfinite(number) or not lower<=number<=upper: raise ValidationError(f'{label} ngoài giới hạn.')
    return number

def haversine(lat1,lng1,lat2,lng2):
    lat1=coordinate(lat1,-90,90,'Latitude'); lat2=coordinate(lat2,-90,90,'Latitude')
    lng1=coordinate(lng1,-180,180,'Longitude'); lng2=coordinate(lng2,-180,180,'Longitude')
    p1,p2=map(math.radians,[lat1,lat2]); dlat=math.radians(lat2-lat1); dlng=math.radians(lng2-lng1)
    a=math.sin(dlat/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dlng/2)**2
    return 6371008.8*2*math.atan2(math.sqrt(min(1,a)),math.sqrt(max(0,1-a)))

def configuration():
    info=RestaurantInfo.objects.filter(is_active=True).select_related('attendance_policy').first()
    if not info: raise ValidationError('Chưa cấu hình nhà hàng và chính sách chấm công.')
    policy=getattr(info,'attendance_policy',None)
    if not policy or not policy.is_active: raise ValidationError('Chính sách chấm công chưa được bật; liên hệ quản lý.')
    if policy.mode!='FACE_ONLY' and (info.latitude is None or info.longitude is None): raise ValidationError('Chưa cấu hình tọa độ nhà hàng.')
    return info,policy

def public_config():
    try: info,policy=configuration()
    except ValidationError as exc: return {'configured':False,'error':' '.join(exc.messages),'mode':'FACE_AND_GPS'}
    return {'configured':True,'name':info.name,'address':info.address,'latitude':float(info.latitude) if info.latitude is not None else None,'longitude':float(info.longitude) if info.longitude is not None else None,'radius':policy.attendance_radius_m,'max_accuracy':policy.max_accuracy_m,'mode':policy.mode}

def evaluate_location(point,info,policy):
    if not isinstance(point,dict): raise ValidationError('Cần latitude, longitude và accuracy từ trình duyệt.')
    lat=coordinate(point.get('latitude'),-90,90,'Latitude'); lng=coordinate(point.get('longitude'),-180,180,'Longitude'); accuracy=coordinate(point.get('accuracy'),0,100000,'Accuracy')
    distance=haversine(lat,lng,info.latitude,info.longitude)
    status='ACCURACY_LOW' if accuracy>policy.max_accuracy_m else 'ALLOWED' if distance<=policy.attendance_radius_m else 'DENIED'
    message='Bạn đang ở trong phạm vi chấm công.' if status=='ALLOWED' else 'Tín hiệu GPS chưa đủ chính xác, vui lòng thử lại.' if status=='ACCURACY_LOW' else f'Bạn đang cách nhà hàng {distance:.0f}m, vượt bán kính {policy.attendance_radius_m}m.'
    return {'latitude':lat,'longitude':lng,'accuracy':accuracy,'calculated_distance':distance,'geo_status':status,'status_code':'GPS_'+status,'message':message,'checked_at':timezone.now().isoformat()}

def secure_punch(*,actor,schedule_id,action,point=None,frames=None,challenge_id=None):
    employee=Employee.objects.select_related('user').filter(user=actor).first()
    if not employee: raise PermissionDenied('Tài khoản chưa liên kết nhân viên.')
    from .employee_identity import require_operational
    require_operational(employee)
    if action not in ['in','out']: raise ValidationError('Thao tác chấm công không hợp lệ.')
    info,policy=configuration(); snapshot={'mode':policy.mode,'radius':policy.attendance_radius_m,'max_accuracy':policy.max_accuracy_m,'restaurant_latitude':str(info.latitude),'restaurant_longitude':str(info.longitude),'policy_updated_at':policy.updated_at.isoformat()}
    try:
        geo=evaluate_location(point,info,policy) if policy.mode!='FACE_ONLY' else {'geo_status':'NOT_REQUIRED','latitude':None,'longitude':None,'accuracy':None,'calculated_distance':None}
    except ValidationError:
        AttendanceLocationEvent.objects.create(employee=employee,action=action,policy_snapshot=snapshot,geo_status='GPS_UNAVAILABLE' if point is None else 'GPS_INVALID')
        raise
    if geo['geo_status'] in ['DENIED','ACCURACY_LOW']:
        AttendanceLocationEvent.objects.create(employee=employee,action=action,policy_snapshot=snapshot,**{key:geo[key] for key in ['latitude','longitude','accuracy','calculated_distance','geo_status']})
        raise ValidationError(geo['message'])
    profile=None; score=None
    if policy.mode!='GPS_ONLY':
        from .ai.face.face_enrollment_service import verify_identity
        from .ai.face.policy import verification_options,effective_threshold,face_result
        from .models import FaceAudit
        try:
            if not hasattr(employee,'face_profile') or not employee.face_profile.samples.exists(): raise ValidationError('Chưa đăng ký FaceID.')
            profile,score=verify_identity(actor=actor,challenge_id=challenge_id,frames=frames,**verification_options())
            if profile.employee_id!=employee.pk: raise PermissionDenied('Khuôn mặt không thuộc tài khoản đang đăng nhập.')
        except (ValidationError,PermissionDenied) as exc:
            failed=getattr(exc,'face_profile',profile); threshold,kind=effective_threshold(failed) if failed else (None,'')
            FaceAudit.objects.create(actor=actor,employee=employee,similarity=getattr(exc,'similarity',score),threshold=threshold,threshold_type=kind,action=action,reason=str(exc)[:250])
            AttendanceLocationEvent.objects.create(employee=employee,action=action,policy_snapshot={**snapshot,'face_result':'DENIED'},**{key:geo[key] for key in ['latitude','longitude','accuracy','calculated_distance','geo_status']})
            raise
        geo['face']=face_result(profile,score)
    try:
        with transaction.atomic():
            from .models import WorkSchedule
            if not WorkSchedule.objects.filter(pk=schedule_id,employee=employee).exists(): raise PermissionDenied('Ca làm không thuộc tài khoản đang đăng nhập.')
            result=punch(schedule_id,action,actor=actor)
            AttendanceLocationEvent.objects.create(employee=employee,attendance=result,action=action,policy_snapshot=snapshot,**{key:geo[key] for key in ['latitude','longitude','accuracy','calculated_distance','geo_status']})
            if profile:
                FaceAudit.objects.create(actor=actor,employee=employee,success=True,similarity=score,threshold=geo['face']['threshold'],threshold_type=geo['face']['threshold_type'],liveness=geo['face']['liveness'],action=action,reason='Attendance service accepted; policy '+policy.mode)
    except (ValidationError,PermissionDenied) as exc:
        if profile:
            FaceAudit.objects.create(actor=actor,employee=employee,similarity=score,threshold=geo['face']['threshold'],threshold_type=geo['face']['threshold_type'],liveness=geo['face']['liveness'],action=action,reason=str(exc)[:250])
        raise
    return result,geo
