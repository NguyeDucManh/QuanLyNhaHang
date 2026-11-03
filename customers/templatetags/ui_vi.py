from datetime import datetime,date
from django import template
from django.utils import timezone
from zoneinfo import ZoneInfo
from customers.ui_labels import display_label
register=template.Library()
from customers.operational_labels import operational_text
register.filter('operational_text',operational_text)

@register.filter
def ui_message(value):
    text=str(value)
    if text.startswith('Verification only'):return 'Chỉ kiểm tra nhận diện; không ghi chấm công.'
    if text.startswith('Self verification only'):return 'Kiểm tra khuôn mặt của tài khoản; khi chấm công hệ thống xác minh lại.'
    if text.startswith('Attendance service accepted'):return 'Chấm công được chấp nhận theo phương thức đã cấu hình.'
    for word,label in [('Order COMPLETED','đơn đã hoàn tất'),('Hold-out theo thời gian','Kiểm tra theo thời gian'),('Features','Đặc trưng'),('train','huấn luyện'),('test','kiểm tra')]:text=text.replace(word,label)
    for word,label in [('Similarity','Độ tương đồng'),('threshold','ngưỡng nhận diện'),('Employee','nhân viên'),('FaceID','nhận diện khuôn mặt'),('frame','khung hình'),('Pose','Hướng mặt'),('liveness','kiểm tra người thật'),('consent','sự đồng ý')]:text=text.replace(word,label)
    return text

@register.filter
def ui_vi(value):
    if isinstance(value,dict):return ' · '.join(f'{ui_vi(key)}: {ui_vi(item)}' for key,item in value.items())
    if isinstance(value,(list,tuple)):return ' · '.join(str(ui_vi(item)) for item in value)
    if isinstance(value,str) and len(value)>18 and value[4:5]=='-' and value[10:11] in ('T',' '):
        try:return ui_vi(datetime.fromisoformat(value))
        except ValueError:pass
    if isinstance(value,datetime):
        if timezone.is_aware(value):value=value.astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
        return value.strftime('%d/%m/%Y %H:%M:%S')
    if isinstance(value,date):return value.strftime('%d/%m/%Y')
    return operational_text(display_label(value))
