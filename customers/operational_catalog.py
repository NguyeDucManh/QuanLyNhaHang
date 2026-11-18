"""Create-only reviewed non-menu reference data; all operational writes explicit."""
import hashlib,json,unicodedata
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,connection
from . import models
from .rbac import get_role,has_capability
from .audit_service import record

PROTECTED=(models.Category,models.MenuItem,models.Topping,models.Topping.menu_items.through,models.Combo,models.ComboItem,models.RecipeIngredient)
ALLOWLIST={
    'Ingredient':(models.Ingredient,{'code','name','unit','minimum_stock','is_active'},'code','add_ingredient'),
    'Supplier':(models.Supplier,{'code','name','contact_name','phone','email','address','is_active'},'code','add_supplier'),
    'IngredientSupplyPolicy':(models.IngredientSupplyPolicy,{'ingredient_id','supplier_id','lead_time_days','safety_days'},'ingredient_id','change_ingredient'),
    'Position':(models.Position,{'name','description','is_active'},'name','add_position'),
}

def menu_snapshot():
    result={}
    for model in PROTECTED:
        rows=list(model.objects.order_by('pk').values())
        result[model._meta.db_table]={'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,default=str,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    return result

def natural(value):return unicodedata.normalize('NFC',str(value)).strip().casefold()
def manifest_digest(entries):return hashlib.sha256(json.dumps(entries,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def preview_catalog(entries):
    if not isinstance(entries,list) or len(entries)>200:raise ValidationError('Danh mục phải là danh sách tối đa 200 mục.')
    changes=[];seen=set()
    for entry in entries:
        if entry.get('model') not in ALLOWLIST:raise ValidationError('Module bị loại trừ: tuyệt đối không ghi thực đơn/công thức/giao dịch bằng command danh mục.')
        model,fields,key,permission=ALLOWLIST[entry['model']]
        if entry.get('verified') is not True or not str(entry.get('source','')).strip():raise ValidationError('Mỗi hồ sơ cần nguồn và xác nhận quản trị, không bịa liên hệ nhà cung cấp.')
        values=entry.get('values',{})
        if not isinstance(values,dict) or not set(values).issubset(fields) or key not in values:raise ValidationError('Trường ngoài danh sách cho phép; không được thay tồn kho hoặc dữ liệu cũ.')
        values={k:(v.strip() if isinstance(v,str) else v) for k,v in values.items()}
        candidate=model(**values);candidate.full_clean(validate_unique=False)
        normalized=(model.__name__,natural(values[key]))
        if normalized in seen:raise ValidationError('Trùng khóa tự nhiên trong bản đề xuất.')
        seen.add(normalized)
        existing=next((v for v in model.objects.all() if natural(getattr(v,key))==normalized[1]),None)
        if existing:
            if any(getattr(existing,k)!=getattr(candidate,k) for k in values):raise ValidationError('Hồ sơ hiện hữu có dữ liệu khác; command không ghi đè. Cần review riêng.')
            changes.append({'model':entry['model'],'key':str(values[key]),'action':'unchanged'});continue
        if hasattr(candidate,'name') and any(natural(v.name)==natural(candidate.name) for v in model.objects.all()):raise ValidationError('Tên đã có ở mã khác; không thêm bản trùng.')
        changes.append({'model':entry['model'],'key':str(values[key]),'action':'create'})
    return {'digest':manifest_digest(entries),'changes':changes,'excluded_modules':[m._meta.db_table for m in PROTECTED],'menu_snapshot':menu_snapshot()}

@transaction.atomic
def apply_catalog(entries,*,actor,approved_digest):
    if get_role(actor) not in ('ADMIN','MANAGER'):raise PermissionDenied
    if approved_digest!=manifest_digest(entries):raise ValidationError('Cần phê duyệt đúng hash danh mục.')
    with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(8410182026)')
    for entry in entries:
        if entry.get('model') not in ALLOWLIST:raise ValidationError('Module không được phép.')
        if not has_capability(actor,'customers.'+ALLOWLIST[entry['model']][3]):raise PermissionDenied
    preview=preview_catalog(entries);before=menu_snapshot();created=[]
    for entry,change in zip(entries,preview['changes']):
        if change['action']!='create':continue
        model=ALLOWLIST[entry['model']][0];obj=model(**{k:v.strip() if isinstance(v,str) else v for k,v in entry['values'].items()});obj.full_clean();obj.save();created.append(obj)
        record(action='OPERATIONAL_REFERENCE_ADDED',entity=obj,actor=actor,after={'manifest_digest':approved_digest,'source':entry['source']})
    if menu_snapshot()!=before:raise ValidationError('Thực đơn thay đổi ngoài dự kiến; rollback toàn bộ.')
    return created
