"""Only these atomic operations change stock; each change has an immutable ledger."""
from .audit_service import with_actor
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import (Ingredient, Supplier, MenuItem, RecipeIngredient, StockReceipt,
                     StockReceiptItem, StockIssue, StockIssueItem, StockMovement)
from .business_service import decimal_value, lock_request, existing_request, save_validated
from .rbac import has_capability


def require_inventory_actor(actor,permission):
    if not has_capability(actor,'customers.'+permission):
        raise PermissionDenied('Bạn chưa được cấp quyền nghiệp vụ kho này.')


def locked_ingredients(quantities):
    rows={row.pk:row for row in Ingredient.objects.select_for_update().filter(pk__in=quantities).order_by('pk')}
    if len(rows)!=len(quantities) or any(not row.is_active for row in rows.values()):
        raise ValidationError('Nguyên liệu không tồn tại hoặc đã ngừng hoạt động.')
    return rows


def apply_movements(quantities, *, actor, movement_type, reference, receipt=None, issue=None, order=None, order_item=None):
    ingredients=locked_ingredients(quantities)
    subtract=movement_type!=StockMovement.Type.IMPORT
    # Validate every ingredient before writing anything. Caller owns transaction.
    for pk,quantity in quantities.items():
        decimal_value(quantity,positive=True)
        if subtract and ingredients[pk].current_stock<quantity:
            raise ValidationError(f'Không đủ tồn kho: {ingredients[pk].name} (cần {quantity}, còn {ingredients[pk].current_stock}).')
    for pk in sorted(quantities):
        ingredient=ingredients[pk]
        before=ingredient.current_stock
        quantity=quantities[pk]
        after=before-quantity if subtract else before+quantity
        movement=StockMovement(ingredient=ingredient,movement_type=movement_type,quantity=quantity,
            stock_before=before,stock_after=after,reference=reference,created_by=actor,receipt=receipt,issue=issue,order=order,order_item=order_item)
        ingredient.current_stock=after
        save_validated(ingredient)
        save_validated(movement)
    from .realtime import notify_inventory_changed
    notify_inventory_changed()


@with_actor
@transaction.atomic
def create_document(*, actor, kind, date, items, request_key, supplier=None, note='',reason='Xuất kho thủ công'):
    if kind not in ('receipt','issue'):
        raise ValidationError('Loại phiếu không hợp lệ.')
    model=StockReceipt if kind=='receipt' else StockIssue
    require_inventory_actor(actor,'add_stockreceipt' if kind=='receipt' else 'add_stockissue')
    key=lock_request(kind,request_key)
    existing=existing_request(model,key,actor)
    if existing:
        return existing
    if not items:
        raise ValidationError('Phiếu phải có ít nhất một nguyên liệu.')
    if date>timezone.localdate():
        raise ValidationError('Ngày phiếu không được ở tương lai.')
    rows={}
    for item in items:
        pk=item['ingredient'].pk
        if pk in rows:
            raise ValidationError('Nguyên liệu bị trùng trong phiếu.')
        rows[pk]=decimal_value(item['quantity'],positive=True)
    locked_ingredients(rows)
    values=dict(created_by=actor,date=date,note=note,request_key=key,code=('NK-' if kind=='receipt' else 'XK-')+str(key))
    if kind=='receipt':
        supplier=Supplier.objects.select_for_update().filter(pk=getattr(supplier,'pk',None),is_active=True).first()
        if not supplier:
            raise ValidationError('Nhà cung cấp không hợp lệ hoặc đã ngừng hoạt động.')
        values['supplier']=supplier
    else:
        if not reason.strip():
            raise ValidationError('Cần ghi lý do xuất kho.')
        values['reason']=reason.strip()
    document=save_validated(model(**values))
    for item in items:
        if kind=='receipt':
            save_validated(StockReceiptItem(receipt=document,ingredient=item['ingredient'],quantity=rows[item['ingredient'].pk],unit_price=decimal_value(item.get('unit_price',0),2)))
        else:
            save_validated(StockIssueItem(issue=document,ingredient=item['ingredient'],quantity=rows[item['ingredient'].pk]))
    return document


