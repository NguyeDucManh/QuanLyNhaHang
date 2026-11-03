"""Clean reference catalog only; never invent employees, contacts, GPS or attendance."""
from decimal import Decimal,ROUND_DOWN
from django.db import transaction
from django.utils import timezone
from .models import Position,Topping,Combo,ComboItem,Promotion,MenuItem
from .operational_seed_data import POSITIONS,TOPPINGS,COMBOS,VOUCHERS
from .operational_labels import clean_name
from .business_service import save_validated

@transaction.atomic
def seed_reference():
    for name in POSITIONS:Position.objects.get_or_create(name=name)
    for legacy,price,ids in TOPPINGS:
        name=clean_name(legacy)
        if Topping.objects.filter(name__in=[name,legacy]).exists():continue
        item=save_validated(Topping(name=name,price=Decimal(price)));item.menu_items.set(ids)
    for legacy,parts,ratio in COMBOS:
        name=clean_name(legacy)
        if Combo.objects.filter(name__in=[name,legacy]).exists():continue
        menus={m.pk:m for m in MenuItem.objects.filter(pk__in=[pk for pk,_ in parts],is_available=True,category__is_active=True)}
        if any(pk not in menus or menus[pk].price is None for pk,_ in parts):continue
        total=sum((menus[pk].price*qty for pk,qty in parts),Decimal(0));price=(total*Decimal(ratio)/10000).quantize(Decimal(1),rounding=ROUND_DOWN)*10000
        if price<=0:continue
        combo=save_validated(Combo(name=name,description='Giá khởi tạo theo thành phần món; quản lý kiểm tra trước khi phục vụ.',price=price))
        for pk,qty in parts:save_validated(ComboItem(combo=combo,menu_item=menus[pk],quantity=qty))
    # Discount codes are business identifiers; never rename an existing code.
    now=timezone.now()
    for code,kind,value,minimum,cap,limit in VOUCHERS:
        if not Promotion.objects.filter(code=code).exists():save_validated(Promotion(code=code,name=code,discount_type=kind,discount_value=Decimal(value),min_order_amount=Decimal(minimum),max_discount_amount=Decimal(cap) if cap else None,start_at=now,end_at=now+timezone.timedelta(days=90),usage_limit=limit))
    return {'reference_catalog_only':True,'employees_created':0,'attendance_created':0,'fake_contacts_created':0}
