"""DB prices and immutable JSON snapshots; client supplies only identifiers."""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import (Topping, Combo, MenuItem, BookingItem, Promotion, Order, Review, OrderItem)
from .business_service import save_validated
from .rbac import get_role, has_capability
from .realtime import notify_order_changed

def identifiers(raw):
    if not isinstance(raw,list) or len(raw)>20: raise ValidationError('Danh sách topping không hợp lệ.')
    try: ids=[int(x) for x in raw]
    except (ValueError,TypeError): raise ValidationError('Mã topping không hợp lệ.')
    if len(set(ids))!=len(ids) or any(x<=0 for x in ids): raise ValidationError('Topping bị trùng/không hợp lệ.')
    return ids

def topping_snapshot(menu, ids):
    ids=identifiers(ids)
    rows=list(Topping.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    if len(rows)!=len(ids) or any(not t.is_available or not t.menu_items.filter(pk=menu.pk).exists() for t in rows):
        raise ValidationError('Topping không phù hợp với món hoặc đang ngừng phục vụ.')
    return [{'id':t.pk,'name':t.name,'price':str(t.price)} for t in rows]

def combo_values(combo_id,quantity):
    combo=Combo.objects.select_for_update().filter(pk=combo_id,is_active=True).first()
    if not combo or isinstance(quantity,bool) or not isinstance(quantity,int) or not 1<=quantity<=20: raise ValidationError('Combo hoặc số lượng không hợp lệ.')
    parts=list(combo.items.order_by('pk'))
    menus={m.pk:m for m in MenuItem.objects.select_for_update(of=('self',)).select_related('category').filter(pk__in=[p.menu_item_id for p in parts]).order_by('pk')}
    if not parts or any(not menus[p.menu_item_id].is_available or not menus[p.menu_item_id].category.is_active or menus[p.menu_item_id].price is None for p in parts): raise ValidationError('Combo có món ngừng phục vụ/chưa có giá.')
    count=sum(p.quantity for p in parts)
    if count>100: raise ValidationError('Một combo tối đa 100 phần món; hãy giảm định lượng thành phần.')
    base,remainder=divmod(int(combo.price*100),count)
    import uuid
    selection_id=str(uuid.uuid4());values=[];position=0
    composition=[{'menu_item':p.menu_item_id,'name':menus[p.menu_item_id].name,'quantity':p.quantity} for p in parts]
    for part in parts:
        menu=menus[part.menu_item_id]
        for _ in range(part.quantity):
            price=Decimal(base+(1 if position<remainder else 0))/100
            snap={'id':combo.pk,'name':combo.name,'price':str(combo.price),'quantity':quantity,'portion':position,'composition':composition,'selection_id':selection_id}
            values.append({'menu_item':menu,'item_name':menu.name,'quantity':quantity,'unit_price':price,'line_total':price*quantity,'extras':{'combo':snap}})
            position+=1
    return values

@transaction.atomic
def add_combo_to_order(order_id,combo_id,quantity,*,actor):
    if not has_capability(actor,'customers.change_order') or not has_capability(actor,'customers.add_orderitem'): raise PermissionDenied
    from .order_service import active_order,recalculate_totals
    order=active_order(order_id)
    for values in combo_values(combo_id,quantity): save_validated(OrderItem(order=order,**values))
    recalculate_totals(order);notify_order_changed(order.pk)
    return order

@transaction.atomic
def snapshot_booking_extras(booking, selections, combo_cart):
    if not isinstance(selections,dict) or not isinstance(combo_cart,dict): raise ValidationError('Giỏ món bổ sung không hợp lệ.')
    for line in booking.preorder_items.select_for_update().order_by('menu_item_id'):
        ids=selections.get(str(line.menu_item_id),[])
        if ids:
            menu=MenuItem.objects.select_for_update().get(pk=line.menu_item_id)
            tops=topping_snapshot(menu,ids)
            line.extras={'toppings':tops}; line.unit_price+=sum((Decimal(t['price']) for t in tops),Decimal(0)); line.line_total=line.unit_price*line.quantity
            save_validated(line)
    try: combo_ids=sorted(int(k) for k in combo_cart)
    except (ValueError,TypeError): raise ValidationError('Mã combo không hợp lệ.')
    combos=list(Combo.objects.select_for_update().filter(pk__in=combo_ids).order_by('pk'))
    if len(combos)!=len(combo_ids): raise ValidationError('Combo không tồn tại.')
    for combo in combos:
        quantity=combo_cart[str(combo.pk)]
        if isinstance(quantity,bool) or not isinstance(quantity,int) or not 1<=quantity<=20 or not combo.is_active: raise ValidationError('Combo ngừng phục vụ hoặc số lượng không hợp lệ.')
        for values in combo_values(combo.pk,quantity):
            snap=values['extras']['combo']
            save_validated(BookingItem(booking=booking,selection_key=f'{snap["selection_id"]}:{snap["portion"]}',**values))
    booking.food_subtotal=sum(booking.preorder_items.values_list('line_total',flat=True),Decimal(0)); save_validated(booking)

def discount_for(snapshot,subtotal):
    value=Decimal(snapshot['discount_value'])
    if subtotal<Decimal(snapshot['min_order_amount']): raise ValidationError('Tạm tính chưa đạt mức tối thiểu của voucher.')
    discount=subtotal*value/100 if snapshot['discount_type']=='PERCENT' else value
    cap=snapshot.get('max_discount_amount')
    if cap is not None: discount=min(discount,Decimal(cap))
    return min(subtotal,discount).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

@transaction.atomic
def apply_voucher(order_id,code,*,actor):
    order=Order.objects.select_for_update().get(pk=order_id)
    if order.customer_id!=actor.pk and not has_capability(actor,'customers.change_order'): raise PermissionDenied
    if not actor.is_active or order.status!='PENDING': raise ValidationError('Chỉ áp dụng voucher cho đơn đang chờ xác nhận.')
    normalized=code.strip().upper()
    if order.promotion_id:
        if order.promotion_snapshot['code']==normalized: return order
        raise ValidationError('Đơn đã áp dụng voucher; không đổi lượt sử dụng.')
    if order.discount_amount: raise ValidationError('Đơn đã có giảm giá thủ công; không cộng thêm voucher.')
    promo=Promotion.objects.select_for_update().filter(code=normalized).first(); now=timezone.now()
    if not promo or not promo.is_active or not promo.start_at<=now<=promo.end_at or (promo.usage_limit is not None and promo.used_count>=promo.usage_limit): raise ValidationError('Voucher không tồn tại, hết hạn hoặc hết lượt.')
    snap={k:str(getattr(promo,k)) if getattr(promo,k) is not None else None for k in ('code','name','discount_type','discount_value','min_order_amount','max_discount_amount')}
    discount=discount_for(snap,order.subtotal)
    order.promotion=promo; order.promotion_snapshot=snap; order.discount_amount=discount; order.total_amount=order.subtotal-discount
    promo.used_count+=1; save_validated(promo); save_validated(order); notify_order_changed(order.pk)
    return order

@transaction.atomic
def add_toppings_to_line(order_id,line_id,ids,*,actor):
    if not has_capability(actor,'customers.change_order') or not has_capability(actor,'customers.change_orderitem'): raise PermissionDenied
    order=Order.objects.select_for_update().get(pk=order_id)
    line=OrderItem.objects.select_for_update().get(pk=line_id,order=order)
    if order.status not in ('PENDING','CONFIRMED','PREPARING') or line.kitchen_status!='DRAFT' or line.extras: raise ValidationError('Chỉ thêm topping vào dòng DRAFT chưa có tùy chọn.')
    tops=topping_snapshot(line.menu_item,ids)
    line.extras={'toppings':tops}; line.unit_price+=sum((Decimal(t['price']) for t in tops),Decimal(0)); line.line_total=line.unit_price*line.quantity
    save_validated(line)
    from .order_service import recalculate_totals
    recalculate_totals(order); notify_order_changed(order.pk,line.pk)
    return line

@transaction.atomic
def write_review(*,actor,order_id,menu_item_id,rating,comment=''):
    if get_role(actor)!='CUSTOMER': raise PermissionDenied
    order=Order.objects.select_for_update().filter(pk=order_id,customer=actor,status='COMPLETED').first()
    if not order or not order.items.filter(menu_item_id=menu_item_id).exclude(kitchen_status='CANCELLED').exists(): raise ValidationError('Chỉ đánh giá món đã mua trong đơn hoàn thành của mình.')
    return save_validated(Review(customer=actor,order=order,menu_item_id=menu_item_id,rating=rating,comment=comment))
