from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum, Q
from .models import Invoice, Order, MembershipPolicy, MembershipDiscount, InvoiceRefund
from .membership_models import default_tiers
from .rbac import get_role, has_capability


def enabled():
    return getattr(settings, 'MEMBERSHIP_DISCOUNTS_ENABLED', False)


def readable():
    """Feature OFF stops writes, but preserves correct history after rollback."""
    if enabled():
        return True
    from django.db import connection
    return {'customers_membershippolicy','customers_membershipdiscount','customers_invoicerefund'}.issubset(connection.introspection.table_names())


def discount_context(order):
    return MembershipDiscount.objects.filter(order=order).first() if readable() else None


def quote(user,subtotal):
    if not enabled() or not user.is_authenticated or get_role(user)!='CUSTOMER':
        return None
    member=status(user.pk)
    return {**member,'discount':money_discount(subtotal,member['percent']),
        'estimated_total':subtotal-money_discount(subtotal,member['percent'])}


def policy():
    row = MembershipPolicy.objects.filter(pk=1).first() if readable() else None
    if row:
        row.clean()
    return (row.tiers, str(row.revision)) if row else (default_tiers(), 'builtin-v1')


def spend_summaries(customer_ids):
    # Aggregate in PostgreSQL, never materialize every historical invoice in RAM.
    from django.db.models import OuterRef,Subquery,Value,DecimalField,Case,When,F,Count,Max
    from django.db.models.functions import Coalesce,Greatest
    from .models import Payment
    ids=list(customer_ids)
    summaries={pk:{'spend':Decimal(0),'orders':0,'last_purchase':None,'refunds':Decimal(0)} for pk in ids}
    if not ids:return summaries
    money=DecimalField(max_digits=24,decimal_places=2)
    zero=Value(Decimal(0),output_field=money)
    receipts=Payment.objects.filter(invoice_id=OuterRef('pk'),status='SUCCEEDED').values('invoice_id').annotate(total=Sum('amount')).values('total')
    refunded=zero
    if readable():
        query=InvoiceRefund.objects.filter(invoice_id=OuterRef('pk')).values('invoice_id').annotate(total=Sum('amount')).values('total')
        refunded=Coalesce(Subquery(query,output_field=money),zero)
    invoices=Invoice.objects.filter(status='PAID',order__status='COMPLETED',order__customer_id__in=ids).annotate(
        received_total=Coalesce(Subquery(receipts,output_field=money),zero),refunded_total=refunded,
        applied_total=Case(When(booking_deposit__status='SUCCEEDED',then=F('deposit_applied_amount')),default=zero,output_field=money))
    invoices=invoices.filter(total_amount__lte=F('received_total')+F('applied_total'))
    rows=invoices.values('order__customer_id').annotate(spend=Sum(Greatest(F('total_amount')-F('refunded_total'),zero),output_field=money),
        orders=Count('pk'),refunds=Sum('refunded_total',output_field=money),last_purchase=Max('paid_at')).order_by()
    for row in rows.iterator(chunk_size=500):
        summaries[row.pop('order__customer_id')]=row
    return summaries


def status(customer_id, *, summary=None, tiers=None):
    summary = summary if summary is not None else spend_summaries([customer_id])[customer_id]
    tiers = tiers if tiers is not None else policy()[0]
    selected = next(row for row in reversed(tiers) if summary['spend'] >= Decimal(row['minimum']))
    next_row = next((row for row in tiers if Decimal(row['minimum']) > summary['spend']), None)
    return {**summary, 'tier': selected['tier'], 'percent': Decimal(selected['percent']),
        'benefits': selected.get('benefits', ''), 'next_tier': next_row['tier'] if next_row else None,
        'remaining': Decimal(next_row['minimum'])-summary['spend'] if next_row else Decimal(0),
        'progress': min(Decimal(100),max(Decimal(0),(summary['spend']-Decimal(selected['minimum']))/(Decimal(next_row['minimum'])-Decimal(selected['minimum']))*100)) if next_row else Decimal(100)}


