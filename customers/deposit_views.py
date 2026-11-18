import logging
import re
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,ImproperlyConfigured
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST,require_GET
from django.utils import timezone
from django.core.cache import cache
from .models import Booking,BookingDeposit
from . import deposit_service as service
from .rbac import capability_required
from .stripe_configuration import configuration_errors,payment_readiness

logger=logging.getLogger(__name__)


def log_webhook(status,reason,event=None):
    # IDs/types only: no raw payload, signature, customer/card data or credentials.
    def safe(value):return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',value) else 'unknown'
    event=service.as_dict(event) if event is not None else {}
    if not isinstance(event,dict):event={}
    logger.log(logging.INFO if status==200 else logging.WARNING,
        'Stripe webhook status=%s reason=%s event=%s type=%s',status,reason,safe(event.get('id')),safe(event.get('type')))

def owned_booking(request,pk):
    return get_object_or_404(Booking.objects.select_related('table__area','deposit').prefetch_related('preorder_items__menu_item'),pk=pk,user=request.user,deposit__isnull=False)


def confirmed(booking):
    return booking.deposit.status=='SUCCEEDED' and not booking.deposit.reconciliation_required and booking.status in ('CONFIRMED','COMPLETED')


def refresh_provider_payment(request,booking,*,force=False):
    if booking.deposit.status=='SUCCEEDED':return
    attempt=booking.deposit.attempts.exclude(session_id__isnull=True).exclude(session_id='').first()
    if not attempt:return
    key=f'stripe-return-check:{attempt.pk}:{attempt.session_id}'
    try:
        if not force and not cache.add(key,True,timeout=10):return
        service.reconcile_checkout(booking.pk,actor=request.user)
    except (stripe.StripeError,ImproperlyConfigured,ValidationError) as error:
        # No payload, key, signature or customer information in logs.
        logger.warning('Stripe payment check unavailable booking=%s type=%s',booking.pk,type(error).__name__)


@login_required
@require_GET
def deposit_page(request,pk,success=False):
    booking=owned_booking(request,pk)
    refresh_provider_payment(request,booking,force=success)
    service.expire_booking(booking.pk)
    booking.refresh_from_db(fields=['status'])
    deposit=BookingDeposit.objects.get(booking=booking)
    booking.deposit=deposit
    paid=confirmed(booking)
    readiness,readiness_message=payment_readiness(booking,deposit,timezone.now())
    progress=service.payment_progress(booking,deposit,awaiting=success)
    context={'page':'booking','booking':booking,'deposit':deposit,'confirmed':paid,'success_view':success,
        'cancelled':request.GET.get('cancelled')=='1','items':booking.preorder_items.all(),'server_now':timezone.now(),
        **progress,
        'stripe_ready':not configuration_errors(),
        'payment_readiness':readiness,'payment_readiness_message':readiness_message,
        'deposit_rule':'Cọc cố định' if settings.BOOKING_DEPOSIT_TYPE=='FIXED' else 'Cọc theo tỷ lệ (có mức tối thiểu)'}
    response=render(request,'customer/deposit_success.html' if success and paid else 'customer/deposit.html',context)
    response['Cache-Control']='no-store'
    return response


@login_required
@require_POST
def checkout_start(request,pk):
    owned_booking(request,pk)
    if configuration_errors():
        messages.error(request,'Stripe Test Mode chưa sẵn sàng. Vui lòng liên hệ nhà hàng.');return redirect('booking_deposit',pk=pk)
    try: url=service.checkout(pk,actor=request.user)
    except ValidationError as error:
        if getattr(error,'code',None)=='awaiting_webhook':return redirect('booking_deposit_success',pk=pk)
        messages.error(request,' '.join(error.messages))
    except (stripe.StripeError,ImproperlyConfigured): messages.error(request,'Chưa kết nối được Stripe Test Mode. Vui lòng thử lại sau; chưa có xác nhận thanh toán.')
    else: return redirect(url)
    return redirect('booking_deposit',pk=pk)


@login_required
@require_GET
def deposit_status(request,pk):
    booking=owned_booking(request,pk)
    refresh_provider_payment(request,booking)
    service.expire_booking(pk)
    booking.refresh_from_db(fields=['status']);booking.deposit=BookingDeposit.objects.get(booking=booking)
    response=JsonResponse({'status':booking.deposit.status,'booking_status':booking.status,'confirmed':confirmed(booking),'server_now':timezone.now().isoformat(),'expires_at':booking.deposit.expires_at.isoformat(),**service.payment_progress(booking,booking.deposit,awaiting=request.GET.get('awaiting')=='1')})
    response['Cache-Control']='no-store'
    return response


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET.startswith('whsec_'):
        log_webhook(503,'not_configured');return JsonResponse({'error':'Webhook not configured'},status=503)
    if len(request.body)>262144: return JsonResponse({'error':'Payload too large'},status=413)
    try: event=stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError,stripe.SignatureVerificationError):
        log_webhook(400,'invalid_signature_or_payload');return JsonResponse({'error':'Invalid signature or payload'},status=400)
    try: outcome=service.handle_verified_event(event)
    except ValidationError:
        log_webhook(409,'event_mismatch',event);return JsonResponse({'error':'Event does not match booking deposit'},status=409)
    except Exception:
        log_webhook(500,'processing_failed_retry_required',event)
        raise
    log_webhook(200,outcome,event)
    return JsonResponse({'received':True,'outcome':outcome})


@capability_required('customers.view_bookingdeposit')
def management_deposits(request):
    rows=BookingDeposit.objects.select_related('booking__table','customer').order_by('-created_at')
    if request.GET.get('review')=='1': rows=rows.filter(reconciliation_required=True)
    return render(request,'admin/deposits.html',{'admin_page':'payments','pagination':Paginator(rows,25).get_page(request.GET.get('page'))})
