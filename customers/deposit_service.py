"""Confirm deposits only from signed events or authenticated Stripe API reads."""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
import uuid
from urllib.parse import urlparse
import stripe
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied, ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from .models import Booking, BookingDeposit, StripeCheckoutAttempt, StripeWebhookEvent, RestaurantTable, Order
from .business_service import save_validated, lock_request
from .audit_service import record


def as_dict(value):
    return value.to_dict() if hasattr(value,'to_dict') else value


def stripe_client():
    if not settings.STRIPE_SECRET_KEY.startswith(('sk_test_','rk_test_')):
        raise ImproperlyConfigured('Cần cấu hình Stripe TEST key trong .env; không chấp nhận live key.')
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY,max_network_retries=1,http_client=stripe.RequestsClient(timeout=10))


def deposit_amount(subtotal):
    from .business_service import decimal_value
    value=decimal_value(settings.BOOKING_DEPOSIT_VALUE,2,positive=True)
    minimum=decimal_value(settings.BOOKING_DEPOSIT_MINIMUM,2,positive=True)
    if settings.BOOKING_DEPOSIT_TYPE=='FIXED': amount=value
    elif settings.BOOKING_DEPOSIT_TYPE=='PERCENT':
        if value>100: raise ValidationError('Tỷ lệ cọc không được vượt 100%.')
        amount=max(minimum,subtotal*value/100) if subtotal>0 else minimum
    else: raise ValidationError('Loại tiền cọc không hợp lệ.')
    return amount.quantize(Decimal(1),rounding=ROUND_CEILING)


def create_deposit(booking):
    """Called within create_booking's allocation transaction, after preorder snapshot."""
    minutes=settings.BOOKING_DEPOSIT_TIMEOUT_MINUTES
    if not isinstance(minutes,int) or not 1<=minutes<=1440: raise ValidationError('Thời gian giữ bàn phải từ 1 đến 1440 phút.')
    row=save_validated(BookingDeposit(booking=booking,customer=booking.user,amount=deposit_amount(booking.food_subtotal),expires_at=min(timezone.now()+timedelta(minutes=minutes),booking.start_time)))
    record(action='DEPOSIT_CREATED',entity=row,actor=booking.user,after={'booking_id':booking.pk,'amount':str(row.amount),'currency':row.currency})
    return row


def require_owner(booking,actor):
    if not actor.is_authenticated or not actor.is_active or booking.user_id!=actor.pk: raise PermissionDenied('Đặt bàn không thuộc tài khoản của bạn.')


def locked_booking(pk):
    from .booking_service import lock_areas
    lock_areas()
    snapshot=Booking.objects.only('table_id').get(pk=pk)
    table=RestaurantTable.objects.select_for_update().select_related('area').get(pk=snapshot.table_id) if snapshot.table_id else None
    return Booking.objects.select_for_update().get(pk=pk),table


def expire_locked(booking,deposit):
    if booking.status=='PENDING_DEPOSIT' and deposit.status!='SUCCEEDED' and deposit.expires_at<=timezone.now():
        booking.status='CANCELLED';save_validated(booking)
        deposit.status='EXPIRED';deposit.expired_at=timezone.now();save_validated(deposit)
        record(action='DEPOSIT_EXPIRED',entity=deposit,after={'booking_id':booking.pk})
        from .booking_advanced_service import notify_floor_changed
        notify_floor_changed()
        return True
    return False


@transaction.atomic
def expire_booking(pk):
    booking,_=locked_booking(pk)
    deposit=BookingDeposit.objects.select_for_update().filter(booking=booking).first()
    if deposit: expire_locked(booking,deposit)
    return deposit


def expire_due_deposits():
    ids=list(BookingDeposit.objects.filter(booking__status='PENDING_DEPOSIT',status__in=['PENDING','FAILED'],expires_at__lte=timezone.now()).values_list('booking_id',flat=True)[:500])
    for pk in ids: expire_booking(pk)
    return len(ids)


def metadata(deposit,attempt):
    return {'booking_id':str(deposit.booking_id),'deposit_id':str(deposit.pk),'customer_id':str(deposit.customer_id),'attempt_key':str(attempt.request_key)}


