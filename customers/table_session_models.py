from django.conf import settings
from django.db import models


class TableSession(models.Model):
    table=models.ForeignKey('RestaurantTable',on_delete=models.PROTECT,related_name='service_sessions')
    booking=models.OneToOneField('Booking',null=True,blank=True,on_delete=models.PROTECT,related_name='table_session')
    order=models.OneToOneField('Order',null=True,blank=True,on_delete=models.PROTECT,related_name='table_session')
    started_at=models.DateTimeField()
    ended_at=models.DateTimeField(null=True,blank=True)
    ended_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    end_reason=models.CharField(max_length=1000,blank=True)

    class Meta:
        default_permissions=()
        constraints=[
            models.UniqueConstraint(fields=['table'],condition=models.Q(ended_at__isnull=True),name='one_open_session_per_table'),
            models.CheckConstraint(condition=models.Q(booking__isnull=False)|models.Q(order__isnull=False),name='session_has_booking_or_order'),
            models.CheckConstraint(condition=models.Q(ended_at__isnull=True)|models.Q(ended_at__gte=models.F('started_at')),name='session_end_after_start'),
        ]
