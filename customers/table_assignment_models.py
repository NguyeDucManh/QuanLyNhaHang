"""Shift-scoped responsibility; changes retain the previous row and audit trail."""
from django.conf import settings
from django.db import models


class TableServiceAssignment(models.Model):
    table = models.ForeignKey('RestaurantTable', on_delete=models.PROTECT, related_name='service_assignments')
    work_schedule = models.ForeignKey('WorkSchedule', on_delete=models.PROTECT, related_name='table_assignments')
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()  # Existing table/HR permissions + own-object scope.
        indexes = [models.Index(fields=['table','start_at','end_at'], name='table_assignment_window')]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_at__gt=models.F('start_at')), name='table_assignment_positive_window'),
            models.UniqueConstraint(fields=['table','work_schedule','start_at'], condition=models.Q(revoked_at__isnull=True), name='table_schedule_start_once'),
        ]
