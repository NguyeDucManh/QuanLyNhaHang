from datetime import date
from django.test import TestCase
from django.core.exceptions import PermissionDenied,ValidationError
from .test_business import BusinessData
from .models import Employee,Position,AuditLog,Attendance
from .employee_identity import operational_employees,confirm_identity,require_operational

class IdentityConfirmationTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.initialize();p=Position.objects.create(name='Phục vụ')
        cls.employee=Employee.objects.create(user=cls.staff,employee_code='DEMO-U0006',full_name='Nhân viên đã xác nhận',position=p,hire_date=date(2026,1,1),base_salary=1)
    def test_explicit_confirmation_is_idempotent_and_preserves_history(self):
        self.assertFalse(operational_employees().filter(pk=self.employee.pk).exists())
        confirm_identity(self.employee.pk,actor=self.admin,reason='Chủ hệ thống xác nhận nhân viên thật')
        confirm_identity(self.employee.pk,actor=self.admin,reason='Chủ hệ thống xác nhận nhân viên thật')
        self.assertTrue(operational_employees().filter(pk=self.employee.pk).exists())
        require_operational(self.employee)
        self.employee.refresh_from_db();self.assertEqual(self.employee.employee_code,'DEMO-U0006')
        self.assertEqual(AuditLog.objects.filter(action='EMPLOYEE_IDENTITY_CONFIRMED').count(),1)
        self.assertFalse(Attendance.objects.exists())
    def test_employee_cannot_self_confirm(self):
        with self.assertRaises(PermissionDenied):confirm_identity(self.employee.pk,actor=self.staff,reason='Tự xác nhận')
    def test_confirmation_does_not_survive_identity_reassignment(self):
        confirm_identity(self.employee.pk,actor=self.admin,reason='Đã kiểm tra hồ sơ')
        self.employee.employee_code='DEMO-OTHER';self.employee.save(update_fields=['employee_code'])
        self.assertFalse(operational_employees().filter(pk=self.employee.pk).exists())
        with self.assertRaises(ValidationError):require_operational(self.employee)
