"""Additive operational records; legacy primary keys and booking enums stay intact."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Nháp'
        SUBMITTED = 'SUBMITTED', 'Chờ duyệt'
        APPROVED = 'APPROVED', 'Đã duyệt'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Nhận một phần'
        RECEIVED = 'RECEIVED', 'Đã nhận đủ'
        CANCELLED = 'CANCELLED', 'Đã hủy'
    code = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey('customers.Supplier', on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='approved_purchase_orders')
    order_date = models.DateField(default=timezone.localdate)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    note = models.TextField(blank=True, max_length=1000)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']
        permissions = [('approve_purchaseorder', 'Duyệt đơn mua hàng'), ('receive_purchaseorder', 'Nhận đơn mua hàng')]
        constraints = [models.CheckConstraint(condition=models.Q(subtotal__gte=0), name='po_subtotal_nonnegative'), models.CheckConstraint(condition=models.Q(status__in=['DRAFT','SUBMITTED','APPROVED','PARTIALLY_RECEIVED','RECEIVED','CANCELLED']), name='po_status_valid')]


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='items')
    ingredient = models.ForeignKey('customers.Ingredient', on_delete=models.PROTECT)
    quantity_ordered = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit = models.CharField(max_length=10)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=16, decimal_places=2)
    @property
    def remaining(self): return self.quantity_ordered - self.quantity_received
    class Meta:
        constraints = [models.UniqueConstraint(fields=['purchase_order','ingredient'], name='po_ingredient_unique'), models.CheckConstraint(condition=models.Q(quantity_ordered__gt=0, quantity_received__gte=0, quantity_received__lte=models.F('quantity_ordered'),unit_price__gte=0,line_total__gte=0), name='po_item_values_valid')]


class PurchaseReceiving(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='receivings')
    receipt = models.OneToOneField('customers.StockReceipt', on_delete=models.PROTECT)
    request_key = models.UUIDField(unique=True)
    payload_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class CustomerLoyalty(models.Model):
    customer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='loyalty')
    points_balance = models.PositiveBigIntegerField(default=0)
    lifetime_points = models.PositiveBigIntegerField(default=0)
    tier = models.CharField(max_length=12, default='MEMBER', choices=[(x,x) for x in ('MEMBER','SILVER','GOLD','VIP')])
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        permissions = [('adjust_customerloyalty','Điều chỉnh điểm thành viên')]


class LoyaltyTransaction(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    type = models.CharField(max_length=8, choices=[('EARN','Tích điểm'),('ADJUST','Điều chỉnh')])
    points = models.BigIntegerField()
    source_type = models.CharField(max_length=30)
    source_id = models.CharField(max_length=64)
    note = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='loyalty_actions')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at','-pk']
        constraints = [models.UniqueConstraint(fields=['source_type','source_id'], name='loyalty_source_once'),models.CheckConstraint(condition=models.Q(type='EARN',points__gte=0)|models.Q(type='ADJUST'),name='loyalty_type_points_valid')]
        indexes = [models.Index(fields=['customer','created_at'],name='loyalty_customer_date')]


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=64)
    description = models.CharField(max_length=250)
    before_data = models.JSONField(default=dict)
    after_data = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at','-pk']
        default_permissions = ('view',)
        indexes = [models.Index(fields=['created_at'],name='audit_created_idx'),models.Index(fields=['entity_type','entity_id'],name='audit_entity_idx')]


class BookingVisit(models.Model):
    """Arrival metadata complements existing CONFIRMED/CANCELLED booking states."""
    booking = models.OneToOneField('customers.Booking', on_delete=models.PROTECT, related_name='visit')
    state = models.CharField(max_length=12, choices=[('CHECKED_IN','Đã đến'),('NO_SHOW','Không đến')])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    occurred_at = models.DateTimeField(default=timezone.now)
    class Meta:
        permissions = [('checkin_booking','Check-in đặt bàn'),('noshow_booking','Đánh dấu không đến'),('transfer_table','Chuyển bàn phục vụ')]


class BookingWaitlist(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    requested_date = models.DateField()
    requested_time = models.TimeField()
    guests = models.PositiveSmallIntegerField()
    phone = models.CharField(max_length=20)
    note = models.TextField(max_length=500, blank=True)
    status = models.CharField(max_length=12, default='WAITING', choices=[('WAITING','Đang chờ'),('OFFERED','Đã có bàn'),('CONVERTED','Đã đặt bàn'),('CANCELLED','Đã hủy'),('EXPIRED','Hết hạn')])
    created_at = models.DateTimeField(auto_now_add=True)
    promoted_at = models.DateTimeField(null=True, blank=True)
    booking = models.OneToOneField('customers.Booking', null=True, blank=True, on_delete=models.PROTECT)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True)
    class Meta:
        ordering = ['created_at']
        permissions = [('convert_bookingwaitlist','Xếp bàn từ danh sách chờ')]
        indexes = [models.Index(fields=['status','requested_date'],name='waitlist_status_date')]
        constraints = [models.CheckConstraint(condition=models.Q(guests__gte=1,guests__lte=20),name='waitlist_guests_valid'),models.CheckConstraint(condition=models.Q(status='CONVERTED',booking__isnull=False,promoted_at__isnull=False)|models.Q(status__in=['WAITING','OFFERED','CANCELLED','EXPIRED'],booking__isnull=True,promoted_at__isnull=True),name='waitlist_conversion_valid')]
