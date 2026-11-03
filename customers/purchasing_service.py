"""PO workflow uses the existing receipt/stock ledger inside one transaction."""
import hashlib
import json
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Avg
from django.utils import timezone
from .models import PurchaseOrder, PurchaseOrderItem, PurchaseReceiving, Supplier, Ingredient, StockReceiptItem
from .business_service import decimal_value, lock_request, save_validated
from .inventory_service import require_inventory_actor, create_document, confirm_document, locked_ingredients
from .audit_service import with_actor


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@with_actor
@transaction.atomic
def create_purchase_order(*, actor, supplier, items, request_key, expected_date=None, note=''):
    require_inventory_actor(actor, 'add_purchaseorder')
    key = lock_request('purchase-order', request_key)
    existing = PurchaseOrder.objects.filter(request_key=key).first()
    if existing:
        if existing.created_by_id != actor.pk: raise ValidationError('Mã yêu cầu đã sử dụng.')
        return existing
    supplier = Supplier.objects.get(pk=supplier.pk)
    if not supplier.is_active: raise ValidationError('Nhà cung cấp ngừng hoạt động.')
    if not items: raise ValidationError('Cần ít nhất một nguyên liệu.')
    if expected_date and expected_date < timezone.localdate(): raise ValidationError('Ngày dự kiến không được ở quá khứ.')
    quantities = {}
    for item in items:
        pk = item['ingredient'].pk
        if pk in quantities: raise ValidationError('Nguyên liệu trùng.')
        quantities[pk] = decimal_value(item['quantity'], positive=True)
    ingredients = locked_ingredients(quantities)
    supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
    if not supplier.is_active: raise ValidationError('Nhà cung cấp ngừng hoạt động.')
    po = save_validated(PurchaseOrder(code='PO-'+str(key), supplier=supplier, created_by=actor, request_key=key, expected_date=expected_date, note=note))
    total = Decimal(0)
    for item in items:
        ingredient = ingredients[item['ingredient'].pk]
        price = decimal_value(item['unit_price'], 2)
        amount = (quantities[ingredient.pk] * price).quantize(Decimal('.01'))
        save_validated(PurchaseOrderItem(purchase_order=po, ingredient=ingredient, unit=ingredient.unit, quantity_ordered=quantities[ingredient.pk], unit_price=price, line_total=amount))
        total += amount
    po.subtotal = total
    return save_validated(po)


@with_actor
@transaction.atomic
def transition_purchase_order(pk, target, *, actor):
    require_inventory_actor(actor, 'approve_purchaseorder' if target == 'APPROVED' else 'change_purchaseorder')
    po = PurchaseOrder.objects.select_for_update().get(pk=pk)
    allowed = {'DRAFT': ('SUBMITTED','CANCELLED'), 'SUBMITTED': ('APPROVED','CANCELLED'), 'APPROVED': ('CANCELLED',)}
    if target not in allowed.get(po.status, ()): raise ValidationError('Không được chuyển trạng thái đơn mua hàng.')
    if target == 'SUBMITTED' and not po.items.exists(): raise ValidationError('Đơn mua chưa có chi tiết.')
    if target == 'APPROVED': po.approved_by = actor
    po.status = target
    return save_validated(po)


@with_actor
@transaction.atomic
def receive_purchase_order(pk, *, actor, items, request_key, date, note=''):
    require_inventory_actor(actor, 'receive_purchaseorder')
    key = lock_request('po-receiving', request_key)
    # Normalize before hashing so reordering browser rows is a safe retry.
    payload = sorted([(int(i['item_id']), format(decimal_value(i['quantity'], positive=True),'.3f'), format(decimal_value(i['unit_price'],2),'.2f') if i.get('unit_price') is not None else None) for i in items])
    signature = digest([pk, payload, date, note])
    existing = PurchaseReceiving.objects.select_related('receipt').filter(request_key=key).first()
    if existing:
        if existing.created_by_id != actor.pk or existing.payload_hash != signature: raise ValidationError('Mã nhận hàng đã dùng với dữ liệu khác.')
        return existing.receipt
    po = PurchaseOrder.objects.select_for_update().get(pk=pk)
    if po.status not in ('APPROVED','PARTIALLY_RECEIVED'): raise ValidationError('Chỉ nhận đơn đã duyệt và chưa nhận đủ.')
    if date < po.order_date: raise ValidationError('Ngày nhận không được trước ngày đặt mua.')
    rows = {i.pk:i for i in po.items.select_for_update(of=('self',)).select_related('ingredient').order_by('pk')}
    if not payload or len({i[0] for i in payload}) != len(payload): raise ValidationError('Chi tiết nhận hàng rỗng hoặc trùng.')
    ingredients=locked_ingredients({row.ingredient_id:row.quantity_ordered for row in rows.values()})
    receipt_items = []
    for item_id, quantity, price in payload:
        row = rows.get(item_id)
        if not row: raise ValidationError('Chi tiết không thuộc đơn mua hàng.')
        quantity = Decimal(quantity)
        if quantity > row.remaining: raise ValidationError('Số nhận vượt số còn lại.')
        ingredient=ingredients[row.ingredient_id]
        if row.unit != ingredient.unit: raise ValidationError('Đơn vị nguyên liệu đã đổi; cần đối soát trước khi nhận.')
        receipt_items.append({'ingredient':ingredient,'quantity':quantity,'unit_price':row.unit_price if price is None else Decimal(price)})
    from .models import StockReceipt
    lock_request('receipt',key)
    if StockReceipt.objects.filter(request_key=key).exists(): raise ValidationError('Mã phiếu nhập đã được dùng.')
    receipt = create_document(actor=actor, kind='receipt', date=date, items=receipt_items, request_key=key, supplier=po.supplier, note=f'{po.code}: {note}')
    # A request UUID from an unrelated manual receipt must never be repurposed.
    if receipt.status != 'DRAFT' or receipt.items.count() != len(payload): raise ValidationError('Mã phiếu nhập đã được dùng.')
    save_validated(PurchaseReceiving(purchase_order=po, receipt=receipt, request_key=key, payload_hash=signature, created_by=actor))
    confirm_document(receipt.pk, kind='receipt', actor=actor)
    for item_id, quantity, _ in payload:
        rows[item_id].quantity_received += Decimal(quantity)
        save_validated(rows[item_id])
    po.status = 'RECEIVED' if all(i.remaining == 0 for i in rows.values()) else 'PARTIALLY_RECEIVED'
    po.received_date = date
    save_validated(po)
    from .audit_service import record
    record(actor=actor, action='PO_RECEIVED', entity=po, after={'receipt_id':receipt.pk,'status':po.status})
    return receipt


def supplier_prices():
    # Confirmed receipt rows are the immutable supplier price history; no duplicate table.
    return StockReceiptItem.objects.filter(receipt__status='CONFIRMED').values('receipt__supplier__name','ingredient__name','ingredient__unit').annotate(average_price=Avg('unit_price'),quantity=Sum('quantity')).order_by('ingredient__name')
