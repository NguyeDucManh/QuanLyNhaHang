"""Module 07 models, registered through customers.models; reuse existing commerce."""
from datetime import datetime, timedelta
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

USER=settings.AUTH_USER_MODEL
MONEY=dict(max_digits=14,decimal_places=2,default=0,validators=[MinValueValidator(0)])

class Topping(models.Model):
    name=models.CharField(max_length=150,unique=True)
    price=models.DecimalField(**MONEY)
    is_available=models.BooleanField(default=True)
    menu_items=models.ManyToManyField('MenuItem',related_name='toppings',blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(price__gte=0),name='topping_price_valid')]
    def __str__(self): return self.name

class Combo(models.Model):
    name=models.CharField(max_length=150,unique=True)
    description=models.TextField(blank=True)
    price=models.DecimalField(**MONEY)
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(price__gte=0),name='combo_price_valid')]
    def __str__(self): return self.name

class ComboItem(models.Model):
    combo=models.ForeignKey(Combo,on_delete=models.CASCADE,related_name='items')
    menu_item=models.ForeignKey('MenuItem',on_delete=models.PROTECT)
    quantity=models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    class Meta:
        constraints=[models.UniqueConstraint(fields=['combo','menu_item'],name='combo_menu_unique'),models.CheckConstraint(condition=models.Q(quantity__gt=0),name='combo_quantity_valid')]
    def __str__(self): return f'{self.combo} / {self.menu_item} × {self.quantity}'

class Promotion(models.Model):
    class Type(models.TextChoices):
        PERCENT='PERCENT','Phần trăm'
        FIXED='FIXED','Số tiền'
    code=models.CharField(max_length=40,unique=True)
    name=models.CharField(max_length=150)
    discount_type=models.CharField(max_length=8,choices=Type.choices)
    discount_value=models.DecimalField(**MONEY)
    min_order_amount=models.DecimalField(**MONEY)
    max_discount_amount=models.DecimalField(max_digits=14,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    start_at=models.DateTimeField()
    end_at=models.DateTimeField()
    usage_limit=models.PositiveIntegerField(null=True,blank=True,validators=[MinValueValidator(1)])
    used_count=models.PositiveIntegerField(default=0,editable=False)
    is_active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(end_at__gt=models.F('start_at'),discount_value__gt=0,min_order_amount__gte=0)&(models.Q(discount_type='FIXED')|models.Q(discount_type='PERCENT',discount_value__lte=100))&(models.Q(usage_limit__isnull=True)|models.Q(usage_limit__gt=0,used_count__lte=models.F('usage_limit')))&(models.Q(max_discount_amount__isnull=True)|models.Q(max_discount_amount__gte=0)),name='promotion_values_valid')]
    def clean(self): self.code=self.code.strip().upper()
    def __str__(self): return f'{self.code} · {self.name}'

class Review(models.Model):
    customer=models.ForeignKey(USER,on_delete=models.PROTECT)
    order=models.ForeignKey('Order',on_delete=models.PROTECT,related_name='reviews')
    menu_item=models.ForeignKey('MenuItem',on_delete=models.PROTECT,related_name='reviews')
    rating=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)])
    comment=models.TextField(max_length=2000,blank=True)
    is_visible=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['order','menu_item'],name='review_order_menu_once'),models.CheckConstraint(condition=models.Q(rating__gte=1,rating__lte=5),name='review_rating_valid')]

class RestaurantInfo(models.Model):
    name=models.CharField(max_length=150)
    description=models.TextField(blank=True)
    address=models.TextField(blank=True)
    phone=models.CharField(max_length=30,blank=True)
    email=models.EmailField(blank=True)
    opening_time=models.TimeField()
    closing_time=models.TimeField()
    latitude=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True,validators=[MinValueValidator(-90),MaxValueValidator(90)])
    longitude=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True,validators=[MinValueValidator(-180),MaxValueValidator(180)])
    is_active=models.BooleanField(default=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['is_active'],condition=models.Q(is_active=True),name='one_active_restaurant')]
    def __str__(self): return self.name

