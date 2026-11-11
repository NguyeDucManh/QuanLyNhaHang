"""Operational identity/policy regression. All biometric inputs here are mocks."""
import json
import math
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from django.test import TestCase,Client,override_settings
from django.core.exceptions import ValidationError,PermissionDenied
from django.urls import reverse
from django.utils import timezone
from .test_module07 import Module07Fixtures
from .models import Employee,FaceProfile,FaceEmbedding,FaceChallenge,FaceAudit,Attendance,RestaurantInfo,AttendanceLocationPolicy,AttendanceLocationEvent
from .employee_identity import operational_employees,account_audit
from .ai.face.face_enrollment_service import verify_identity,enroll
from .ai.face.liveness_service import issue
from .ai.face.policy import effective_threshold,verification_options
from .face_attendance_service import secure_punch

@override_settings(FACEID_REQUIRE_LIVENESS=False,FACEID_DEFAULT_THRESHOLD=.8)
class OperationalFaceTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        super().setUp();self.personnel()
        self.profile=FaceProfile.objects.create(employee=self.employee,model_version='mock')
        FaceEmbedding.objects.create(profile=self.profile,vector=[1.,0.],image_hash='enrollment')
        self.fake=SimpleNamespace(model_version='mock',process=lambda frame:(np.array([1.,0.]),{'yaw':0,'blink':0,'blur':100,'brightness':100},frame))
        self.client=Client();self.client.force_login(self.manager)
    def verify(self,actor=None,frames=None):
        actor=actor or self.staff
        challenge=issue(actor,require_liveness=False)
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=self.fake):
            return verify_identity(actor=actor,challenge_id=challenge['id'],frames=frames or ['a','b','c','d','e'],**verification_options())
    def test_operational_real_included_demo_and_inactive_excluded(self):
        self.assertIn(self.employee,operational_employees())
        self.employee.employee_code='DEMO-U0001';self.employee.save();self.assertFalse(operational_employees().filter(pk=self.employee.pk).exists())
        self.employee.employee_code='NV001';self.employee.is_active=False;self.employee.save();self.assertFalse(operational_employees().filter(pk=self.employee.pk).exists())
    def test_list_excludes_seed_profile_but_keeps_history(self):
        self.employee.employee_code='DEMO-U0001';self.employee.save()
        response=self.client.get(reverse('ai_faces'));self.assertNotContains(response,'DEMO-U0001');self.assertTrue(FaceEmbedding.objects.filter(profile=self.profile).exists());self.assertEqual(len(response.context['employees']),0)
    def test_readonly_audit_detects_direct_user_links_and_references(self):
        self.employee.employee_code='DEMO-U0001';self.employee.save();before=Employee.objects.count();audit=account_audit();self.assertEqual(audit['demo_employees'][0]['user_id'],self.staff.pk);self.assertEqual(Employee.objects.count(),before)
    def test_confirmation_retains_pk_user_profile_and_references(self):
        self.employee.employee_code='DEMO-U0001';self.employee.save();schedule=self.approved_schedule()
        data={'employee_code':'NV001','full_name':'Confirmed employee','phone':'','position':self.employee.position_id,'hire_date':self.employee.hire_date.isoformat(),'employment_status':'ACTIVE','base_salary':'10000000','is_active':'on','confirmed':'on','user':self.customer.pk}
        response=self.client.post(reverse('employee_operational_link',args=[self.staff.pk]),data)
        self.assertEqual(response.status_code,302);self.employee.refresh_from_db();self.assertEqual(self.employee.user_id,self.staff.pk);self.assertEqual(self.employee.employee_code,'NV001');self.assertEqual(schedule.employee_id,self.employee.pk);self.assertEqual(FaceProfile.objects.get().employee_id,self.employee.pk)
    def test_confirmation_requires_explicit_check_and_unique_employee(self):
        response=self.client.post(reverse('employee_operational_link',args=[self.staff.pk]),{})
        self.assertEqual(response.status_code,200);self.assertIn('confirmed',response.context['form'].errors);self.assertEqual(Employee.objects.filter(user=self.staff).count(),1)
    def test_staff_cannot_manage_link_or_enroll_other(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('employee_operational_link',args=[self.manager.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('face_enrollment',args=[self.employee.pk]),'{}',content_type='application/json').status_code,403)
    def test_enrollment_correct_employee_and_seed_rejected(self):
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=self.fake):
            profile=enroll(self.employee.pk,list(map(str,range(15))),self.manager);self.assertEqual(profile.employee.user,self.staff);self.assertEqual(profile.samples.count(),15)
            self.employee.employee_code='DEMO-U0001';self.employee.save()
            with self.assertRaises(ValidationError):enroll(self.employee.pk,list(map(str,range(15))),self.manager)
    def test_enrollment_http_requires_consent(self):
        response=self.client.post(reverse('face_enrollment',args=[self.employee.pk]),json.dumps({'frames':list(map(str,range(15)))}),content_type='application/json');self.assertEqual(response.status_code,400);self.assertEqual(self.profile.samples.count(),1)
    def test_straight_provisional_passes_without_blink(self):
        profile,score=self.verify();self.assertEqual(profile,self.profile);self.assertAlmostEqual(score,1);self.assertEqual(effective_threshold(profile),(.8,'PROVISIONAL'))
    def test_calibrated_threshold_overrides_default(self):
        self.profile.threshold=.95;self.profile.save();self.assertEqual(effective_threshold(self.profile),(.95,'CALIBRATED'));self.verify()
    def test_below_threshold_fails_and_has_score_evidence(self):
        self.fake.process=lambda frame:(np.array([.6,.8]),{'yaw':0},frame)
        with self.assertRaises(ValidationError) as failure:self.verify()
        self.assertAlmostEqual(failure.exception.similarity,.6)
    def test_mean_embedding_normalized_metric(self):
        self.fake.process=lambda frame:(np.array([.8,.6 if frame in ['a','b'] else -.6]),{'yaw':0},frame)
        _,score=self.verify();self.assertAlmostEqual(score,.8/math.sqrt(.8**2+.12**2),places=5)
    def test_no_enrollment_fails(self):
        self.profile.delete()
        with self.assertRaises(ValidationError):self.verify()
    def test_missing_embeddings_fails(self):
        self.profile.samples.all().delete()
        with self.assertRaises(ValidationError):self.verify()
    def test_duplicate_or_wrong_frame_count_rejected(self):
        for frames in [['a']*5,['a','b']]:
            with self.assertRaises(ValidationError):self.verify(frames=frames)
    def test_wrong_pose_rejected(self):
        self.fake.process=lambda frame:(np.array([1.,0.]),{'yaw':.3},frame)
        with self.assertRaises(ValidationError):self.verify()
    def test_quality_or_multiple_faces_fail_before_recognition(self):
        for message in ['Phát hiện nhiều khuôn mặt','Ảnh quá mờ','Ánh sáng không đạt','Khuôn mặt quá nhỏ']:
            self.fake.process=lambda frame:(_ for _ in ()).throw(ValidationError(message))
            with self.assertRaises(ValidationError):self.verify()
    def test_test_only_never_writes_attendance_and_audits_provisional(self):
        challenge=issue(self.manager,require_liveness=False)
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=self.fake):
            response=self.client.post(reverse('face_test_verify'),json.dumps({'frames':['a','b','c','d','e'],'challenge':challenge['id']}),content_type='application/json')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['threshold_type'],'PROVISIONAL');self.assertEqual(Attendance.objects.count(),0);self.assertFalse(FaceAudit.objects.get().liveness)
    def test_challenge_replay_wrong_actor_and_mode_rejected(self):
        challenge=issue(self.staff,require_liveness=False)
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=self.fake):
            kwargs={'actor':self.staff,'challenge_id':challenge['id'],'frames':['a','b','c'],**verification_options()};verify_identity(**kwargs)
            with self.assertRaises(ValidationError):verify_identity(**kwargs)
            challenge=issue(self.manager,require_liveness=False);kwargs['challenge_id']=challenge['id']
            with self.assertRaises(ValidationError):verify_identity(**kwargs)
            kwargs['challenge_id']=issue(self.staff)['id']
            with self.assertRaises(ValidationError):verify_identity(**kwargs)
    @override_settings(FACEID_REQUIRE_LIVENESS=True)
    def test_enabled_liveness_rejects_static_sequence(self):
        challenge=issue(self.staff)
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=self.fake),self.assertRaises(ValidationError):
            verify_identity(actor=self.staff,challenge_id=challenge['id'],frames=list(map(str,range(10))),**verification_options())
    def test_spoof_employee_id_cannot_override_self_identity(self):
        self.client.force_login(self.manager);challenge=issue(self.manager,require_liveness=False)
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=self.fake):
            response=self.client.post(reverse('face_self_test'),json.dumps({'employee_id':self.employee.pk,'verified':True,'challenge':challenge['id'],'frames':['a','b','c']}),content_type='application/json')
        self.assertIn(response.status_code,[403,404]);self.assertEqual(Attendance.objects.count(),0)