def money_discount(subtotal, rate):
    return min(subtotal, max(Decimal(0), subtotal*Decimal(rate)/100)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def release_voucher(order,reason):
    """Release one selected voucher while its locked order is still unpaid."""
    if not order.promotion_id:
        return
    from .models import Promotion
    from .business_service import save_validated
    promo=Promotion.objects.select_for_update().get(pk=order.promotion_id)
    if promo.used_count<=0:
        raise ValidationError('Số lượt voucher không nhất quán; cần quản lý đối soát.')
    promo.used_count-=1;save_validated(promo)
    from .audit_service import record
    record(action='VOUCHER_RELEASED',entity=order,after={'promotion_id':promo.pk,'code':promo.code,'reason':reason})
    order.promotion=None;order.promotion_snapshot={}


def select_discount(order, *, voucher=None):
    """Caller owns Order row lock. Freeze tier/rate once; recalculate amounts only."""
    if not enabled():
        return
    if order.status=='CANCELLED':
        release_voucher(order,'Order cancelled before service completion')
        return
    if order.status not in ('PENDING','CONFIRMED','PREPARING'):
        return
    if not order.customer_id:
        return
    entry = MembershipDiscount.objects.filter(order=order).first()
    previous=(entry.selected,entry.amount) if entry else None
    if entry is None:
        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update().get(pk=order.customer_id)
        tiers, revision = policy()
        member = status(order.customer_id, tiers=tiers)
        snapshot = {'tier': member['tier'], 'percent': str(member['percent']),
            'eligible_spend': str(member['spend']), 'policy_revision': revision,
            'benefits': member['benefits'], 'manual_amount': str(order.discount_amount if not order.promotion_id else 0)}
        entry = MembershipDiscount(order=order, snapshot=snapshot, selected='MEMBERSHIP')
    manual=Decimal(entry.snapshot.get('manual_amount','0'))
    if manual>order.subtotal:
        raise ValidationError('Tạm tính mới thấp hơn giảm giá thủ công đã lưu.')
    candidates = {'MEMBERSHIP': money_discount(order.subtotal, entry.snapshot['percent']), 'MANUAL': manual}
    if voucher:
        candidates['VOUCHER'] = voucher
    entry.selected = max(candidates, key=candidates.get)
    entry.amount = candidates[entry.selected]
    entry.full_clean();entry.save()
    if entry.selected!='VOUCHER':
        release_voucher(order,'A better valid membership benefit was selected')
    order.discount_amount = entry.amount
    order.total_amount = order.subtotal-entry.amount
    # Booking orders initially have subtotal=0 in the DB; persist all three
    # amounts together so the existing financial CHECK is never violated.
    order.save(update_fields=['subtotal', 'discount_amount', 'total_amount','promotion','promotion_snapshot', 'updated_at'])
    if entry.amount and previous!=(entry.selected,entry.amount):
        from .audit_service import record
        record(action='MEMBERSHIP_DISCOUNT_SELECTED',entity=order,after={'tier':entry.snapshot['tier'],
            'selected':entry.selected,'amount':str(entry.amount),'policy_revision':entry.snapshot['policy_revision']})
    return entry


@transaction.atomic
def save_policy(tiers, *, actor):
    if get_role(actor) not in ('ADMIN', 'MANAGER') or not has_capability(actor, 'customers.manage_membership_policy'):
        raise PermissionDenied
    if not enabled():
        raise ValidationError('Chính sách thành viên chưa được bật sau migration.')
    from django.db import connection
    # All managers serialize first creation, not just updates of an existing row.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(7429031)')
    row = MembershipPolicy.objects.select_for_update().filter(pk=1).first() or MembershipPolicy()
    before = row.tiers
    row.tiers = tiers;row.revision += 1;row.full_clean();row.save()
    from .audit_service import record
    record(actor=actor, action='MEMBERSHIP_POLICY_CHANGED', entity=row, before={'tiers': before}, after={'tiers': tiers, 'revision': row.revision})
    return row


@transaction.atomic
def record_refund(invoice_id, *, amount, reference, reason, actor):
    if get_role(actor) not in ('ADMIN', 'MANAGER') or not has_capability(actor, 'customers.record_invoice_refund'):
        raise PermissionDenied
    if not enabled():
        raise ValidationError('Chưa bật sổ hoàn tiền sau migration.')
    if not isinstance(reference,str) or not isinstance(reason,str):
        raise ValidationError('Cần mã đối soát và lý do hợp lệ.')
    if not has_capability(actor,'customers.view_invoice') or not has_capability(actor,'customers.view_payment'):
        raise PermissionDenied
    from django.db import connection
    import hashlib
    lock_id=int.from_bytes(hashlib.blake2b(('invoice-refund:'+reference.strip()).encode(),digest_size=8).digest(),'big') & ((1<<63)-1)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)',[lock_id])
    from .service_scope import require_order
    invoice = Invoice.objects.select_for_update().select_related('order').get(pk=invoice_id)
    require_order(actor, invoice.order_id)
    if invoice.order.customer_id:
        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update().get(pk=invoice.order.customer_id)
    try: value = Decimal(str(amount))
    except Exception: raise ValidationError('Số tiền không hợp lệ.')
    if not value.is_finite() or not 0 < value <= Decimal('999999999999.99') or value != value.quantize(Decimal('.01')) or not reference.strip() or not reason.strip():
        raise ValidationError('Cần tiền hoàn dương, mã đối soát và lý do.')
    old = InvoiceRefund.objects.filter(reference=reference.strip()).first()
    if old:
        if old.invoice_id != invoice.pk or old.amount != value or old.reason != reason.strip():
            raise ValidationError('Mã hoàn tiền đã dùng cho nội dung khác.')
        return old
    previous = invoice.recorded_refunds.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    received=invoice.payments.filter(status='SUCCEEDED').aggregate(total=Sum('amount'))['total'] or Decimal(0)
    deposit=invoice.deposit_applied_amount if invoice.booking_deposit_id and invoice.booking_deposit.status=='SUCCEEDED' else Decimal(0)
    if invoice.status != 'PAID' or invoice.order.status!='COMPLETED' or received+deposit<invoice.total_amount or previous+value > invoice.total_amount:
        raise ValidationError('Không hoàn vượt hóa đơn đã thanh toán.')
    row = InvoiceRefund(invoice=invoice, amount=value, reference=reference.strip(), reason=reason.strip(), actor=actor)
    row.full_clean();row.save()
    from .audit_service import record
    record(actor=actor, action='INVOICE_REFUND_RECORDED', entity=row, after={'invoice_id': invoice.pk, 'amount': str(value), 'reference': row.reference})
    return row