class Position(models.Model):
    name=models.CharField(max_length=100,unique=True)
    description=models.TextField(blank=True)
    is_active=models.BooleanField(default=True)
    def __str__(self): return self.name

class Employee(models.Model):
    user=models.OneToOneField(USER,on_delete=models.PROTECT,related_name='employee')
    employee_code=models.CharField(max_length=30,unique=True)
    full_name=models.CharField(max_length=150)
    phone=models.CharField(max_length=30,blank=True)
    position=models.ForeignKey(Position,on_delete=models.PROTECT)
    hire_date=models.DateField()
    employment_status=models.CharField(max_length=12,choices=[('ACTIVE','Đang làm'),('ON_LEAVE','Nghỉ phép'),('ENDED','Đã nghỉ')],default='ACTIVE')
    base_salary=models.DecimalField(**MONEY)
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(base_salary__gte=0,employment_status__in=['ACTIVE','ON_LEAVE','ENDED']),name='employee_salary_status_valid')]
    def __str__(self): return f'{self.employee_code} · {self.full_name}'

class Shift(models.Model):
    name=models.CharField(max_length=100,unique=True)
    start_time=models.TimeField()
    end_time=models.TimeField()
    required_staff=models.PositiveSmallIntegerField(default=1,validators=[MinValueValidator(1)])
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(required_staff__gte=1)&~models.Q(start_time=models.F('end_time')),name='shift_values_valid')]
    def __str__(self): return self.name

class WorkSchedule(models.Model):
    employee=models.ForeignKey(Employee,on_delete=models.PROTECT,related_name='schedules')
    shift=models.ForeignKey(Shift,on_delete=models.PROTECT)
    work_date=models.DateField()
    source=models.CharField(max_length=6,choices=[('MANUAL','Thủ công'),('AI','AI (chưa triển khai)')],default='MANUAL',editable=False)
    status=models.CharField(max_length=10,choices=[('DRAFT','Nháp'),('APPROVED','Đã duyệt'),('CANCELLED','Đã hủy')],default='DRAFT',editable=False)
    start_at=models.DateTimeField(editable=False)
    end_at=models.DateTimeField(editable=False)
    approved_by=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='approved_schedules',editable=False)
    approved_at=models.DateTimeField(null=True,blank=True,editable=False)
    note=models.TextField(blank=True,max_length=1000)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['employee','work_date','shift'],condition=~models.Q(status='CANCELLED'),name='schedule_once'),models.CheckConstraint(condition=models.Q(end_at__gt=models.F('start_at'),source__in=['MANUAL','AI'],status__in=['DRAFT','APPROVED','CANCELLED']),name='schedule_window_valid')]
    def window(self):
        start=timezone.make_aware(datetime.combine(self.work_date,self.shift.start_time))
        end=timezone.make_aware(datetime.combine(self.work_date,self.shift.end_time))
        if end<=start: end+=timedelta(days=1)
        return start,end
    def __str__(self): return f'{self.employee} / {self.work_date} / {self.shift}'

class Attendance(models.Model):
    employee=models.ForeignKey(Employee,on_delete=models.PROTECT,related_name='attendances')
    work_schedule=models.OneToOneField(WorkSchedule,on_delete=models.PROTECT,related_name='attendance')
    work_date=models.DateField()
    check_in_time=models.DateTimeField(null=True,blank=True)
    check_out_time=models.DateTimeField(null=True,blank=True)
    status=models.CharField(max_length=12,choices=[(s,s) for s in ['PRESENT','LATE','EARLY_LEAVE','ABSENT','LEAVE']],default='PRESENT')
    note=models.TextField(blank=True,max_length=1000)
    confirmed_by=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='confirmed_attendance',editable=False)
    confirmed_at=models.DateTimeField(null=True,blank=True,editable=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=(models.Q(check_out_time__isnull=True)|models.Q(check_in_time__isnull=False,check_out_time__gt=models.F('check_in_time')))&models.Q(status__in=['PRESENT','LATE','EARLY_LEAVE','ABSENT','LEAVE']),name='attendance_times_valid')]
    @property
    def working_hours(self):
        return Decimal(str((self.check_out_time-self.check_in_time).total_seconds()))/Decimal(3600) if self.check_in_time and self.check_out_time else Decimal(0)
    def __str__(self): return f'{self.employee} / {self.work_date}'

