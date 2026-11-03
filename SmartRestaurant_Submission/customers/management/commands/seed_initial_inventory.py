"""One confirmed initial receipt; all stock changes go through inventory_service."""
import json
import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand,CommandError
from django.db import connection,transaction
from django.db.models import F
from django.utils import timezone
from django.contrib.auth import get_user_model
from customers.models import Ingredient,Supplier,StockReceipt,StockMovement
from customers.rbac import get_role
from customers.inventory_service import create_document,confirm_document

REQUEST_KEY=uuid.uuid5(uuid.NAMESPACE_URL,'smart-restaurant/initial-inventory/v1')
MARKER='[DEMO INITIAL INVENTORY V1]'
QUANTITIES={
 'Cá hồi':'4','Thịt bò':'6','Bào ngư':'3','Hải sâm':'3','Tôm hùm':'3',
 'Sò điệp':'4','Cua tuyết':'3','Cua':'5','Tôm':'6','Cá tuyết':'3','Vi cá':'2','Trứng cá':'2',
 'Gạo':'20','Gạo nếp':'15','Dầu ăn':'20','Tỏi':'8','Đường':'12','Muối':'10','Nước dùng':'25',
 'Nước tương':'12','Dầu hào':'8','Sữa':'10','Kem tươi':'5','Cà phê':'5','Vang đỏ nấu ăn':'5',
 'Hương thảo':'.250','Kỷ tử':'.500','Táo đỏ':'1','Mè rang':'1.500','Tiêu đen':'.500','Tiêu xanh':'.500','Wasabi':'.500',
 'Trứng':'80','Lòng đỏ trứng muối':'40','Chim câu':'20',
}
LOW_NAMES=('Bơ','Chanh dây','Nấm')

def initial_target(ingredient):
    default={'kg':'5','g':'5000','l':'8','ml':'8000','piece':'40','portion':'30'}[ingredient.unit]
    target=Decimal(QUANTITIES.get(ingredient.name,default))
    if ingredient.name in LOW_NAMES and ingredient.minimum_stock>0:
        return ingredient.minimum_stock
    # Preserve existing thresholds; ensure the ordinary rows are above them.
    return max(target,ingredient.minimum_stock+max(Decimal('.001'),target/5))

class Command(BaseCommand):
    help='Atomic initial inventory receipt, idempotent by a fixed request key; never refill on rerun.'
    @transaction.atomic
    def handle(self,*args,**options):
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',['initial-inventory-v1'])
        existing=StockReceipt.objects.select_for_update().filter(request_key=REQUEST_KEY).first()
        if existing:
            if existing.note!=MARKER or existing.status!='CONFIRMED':raise CommandError('Phiếu cùng key đã được chỉnh/chưa xác nhận; không tự ghi đè hoặc nhập lần hai.')
            self.stdout.write(f'Already seeded: {existing.code}. No stock change.');return
        actor=next((u for u in get_user_model().objects.filter(is_active=True).order_by('pk') if get_role(u)=='ADMIN'),None)
        if actor is None:raise CommandError('Cần ADMIN active; không tự nâng quyền.')
        supplier=Supplier.objects.filter(is_active=True).order_by('pk').first()
        if supplier is None:raise CommandError('Cần nhà cung cấp active; không tự tạo nhà cung cấp giả.')
        ingredients=list(Ingredient.objects.select_for_update().filter(is_active=True).order_by('pk'))
        items=[]
        for ingredient in ingredients:
            delta=initial_target(ingredient)-ingredient.current_stock
            if delta>0:items.append({'ingredient':ingredient,'quantity':delta,'unit_price':Decimal(0)})
        if not items:
            self.stdout.write('All active ingredients already have adequate stock; no receipt created.');return
        receipt=create_document(actor=actor,kind='receipt',date=timezone.localdate(),supplier=supplier,items=items,request_key=REQUEST_KEY,note=MARKER)
        confirm_document(receipt.pk,kind='receipt',actor=actor)
        active=Ingredient.objects.filter(is_active=True)
        self.stdout.write(json.dumps({'receipt':receipt.code,'items':receipt.items.count(),'movements':StockMovement.objects.filter(receipt=receipt).count(),'active':active.count(),'zero_stock':active.filter(current_stock=0).count(),'low_stock':list(active.filter(current_stock__lte=F('minimum_stock')).values('name','current_stock','minimum_stock')),'purchase_unit_price':'0: giá nhập chưa được cung cấp, không bịa chi phí mua hàng'},default=str,ensure_ascii=False,indent=2))
