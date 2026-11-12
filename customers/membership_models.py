"""Additive membership policy/snapshots. Existing invoices and points stay intact."""
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def default_tiers():
    return [{'tier': tier, 'minimum': minimum, 'percent': rate, 'benefits': ''}
        for tier, minimum, rate in [('MEMBER', '0', '0'), ('SILVER', '2000000', '3'),
            ('GOLD', '5000000', '5'), ('VIP', '15000000', '5')]]


class MembershipPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    tiers = models.JSONField(default=default_tiers)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        default_permissions = ()
        permissions = [('manage_membership_policy', 'Quản lý chính sách thành viên')]
        constraints = [models.CheckConstraint(condition=models.Q(pk=1), name='membership_policy_singleton')]

    def clean(self):
        super().clean()
        try:
            if not isinstance(self.tiers, list) or [x['tier'] for x in self.tiers] != ['MEMBER', 'SILVER', 'GOLD', 'VIP']:
                raise ValueError
            minimums = [Decimal(str(row['minimum'])) for row in self.tiers]
            rates = [Decimal(str(row['percent'])) for row in self.tiers]
            if any(not x.is_finite() for x in minimums+rates) or minimums[0] != 0 or rates[0] != 0:
                raise ValueError
            if any(a >= b for a, b in zip(minimums, minimums[1:])) or any(x>Decimal('999999999999.99') for x in minimums) or any(not 0 <= x <= 100 for x in rates):
                raise ValueError
            if any(len(str(row.get('benefits', ''))) > 2000 for row in self.tiers):
                raise ValueError
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValidationError('Cần đủ MEMBER/SILVER/GOLD/VIP, ngưỡng tăng dần từ 0, ưu đãi 0–100%; MEMBER 0%.')


class MembershipDiscount(models.Model):
    order = models.OneToOneField('customers.Order', on_delete=models.PROTECT, related_name='membership_discount')
    snapshot = models.JSONField()
    selected = models.CharField(max_length=12, choices=[('MEMBERSHIP', 'Thành viên'), ('VOUCHER', 'Voucher'), ('MANUAL', 'Thủ công')])
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=models.Q(amount__gte=0), name='membership_discount_nonnegative')]


class InvoiceRefund(models.Model):
    """Record a refund ALREADY completed outside this system; never calls a provider."""
    invoice = models.ForeignKey('customers.Invoice', on_delete=models.PROTECT, related_name='recorded_refunds')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=160, unique=True)
    reason = models.CharField(max_length=1000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        default_permissions = ()
        permissions = [('record_invoice_refund', 'Ghi nhận hoàn tiền đã đối soát')]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='invoice_refund_positive')]