def payment_progress(booking,deposit,*,awaiting=False):
    """Presentation only. Neither a return URL nor an open attempt proves payment."""
    attempt=deposit.attempts.filter(status__in=['CREATING','OPEN']).first()
    state='READY';message='Có thể mở Stripe Checkout trong thời gian giữ bàn.'
    if deposit.reconciliation_required:
        state='RECONCILIATION';message='Giao dịch cần nhà hàng đối soát. Không thanh toán lại.'
    elif deposit.status=='SUCCEEDED':
        state='CONFIRMED' if booking.status in ('CONFIRMED','COMPLETED') else 'PAID'
        message='Tiền cọc đã được ghi nhận.'
    elif deposit.expires_at<=timezone.now() or deposit.status in ('EXPIRED','CANCELLED') or booking.status!='PENDING_DEPOSIT':
        state='EXPIRED';message='Bàn không còn được giữ. Nếu đã trả tiền, không thanh toán lại; liên hệ nhà hàng để đối soát.'
    elif awaiting and attempt and attempt.session_id:
        state='AWAITING_WEBHOOK';message='Đang chờ webhook Stripe xác nhận. Không thanh toán lại cho đặt bàn này.'
    elif attempt:
        state='CHECKOUT_OPEN';message='Đã có một phiên Stripe. Chỉ kiểm tra hoặc tiếp tục phiên hiện có; không tạo thanh toán mới.'
    elif deposit.status=='FAILED':
        state='FAILED';message='Stripe báo giao dịch thất bại. Có thể thử lại trong thời gian giữ bàn.'
    return {'payment_state':state,'payment_message':message,
        'can_pay':state in ('READY','FAILED'),'can_resume':state=='CHECKOUT_OPEN',
        'awaiting_webhook':state=='AWAITING_WEBHOOK','reconciliation_required':deposit.reconciliation_required}


