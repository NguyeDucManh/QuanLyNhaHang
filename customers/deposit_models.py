import uuid
from django.conf import settings
from django.db import models


class BookingDeposit(models.Model):
    booking = models.OneToOneField('customers.Booking',on_delete=models.PROTECT,related_name='deposit')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=14,decimal_places=0)
    currency = models.CharField(max_length=3,default='vnd')
    provider = models.CharField(max_length=12,default='STRIPE')
    status = models.CharField(max_length=12,default='PENDING',choices=[(s,label) for s,label in [('PENDING','Chờ thanh toán'),('SUCCEEDED','Đã thanh toán'),('FAILED','Thanh toán không thành công'),('EXPIRED','Hết hạn'),('CANCELLED','Đã hủy')]])
    expires_at = models.DateTimeField(db_index=True)
    paid_at = models.DateTimeField(null=True,blank=True)
    expired_at = models.DateTimeField(null=True,blank=True)
    reconciliation_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    @property
    def remaining_estimated_amount(self): return max(0,self.booking.food_subtotal-self.amount)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(amount__gt=0,currency='vnd',provider='STRIPE'),name='deposit_positive_vnd'),models.CheckConstraint(condition=models.Q(status='SUCCEEDED',paid_at__isnull=False)|models.Q(status__in=['PENDING','FAILED','EXPIRED','CANCELLED'],paid_at__isnull=True),name='deposit_payment_state')]
        indexes=[models.Index(fields=['status','expires_at'],name='deposit_expiry_idx')]


class StripeCheckoutAttempt(models.Model):
    deposit = models.ForeignKey(BookingDeposit,on_delete=models.PROTECT,related_name='attempts')
    request_key = models.UUIDField(default=uuid.uuid4,unique=True)
    session_id = models.CharField(max_length=255,unique=True,null=True,blank=True)
    payment_intent_id = models.CharField(max_length=255,unique=True,null=True,blank=True)
    checkout_url = models.URLField(max_length=3000,blank=True)
    status = models.CharField(max_length=12,default='CREATING',choices=[(s,s) for s in ['CREATING','OPEN','PAID','FAILED','EXPIRED']])
    stripe_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-pk']
        constraints=[models.UniqueConstraint(fields=['deposit'],condition=models.Q(status__in=['CREATING','OPEN']),name='deposit_one_open_checkout')]


class StripeWebhookEvent(models.Model):
    event_id = models.CharField(max_length=255,unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=80)
    # Intentionally no raw payload, customer card details, headers or secrets.
