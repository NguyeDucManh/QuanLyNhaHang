from django.db import models
from django.core.validators import MinValueValidator,MaxValueValidator

class AttendanceLocationPolicy(models.Model):
    restaurant=models.OneToOneField('RestaurantInfo',on_delete=models.PROTECT,related_name='attendance_policy')
    attendance_radius_m=models.PositiveIntegerField(default=150,validators=[MinValueValidator(1),MaxValueValidator(5000)])
    max_accuracy_m=models.PositiveIntegerField(default=50,validators=[MinValueValidator(1),MaxValueValidator(500)])
    mode=models.CharField(max_length=16,choices=[(m,m) for m in ['FACE_ONLY','GPS_ONLY','FACE_AND_GPS']],default='FACE_AND_GPS')
    is_active=models.BooleanField(default=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(attendance_radius_m__gte=1,attendance_radius_m__lte=5000,max_accuracy_m__gte=1,max_accuracy_m__lte=500,mode__in=['FACE_ONLY','GPS_ONLY','FACE_AND_GPS']),name='attendance_geo_policy_valid')]

class AttendanceLocationEvent(models.Model):
    employee=models.ForeignKey('Employee',on_delete=models.PROTECT)
    attendance=models.ForeignKey('Attendance',null=True,on_delete=models.PROTECT,related_name='location_events')
    action=models.CharField(max_length=3,choices=[('in','Check-in'),('out','Check-out')])
    latitude=models.FloatField(null=True)
    longitude=models.FloatField(null=True)
    accuracy=models.FloatField(null=True)
    calculated_distance=models.FloatField(null=True)
    geo_status=models.CharField(max_length=20)
    policy_snapshot=models.JSONField(default=dict)
    created_at=models.DateTimeField(auto_now_add=True)
