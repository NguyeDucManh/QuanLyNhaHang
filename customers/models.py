from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
import uuid
from .order_numbers import generate_order_number
from .payment_numbers import generate_payment_number
from django.utils import timezone


class Booking(models.Model):
    promotion_code = models.CharField(max_length=40, blank=True, editable=False)
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Chờ xác nhận'
        CONFIRMED = 'CONFIRMED', 'Đã xác nhận'
        CANCELLED = 'CANCELLED', 'Đã hủy'
        COMPLETED = 'COMPLETED', 'Hoàn thành'
        PENDING_DEPOSIT = 'PENDING_DEPOSIT', 'Chờ thanh toán tiền cọc'

    table = models.ForeignKey('RestaurantTable', on_delete=models.PROTECT, null=True, blank=True, related_name='bookings', verbose_name='Bàn')
    status = models.CharField('Trạng thái', max_length=16, choices=Status.choices, default=Status.PENDING)
    start_time = models.DateTimeField('Bắt đầu', null=True, blank=True)
    end_time = models.DateTimeField('Kết thúc', null=True, blank=True)
    food_subtotal = models.DecimalField('Tạm tính món đặt trước', max_digits=14, decimal_places=2, default=0, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField("Họ tên", max_length=100)
    phone = models.CharField("Số điện thoại", max_length=20)
    date = models.DateField("Ngày đặt")
    time = models.TimeField("Giờ đến")
    guests = models.PositiveSmallIntegerField("Số khách")
    note = models.TextField("Ghi chú", blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Yêu cầu đặt bàn"
        verbose_name_plural = "Yêu cầu đặt bàn"
        constraints = [
            models.CheckConstraint(condition=models.Q(food_subtotal__gte=0), name='booking_food_nonnegative'),
            models.CheckConstraint(condition=models.Q(guests__gt=0), name='booking_guests_positive'),
            models.CheckConstraint(condition=models.Q(status__in=['PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED','PENDING_DEPOSIT']), name='booking_status_valid'),
            models.CheckConstraint(condition=(models.Q(start_time__isnull=True, end_time__isnull=True) | models.Q(start_time__isnull=False, end_time__isnull=False, end_time__gt=models.F('start_time'))), name='booking_window_valid'),
        ]
        indexes = [models.Index(fields=['table', 'status', 'start_time', 'end_time'], name='booking_slot_idx')]

    def __str__(self):
        return f"{self.name} - {self.date} {self.time}"

    def clean(self):
        if self.pk and self.status=='CONFIRMED':
            from .deposit_models import BookingDeposit
            if BookingDeposit.objects.filter(booking_id=self.pk).exclude(status='SUCCEEDED',reconciliation_required=False).exists():
                raise ValidationError('Booking yêu cầu cọc chỉ được xác nhận sau khi Stripe webhook hợp lệ đã ghi nhận thanh toán.')



class MobileBookingReceipt(models.Model):
    """Legacy retry receipts retained for migration and stored-data compatibility.

    No active endpoint writes these records. Keep the model/table so removing
    the former client adapters does not delete existing receipts or migrations.
    """
    request_key = models.UUIDField(unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT)
    payload_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class Category(models.Model):
    name = models.CharField("Danh mục", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    is_active = models.BooleanField("Đang hoạt động", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = "Danh mục món"
        verbose_name_plural = "Danh mục món"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    name = models.CharField("Tên món", max_length=200, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='menu_items', verbose_name="Danh mục")
    price = models.DecimalField("Giá (VND)", max_digits=12, decimal_places=2, null=True, blank=True)
    image = models.CharField("Ảnh trong static/", max_length=255)
    description = models.TextField("Mô tả", blank=True)
    is_available = models.BooleanField("Đang phục vụ", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = "Món ăn / đồ uống"
        verbose_name_plural = "Món ăn / đồ uống"
        constraints = [models.CheckConstraint(condition=models.Q(price__gte=0) | models.Q(price__isnull=True), name='menu_price_nonnegative')]

    def __str__(self):
        return self.name


class BookingItem(models.Model):
    selection_key = models.CharField(max_length=60, default='', blank=True, editable=False)
    extras = models.JSONField(default=dict, blank=True, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='preorder_items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    item_name = models.CharField('Tên món đã lưu', max_length=200)
    quantity = models.PositiveSmallIntegerField('Số lượng')
    unit_price = models.DecimalField('Đơn giá đã lưu', max_digits=12, decimal_places=2)
    line_total = models.DecimalField('Thành tiền', max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['booking','menu_item','selection_key'], name='booking_menu_selection_unique'),
            models.CheckConstraint(condition=models.Q(quantity__gt=0,quantity__lte=99,unit_price__gte=0,line_total=models.F('unit_price')*models.F('quantity')), name='bookingitem_values_valid'),
            models.CheckConstraint(condition=models.Q(item_name__regex=r'\S'), name='bookingitem_name_nonblank'),
        ]


class Area(models.Model):
    name = models.CharField('Tên khu vực', max_length=100, unique=True)
    description = models.TextField('Mô tả', blank=True)
    is_active = models.BooleanField('Đang hoạt động', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Khu vực'
        verbose_name_plural = 'Khu vực'
        constraints = [models.CheckConstraint(condition=models.Q(name__regex=r'\S'), name='area_name_nonblank')]

    def clean(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({'name': 'Tên khu vực không được rỗng.'})

    def __str__(self):
        return self.name


class RestaurantTable(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Trống'
        OCCUPIED = 'OCCUPIED', 'Đang sử dụng'
        MAINTENANCE = 'MAINTENANCE', 'Bảo trì'

    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name='tables', verbose_name='Khu vực')
    code = models.CharField('Mã bàn', max_length=30, unique=True)
    capacity = models.PositiveSmallIntegerField('Sức chứa')
    status = models.CharField('Trạng thái vận hành', max_length=12, choices=Status.choices, default=Status.AVAILABLE)
    is_active = models.BooleanField('Đang hoạt động', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['area_id', 'code']
        verbose_name = 'Bàn ăn'
        verbose_name_plural = 'Bàn ăn'
        constraints = [
            models.CheckConstraint(condition=models.Q(capacity__gt=0), name='table_capacity_positive'),
            models.CheckConstraint(condition=models.Q(code__regex=r'\S'), name='table_code_nonblank'),
            models.CheckConstraint(condition=models.Q(status__in=['AVAILABLE', 'OCCUPIED', 'MAINTENANCE']), name='table_status_valid'),
        ]

    def clean(self):
        self.code = self.code.strip()
        if not self.code:
            raise ValidationError({'code': 'Mã bàn không được rỗng.'})
        if self.capacity is not None and self.capacity <= 0:
            raise ValidationError({'capacity': 'Sức chứa phải lớn hơn 0.'})

    def __str__(self):
        return self.code


class Supplier(models.Model):
    code = models.CharField('Mã', max_length=30, unique=True)
    name = models.CharField('Tên nhà cung cấp', max_length=150)
    contact_name = models.CharField('Người liên hệ', max_length=150, blank=True)
    phone = models.CharField('Điện thoại', max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField('Địa chỉ', blank=True)
    is_active = models.BooleanField('Hoạt động', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        constraints = [models.CheckConstraint(condition=models.Q(code__regex=r'\S', name__regex=r'\S'), name='supplier_nonblank')]

    def __str__(self):
        return f'{self.code} · {self.name}'


class Ingredient(models.Model):
    class Unit(models.TextChoices):
        KG = 'kg', 'kg'
        G = 'g', 'g'
        L = 'l', 'lít'
        ML = 'ml', 'ml'
        PIECE = 'piece', 'cái'
        PORTION = 'portion', 'phần'

    code = models.CharField('Mã', max_length=30, unique=True)
    name = models.CharField('Tên nguyên liệu', max_length=150)
    unit = models.CharField('Đơn vị', max_length=10, choices=Unit.choices)
    current_stock = models.DecimalField('Tồn hiện tại', max_digits=14, decimal_places=3, default=0, editable=False)
    minimum_stock = models.DecimalField('Tồn tối thiểu', max_digits=14, decimal_places=3, default=0)
    is_active = models.BooleanField('Hoạt động', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        constraints = [
            models.CheckConstraint(condition=models.Q(current_stock__gte=0, minimum_stock__gte=0), name='ingredient_nonnegative'),
            models.CheckConstraint(condition=models.Q(code__regex=r'\S', name__regex=r'\S'), name='ingredient_nonblank'),
            models.CheckConstraint(condition=models.Q(unit__in=['kg','g','l','ml','piece','portion']), name='ingredient_unit_valid'),
        ]

    def __str__(self):
        return f'{self.code} · {self.name} ({self.get_unit_display()})'


class RecipeIngredient(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name='recipe_lines', verbose_name='Món')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, verbose_name='Nguyên liệu')
    quantity_required = models.DecimalField('Lượng cho một món', max_digits=12, decimal_places=3)

    class Meta:
        ordering = ['menu_item_id','ingredient_id']
        constraints = [
            models.UniqueConstraint(fields=['menu_item','ingredient'], name='recipe_ingredient_unique'),
            models.CheckConstraint(condition=models.Q(quantity_required__gt=0), name='recipe_quantity_positive'),
        ]


class Order(models.Model):
    promotion = models.ForeignKey('Promotion', null=True, blank=True, on_delete=models.PROTECT, editable=False)
    promotion_snapshot = models.JSONField(default=dict, blank=True, editable=False)
    order_number = models.CharField(max_length=50, unique=True, default=generate_order_number, editable=False)
    booking = models.OneToOneField(Booking, null=True, blank=True, on_delete=models.PROTECT, related_name='service_order')
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Chờ xác nhận'
        CONFIRMED = 'CONFIRMED', 'Đã xác nhận'
        PREPARING = 'PREPARING', 'Đang chuẩn bị'
        COMPLETED = 'COMPLETED', 'Hoàn thành'
        CANCELLED = 'CANCELLED', 'Đã hủy'

    class Type(models.TextChoices):
        DINE_IN = 'DINE_IN', 'Tại bàn'
        TAKEAWAY = 'TAKEAWAY', 'Mang đi'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='restaurant_orders', verbose_name='Khách hàng')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_orders')
    table = models.ForeignKey(RestaurantTable, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Bàn')
    order_type = models.CharField('Hình thức', max_length=12, choices=Type.choices, default=Type.TAKEAWAY)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField('Giảm giá', max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.TextField('Ghi chú', blank=True)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status','created_at'], name='order_status_date_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['PENDING','CONFIRMED','PREPARING','COMPLETED','CANCELLED']), name='order_status_valid'),
            models.CheckConstraint(condition=models.Q(subtotal__gte=0,discount_amount__gte=0,total_amount__gte=0,discount_amount__lte=models.F('subtotal'),total_amount=models.F('subtotal')-models.F('discount_amount')), name='order_amounts_valid'),
            models.CheckConstraint(condition=(models.Q(order_type='DINE_IN',table__isnull=False)|models.Q(order_type='TAKEAWAY',table__isnull=True)), name='order_type_table_valid'),
        ]


class OrderItem(models.Model):
    extras = models.JSONField(default=dict, blank=True, editable=False)
    class InventoryStatus(models.TextChoices):
        NOT_PROCESSED = 'NOT_PROCESSED', 'Chưa xử lý kho'
        DEDUCTED = 'DEDUCTED', 'Đã trừ kho'
        NO_RECIPE = 'NO_RECIPE', 'Chưa có công thức — không trừ kho'
        LEGACY = 'LEGACY', 'Món đã xong trước MODULE 06 — không trừ hồi tố'

    inventory_status = models.CharField(max_length=16, choices=InventoryStatus.choices, default=InventoryStatus.NOT_PROCESSED, editable=False)
    inventory_processed_at = models.DateTimeField(null=True, blank=True, editable=False)
    class KitchenStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Chưa gửi bếp'
        QUEUED = 'QUEUED', 'Chờ bếp'
        PREPARING = 'PREPARING', 'Đang chuẩn bị'
        READY = 'READY', 'Đã làm xong'
        CANCELLED = 'CANCELLED', 'Đã hủy món'

    kitchen_status = models.CharField(max_length=10, choices=KitchenStatus.choices, default=KitchenStatus.DRAFT, editable=False)
    queued_at = models.DateTimeField(null=True, blank=True, editable=False)
    preparing_at = models.DateTimeField(null=True, blank=True, editable=False)
    ready_at = models.DateTimeField(null=True, blank=True, editable=False)
    class Source(models.TextChoices):
        PREORDER = 'PREORDER', 'Đặt trước'
        DIRECT = 'DIRECT', 'Gọi thêm'

    item_name = models.CharField(max_length=200)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.DIRECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, verbose_name='Món')
    quantity = models.PositiveIntegerField('Số lượng')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField('Ghi chú món', max_length=250, blank=True)

    class Meta:
        indexes = [models.Index(fields=['kitchen_status','queued_at'], name='kitchen_queue_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0,unit_price__gte=0,line_total=models.F('unit_price')*models.F('quantity')), name='orderitem_amount_valid'),
            models.CheckConstraint(condition=models.Q(source__in=['PREORDER','DIRECT'], item_name__regex=r'\S'), name='orderitem_snapshot_valid'),
            models.CheckConstraint(condition=(
                models.Q(kitchen_status='DRAFT',queued_at__isnull=True,preparing_at__isnull=True,ready_at__isnull=True)
                | models.Q(kitchen_status='QUEUED',queued_at__isnull=False,preparing_at__isnull=True,ready_at__isnull=True)
                | models.Q(kitchen_status='PREPARING',queued_at__isnull=False,preparing_at__isnull=False,ready_at__isnull=True)
                | models.Q(kitchen_status='READY',queued_at__isnull=False,preparing_at__isnull=False,ready_at__isnull=False)
                | models.Q(kitchen_status='CANCELLED',preparing_at__isnull=True,ready_at__isnull=True)
            ),name='orderitem_kitchen_state_valid'),
            models.CheckConstraint(condition=(models.Q(preparing_at__isnull=True)|models.Q(preparing_at__gte=models.F('queued_at')))&(models.Q(ready_at__isnull=True)|models.Q(ready_at__gte=models.F('preparing_at'))),name='orderitem_kitchen_times_valid'),
              models.CheckConstraint(condition=(
                  models.Q(inventory_status='NOT_PROCESSED',inventory_processed_at__isnull=True)&~models.Q(kitchen_status='READY')
                  |models.Q(inventory_status__in=['DEDUCTED','NO_RECIPE'],inventory_processed_at__isnull=False,kitchen_status='READY')
                  |models.Q(inventory_status='LEGACY',inventory_processed_at__isnull=True,kitchen_status='READY')
              ),name='orderitem_inventory_state_valid'),
        ]


class Invoice(models.Model):
    booking_deposit = models.OneToOneField('customers.BookingDeposit',null=True,blank=True,on_delete=models.PROTECT,related_name='applied_invoice')
    deposit_applied_amount = models.DecimalField(max_digits=14,decimal_places=2,default=0,editable=False)
    @property
    def balance_due(self): return max(0,self.total_amount-self.deposit_applied_amount)
    class Status(models.TextChoices):
        UNPAID = 'UNPAID', 'Chưa thanh toán'
        PAID = 'PAID', 'Đã thanh toán'
        CANCELLED = 'CANCELLED', 'Đã hủy'

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='invoice')
    invoice_number = models.CharField(max_length=50, unique=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)
    issued_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=models.Q(subtotal__gte=0,discount_amount__gte=0,total_amount__gte=0,discount_amount__lte=models.F('subtotal'),total_amount=models.F('subtotal')-models.F('discount_amount'),status__in=['UNPAID','PAID','CANCELLED']), name='invoice_amounts_status_valid'),models.CheckConstraint(condition=models.Q(deposit_applied_amount__gte=0,deposit_applied_amount__lte=models.F('total_amount'))&(models.Q(booking_deposit__isnull=False)|models.Q(deposit_applied_amount=0)),name='invoice_deposit_valid')]


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'CASH', 'Tiền mặt'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Chuyển khoản'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Chờ xác nhận'
        SUCCEEDED = 'SUCCEEDED', 'Thành công'
        FAILED = 'FAILED', 'Thất bại'
        CANCELLED = 'CANCELLED', 'Đã hủy'

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    payment_number = models.CharField(max_length=50, unique=True, default=generate_payment_number, editable=False)
    customer_confirmed_at = models.DateTimeField(null=True, blank=True)
    customer_initiated = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField('Số tiền', max_digits=14, decimal_places=2)
    payment_method = models.CharField('Phương thức', max_length=15, choices=Method.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    transaction_reference = models.CharField('Mã giao dịch', max_length=100, blank=True)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_payments')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='confirmed_payments')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0,payment_method__in=['CASH','BANK_TRANSFER'],status__in=['PENDING','SUCCEEDED','FAILED','CANCELLED']), name='payment_values_valid'),
            models.UniqueConstraint(fields=['invoice'], condition=models.Q(status__in=['PENDING','SUCCEEDED']), name='invoice_one_live_payment'),
            models.UniqueConstraint(fields=['transaction_reference'],condition=models.Q(payment_method='BANK_TRANSFER',status__in=['PENDING','SUCCEEDED']),name='bank_reference_once'),
            models.CheckConstraint(condition=(models.Q(payment_method='CASH')|models.Q(payment_method='BANK_TRANSFER',transaction_reference__regex=r'\S')),name='bank_reference_required'),
            models.CheckConstraint(condition=(models.Q(status='SUCCEEDED',paid_at__isnull=False,confirmed_by__isnull=False)|models.Q(status__in=['PENDING','FAILED','CANCELLED'],paid_at__isnull=True)), name='payment_confirmation_valid'),
        ]


class StockDocument(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Nháp'
        CONFIRMED = 'CONFIRMED', 'Đã xác nhận'

    code = models.CharField('Mã phiếu', max_length=50, unique=True)
    date = models.DateField('Ngày')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    note = models.TextField('Ghi chú', blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=(models.Q(status='DRAFT',confirmed_at__isnull=True)|models.Q(status='CONFIRMED',confirmed_at__isnull=False)), name='%(class)s_state_valid')]


class StockReceipt(StockDocument):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name='Nhà cung cấp')


class StockIssue(StockDocument):
    reason = models.CharField('Lý do xuất', max_length=250, blank=True)


class StockReceiptItem(models.Model):
    receipt = models.ForeignKey(StockReceipt, on_delete=models.PROTECT, related_name='items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, verbose_name='Nguyên liệu')
    quantity = models.DecimalField('Số lượng', max_digits=12, decimal_places=3)
    unit_price = models.DecimalField('Đơn giá', max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return self.quantity*self.unit_price

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0,unit_price__gte=0), name='receiptitem_values_valid'),models.UniqueConstraint(fields=['receipt','ingredient'], name='receipt_ingredient_unique')]


class StockIssueItem(models.Model):
    issue = models.ForeignKey(StockIssue, on_delete=models.PROTECT, related_name='items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, verbose_name='Nguyên liệu')
    quantity = models.DecimalField('Số lượng', max_digits=12, decimal_places=3)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='issueitem_quantity_positive'),models.UniqueConstraint(fields=['issue','ingredient'], name='issue_ingredient_unique')]


class StockMovement(models.Model):
    class Type(models.TextChoices):
        IMPORT = 'IMPORT', 'Nhập kho'
        EXPORT = 'EXPORT', 'Xuất kho'
        ORDER_USAGE = 'ORDER_USAGE', 'Dùng cho đơn hàng'

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=12, choices=Type.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    stock_before = models.DecimalField(max_digits=14, decimal_places=3)
    stock_after = models.DecimalField(max_digits=14, decimal_places=3)
    reference = models.CharField(max_length=80)
    receipt = models.ForeignKey(StockReceipt, null=True, blank=True, on_delete=models.PROTECT)
    issue = models.ForeignKey(StockIssue, null=True, blank=True, on_delete=models.PROTECT)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT)
    order_item = models.ForeignKey(OrderItem, null=True, blank=True, on_delete=models.PROTECT, related_name='stock_movements')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def reference_type(self):
        return 'STOCK_RECEIPT' if self.receipt_id else 'STOCK_ISSUE' if self.issue_id else 'ORDER_ITEM' if self.order_item_id else 'ORDER_LEGACY'

    @property
    def reference_id(self):
        return self.receipt_id or self.issue_id or self.order_item_id or self.order_id

    class Meta:
        ordering = ['-created_at','-id']
        indexes = [models.Index(fields=['ingredient','created_at'], name='movement_ingredient_date_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0,stock_before__gte=0,stock_after__gte=0), name='movement_nonnegative'),
            models.CheckConstraint(condition=(models.Q(movement_type='IMPORT',receipt__isnull=False,issue__isnull=True,order__isnull=True,stock_after=models.F('stock_before')+models.F('quantity'))|models.Q(movement_type='EXPORT',receipt__isnull=True,issue__isnull=False,order__isnull=True,stock_after=models.F('stock_before')-models.F('quantity'))|models.Q(movement_type='ORDER_USAGE',receipt__isnull=True,issue__isnull=True,order__isnull=False,stock_after=models.F('stock_before')-models.F('quantity'))), name='movement_reference_balance_valid'),
            models.UniqueConstraint(fields=['ingredient','receipt'],condition=models.Q(receipt__isnull=False),name='movement_receipt_once'),
            models.UniqueConstraint(fields=['ingredient','issue'],condition=models.Q(issue__isnull=False),name='movement_issue_once'),
            models.UniqueConstraint(fields=['ingredient','order'],condition=models.Q(order__isnull=False,order_item__isnull=True),name='movement_order_once'),
            models.UniqueConstraint(fields=['ingredient','order_item'],condition=models.Q(order_item__isnull=False),name='movement_orderitem_once'),
            models.CheckConstraint(condition=models.Q(order_item__isnull=True)|models.Q(movement_type='ORDER_USAGE',order__isnull=False,receipt__isnull=True,issue__isnull=True),name='movement_orderitem_reference_valid'),
        ]

from .module07_models import Topping, Combo, ComboItem, Promotion, Review, RestaurantInfo, Position, Employee, Shift, WorkSchedule, Attendance, PayrollPeriod, Payroll, Conversation, ConversationParticipant, Message
from .ai_models import IngredientSupplyPolicy, FaceProfile, FaceEmbedding, FaceAudit, FaceChallenge, AIConversation, AIMessage
from .location_models import AttendanceLocationPolicy,AttendanceLocationEvent
from .operations_models import PurchaseOrder, PurchaseOrderItem, PurchaseReceiving, CustomerLoyalty, LoyaltyTransaction, AuditLog, BookingVisit, BookingWaitlist
from .deposit_models import BookingDeposit, StripeCheckoutAttempt, StripeWebhookEvent
from .table_assignment_models import TableServiceAssignment
