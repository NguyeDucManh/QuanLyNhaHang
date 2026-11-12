from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .test_module07 import Module07Fixtures
from .attendance_status import attendance_context
from .face_attendance_views import public_config
from .models import Attendance, FaceAudit, FaceChallenge, WorkSchedule


class AttendanceReadinessTests(Module07Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.initialize()

    def setUp(self):
        self.personnel()
        self.client.force_login(self.staff)

    def test_actual_reported_coordinates_are_outside_150_metres(self):
        config=public_config()
        self.assertEqual(config['mode'],'FACE_ONLY')
        self.assertTrue({'latitude','longitude','radius','max_accuracy'}.isdisjoint(config))

    def test_missing_unapproved_cancelled_and_outside_window_are_distinct(self):
        self.assertEqual(attendance_context(self.staff)['schedule_status'],'NO_SCHEDULE')
        schedule = self.schedule()
        self.assertEqual(attendance_context(self.staff)['schedule_status'],'UNAPPROVED')
        WorkSchedule.objects.filter(pk=schedule.pk).update(status='CANCELLED')
        self.assertEqual(attendance_context(self.staff)['schedule_status'],'CANCELLED')
        WorkSchedule.objects.filter(pk=schedule.pk).update(status='APPROVED',start_at=timezone.now()+timedelta(days=2),end_at=timezone.now()+timedelta(days=2,hours=8))
        self.assertEqual(attendance_context(self.staff)['schedule_status'],'OUTSIDE_WINDOW')
        WorkSchedule.objects.filter(pk=schedule.pk).update(start_at=timezone.now(),end_at=timezone.now()+timedelta(hours=8))
        self.assertEqual(attendance_context(self.staff)['schedule_status'],'AVAILABLE')
        self.assertEqual(attendance_context(self.customer)['schedule_status'],'NO_EMPLOYEE')

    def test_status_endpoint_is_own_scoped_and_has_no_mutations(self):
        before = [Attendance.objects.count(),FaceAudit.objects.count(),FaceChallenge.objects.count()]
        response = self.client.get(reverse('attendance_status'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['schedule_status'],'NO_SCHEDULE')
        self.assertEqual(response['Cache-Control'],'no-store')
        self.assertEqual(before,[Attendance.objects.count(),FaceAudit.objects.count(),FaceChallenge.objects.count()])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('attendance_status')).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('attendance_status')).status_code,401)

    def test_get_only_endpoint_keeps_correct_allow_header(self):
        response=self.client.post(reverse('attendance_status'))
        self.assertEqual(response.status_code,405)
        self.assertEqual(response['Allow'],'GET')

    def test_out_of_window_schedule_cannot_be_chosen_in_ui(self):
        schedule=self.approved_schedule()
        WorkSchedule.objects.filter(pk=schedule.pk).update(start_at=timezone.now()+timedelta(days=3),end_at=timezone.now()+timedelta(days=3,hours=8))
        response=self.client.get(reverse('face_attendance'))
        self.assertContains(response,'OUTSIDE_WINDOW')
        self.assertEqual(len(response.context['schedules']),0)
