from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
import uuid
from .models import Order,Invoice,Payment
from .business_service import decimal_value,lock_request,existing_request,save_validated
from .rbac import has_capability
from .realtime import notify_invoice_changed


def require_payment_actor(actor, permission):
    if not has_capability(actor, 'customers.' + permission):
        raise PermissionDenied('Bạn chưa được cấp quyền thanh toán này.')


def require_owner(invoice, actor):
    if not actor.is_authenticated or not actor.is_active or invoice.order.customer_id != actor.pk:
        raise PermissionDenied('Hóa đơn không thuộc tài khoản của bạn.')


@transaction.atomic
def issue_invoice(order_id, *, actor=None):
    if actor is not None:
        require_payment_actor(actor, 'add_invoice')
    order=Order.objects.select_for_update().get(pk=order_id)
    if order.status!=Order.Status.COMPLETED:
        raise ValidationError('Chỉ xuất hóa đơn cho đơn đã hoàn thành.')
    invoice=Invoice.objects.filter(order=order).first()
    if invoice:
        return invoice
    invoice=save_validated(Invoice(order=order,invoice_number=f'HD-{order.pk:08d}',subtotal=order.subtotal,
        discount_amount=order.discount_amount,total_amount=order.total_amount))
    notify_invoice_changed(invoice.pk)
    return invoice


@transaction.atomic
def create_payment(*, invoice_id, actor, payment_method, request_key, amount=None, transaction_reference='', customer_initiated=False):
    if not customer_initiated:
        require_payment_actor(actor,'add_payment')
    key=lock_request('payment',request_key)
    invoice=Invoice.objects.select_for_update().select_related('order').get(pk=invoice_id)
    if customer_initiated:
        require_owner(invoice,actor)
    existing=existing_request(Payment,key,actor)
    if existing:
        if existing.invoice_id!=invoice.pk or existing.payment_method!=payment_method:
            raise ValidationError('Mã yêu cầu đã dùng cho hóa đơn/phương thức khác.')
        return existing
    reference=transaction_reference.strip()
    if payment_method not in Payment.Method.values:
        raise ValidationError('Phương thức thanh toán không hợp lệ.')
    pending=invoice.payments.filter(status='PENDING').first()
    if customer_initiated and invoice.status=='UNPAID' and pending and pending.customer_initiated and pending.created_by_id==actor.pk and pending.payment_method==payment_method:
        return pending
    if customer_initiated and payment_method=='BANK_TRANSFER':
        reference='DEMO-'+uuid.uuid4().hex.upper()
    if payment_method==Payment.Method.BANK_TRANSFER:
        if not reference:
            raise ValidationError('Chuyển khoản cần mã giao dịch để đối soát thủ công.')
        lock_request('bank-reference',uuid.uuid5(uuid.NAMESPACE_URL,reference))
        if Payment.objects.filter(payment_method=payment_method,transaction_reference=reference,status__in=['PENDING','SUCCEEDED']).exists():
            raise ValidationError('Mã giao dịch chuyển khoản đã được sử dụng.')
    if invoice.status!=Invoice.Status.UNPAID or invoice.payments.filter(status__in=[Payment.Status.PENDING,Payment.Status.SUCCEEDED]).exists():
        raise ValidationError('Hóa đơn đã thanh toán hoặc có thanh toán đang chờ xác nhận.')
    if amount is not None and decimal_value(amount,2)!=invoice.total_amount:
        raise ValidationError('Số tiền thanh toán phải bằng tổng hóa đơn.')
    payment=save_validated(Payment(invoice=invoice,amount=invoice.total_amount,payment_method=payment_method,request_key=key,
        transaction_reference=reference,created_by=actor,customer_initiated=customer_initiated))
    notify_invoice_changed(invoice.pk,payment.pk)
    return payment


@transaction.atomic
def report_customer_payment(payment_id,*,actor):
    snapshot=Payment.objects.only('invoice_id').get(pk=payment_id)
    invoice=Invoice.objects.select_for_update().select_related('order').get(pk=snapshot.invoice_id)
    require_owner(invoice,actor)
    payment=Payment.objects.select_for_update().get(pk=payment_id)
    if invoice.status!='UNPAID' or payment.status!='PENDING':
        raise ValidationError('Thanh toán không còn ở trạng thái chờ xác nhận.')
    if payment.amount!=invoice.total_amount:
        raise ValidationError('Số tiền thanh toán không hợp lệ.')
    if payment.customer_confirmed_at:
        return payment
    payment.customer_confirmed_at=timezone.now()
    save_validated(payment)
    notify_invoice_changed(invoice.pk,payment.pk)
    return payment


@transaction.atomic
def confirm_payment(payment_id,*,actor,successful=True,outcome=None):
    require_payment_actor(actor,'change_payment')
    target=outcome or ('SUCCEEDED' if successful else 'FAILED')
    if target not in ('SUCCEEDED','FAILED','CANCELLED'):
        raise ValidationError('Kết quả xác nhận không hợp lệ.')
    snapshot=Payment.objects.get(pk=payment_id)
    invoice=Invoice.objects.select_for_update().get(pk=snapshot.invoice_id)
    payment=Payment.objects.select_for_update().get(pk=payment_id)
    if payment.status!=Payment.Status.PENDING:
        raise ValidationError('Thanh toán đã được xử lý, không thể đổi trạng thái.')
    if invoice.status!='UNPAID':
        raise ValidationError('Hóa đơn không còn ở trạng thái chưa thanh toán.')
    if target=='SUCCEEDED':
        if payment.customer_initiated and not payment.customer_confirmed_at:
            raise ValidationError('Khách chưa báo đã thanh toán; chưa có biên nhận để xác nhận.')
        if payment.amount!=invoice.total_amount or invoice.status!=Invoice.Status.UNPAID:
            raise ValidationError('Số tiền hoặc trạng thái hóa đơn không hợp lệ.')
        if payment.payment_method==Payment.Method.BANK_TRANSFER and not payment.transaction_reference:
            raise ValidationError('Thiếu mã giao dịch chuyển khoản.')
        if invoice.payments.exclude(pk=payment.pk).filter(status='SUCCEEDED').exists():
            raise ValidationError('Hóa đơn đã nhận tiền.')
        payment.paid_at=timezone.now()
        invoice.status=Invoice.Status.PAID
        invoice.paid_at=payment.paid_at
        save_validated(invoice)
    payment.status=target
    payment.confirmed_by=actor
    payment.processed_at=payment.paid_at or timezone.now()
    save_validated(payment)
    notify_invoice_changed(invoice.pk,payment.pk)
    return payment