@override_settings(FACEID_REQUIRE_LIVENESS=False)
class AttendanceOperationalTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        super().setUp();self.personnel();self.info=RestaurantInfo.objects.create(name='Test restaurant',opening_time='08:00',closing_time='23:00',latitude=10,longitude=106)
        self.policy=AttendanceLocationPolicy.objects.create(restaurant=self.info,mode='GPS_ONLY');self.point={'latitude':10,'longitude':106,'accuracy':5}
    def test_all_modes_call_existing_punch_only_when_components_pass(self):
        profile=FaceProfile.objects.create(employee=self.employee,model_version='mock');FaceEmbedding.objects.create(profile=profile,vector=[1,0],image_hash='mock')
        for mode in ['FACE_ONLY','GPS_ONLY','FACE_AND_GPS']:
            self.policy.mode=mode;self.policy.save();schedule=self.approved_schedule()
            with patch('django.utils.timezone.now',return_value=schedule.start_at),patch('customers.face_attendance_service.punch',return_value=Attendance.objects.create(employee=self.employee,work_schedule=schedule,work_date=schedule.work_date)) as punch,patch('customers.ai.face.face_enrollment_service.verify_identity',return_value=(profile,1.0)) as verify:
                result,geo=secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in',frames=['a','b','c']);self.assertEqual(result.employee,self.employee);punch.assert_called_once();self.assertEqual(verify.call_count,1)
            AttendanceLocationEvent.objects.all().delete();Attendance.objects.all().delete();schedule.delete()
    def test_missing_gps_is_event_and_never_mutates_attendance(self):
        schedule=self.approved_schedule()
        with patch('django.utils.timezone.now',return_value=schedule.start_at):
            with self.assertRaises(ValidationError):secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in')
        self.assertFalse(Attendance.objects.exists());self.assertFalse(AttendanceLocationEvent.objects.exists())
        self.assertTrue(FaceAudit.objects.exists())
    def test_invalid_coordinates_are_rejected_and_audited(self):
        self.client=Client();self.client.force_login(self.staff)
        for key,value in [('latitude',91),('longitude',181),('latitude','nan'),('longitude','inf')]:
            response=self.client.post(reverse('secure_attendance'),json.dumps({'schedule':1,'action':'in','location':{key:value}}),content_type='application/json')
            self.assertEqual(response.status_code,400)
        self.assertFalse(AttendanceLocationEvent.objects.exists());self.assertFalse(Attendance.objects.exists())
    def test_geofence_inside_outside_accuracy_boundary(self):
        from .face_attendance_views import public_config
        self.assertEqual(public_config()['mode'],'FACE_ONLY')
        self.assertNotIn('radius',public_config());self.assertNotIn('max_accuracy',public_config())
        self.policy.refresh_from_db();self.assertEqual(self.policy.mode,'GPS_ONLY')
    def test_face_missing_fails_without_attendance(self):
        schedule=self.approved_schedule()
        with patch('django.utils.timezone.now',return_value=schedule.start_at):
            with self.assertRaises(ValidationError):secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in')
        self.assertFalse(Attendance.objects.exists());self.assertEqual(FaceAudit.objects.count(),1)
    def test_seed_employee_cannot_self_punch(self):
        self.employee.employee_code='DEMO-U0001';self.employee.save()
        with self.assertRaises(ValidationError):secure_punch(actor=self.staff,schedule_id=1,action='in')
    def test_wrong_identity_and_foreign_schedule_never_write_attendance(self):
        from django.contrib.auth import get_user_model
        from .rbac import assign_role
        other=get_user_model().objects.create_user('another-employee');assign_role(other,'STAFF')
        other_employee=Employee.objects.create(user=other,employee_code='NV2',full_name='Other QA',position=self.position,hire_date=self.day)
        own_profile=FaceProfile.objects.create(employee=self.employee,model_version='mock');FaceEmbedding.objects.create(profile=own_profile,vector=[1,0],image_hash='mock')
        other_profile=FaceProfile.objects.create(employee=other_employee,model_version='mock')
        self.policy.mode='FACE_AND_GPS';self.policy.save();schedule=self.approved_schedule()
        with patch('django.utils.timezone.now',return_value=schedule.start_at),patch('customers.ai.face.face_enrollment_service.verify_identity',return_value=(other_profile,1.0)),self.assertRaises(PermissionDenied):
            secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in',frames=['a','b','c'])
        self.assertEqual(Attendance.objects.count(),0)
        self.policy.mode='GPS_ONLY';self.policy.save()
        with self.assertRaises(PermissionDenied):secure_punch(actor=self.staff,schedule_id=999999,action='in')
        self.assertEqual(Attendance.objects.count(),0)