def checkout(booking_id,*,actor):
    require_owner(Booking.objects.only('user_id').get(pk=booking_id),actor)
    client=stripe_client()
    expire_booking(booking_id)
    with transaction.atomic():
        booking=Booking.objects.select_for_update().get(pk=booking_id)
        require_owner(booking,actor)
        deposit=BookingDeposit.objects.select_for_update().get(booking=booking)
        if booking.status!='PENDING_DEPOSIT' or deposit.status not in ('PENDING','FAILED') or deposit.expires_at<=timezone.now(): raise ValidationError('Đặt bàn không còn trong thời gian thanh toán tiền cọc.')
        attempt=deposit.attempts.select_for_update().filter(status__in=['CREATING','OPEN']).first()
        if not attempt:
            # Stripe requires at least 30 minutes; our earlier DB deadline remains authoritative.
            attempt=save_validated(StripeCheckoutAttempt(deposit=deposit,stripe_expires_at=max(deposit.expires_at,timezone.now()+timedelta(minutes=31))))
        key=str(attempt.request_key)
        values=metadata(deposit,attempt)
        amount=int(deposit.amount)
    # Persist the retry key before contacting Stripe. Network failures reuse this attempt.
    if attempt.session_id:
        session=as_dict(client.v1.checkout.sessions.retrieve(attempt.session_id))
        if session.get('livemode') is not False or session.get('id')!=attempt.session_id or session.get('amount_total')!=amount or session.get('currency')!='vnd' or dict(session.get('metadata',{}))!=values:
            raise ValidationError('Thông tin phiên Stripe không khớp đặt bàn.')
        if session.get('status')=='complete': raise ValidationError('Phiên Stripe đã hoàn tất. Không thanh toán lại; chờ webhook hợp lệ cập nhật.',code='awaiting_webhook')
        if session.get('status') not in ('open','expired'):raise ValidationError('Chưa xác định được trạng thái phiên Stripe; không tạo phiên mới.')
        if session.get('status')=='expired':
            with transaction.atomic():
                locked=StripeCheckoutAttempt.objects.select_for_update().get(pk=attempt.pk)
                if locked.status!='PAID': locked.status='EXPIRED';save_validated(locked)
            raise ValidationError('Phiên Stripe đã hết hạn. Nếu vẫn còn thời gian giữ bàn, hãy thử lại.')
    else:
        base=settings.STRIPE_PUBLIC_BASE_URL
        parsed=urlparse(base)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment: raise ImproperlyConfigured('STRIPE_PUBLIC_BASE_URL không hợp lệ.')
        session=as_dict(client.v1.checkout.sessions.create({'mode':'payment','payment_method_types':['card'],
            'client_reference_id':str(deposit.pk),'metadata':values,'payment_intent_data':{'metadata':values},
            'line_items':[{'price_data':{'currency':'vnd','unit_amount':amount,'product_data':{'name':f'Tiền cọc đặt bàn #{booking_id} · Smart Restaurant'}},'quantity':1}],
            'success_url':base+reverse('booking_deposit_success',args=[booking_id])+'?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url':base+reverse('booking_deposit',args=[booking_id])+'?cancelled=1',
            'expires_at':int(attempt.stripe_expires_at.timestamp())},options={'idempotency_key':'booking-deposit-'+key}))
    if session.get('livemode') is not False or not str(session.get('id','')).startswith('cs_test_') or session.get('amount_total')!=amount or session.get('currency')!='vnd' or dict(session.get('metadata',{}))!=values:
        raise ValidationError('Thông tin phiên Stripe không khớp đặt bàn.')
    url=session.get('url','')
    if urlparse(url).scheme!='https' or urlparse(url).hostname!='checkout.stripe.com': raise ValidationError('Stripe chưa cung cấp địa chỉ thanh toán hợp lệ.')
    expired=False
    with transaction.atomic():
        booking=Booking.objects.select_for_update().get(pk=booking_id)
        deposit=BookingDeposit.objects.select_for_update().get(pk=deposit.pk)
        attempt=StripeCheckoutAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.session_id and attempt.session_id!=session['id']: raise ValidationError('Phiên thanh toán đã thay đổi.')
        first=attempt.session_id is None
        attempt.session_id=session['id'];attempt.checkout_url=url
        if attempt.status=='CREATING': attempt.status='OPEN'
        save_validated(attempt)
        if first: record(action='STRIPE_SESSION_CREATED',entity=deposit,actor=actor,after={'session_id':session['id'],'booking_id':booking_id})
        expired=booking.status!='PENDING_DEPOSIT' or deposit.expires_at<=timezone.now()
    if expired:
        try: client.v1.checkout.sessions.expire(session['id'])
        except stripe.StripeError: pass
        raise ValidationError('Thời gian giữ bàn đã hết; vui lòng đặt lại.')
    return url


def settle_paid_deposit(booking,table,deposit,attempt,intent):
    """Caller holds booking/deposit/attempt locks and verified provider evidence."""
    if not intent or not str(intent).startswith('pi_'):raise ValidationError('Thiếu PaymentIntent.')
    if deposit.status=='SUCCEEDED':
        if attempt.status!='PAID':
            record(action='DEPOSIT_DUPLICATE_CHARGE_REVIEW',entity=deposit,after={'session_id':attempt.session_id})
            deposit.reconciliation_required=True;save_validated(deposit)
        outcome='ALREADY_PAID'
    else:
        from .booking_service import overlaps,table_eligible
        conflict=not table or not table_eligible(table,table.area,booking.guests) or overlaps(table.pk,booking.start_time,booking.end_time,booking.pk)
        if table and booking.start_time<=timezone.now() and Order.objects.filter(table=table,status__in=['PENDING','CONFIRMED','PREPARING']).exists():conflict=True
        late=deposit.expires_at<=timezone.now() or booking.status!='PENDING_DEPOSIT' or conflict
        deposit.status='SUCCEEDED';deposit.paid_at=timezone.now();deposit.reconciliation_required=late;save_validated(deposit)
        if not late:
            booking.status='CONFIRMED';save_validated(booking)
            record(action='BOOKING_CONFIRMED_FROM_DEPOSIT',entity=booking,after={'deposit_id':deposit.pk})
        elif booking.status=='PENDING_DEPOSIT':booking.status='CANCELLED';save_validated(booking)
        record(action='DEPOSIT_SUCCEEDED_REVIEW' if late else 'DEPOSIT_SUCCEEDED',entity=deposit,after={'booking_id':booking.pk,'amount':str(deposit.amount),'session_id':attempt.session_id})
        outcome='RECONCILIATION_REQUIRED' if late else 'CONFIRMED'
    attempt.status='PAID';attempt.payment_intent_id=intent;save_validated(attempt)
    return outcome


