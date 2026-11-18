"""Secret-free hosted TEST Checkout readiness; never contact the provider."""
from urllib.parse import urlsplit
from django.conf import settings


def configuration_errors():
    errors=[]
    key=settings.STRIPE_SECRET_KEY
    secret=settings.STRIPE_WEBHOOK_SECRET
    if not key:
        errors.append('Thiếu STRIPE_SECRET_KEY của Stripe Test Mode.')
    elif key != key.strip() or not key.startswith(('sk_test_','rk_test_')):
        errors.append('STRIPE_SECRET_KEY phải là Test Mode key, không có khoảng trắng thừa.')
    if not secret:
        errors.append('Thiếu STRIPE_WEBHOOK_SECRET của endpoint Test Mode.')
    elif secret != secret.strip() or not secret.startswith('whsec_'):
        errors.append('STRIPE_WEBHOOK_SECRET phải có định dạng whsec_, không có khoảng trắng thừa.')
    try:
        origin=urlsplit(settings.STRIPE_PUBLIC_BASE_URL)
        valid=bool(origin.hostname and origin.scheme in ('http','https') and not origin.username
                   and not origin.password and origin.path in ('','/') and not origin.query and not origin.fragment)
        _=origin.port
        if settings.ON_RENDER:
            valid=valid and origin.scheme=='https' and origin.hostname in settings.ALLOWED_HOSTS
    except ValueError:
        valid=False
    if not valid:
        errors.append('STRIPE_PUBLIC_BASE_URL phải là origin hợp lệ; Render cần HTTPS và hostname của service.')
    return errors


def payment_readiness(booking, deposit, now):
    """Explain the first blocker without changing deposit/booking state."""
    if deposit.reconciliation_required:
        return 'RECONCILIATION', 'Giao dịch cần nhà hàng đối soát; chưa thể thanh toán lại.'
    if deposit.status=='SUCCEEDED':
        return 'PAID', 'Tiền cọc đã được ghi nhận.'
    if deposit.expires_at<=now or deposit.status=='EXPIRED':
        return 'EXPIRED', 'Đã hết thời gian giữ bàn. Vui lòng tạo đặt bàn mới.'
    if booking.status!='PENDING_DEPOSIT' or deposit.status not in ('PENDING','FAILED'):
        return 'NOT_PAYABLE', 'Trạng thái đặt bàn hiện tại không cho phép thanh toán tiền cọc.'
    if configuration_errors():
        return 'CONFIGURATION', 'Nhà hàng chưa cấu hình đầy đủ Stripe Test Mode; vui lòng liên hệ quản lý.'
    return 'READY', 'Có thể mở Stripe Checkout trong thời gian giữ bàn.'