class PayrollPeriod(models.Model):
    name=models.CharField(max_length=100,unique=True)
    start_date=models.DateField()
    end_date=models.DateField()
    standard_hours=models.DecimalField(max_digits=8,decimal_places=2,default=208,validators=[MinValueValidator(Decimal('.01'))])
    overtime_multiplier=models.DecimalField(max_digits=4,decimal_places=2,default=Decimal('1.50'),validators=[MinValueValidator(1)])
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(end_date__gte=models.F('start_date'),standard_hours__gt=0,overtime_multiplier__gte=1),name='payroll_period_valid')]
    def __str__(self): return self.name

class Payroll(models.Model):
    employee=models.ForeignKey(Employee,on_delete=models.PROTECT,related_name='payrolls')
    period=models.ForeignKey(PayrollPeriod,on_delete=models.PROTECT)
    base_salary=models.DecimalField(**MONEY)
    working_hours=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    overtime_hours=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    earned_base=models.DecimalField(**MONEY)
    overtime_pay=models.DecimalField(**MONEY)
    allowance=models.DecimalField(**MONEY)
    bonus=models.DecimalField(**MONEY)
    deduction=models.DecimalField(**MONEY)
    gross_salary=models.DecimalField(**MONEY)
    net_salary=models.DecimalField(**MONEY)
    calculation_snapshot=models.JSONField(default=dict,editable=False)
    status=models.CharField(max_length=8,choices=[('DRAFT','Nháp'),('APPROVED','Đã duyệt'),('PAID','Đã ghi nhận trả')],default='DRAFT',editable=False)
    approved_by=models.ForeignKey(USER,null=True,blank=True,on_delete=models.PROTECT,related_name='approved_payrolls',editable=False)
    approved_at=models.DateTimeField(null=True,blank=True,editable=False)
    paid_at=models.DateTimeField(null=True,blank=True,editable=False)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['employee','period'],name='payroll_employee_period_once'),models.CheckConstraint(condition=models.Q(base_salary__gte=0,working_hours__gte=0,overtime_hours__gte=0,earned_base__gte=0,overtime_pay__gte=0,allowance__gte=0,bonus__gte=0,deduction__gte=0,net_salary__gte=0,gross_salary=models.F('earned_base')+models.F('overtime_pay')+models.F('allowance')+models.F('bonus'),net_salary=models.F('gross_salary')-models.F('deduction'))&(models.Q(status='DRAFT',approved_by__isnull=True,approved_at__isnull=True,paid_at__isnull=True)|models.Q(status='APPROVED',approved_by__isnull=False,approved_at__isnull=False,paid_at__isnull=True)|models.Q(status='PAID',approved_by__isnull=False,approved_at__isnull=False,paid_at__isnull=False)),name='payroll_totals_state_valid')]
    def __str__(self): return f'{self.employee} / {self.period}'

class Conversation(models.Model):
    created_at=models.DateTimeField(auto_now_add=True)
    created_by=models.ForeignKey(USER,on_delete=models.PROTECT)
    participants=models.ManyToManyField(USER,through='ConversationParticipant',related_name='conversations')
    is_support=models.BooleanField(default=False)
    def __str__(self): return f'Hội thoại #{self.pk}'

class ConversationParticipant(models.Model):
    conversation=models.ForeignKey(Conversation,on_delete=models.CASCADE)
    user=models.ForeignKey(USER,on_delete=models.PROTECT)
    last_read_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['conversation','user'],name='conversation_user_once')]

class Message(models.Model):
    conversation=models.ForeignKey(Conversation,on_delete=models.PROTECT,related_name='messages')
    sender=models.ForeignKey(USER,on_delete=models.PROTECT)
    content=models.TextField(max_length=2000)
    request_key=models.UUIDField(unique=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['id']
        constraints=[models.CheckConstraint(condition=models.Q(content__regex=r'\S'),name='message_nonblank')]