@with_actor
@transaction.atomic
def confirm_document(document_id, *, kind, actor):
    if kind not in ('receipt','issue'):
        raise ValidationError('Loại phiếu không hợp lệ.')
    model=StockReceipt if kind=='receipt' else StockIssue
    require_inventory_actor(actor,'change_stockreceipt' if kind=='receipt' else 'change_stockissue')
    document=model.objects.select_for_update().get(pk=document_id)
    if document.status==model.Status.CONFIRMED:
        return document
    items=list(document.items.order_by('ingredient_id'))
    if not items:
        raise ValidationError('Phiếu chưa có chi tiết.')
    quantities={item.ingredient_id:item.quantity for item in items}
    apply_movements(quantities,actor=actor,movement_type=StockMovement.Type.IMPORT if kind=='receipt' else StockMovement.Type.EXPORT,
        reference=document.code,receipt=document if kind=='receipt' else None,issue=document if kind=='issue' else None)
    document.status=model.Status.CONFIRMED
    document.confirmed_at=timezone.now()
    return save_validated(document)


def consume_order(order, actor):
    # Legacy entry point cannot become a second deduction trigger.
    raise ValidationError('Trừ kho theo từng món khi PREPARING → READY, không trừ lại toàn Order.')


def consume_order_item(item,actor,*,now=None):
    """Internal: kitchen service owns atomic Order -> OrderItem locks.

    Menu lock serializes recipe edits. Ingredients lock by PK across all writers.
    Flags are saved together with READY by change_item_state, never beforehand.
    """
    from .models import OrderItem
    from .order_service import require_actor
    require_actor(actor,'change_order')
    require_actor(actor,'change_orderitem')
    if item.kitchen_status!='PREPARING' or item.inventory_status!='NOT_PROCESSED':
        raise ValidationError('Món đã xử lý kho hoặc không ở trạng thái đang chế biến.')
    MenuItem.objects.select_for_update().get(pk=item.menu_item_id)
    recipes=list(RecipeIngredient.objects.filter(menu_item_id=item.menu_item_id).order_by('ingredient_id'))
    if recipes:
        quantities={line.ingredient_id:line.quantity_required*item.quantity for line in recipes}
        apply_movements(quantities,actor=actor,movement_type=StockMovement.Type.ORDER_USAGE,
            reference=f'{item.order.order_number}/ITEM-{item.pk}',order=item.order,order_item=item)
        item.inventory_status=OrderItem.InventoryStatus.DEDUCTED
    else:
        item.inventory_status=OrderItem.InventoryStatus.NO_RECIPE
    item.inventory_processed_at=now or timezone.now()


@with_actor
@transaction.atomic
def save_recipe(form):
    menu_id=form.cleaned_data['menu_item'].pk
    ids={menu_id}
    if form.instance.pk:
        ids.add(RecipeIngredient.objects.get(pk=form.instance.pk).menu_item_id)
    list(MenuItem.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    Ingredient.objects.select_for_update().get(pk=form.cleaned_data['ingredient'].pk)
    return form.save()


@with_actor
@transaction.atomic
def delete_recipe(pk):
    original=RecipeIngredient.objects.get(pk=pk)
    MenuItem.objects.select_for_update().get(pk=original.menu_item_id)
    RecipeIngredient.objects.filter(pk=pk).delete()


@with_actor
@transaction.atomic
def save_ingredient(form):
    if form.instance.pk:
        original=Ingredient.objects.select_for_update().get(pk=form.instance.pk)
        if original.unit!=form.cleaned_data['unit'] and (original.current_stock or original.stockmovement_set.exists() or original.recipeingredient_set.exists() or original.purchaseorderitem_set.exists()):
            raise ValidationError('Không đổi đơn vị khi nguyên liệu đã có tồn kho, lịch sử hoặc công thức.')
        form.instance.current_stock=original.current_stock
    return form.save()