def reconcile_checkout(booking_id,*,actor):
    """Server-to-server verification, never trust a browser-supplied Session ID."""
    booking=Booking.objects.get(pk=booking_id);require_owner(booking,actor)
    deposit=BookingDeposit.objects.get(booking=booking)
    if deposit.status=='SUCCEEDED':return 'ALREADY_PAID'
    attempt=deposit.attempts.exclude(session_id__isnull=True).exclude(session_id='').first()
    if not attempt:return 'NO_SESSION'
    session=as_dict(stripe_client().v1.checkout.sessions.retrieve(attempt.session_id,{'expand':['payment_intent']}))
    intent=as_dict(session.get('payment_intent'))
    expected=metadata(deposit,attempt)
    if session.get('id')!=attempt.session_id or session.get('livemode') is not False or session.get('currency')!='vnd' or session.get('amount_total')!=int(deposit.amount) or dict(session.get('metadata') or {})!=expected or session.get('client_reference_id')!=str(deposit.pk):
        raise ValidationError('Phiên Stripe không thuộc tiền cọc này.')
    if session.get('status')!='complete' or session.get('payment_status')!='paid':return 'AWAITING_PAYMENT'
    if not isinstance(intent,dict) or not str(intent.get('id','')).startswith('pi_') or intent.get('status')!='succeeded' or intent.get('livemode') is not False or intent.get('currency')!='vnd' or intent.get('amount')!=int(deposit.amount) or intent.get('amount_received')!=int(deposit.amount) or dict(intent.get('metadata') or {})!=expected:
        raise ValidationError('PaymentIntent chưa xác nhận đúng số tiền cọc.')
    with transaction.atomic():
        booking,table=locked_booking(booking_id);require_owner(booking,actor)
        deposit=BookingDeposit.objects.select_for_update().get(pk=deposit.pk)
        locked=StripeCheckoutAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.session_id!=session['id'] or locked.deposit_id!=deposit.pk or (locked.payment_intent_id and locked.payment_intent_id!=intent['id']):raise ValidationError('Phiên thanh toán đã thay đổi.')
        if session['amount_total']!=int(deposit.amount) or dict(session['metadata'])!=metadata(deposit,locked) or session['client_reference_id']!=str(deposit.pk):raise ValidationError('Tiền cọc đã đổi sau khi kiểm tra Stripe.')
        if deposit.status=='SUCCEEDED' and locked.status=='PAID':return 'ALREADY_PAID'
        outcome=settle_paid_deposit(booking,table,deposit,locked,intent['id'])
        record(action='STRIPE_API_RECONCILED',entity=deposit,actor=actor,after={'booking_id':booking.pk,'session_id':locked.session_id,'payment_intent_id':intent['id'],'outcome':outcome,'source':'authenticated_stripe_api'})
        from .booking_advanced_service import notify_floor_changed
        notify_floor_changed()
        return outcome


