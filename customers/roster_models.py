from django.conf import settings
from django.db import models


class RosterWeek(models.Model):
    start_date=models.DateField(unique=True)
    registration_deadline=models.DateTimeField()
    rules=models.JSONField(default=dict)
    status=models.CharField(max_length=12,default='OPEN',choices=[('OPEN','Nhận đăng ký'),('PUBLISHED','Đã công bố')])
    revision=models.PositiveIntegerField(default=0)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        default_permissions=()
        constraints=[models.CheckConstraint(condition=models.Q(status__in=['OPEN','PUBLISHED']),name='roster_week_status_valid')]


class ShiftRegistration(models.Model):
    week=models.ForeignKey(RosterWeek,on_delete=models.PROTECT,related_name='registrations')
    employee=models.ForeignKey('Employee',on_delete=models.PROTECT,related_name='shift_registrations')
    availability=models.JSONField(default=dict)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        default_permissions=()
        constraints=[models.UniqueConstraint(fields=['week','employee'],name='one_registration_per_employee_week')]
