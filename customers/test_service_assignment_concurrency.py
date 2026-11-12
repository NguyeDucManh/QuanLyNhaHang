from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from unittest.mock import patch
from django.test import TransactionTestCase,override_settings
from django.db import connections,connection
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from .test_module07 import Module07Fixtures
from .models import Employee,WorkSchedule,TableServiceAssignment
from .table_assignment_service import assign_table


@override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=True)
class AssignmentConcurrencyTests(Module07Fixtures,TransactionTestCase):
    def setUp(self):
        self.initialize();self.personnel();self.schedule=self.approved_schedule()
        other=Employee.objects.create(user=self.manager,employee_code='MGR-CONCURRENT',full_name='Second employee',position=self.position,hire_date=self.day)
        self.other=WorkSchedule.objects.create(employee=other,shift=self.shift,work_date=self.day,start_at=self.schedule.start_at,end_at=self.schedule.end_at,status='APPROVED',approved_by=self.admin,approved_at=timezone.now())

    def test_competing_managers_do_not_create_overlapping_assignments(self):
        barrier=Barrier(2)
        def attempt(schedule_id):
            connections.close_all()
            try:
                actor=get_user_model().objects.get(pk=self.manager.pk)
                with connection.cursor() as cursor:cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=10)
                try:assign_table(actor=actor,table_id=self.table.pk,schedule_id=schedule_id)
                except ValidationError:return 'conflict'
                return 'created'
            finally:connections.close_all()
        with patch('django.utils.timezone.now',return_value=self.schedule.start_at+timedelta(minutes=30)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                result=list(pool.map(attempt,[self.schedule.pk,self.other.pk]))
        self.assertEqual(sorted(result),['conflict','created'])
        self.assertEqual(TableServiceAssignment.objects.count(),1)
