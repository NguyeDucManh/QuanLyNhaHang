"""Customer booking composition. Drafts do not reserve tables or create orders."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.urls import reverse
from .forms import BookingForm
from .menu_service import session_cart, booking_cart_preview, format_money
from .module07_cart import enrich_preview
from .booking_workspace import booking_panel

DRAFT_KEY = 'customer_booking_draft'
DRAFT_FIELDS = {'name': 100, 'phone': 20, 'date': 10, 'time': 8,
                'guests': 3, 'note': 2000, 'promotion_code': 40, 'preferred_area': 12, 'preferred_table': 12}


def draft_values(request):
    draft = request.session.get(DRAFT_KEY, {})
    return draft.get('fields', {}) if draft.get('owner') == request.user.pk else {}


def cart_preview(request):
    preview = booking_cart_preview(session_cart(request))
    extra = enrich_preview(request, preview['selected_food'])
    preview['food_count'] += extra['combo_parts']
    from .membership_service import quote
    preview['membership_quote']=quote(request.user,extra['total'])
    preview.update(selected_food=extra['rows'], food_total=format_money(extra['total']),
                   combo_rows=extra['combo_rows'], cart_errors=preview['cart_errors'] + extra['errors'],
                   has_cart=preview['has_cart'] or bool(extra['combo_rows']))
    return preview


def menu_context(request):
    # Explicit navigation opt-in; ordinary menu browsing never inherits this mode.
    if request.GET.get('from') != 'booking' or not request.user.is_authenticated:
        return {}
    from .models import Combo
    return {'booking_menu': True, 'booking_combos': Combo.objects.filter(is_active=True).prefetch_related('items__menu_item'), **cart_preview(request)}


def payment_state(booking, user):
    order = getattr(booking, 'service_order', None)
    deposit=getattr(booking,'deposit',None)
    if deposit and not order:
        return {'state':'deposit-paid' if deposit.status=='SUCCEEDED' else 'deposit','deposit':deposit,'booking':booking}
    if not order or order.customer_id != user.pk:
        return {'state': 'unavailable'}
    invoice = getattr(order, 'invoice', None)
    state = {'state': 'unavailable', 'order': order}
    if not invoice:
        return state
    state['invoice'] = invoice
    payments = list(invoice.payments.all())
    latest = next(iter(payments), None)
    labels = {'PENDING': 'Chờ thanh toán', 'SUCCEEDED': 'Đã thanh toán',
              'FAILED': 'Thanh toán thất bại', 'CANCELLED': 'Đã hủy'}
    if latest:
        state['payment_label'] = labels.get(latest.status, '')
    if invoice.status == 'PAID':
        state['state'] = 'paid'
    elif invoice.status == 'UNPAID' and order.status == 'COMPLETED':
        state['state'] = 'pending' if any(p.status in {'PENDING', 'SUCCEEDED'} for p in payments) else 'payable'
    return state


def workspace(request):
    fields = draft_values(request)
    if request.method == 'POST':
        fields = {key: request.POST.get(key, '')[:limit] for key, limit in DRAFT_FIELDS.items()}
        request.session[DRAFT_KEY] = {'owner': request.user.pk, 'fields': fields}
        if request.POST.get('intent') == 'menu':
            return redirect(reverse('customer_menu') + '?from=booking')
    # Reuse this owner's last contact details as form defaults, never as a history panel.
    contact = request.user.booking_set.order_by('-pk').values('name', 'phone').first() or {}
    quick = {key: request.GET[key][:DRAFT_FIELDS[key]] for key in ('date', 'time', 'guests') if key in request.GET}
    initial = {**contact, 'name': request.user.get_full_name() or contact.get('name', ''), 'guests': 2, **fields, **quick}
    form = BookingForm(request.POST if request.method == 'POST' else None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        from .booking_service import create_booking
        try:
            reservation = create_booking(user=request.user, online=True, food_cart=session_cart(request),
                topping_cart=request.session.get('topping_cart', {}), combo_cart=request.session.get('combo_cart', {}),
                promotion_code=request.POST.get('promotion_code', ''), **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, 'Chưa thể lưu đặt bàn và món đặt trước. Giỏ món được giữ lại; vui lòng thử lại.')
        else:
            def clear_draft_and_cart():
                for key in ('cart', 'topping_cart', 'combo_cart'):
                    request.session[key] = {}
                request.session.pop(DRAFT_KEY, None)
            transaction.on_commit(clear_draft_and_cart)
            request.session['booking_confirmation'] = reservation.pk
            if reservation.status=='PENDING_DEPOSIT':
                messages.info(request,'Đặt bàn đang chờ thanh toán tiền cọc.')
                return redirect('booking_deposit',pk=reservation.pk)
            messages.success(request, 'Đặt bàn thành công!')
            # Preserve the existing redirect contract for integrations posting the old form.
            if 'intent' not in request.POST:
                return redirect('customer_booking')
            return redirect(reverse('customer_booking') + '?view=success&id=' + str(reservation.pk))
    panel = booking_panel(request, request.user.booking_set.all(), customer=True)
    view = request.GET.get('view', 'mine' if 'tab' in request.GET else 'new')
    confirmation = None
    # Keep the last confirmation reloadable. Explicit new always starts the draft workspace.
    last = request.session.get('booking_confirmation')
    if request.method == 'GET' and (view == 'success' or ('view' not in request.GET and 'tab' not in request.GET and last)):
        try:
            confirmation_id = int(request.GET.get('id', last))
        except (TypeError, ValueError):
            raise Http404('Không tìm thấy đặt bàn.')
        confirmation = get_object_or_404(request.user.booking_set.select_related('table__area', 'service_order__invoice').prefetch_related('preorder_items', 'service_order__invoice__payments'), pk=confirmation_id)
        if getattr(confirmation,'deposit',None):
            return redirect('booking_deposit_success' if confirmation.deposit.status=='SUCCEEDED' else 'booking_deposit',pk=confirmation.pk)
        view = 'success'
    if view not in {'new', 'mine', 'success'} or request.method == 'POST':
        view = 'new'
    for row in panel['workspace_rows']:
        row['payment'] = payment_state(row['booking'], request.user)
    response = render(request, 'customer/booking.html', {'form': form, 'page': 'booking',
        'customer_booking': True, 'booking_view': view, 'draft_promotion': fields.get('promotion_code', ''),
        'reservations': request.user.booking_set.all()[:5], 'booking_confirmation': confirmation,
        'confirmation_payment': payment_state(confirmation, request.user) if confirmation else {},
        **panel, **cart_preview(request)})
    response['Cache-Control'] = 'no-store'
    return response