@transaction.atomic
def handle_verified_event(event):
    """Only call after SDK signature verification, never from a browser status endpoint."""
    event=as_dict(event)
    if not isinstance(event,dict): raise ValidationError('Sự kiện Stripe không hợp lệ.')
    if event.get('livemode') is not False: raise ValidationError('Không chấp nhận sự kiện Stripe live.')
    event_id=event.get('id','');kind=event.get('type','')
    if not isinstance(event_id,str) or not event_id.startswith('evt_') or not isinstance(kind,str): raise ValidationError('Stripe event ID không hợp lệ.')
    lock_request('stripe-event',uuid.uuid5(uuid.NAMESPACE_URL,event_id))
    if StripeWebhookEvent.objects.filter(event_id=event_id).exists(): return 'DUPLICATE'
    supported={'checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.async_payment_failed','checkout.session.expired','payment_intent.payment_failed'}
    if kind not in supported:
        StripeWebhookEvent.objects.create(event_id=event_id,event_type=kind,outcome='IGNORED');return 'IGNORED'
    data=event.get('data',{})
    if not isinstance(data,dict): raise ValidationError('Dữ liệu Stripe không hợp lệ.')
    obj=data.get('object',{})
    if not isinstance(obj,dict): raise ValidationError('Dữ liệu Stripe không hợp lệ.')
    values=obj.get('metadata',{})
    if not isinstance(values,dict): raise ValidationError('Metadata Stripe không hợp lệ.')
    try: attempt_key=uuid.UUID(values.get('attempt_key',''))
    except (ValueError,TypeError,AttributeError): return 'UNRELATED'
    snapshot=StripeCheckoutAttempt.objects.select_related('deposit').filter(request_key=attempt_key).first()
    if not snapshot: return 'UNRELATED'
    booking,table=locked_booking(snapshot.deposit.booking_id)
    deposit=BookingDeposit.objects.select_for_update().get(pk=snapshot.deposit_id)
    attempt=StripeCheckoutAttempt.objects.select_for_update().get(pk=snapshot.pk)
    if dict(values)!=metadata(deposit,attempt) or obj.get('currency')!='vnd': raise ValidationError('Metadata hoặc currency không khớp.')
    if kind.startswith('checkout.'):
        if obj.get('id')!=attempt.session_id or not attempt.session_id: raise ValidationError('Session chưa được liên kết hoặc không khớp.')
        if obj.get('amount_total')!=int(deposit.amount): raise ValidationError('Số tiền không khớp.')
        intent=obj.get('payment_intent')
    else:
        intent=obj.get('id')
        if obj.get('amount')!=int(deposit.amount) or not attempt.session_id: raise ValidationError('PaymentIntent không khớp.')
    if attempt.payment_intent_id and intent and attempt.payment_intent_id!=intent: raise ValidationError('PaymentIntent đã thay đổi.')
    succeeded=kind in ('checkout.session.completed','checkout.session.async_payment_succeeded') and obj.get('payment_status')=='paid' and obj.get('status')=='complete'
    if succeeded:
        outcome=settle_paid_deposit(booking,table,deposit,attempt,intent)
    elif deposit.status in ('SUCCEEDED','EXPIRED','CANCELLED'): outcome='IGNORED_TERMINAL'
    elif kind=='checkout.session.expired':
        attempt.status='EXPIRED';save_validated(attempt)
        expire_locked(booking,deposit);outcome='SESSION_EXPIRED'
    elif kind in ('checkout.session.async_payment_failed','payment_intent.payment_failed'):
        deposit.status='FAILED';save_validated(deposit)
        if kind.startswith('checkout.'): attempt.status='FAILED'
        if intent: attempt.payment_intent_id=intent
        save_validated(attempt)
        record(action='DEPOSIT_FAILED',entity=deposit,after={'booking_id':booking.pk})
        expire_locked(booking,deposit);outcome='FAILED'
    else: outcome='AWAITING_PAYMENT'
    StripeWebhookEvent.objects.create(event_id=event_id,event_type=kind,outcome=outcome)
    record(action='STRIPE_WEBHOOK_PROCESSED',entity=deposit,after={'event_id':event_id,'event_type':kind,'outcome':outcome,'booking_id':booking.pk})
    from .booking_advanced_service import notify_floor_changed
    notify_floor_changed()
    return outcome


def expire_provider_sessions():
    """Scheduled command closes Stripe sessions; allocation already ignores DB-expired holds."""
    expire_due_deposits()
    attempts=StripeCheckoutAttempt.objects.filter(status='OPEN',deposit__status__in=['EXPIRED','CANCELLED'])
    count=0
    for attempt in attempts[:500]:
        session=as_dict(stripe_client().v1.checkout.sessions.expire(attempt.session_id))
        if session.get('status')=='expired':
            with transaction.atomic():
                row=StripeCheckoutAttempt.objects.select_for_update().get(pk=attempt.pk)
                if row.status=='OPEN': row.status='EXPIRED';save_validated(row)
            count+=1
    return count
