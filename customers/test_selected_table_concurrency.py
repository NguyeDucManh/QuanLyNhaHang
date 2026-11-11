from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from django.test import TransactionTestCase
from django.db import connections, connection
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from .test_business import BusinessData
from .models import RestaurantTable, Booking
from .booking_service import create_booking


class SelectedTableConcurrencyTests(BusinessData, TransactionTestCase):
    def setUp(self): self.initialize()

    def test_same_table_competing_customers_get_one_booking(self):
        barrier=Barrier(2)
        start=(timezone.localtime()+timedelta(days=3)).replace(hour=12,minute=0,second=0,microsecond=0)
        def attempt(_):
            connections.close_all()
            try:
                user=get_user_model().objects.get(pk=self.customer.pk)
                table=RestaurantTable.objects.get(pk=self.table.pk)
                with connection.cursor() as c:c.execute("SET statement_timeout='10s'")
                barrier.wait(timeout=10)
                try:create_booking(user=user,name='Concurrent test',phone='0901234567',date=start.date(),time=start.time(),guests=2,preferred_table=table)
                except ValidationError:return 'conflict'
                return 'created'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),['conflict','created'])
        self.assertEqual(Booking.objects.filter(table=self.table).count(),1)
