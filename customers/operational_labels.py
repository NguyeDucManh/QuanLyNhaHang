"""Display labels and explicit rename plans; never infer employee identities."""
import re
from django.apps import apps
from django.db.models import CharField,TextField

MARKER=re.compile(r'(?i)\bdemo\b')
def clean_name(value):
    text=str(value or '')
    text=re.sub(r'(?i)\(\s*demo\s*\)|\[\s*demo[^\]]*\]','',text)
    text=MARKER.sub('',text)
    return re.sub(r'\s+',' ',text).strip(' -_:,')

def operational_text(value):
    text=str(value or '')
    if re.search(r'(?i)demo[-_]u|nhân viên\s+demo|demo_m07_',text):return 'Hồ sơ cần xác nhận'
    if ('@' in text and ('demo' in text.lower() or text.lower().endswith('.example'))) or re.fullmatch(r'[0\s()+.-]{9,}',text):return 'Chưa cập nhật'
    if re.search(r'(?i)demo',text) and ('đường' in text.lower() or 'địa chỉ' in text.lower()):return 'Chưa cập nhật'
    if re.match(r'(?i)^Đánh giá demo',text):return re.sub(r'(?i)demo','mô phỏng',text)
    if 'DEMO MODULE07' in text or 'DEMO INITIAL' in text:return re.sub(r'\[[^\]]*DEMO[^\]]*\]','Dữ liệu khởi tạo',text,flags=re.I)
    return clean_name(text) if MARKER.search(text) else text

CLEAN_FIELDS={'MenuItem':['name'],'Category':['name'],'Combo':['name'],'Topping':['name'],'Promotion':['name'],'Position':['name'],'Ingredient':['name'],'Supplier':['name'],'Shift':['name'],'PayrollPeriod':['name'],'RestaurantInfo':['name']}
def audit_labels():
    rows=[]
    from django.contrib.auth import get_user_model
    for model in [*apps.get_app_config('customers').get_models(),get_user_model()]:
        for field in model._meta.concrete_fields:
            if isinstance(field,(CharField,TextField)) and field.name not in {'password','token','secret','nonce_hash'}:
                for obj in model.objects.filter(**{field.name+'__icontains':'demo'}).only('pk',field.name):
                    before=getattr(obj,field.name);after=clean_name(before)
                    eligible=field.name in CLEAN_FIELDS.get(model.__name__,[]) and bool(after)
                    action='RENAME' if eligible else 'KEEP_INTERNAL; clean display or require manager confirmation'
                    if eligible and model.objects.filter(**{field.name:after}).exclude(pk=obj.pk).exists():action='REVIEW_COLLISION';eligible=False
                    rows.append({'model':model.__name__,'pk':obj.pk,'field':field.name,'location':f'{model.__name__}#{obj.pk}.{field.name}','current_value':before,'type':'business text','visible_to_user':model.__name__ not in {'FaceAudit','AIMessage'},'action':action,'after':after if eligible else operational_text(before)})
    return rows
