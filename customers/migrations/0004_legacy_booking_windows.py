from datetime import datetime, timedelta
from django.conf import settings
from django.db import migrations
from django.utils import timezone


def fill_legacy_windows(apps, schema_editor):
    Booking = apps.get_model('customers', 'Booking')
    alias = schema_editor.connection.alias
    duration = timedelta(minutes=settings.DEFAULT_BOOKING_DURATION_MINUTES)
    for booking in Booking.objects.using(alias).filter(start_time__isnull=True).iterator():
        start = timezone.make_aware(datetime.combine(booking.date, booking.time), timezone.get_default_timezone())
        Booking.objects.using(alias).filter(pk=booking.pk).update(start_time=start, end_time=start+duration)
    # No fictional tables: old requests remain unassigned until safely confirmed.


class Migration(migrations.Migration):
    dependencies = [('customers', '0003_booking_end_time_booking_start_time_booking_status_and_more')]
    operations = [migrations.RunPython(fill_legacy_windows, migrations.RunPython.noop)]
