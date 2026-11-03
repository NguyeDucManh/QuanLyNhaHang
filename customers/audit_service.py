"""Allowlisted snapshots only: never serialize models or request bodies wholesale."""
from contextlib import contextmanager
from contextvars import ContextVar
from django.db.models.signals import pre_save, post_save, post_delete, m2m_changed
from django.dispatch import receiver

_actor = ContextVar('audit_actor', default=None)
_ip = ContextVar('audit_ip', default=None)
FIELDS = {
 'MenuItem':('name','price','is_available','category_id'),
 'Booking':('table_id','status','guests','start_time','end_time'),
 'Order':('status','table_id','booking_id','customer_id','total_amount'),
 'Payment':('invoice_id','status','amount','confirmed_by_id'),
 'StockReceipt':('code','supplier_id','status','date'),
 'StockIssue':('code','status','date'),
 'StockMovement':('ingredient_id','movement_type','quantity','stock_before','stock_after','receipt_id','issue_id','order_id'),
 'Employee':('user_id','position_id','is_active','full_name','employee_code','employment_status','base_salary'),
 'Attendance':('employee_id','work_date','status','check_in_time','check_out_time','confirmed_by_id'),
 'FaceProfile':('employee_id','is_active'),
 'PurchaseOrder':('status','supplier_id','subtotal','approved_by_id'),
 'PurchaseReceiving':('purchase_order_id','receipt_id'),
 'LoyaltyTransaction':('customer_id','type','points','source_type','source_id'),
 'BookingWaitlist':('customer_id','status','booking_id','guests','requested_date'),
 'BookingVisit':('booking_id','state','occurred_at'),
 'Invoice':('order_id','status','total_amount','booking_deposit_id','deposit_applied_amount'),
 'User':('is_active','is_staff','is_superuser'),
}


@contextmanager
def audit_actor(actor):
    # Resolve Django's lazy request user in the sync thread before ASGI copies context.
    if actor is not None:
        getattr(actor,'is_authenticated',False)
        actor=getattr(actor,'_wrapped',actor)
    token = _actor.set(actor)
    try: yield
    finally: _actor.reset(token)


def with_actor(function):
    from functools import wraps
    @wraps(function)
    def wrapped(*args,**kwargs):
        actor=kwargs.get('actor') or _actor.get() or kwargs.get('owner') or kwargs.get('user') or kwargs.get('customer')
        with audit_actor(actor): return function(*args,**kwargs)
    return wrapped


def snapshot(obj):
    result = {}
    for field in FIELDS.get(type(obj).__name__, ()):
        if hasattr(obj,field):
            value = getattr(obj,field)
            result[field] = value if value is None or isinstance(value,(int,bool,float)) else str(value)
    return result


def record(*, action, entity, actor=None, before=None, after=None):
    from .models import AuditLog
    actor = actor or _actor.get()
    return AuditLog.objects.create(actor=actor if getattr(actor,'is_authenticated',False) else None,
        action=action, entity_type=type(entity).__name__, entity_id=str(entity.pk), description=f'{action} · {type(entity).__name__} #{entity.pk}',
        before_data=before or {}, after_data=after or {}, ip_address=_ip.get())


class AuditActorMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        # REMOTE_ADDR only; never trust an arbitrary client X-Forwarded-For.
        import ipaddress
        try: ip = str(ipaddress.ip_address(request.META.get('REMOTE_ADDR','')))
        except ValueError: ip = None
        token = _ip.set(ip)
        try:
            with audit_actor(request.user): return self.get_response(request)
        finally: _ip.reset(token)


@receiver(pre_save)
def remember_before(sender, instance, raw=False, **kwargs):
    from django.apps import apps
    if raw or sender._meta.apps is not apps or sender.__name__ not in FIELDS: return
    old = sender.objects.filter(pk=instance.pk).first() if instance.pk else None
    instance._audit_before = snapshot(old) if old else {}


@receiver(post_save)
def audit_save(sender, instance, created, raw=False, **kwargs):
    from django.apps import apps
    if raw or sender._meta.apps is not apps or sender.__name__ not in FIELDS: return
    before, after = getattr(instance,'_audit_before',{}), snapshot(instance)
    if not created and before == after: return
    actor = _actor.get()
    # Service calls outside HTTP still retain the actual business actor.
    if not getattr(actor,'is_authenticated',False):
        for field in ('confirmed_by','actor','approved_by','created_by'):
            candidate = getattr(instance,field,None)
            if getattr(candidate,'is_authenticated',False): actor=candidate;break
    record(action='CREATE' if created else 'UPDATE',entity=instance,actor=actor,before=before,after=after)


@receiver(post_delete)
def audit_delete(sender,instance,**kwargs):
    from django.apps import apps
    if sender._meta.apps is not apps: return
    if sender.__name__ in FIELDS: record(action='DELETE',entity=instance,before=snapshot(instance))


@receiver(m2m_changed)
def audit_permissions(sender,instance,action,pk_set,**kwargs):
    from django.apps import apps
    if sender._meta.apps is not apps: return
    if sender._meta.model_name not in ('user_groups','user_user_permissions','group_permissions'): return
    if action in ('post_add','post_remove','pre_clear'):
        record(action='PERMISSIONS_'+action.upper(),entity=instance,after={'related_ids':sorted(pk_set or [])})
