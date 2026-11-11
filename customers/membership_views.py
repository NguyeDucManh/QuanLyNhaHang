import uuid
from decimal import Decimal
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from .models import CustomerLoyalty, LoyaltyTransaction, MembershipDiscount, Invoice
from .rbac import role_required, capability_required, has_capability
from . import membership_service as service


def customer_accounts():
    return get_user_model().objects.exclude(is_superuser=True).exclude(groups__name__in=['ADMIN', 'MANAGER', 'STAFF']).distinct()


@role_required('ADMIN', 'MANAGER')
@capability_required('customers.view_customerloyalty')
def members(request):
    users = customer_accounts().order_by('username', 'pk')
    query = request.GET.get('q', '').strip()
    if query:
        users = users.filter(Q(username__icontains=query)|Q(first_name__icontains=query)|Q(last_name__icontains=query))
    tiers, _ = service.policy()
    selected = request.GET.get('tier', '')
    if selected in ('MEMBER', 'SILVER', 'GOLD', 'VIP'):
        summaries = service.spend_summaries(users.values_list('pk', flat=True))
        ids = [pk for pk, summary in summaries.items() if service.status(pk, summary=summary, tiers=tiers)['tier'] == selected]
        users = users.filter(pk__in=ids)
    page = Paginator(users, 20).get_page(request.GET.get('page'))
    summaries = service.spend_summaries([user.pk for user in page])
    accounts = {row.customer_id: row for row in CustomerLoyalty.objects.filter(customer_id__in=summaries)}
    rows = [{'customer': user, 'member': service.status(user.pk, summary=summaries[user.pk], tiers=tiers),
        'account': accounts.get(user.pk)} for user in page]
    return render(request, 'admin/membership/members.html', {'admin_page': 'loyalty', 'rows': rows, 'pagination': page,
        'tiers': tiers, 'selected_tier': selected, 'query': query, 'enabled': service.enabled(),
        'can_policy': has_capability(request.user, 'customers.manage_membership_policy')})


@role_required('ADMIN', 'MANAGER')
@capability_required('customers.view_customerloyalty')
def member_detail(request, pk):
    customer = get_object_or_404(customer_accounts(), pk=pk)
    return render(request, 'admin/membership/detail.html', {'admin_page': 'loyalty', 'customer': customer,
        'member': service.status(customer.pk), 'account': CustomerLoyalty.objects.filter(customer=customer).first(),
        'ledger': Paginator(LoyaltyTransaction.objects.filter(customer=customer), 20).get_page(request.GET.get('page')),
        'discounts': MembershipDiscount.objects.filter(order__customer=customer).select_related('order').order_by('-pk')[:30] if service.readable() else [],
        'request_key': uuid.uuid4(), 'can_adjust': has_capability(request.user, 'customers.adjust_customerloyalty')})


class TierForm(forms.Form):
    minimum = forms.DecimalField(label='Chi tiêu từ (đ)', min_value=0, max_value=Decimal('999999999999'), decimal_places=2)
    percent = forms.DecimalField(label='Giảm giá (%)', min_value=0, max_value=100, decimal_places=2)
    benefits = forms.CharField(label='Quyền lợi', required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 2}))


@role_required('ADMIN', 'MANAGER')
@capability_required('customers.manage_membership_policy')
def policy(request):
    tiers, revision = service.policy()
    forms_by_tier = [(row['tier'], TierForm(request.POST or None, prefix=row['tier'], initial=row)) for row in tiers]
    if request.method == 'POST' and all(form.is_valid() for _, form in forms_by_tier):
        values = [{'tier': tier, **{key: str(value) for key, value in form.cleaned_data.items()}} for tier, form in forms_by_tier]
        try:
            service.save_policy(values, actor=request.user)
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(request, 'Đã lưu chính sách; ưu đãi đã chốt của đơn/hóa đơn cũ giữ nguyên.')
            return redirect('membership_policy')
    return render(request, 'admin/membership/policy.html', {'admin_page': 'loyalty', 'tier_forms': forms_by_tier,
        'revision': revision, 'enabled': service.enabled()})


class RefundForm(forms.Form):
    amount = forms.DecimalField(label='Số tiền đã hoàn', min_value=Decimal('.01'), decimal_places=2, max_digits=14)
    reference = forms.CharField(label='Mã đối soát duy nhất', max_length=160)
    reason = forms.CharField(label='Lý do và bằng chứng đối soát', max_length=1000, widget=forms.Textarea)
    confirm_completed = forms.BooleanField(label='Tôi xác nhận tiền đã được hoàn và đối soát bên ngoài hệ thống')


@role_required('ADMIN', 'MANAGER')
@capability_required('customers.record_invoice_refund')
@capability_required('customers.view_invoice')
@capability_required('customers.view_payment')
def refund(request, pk):
    from .service_scope import invoices
    invoice = get_object_or_404(invoices(request.user), pk=pk)
    form = RefundForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        values = form.cleaned_data.copy();values.pop('confirm_completed')
        try:
            service.record_refund(invoice.pk, actor=request.user, **values)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Đã ghi sổ hoàn tiền đã đối soát. Không gửi lệnh hoàn tiền tới Stripe/ngân hàng.')
            return redirect('admin_invoice_detail', pk=pk)
    return render(request, 'admin/membership/refund.html', {'admin_page': 'payments', 'invoice': invoice, 'form': form, 'enabled': service.enabled()})
