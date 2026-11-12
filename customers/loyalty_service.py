"""Earn once per paid invoice. Tiers use lifetime earned points, never browser data."""
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from .models import Payment, Invoice, CustomerLoyalty, LoyaltyTransaction
from .business_service import lock_request, save_validated
from .rbac import has_capability
from .audit_service import audit_actor


def tier_for(points):
    thresholds = settings.LOYALTY_TIERS
    if not thresholds or thresholds[0] != ('MEMBER',0) or any(tier not in ('MEMBER','SILVER','GOLD','VIP') or not isinstance(minimum,int) or minimum<0 for tier,minimum in thresholds) or thresholds != sorted(thresholds,key=lambda row:row[1]):
        raise ValidationError('Cấu hình hạng thành viên không hợp lệ.')
    return next((tier for tier,minimum in reversed(thresholds) if points >= minimum),'MEMBER')


@transaction.atomic
def earn_payment(payment_id, *, actor=None):
    payment = Payment.objects.select_related('invoice__order').get(pk=payment_id)
    order = payment.invoice.order
    if payment.status != 'SUCCEEDED' or payment.invoice.status != 'PAID' or order.status != 'COMPLETED' or not order.customer_id: return None
    return earn_invoice(payment.invoice_id,actor=actor or payment.confirmed_by)


@transaction.atomic
def earn_invoice(invoice_id,*,actor=None):
    invoice=Invoice.objects.select_related('order').get(pk=invoice_id)
    order=invoice.order
    if invoice.status!='PAID' or order.status!='COMPLETED' or not order.customer_id: return None
    if not invoice.payments.filter(status='SUCCEEDED').exists() and not (invoice.booking_deposit_id and invoice.booking_deposit.status=='SUCCEEDED' and invoice.balance_due==0): return None
    # Customer row serializes account creation and invoice retries across all payments.
    get_user_model().objects.select_for_update().get(pk=order.customer_id)
    old = LoyaltyTransaction.objects.filter(source_type='INVOICE',source_id=str(invoice.pk)).first()
    if old: return old
    divisor = Decimal(str(settings.LOYALTY_VND_PER_POINT))
    if not divisor.is_finite() or divisor <= 0: raise ValidationError('Cấu hình điểm không hợp lệ.')
    points = int(invoice.total_amount // divisor)
    account, _ = CustomerLoyalty.objects.get_or_create(customer_id=order.customer_id)
    account = CustomerLoyalty.objects.select_for_update().get(pk=account.pk)
    account.points_balance += points
    account.lifetime_points += points
    from .membership_service import enabled,status
    account.tier = status(order.customer_id)['tier'] if enabled() else tier_for(account.lifetime_points)
    save_validated(account)
    with audit_actor(actor):
        return save_validated(LoyaltyTransaction(customer_id=order.customer_id,type='EARN',points=points,source_type='INVOICE',source_id=str(invoice.pk),actor=actor,note='Thanh toán hóa đơn thành công'))


@transaction.atomic
def adjust_points(customer_id, *, actor, points, reason, request_key):
    if not has_capability(actor,'customers.adjust_customerloyalty'): raise PermissionDenied
    if not reason.strip() or isinstance(points,bool) or not isinstance(points,int) or points == 0: raise ValidationError('Cần số điểm nguyên khác 0 và lý do.')
    key = lock_request('loyalty-adjust',request_key)
    get_user_model().objects.select_for_update().get(pk=customer_id)
    old = LoyaltyTransaction.objects.filter(source_type='ADJUST',source_id=str(key)).first()
    if old:
        if old.actor_id != actor.pk or old.customer_id != customer_id or old.points != points or old.note != reason.strip(): raise ValidationError('Mã yêu cầu đã sử dụng.')
        return old
    account,_ = CustomerLoyalty.objects.get_or_create(customer_id=customer_id)
    account = CustomerLoyalty.objects.select_for_update().get(pk=account.pk)
    if account.points_balance+points < 0: raise ValidationError('Không đủ điểm để điều chỉnh giảm.')
    account.points_balance += points
    save_validated(account)
    with audit_actor(actor):
        from .audit_service import record
        entry = save_validated(LoyaltyTransaction(customer_id=customer_id,type='ADJUST',points=points,source_type='ADJUST',source_id=str(key),actor=actor,note=reason.strip()))
        record(action='LOYALTY_ADJUST',entity=entry,actor=actor,after={'points':points,'reason':reason.strip()})
        return entry
