from . import service_scope as service_scope
"""Customer ownership and management financial permissions around payment services."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_POST
from .models import Invoice,Payment
from .business_forms import CustomerPaymentForm
from .rbac import capability_required,has_capability
from .payment_service import create_payment,report_customer_payment
from .payment_demo import qr_svg,DEMO_BANK


def partial(request,template,context):
    response=render(request,template,context)
    response['Cache-Control']='no-store'
    response['Vary']='Cookie, X-Realtime-Partial'
    return response


def owned_invoice(request,pk):
    return get_object_or_404(service_scope.invoices(request.user).select_related('order__customer','order__table__area'),pk=pk,order__customer=request.user)


@login_required
def customer_invoices(request):
    queryset=service_scope.invoices(request.user).filter(order__customer=request.user).select_related('order__table').order_by('-created_at')
    return partial(request,'customer/invoices.html',{'pagination':Paginator(queryset,20).get_page(request.GET.get('page')),'page':'invoices'})


@login_required
def customer_invoice(request,pk):
    invoice=owned_invoice(request,pk)
    payments=list(invoice.payments.select_related('confirmed_by').order_by('-created_at','-pk'))
    pending=next((p for p in payments if p.status=='PENDING'),None)
    template='customer/_invoice_content.html' if request.headers.get('X-Realtime-Partial')=='1' else 'customer/invoice.html'
    return partial(request,template,{'invoice':invoice,'payments':payments,'pending_payment':pending,
        'items':invoice.order.items.exclude(kitchen_status='CANCELLED').order_by('pk'),'payment_form':CustomerPaymentForm(),
        'demo_bank':DEMO_BANK,'page':'invoices','can_create':invoice.status=='UNPAID' and invoice.balance_due>0 and not pending})


@login_required
@require_POST
def customer_payment_start(request,pk):
    invoice=owned_invoice(request,pk)
    form=CustomerPaymentForm(request.POST)
    if form.is_valid():
        try:
            create_payment(invoice_id=invoice.pk,actor=request.user,customer_initiated=True,**form.cleaned_data)
        except ValidationError as exc:
            messages.error(request,' '.join(exc.messages))
        else:
            messages.success(request,'Đã tạo yêu cầu thanh toán. Hóa đơn vẫn chưa thanh toán đến khi nhân viên xác nhận nhận tiền.')
    else:
        messages.error(request,'Thông tin phương thức/mã yêu cầu không hợp lệ. Hãy tải lại trang.')
    return redirect('customer_invoice_detail',pk=invoice.pk)


@login_required
@require_POST
def customer_payment_report(request,pk):
    payment=get_object_or_404(service_scope.payments(request.user),pk=pk,invoice__order__customer=request.user)
    try:
        report_customer_payment(payment.pk,actor=request.user)
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
    else:
        messages.success(request,'Đã ghi nhận biên nhận chờ nhân viên xác nhận. Hóa đơn chưa được đánh dấu đã thanh toán.')
    return redirect('customer_invoice_detail',pk=payment.invoice_id)


@login_required
def customer_payment_qr(request,pk):
    payment=get_object_or_404(service_scope.payments(request.user).select_related('invoice'),pk=pk,invoice__order__customer=request.user,payment_method='BANK_TRANSFER')
    response=HttpResponse(qr_svg(payment),content_type='image/svg+xml')
    response['Cache-Control']='no-store'
    response['X-Content-Type-Options']='nosniff'
    response['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'"
    return response


@capability_required('customers.view_invoice')
@capability_required('customers.view_payment')
def management_payments(request):
    query=request.GET.get('q','').strip()
    payment_status=request.GET.get('payment_status','')
    invoice_status=request.GET.get('invoice_status','')
    receipts=request.GET.get('receipts')=='1'
    payments=service_scope.payments(request.user).select_related('invoice__order__customer','invoice__order__table','confirmed_by','created_by')
    if payment_status in Payment.Status.values: payments=payments.filter(status=payment_status)
    if receipts: payments=payments.filter(status='PENDING',customer_confirmed_at__isnull=False)
    if query:
        payments=payments.filter(Q(payment_number__icontains=query)|Q(invoice__invoice_number__icontains=query)|Q(invoice__order__order_number__icontains=query)|Q(invoice__order__customer__username__icontains=query)|Q(invoice__order__table__code__icontains=query))
    invoices=service_scope.invoices(request.user).select_related('order__customer','order__table')
    if invoice_status in Invoice.Status.values: invoices=invoices.filter(status=invoice_status); payments=payments.filter(invoice__status=invoice_status)
    if query: invoices=invoices.filter(Q(invoice_number__icontains=query)|Q(order__order_number__icontains=query)|Q(order__customer__username__icontains=query)|Q(order__table__code__icontains=query)|Q(payments__payment_number__icontains=query)).distinct()
    context={'admin_page':'payments','query':query,'payment_status':payment_status,'invoice_status':invoice_status,'receipts':receipts,
        'pagination':Paginator(payments.order_by('-created_at','-pk'),30).get_page(request.GET.get('page')),
        'invoice_pagination':Paginator(invoices.order_by('-created_at','-pk'),30).get_page(request.GET.get('invoice_page')),
        'payment_statuses':Payment.Status.choices,'invoice_statuses':Invoice.Status.choices}
    invoice_query=request.GET.copy()
    invoice_query.pop('invoice_page',None)
    context['invoice_query']=invoice_query.urlencode()
    template='admin/business/_payments_content.html' if request.headers.get('X-Realtime-Partial')=='1' else 'admin/business/payments.html'
    return partial(request,template,context)


@capability_required('customers.view_invoice')
@capability_required('customers.view_payment')
def payment_receipt(request,pk):
    payment=get_object_or_404(service_scope.payments(request.user).select_related('invoice__order__customer','invoice__order__table__area','created_by','confirmed_by'),pk=pk)
    context={'admin_page':'payments','payment':payment,'invoice':payment.invoice,
        'can_confirm':has_capability(request.user,'customers.change_payment') and payment.status=='PENDING' and payment.invoice.status=='UNPAID',
        'can_succeed':bool(payment.customer_confirmed_at) or not payment.customer_initiated}
    template='admin/business/_receipt_content.html' if request.headers.get('X-Realtime-Partial')=='1' else 'admin/business/receipt.html'
    return partial(request,template,context)
