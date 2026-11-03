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
from .models import Booking,BookingDeposit
from . import deposit_service as service
from .rbac import capability_required


def owned_booking(request,pk):
    return get_object_or_404(Booking.objects.select_related('table__area','deposit').prefetch_related('preorder_items__menu_item'),pk=pk,user=request.user,deposit__isnull=False)


def confirmed(booking):
    return booking.deposit.status=='SUCCEEDED' and not booking.deposit.reconciliation_required and booking.status in ('CONFIRMED','COMPLETED')


@login_required
@require_GET
def deposit_page(request,pk,success=False):
    booking=owned_booking(request,pk)
    service.expire_booking(booking.pk)
    booking.refresh_from_db(fields=['status'])
    deposit=BookingDeposit.objects.get(booking=booking)
    booking.deposit=deposit
    paid=confirmed(booking)
    context={'page':'booking','booking':booking,'deposit':deposit,'confirmed':paid,'success_view':success,
        'cancelled':request.GET.get('cancelled')=='1','items':booking.preorder_items.all(),'server_now':timezone.now(),
        'can_pay':booking.status=='PENDING_DEPOSIT' and deposit.status in ('PENDING','FAILED') and deposit.expires_at>timezone.now(),
        'stripe_ready':settings.STRIPE_SECRET_KEY.startswith(('sk_test_','rk_test_')) and bool(settings.STRIPE_WEBHOOK_SECRET),
        'deposit_rule':'Cọc cố định' if settings.BOOKING_DEPOSIT_TYPE=='FIXED' else 'Cọc theo tỷ lệ (có mức tối thiểu)'}
    response=render(request,'customer/deposit_success.html' if success and paid else 'customer/deposit.html',context)
    response['Cache-Control']='no-store'
    return response


@login_required
@require_POST
def checkout_start(request,pk):
    owned_booking(request,pk)
    if not settings.STRIPE_WEBHOOK_SECRET:
        messages.error(request,'Stripe Test Mode chưa sẵn sàng. Vui lòng liên hệ nhà hàng.');return redirect('booking_deposit',pk=pk)
    try: url=service.checkout(pk,actor=request.user)
    except ValidationError as error: messages.error(request,' '.join(error.messages))
    except (stripe.StripeError,ImproperlyConfigured): messages.error(request,'Chưa kết nối được Stripe Test Mode. Vui lòng thử lại sau; chưa có xác nhận thanh toán.')
    else: return redirect(url)
    return redirect('booking_deposit',pk=pk)


@login_required
@require_GET
def deposit_status(request,pk):
    booking=owned_booking(request,pk)
    service.expire_booking(pk)
    booking.refresh_from_db(fields=['status']);booking.deposit=BookingDeposit.objects.get(booking=booking)
    response=JsonResponse({'status':booking.deposit.status,'booking_status':booking.status,'confirmed':confirmed(booking),'server_now':timezone.now().isoformat(),'expires_at':booking.deposit.expires_at.isoformat()})
    response['Cache-Control']='no-store'
    return response


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET.startswith('whsec_'): return JsonResponse({'error':'Webhook not configured'},status=503)
    if len(request.body)>262144: return JsonResponse({'error':'Payload too large'},status=413)
    try: event=stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError,stripe.SignatureVerificationError): return JsonResponse({'error':'Invalid signature or payload'},status=400)
    try: outcome=service.handle_verified_event(event)
    except ValidationError: return JsonResponse({'error':'Event does not match booking deposit'},status=409)
    return JsonResponse({'received':True,'outcome':outcome})


@capability_required('customers.view_bookingdeposit')
def management_deposits(request):
    rows=BookingDeposit.objects.select_related('booking__table','customer').order_by('-created_at')
    if request.GET.get('review')=='1': rows=rows.filter(reconciliation_required=True)
    return render(request,'admin/deposits.html',{'admin_page':'payments','pagination':Paginator(rows,25).get_page(request.GET.get('page'))})
