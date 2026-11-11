from .ai.face.runtime import face_api
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render,redirect
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.db import transaction
from django.utils import timezone
from .rbac import role_required,capability_required
from .models import RestaurantInfo,AttendanceLocationPolicy
from .location_service import public_config,configuration,evaluate_location,secure_punch
from .ai_phase_views import payload

@face_api
@role_required('STAFF','MANAGER','ADMIN')
@require_GET
def attendance_status(request):
    from .attendance_status import attendance_context
    state = attendance_context(request.user)
    response = JsonResponse({'config': public_config(), 'schedule_status': state['schedule_status'],
        'schedule_reason': state['schedule_reason'], 'schedules': [
            {'id': s.pk, 'label': f'{timezone.localtime(s.start_at):%d/%m/%Y %H:%M} · {s.shift.name}'}
            for s in state['schedules']]})
    response['Vary'] = 'Cookie'
    return response

class LocationForm(forms.Form):
    confirm_location_change=forms.BooleanField(required=True,label='Tôi xác nhận lưu vị trí nhà hàng và chính sách đã chỉnh sửa')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from .ui_labels import LABELS
        for name,field in self.fields.items():field.label=LABELS.get(name,field.label)
    latitude=forms.DecimalField(min_value=-90,max_value=90,max_digits=9,decimal_places=6,required=False)
    longitude=forms.DecimalField(min_value=-180,max_value=180,max_digits=9,decimal_places=6,required=False)
    address=forms.CharField(max_length=1000,required=False,widget=forms.Textarea(attrs={'rows':2}))
    attendance_radius_m=forms.IntegerField(min_value=1,max_value=5000,initial=150)
    max_accuracy_m=forms.IntegerField(min_value=1,max_value=500,initial=50)
    mode=forms.ChoiceField(choices=[('FACE_AND_GPS','Khuôn mặt và vị trí'),('FACE_ONLY','Chỉ nhận diện khuôn mặt'),('GPS_ONLY','Chỉ xác thực vị trí')],label='Phương thức xác thực')
    is_active=forms.BooleanField(required=False,initial=True)
    def clean(self):
        values=super().clean()
        required=values.get('mode')!='FACE_ONLY'
        if required or (values.get('latitude') is not None)!=(values.get('longitude') is not None):
            for key in ['latitude','longitude']:
                if values.get(key) is None: self.add_error(key,'Nhập đủ tọa độ để sử dụng GPS.')
        return values

@role_required('ADMIN')
@capability_required('customers.change_restaurantinfo')
def settings_page(request):
    info=RestaurantInfo.objects.filter(is_active=True).first(); policy=AttendanceLocationPolicy.objects.filter(restaurant=info).first() if info else None
    initial={key:getattr(policy,key) for key in ['attendance_radius_m','max_accuracy_m','mode','is_active']} if policy else {'mode':'FACE_AND_GPS','is_active':True}
    if info: initial.update(latitude=info.latitude,longitude=info.longitude,address=info.address)
    form=LocationForm(request.POST if request.method=='POST' else None,initial=initial)
    if request.method=='POST' and form.is_valid():
        if not info: form.add_error(None,'Tạo thông tin nhà hàng đang hoạt động trước khi cấu hình vị trí.')
        else:
            with transaction.atomic():
                info=RestaurantInfo.objects.select_for_update().get(pk=info.pk)
                values=form.cleaned_data.copy(); values.pop('confirm_location_change'); info.latitude=values.pop('latitude'); info.longitude=values.pop('longitude'); info.address=values.pop('address'); info.full_clean(); info.save()
                AttendanceLocationPolicy.objects.update_or_create(restaurant=info,defaults=values)
            messages.success(request,'Đã lưu vị trí và chính sách chấm công.'); return redirect('location_settings')
    return render(request,'admin/location/settings.html',{'admin_page':'location-settings','form':form,'restaurant':info,'location_config':public_config()})

@face_api
@role_required('STAFF','MANAGER','ADMIN')
@require_POST
def check_location(request):
    point=None
    try:
        info,policy=configuration()
        if policy.mode=='FACE_ONLY': return JsonResponse({'geo_status':'NOT_REQUIRED','message':'Chính sách hiện tại không yêu cầu thu vị trí.'})
        point=payload(request).get('location');result=evaluate_location(point,info,policy)
    except (ValueError,ValidationError) as exc: return JsonResponse({'error':str(exc),'status_code':'GPS_UNAVAILABLE' if point is None else 'GPS_INVALID'},status=400)
    return JsonResponse({**result, 'config': public_config()})

@face_api

@role_required('STAFF','MANAGER','ADMIN')
@require_POST
def attendance(request):
    try:
        data=payload(request); result,geo=secure_punch(actor=request.user,schedule_id=int(data.get('schedule')),action=data.get('action'),point=data.get('location'),frames=data.get('frames'),challenge_id=data.get('challenge'))
    except (ValueError,TypeError,ValidationError) as exc: return JsonResponse({'error':str(exc)},status=400)
    return JsonResponse({'message':'Chấm công thành công.','attendance_id':result.pk,'geo_status':geo['geo_status'],'distance':geo['calculated_distance'],'face':geo.get('face'),'timestamp':timezone.now().isoformat()})
