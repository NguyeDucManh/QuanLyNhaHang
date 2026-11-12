import re
from datetime import datetime,timezone as dt_timezone
from pathlib import Path
from django.conf import settings
from django.test import TestCase,SimpleTestCase,override_settings
from django.urls import reverse
from html.parser import HTMLParser
from .test_module07 import Module07Fixtures
from .module07_forms import EmployeeForm,AttendanceForm,PayrollForm,ShiftForm
from .models import Attendance
from .templatetags.ui_vi import ui_vi,ui_message

class PageMarkup(HTMLParser):
    def __init__(self,source):
        super().__init__();self.nodes=[];self.text=[];self.hidden=0;self.feed(source)
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        self.nodes.append(dict(attrs))
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden-=1
    def handle_data(self,data):
        if not self.hidden:self.text.append(data)
    def select(self,selector):
        name,value=re.fullmatch(r'\[([^=\]]+)(?:="([^\"]*)")?\]',selector).groups()
        return [node for node in self.nodes if name in node and (value is None or node[name]==value)]
    def select_one(self,selector):
        matches=self.select(selector);return matches[0] if matches else None

class VietnamesePresentationTests(SimpleTestCase):
    def test_enums_localized_without_changing_values(self):
        self.assertEqual(ui_vi('PROVISIONAL'),'Ngưỡng tạm thời');self.assertEqual(ui_vi('CALIBRATED'),'Ngưỡng đã hiệu chỉnh');self.assertEqual(ui_vi('GPS_DENIED'),'Ngoài phạm vi')
        self.assertEqual(dict(AttendanceForm().fields['status'].choices)['PRESENT'],'Có mặt')
    def test_time_always_uses_vietnam_timezone(self):
        value=datetime(2026,10,14,3,19,14,tzinfo=dt_timezone.utc)
        with override_settings(TIME_ZONE='UTC'):self.assertEqual(ui_vi(value),'14/10/2026 10:19:14')
        self.assertEqual(ui_vi(value.isoformat()),'14/10/2026 10:19:14')
    def test_hr_form_labels_are_vietnamese(self):
        self.assertEqual(EmployeeForm.base_fields['employee_code'].label,'Mã nhân viên');self.assertEqual(EmployeeForm.base_fields['base_salary'].label,'Lương cơ bản');self.assertEqual(PayrollForm.base_fields['bonus'].label,'Thưởng');self.assertEqual(ShiftForm.base_fields['start_time'].label,'Giờ bắt đầu')
    def test_internal_face_audit_reason_is_presentation_only(self):
        self.assertEqual(ui_message('Verification only; no Attendance written'),'Chỉ kiểm tra nhận diện; không ghi chấm công.')

@override_settings(FACEID_REQUIRE_LIVENESS=False)
class FaceVietnamesePageTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):self.personnel();self.client.force_login(self.manager)
    def visible(self,response):
        soup=PageMarkup(response.content.decode('utf-8'))
        return soup,' '.join(soup.text)
    def test_test_page_has_location_and_identity_hud_without_map(self):
        response=self.client.get(reverse('face_test_page'));soup,text=self.visible(response)
        for selector in ('[data-face-hud]','[data-face-threshold-type]'):self.assertIsNotNone(soup.select_one(selector))
        for selector in ('[data-geo-hud]','[data-location-map]','[data-location-start]'):self.assertIsNone(soup.select_one(selector))
        self.assertEqual(Attendance.objects.count(),0);self.assertNotContains(response,'vendor/leaflet/')
    def test_straight_mode_has_no_blink_instruction(self):
        _,text=self.visible(self.client.get(reverse('face_test_page')))
        self.assertIn('Nhìn thẳng vào camera',text);self.assertNotRegex(text,r'chớp mắt|quay trái|quay phải|blink|head turn')
    def test_operational_visible_labels_are_localized(self):
        _,text=self.visible(self.client.get(reverse('ai_faces')))
        self.assertNotRegex(text,r'\b(?:Samples|Employee|Threshold|PROVISIONAL|CALIBRATED|Actions|Enrollment|Last verify|Test)\b')
        self.assertIn('Mã nhân viên',text);self.assertIn('Đăng ký khuôn mặt',text)
    def test_attendance_labels_and_browser_hooks_preserved(self):
        self.client.force_login(self.staff);response=self.client.get(reverse('face_attendance'));soup,text=self.visible(response)
        self.assertIn('CHẤM CÔNG VÀO CA',text);self.assertIn('CHẤM CÔNG RA CA',text)
        self.assertIsNotNone(soup.select_one('[data-punch="in"]'));self.assertIsNotNone(soup.select_one('[role="status"]'));self.assertIsNone(soup.select_one('[role="trạng thái"]'));self.assertNotRegex(text,r'GPS_ALLOWED|FACE_ONLY|PROVISIONAL|CHECK-IN|Similarity|Threshold')
    def test_enrollment_quality_hooks_and_consent_are_intact(self):
        response=self.client.get(reverse('face_enrollment_page',args=[self.employee.pk]));soup,text=self.visible(response)
        for key in ['blur','brightness','yaw']:self.assertIsNotNone(soup.select_one(f'[data-quality="{key}"]'))
        self.assertEqual(len(soup.select('[data-consent]')),1);self.assertIn('Đăng ký khuôn mặt',text)
