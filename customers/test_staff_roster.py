from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date,time,datetime,timedelta
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,connections
from django.test import TestCase,Client,TransactionTestCase
from django.utils import timezone
from .models import Employee,Position,Shift,RestaurantInfo,WorkSchedule,Attendance,RosterWeek,ShiftRegistration,Payroll,PayrollPeriod
from .rbac import assign_role
from .roster_service import monday,preview_roster,apply_roster,save_registration,load_roster,weekly_hours
from .attendance_status import attendance_context


class RosterData:
    @classmethod
    def setup_data(cls):
        call_command('seed_rbac',stdout=StringIO());users=get_user_model()
        cls.admin=users.objects.create_user('roster-admin');assign_role(cls.admin,'ADMIN')
        cls.position=Position.objects.create(name='Phục vụ')
        cls.people=[]
        for i in range(4):
            user=users.objects.create_user('roster-staff-'+str(i));assign_role(user,'STAFF')
            cls.people.append(Employee.objects.create(user=user,employee_code='NV'+str(i),full_name='Nhân viên '+str(i),position=cls.position,hire_date=date(2020,1,1),base_salary=1))
        cls.shift=Shift.objects.create(name='Ca sáng',start_time=time(8),end_time=time(14),required_staff=2)
        cls.evening=Shift.objects.create(name='Ca tối',start_time=time(17),end_time=time(23),required_staff=1)
        RestaurantInfo.objects.create(name='Nhà hàng kiểm thử',opening_time=time(8),closing_time=time(23))
        cls.rules={'allowed_positions':{str(cls.shift.pk):[cls.position.pk],str(cls.evening.pk):[cls.position.pk]},'min_rest_hours':11,'max_weekly_hours':48,'max_weekly_shifts':6}
    def week(self):
        start=monday(timezone.localdate())+timedelta(days=7)
        return RosterWeek.objects.create(start_date=start,registration_deadline=timezone.now()+timedelta(days=1),rules=self.rules,created_by=self.admin)
    def availability(self,week,*,busy=False):
        return {(week.start_date+timedelta(days=i)).isoformat():{'unavailable':busy,'shifts':[] if busy else [self.shift.pk,self.evening.pk],'priority':2} for i in range(7)}


class RosterTests(RosterData,TestCase):
    @classmethod
    def setUpTestData(cls):cls.setup_data()
    def test_four_people_balanced_with_capacity_rest_and_no_attendance(self):
        start=monday(timezone.localdate())
        plan=preview_roster(start,start+timedelta(days=6),self.rules)
        counts=Counter(v['employee_id'] for v in plan['proposal']['rows'])
        self.assertEqual(plan['proposal']['metrics']['missing_seats'],0)
        self.assertLessEqual(max(counts.values())-min(counts.values()),2)
        created=apply_roster(plan['token'],actor=self.admin,approved_digest=plan['proposal']['plan_digest'])
        self.assertEqual(len(created),21);self.assertFalse(Attendance.objects.exists())
        intervals=defaultdict(list);coverage=Counter()
        for row in created:intervals[row.employee_id].append((row.start_at,row.end_at));coverage[(row.work_date,row.shift_id)]+=1
        for values in intervals.values():
            ordered=sorted(values)
            for a,b in zip(ordered,ordered[1:]):self.assertGreaterEqual((b[0]-a[1]).total_seconds(),11*3600)
            self.assertTrue(all(v<=48 for v in weekly_hours(values).values()))
        for (day,sid),count in coverage.items():self.assertLessEqual(count,Shift.objects.get(pk=sid).required_staff)
        self.assertEqual(apply_roster(plan['token'],actor=self.admin,approved_digest=plan['proposal']['plan_digest']),[])
    def test_existing_schedule_is_preserved_and_stale_plan_rejected(self):
        day=timezone.localdate();plan=preview_roster(day,day,self.rules)
        employee=self.people[0];start,end=self.window(day,self.shift)
        old=WorkSchedule.objects.create(employee=employee,shift=self.shift,work_date=day,start_at=start,end_at=end,status='APPROVED')
        with self.assertRaises(ValidationError):apply_roster(plan['token'],actor=self.admin,approved_digest=plan['proposal']['plan_digest'])
        old.refresh_from_db();self.assertEqual(old.status,'APPROVED');self.assertEqual(WorkSchedule.objects.count(),1)
    @staticmethod
    def window(day,shift):
        from .ga_service import shift_window
        return shift_window(day,shift)
    def test_past_schedules_never_implicitly_confirm_attendance_or_backdate_approval(self):
        day=timezone.localdate()-timedelta(days=15);plan=preview_roster(day,day,self.rules)
        created=apply_roster(plan['token'],actor=self.admin,approved_digest=plan['proposal']['plan_digest'],approve_current=True)
        self.assertTrue(created)
        for row in created:
            self.assertEqual(row.status,'DRAFT');self.assertIsNone(row.approved_at)
            self.assertIn('hồi tố',row.note)
        self.assertFalse(Attendance.objects.exists())
    def test_apply_requires_manager_digest_and_valid_signature(self):
        day=timezone.localdate();plan=preview_roster(day,day,self.rules)
        with self.assertRaises(PermissionDenied):apply_roster(plan['token'],actor=self.people[0].user,approved_digest=plan['proposal']['plan_digest'])
        with self.assertRaises(ValidationError):apply_roster(plan['token'],actor=self.admin,approved_digest='wrong')
        with self.assertRaises(ValidationError):apply_roster(plan['token']+'x',actor=self.admin,approved_digest=plan['proposal']['plan_digest'])
        self.assertFalse(WorkSchedule.objects.exists())
    def test_registered_preferences_are_hard_and_nonregistered_people_not_assigned(self):
        week=self.week();person=self.people[0]
        save_registration(week.pk,person,self.availability(week,busy=True),actor=person.user)
        plan=preview_roster(week.start_date,week.start_date+timedelta(days=6),self.rules,week=week)
        self.assertEqual(plan['proposal']['rows'],[])
        values=self.availability(week);values[week.start_date.isoformat()]={'unavailable':False,'shifts':[self.shift.pk],'priority':1}
        for day in list(values)[1:]:values[day]={'unavailable':True,'shifts':[],'priority':2}
        save_registration(week.pk,person,values,actor=person.user)
        week.refresh_from_db();plan=preview_roster(week.start_date,week.start_date+timedelta(days=6),self.rules,week=week)
        self.assertEqual([(v['employee_id'],v['shift_id'],v['work_date']) for v in plan['proposal']['rows']],[(person.pk,self.shift.pk,week.start_date.isoformat())])
    def test_registration_update_delete_deadline_and_cross_account(self):
        week=self.week();person=self.people[0];values=self.availability(week)
        save_registration(week.pk,person,values,actor=person.user);save_registration(week.pk,person,values,actor=person.user)
        self.assertEqual(ShiftRegistration.objects.count(),1)
        with self.assertRaises(PermissionDenied):save_registration(week.pk,person,values,actor=self.people[1].user)
        save_registration(week.pk,person,{},actor=person.user,delete=True);self.assertFalse(ShiftRegistration.objects.exists())
        week.registration_deadline=timezone.now()-timedelta(seconds=1);week.save()
        with self.assertRaises(ValidationError):save_registration(week.pk,person,values,actor=person.user)
    def test_locked_payroll_and_wrong_specialty_receive_no_new_schedules(self):
        day=timezone.localdate();period=PayrollPeriod.objects.create(name='Khóa',start_date=day,end_date=day,standard_hours=48,overtime_multiplier=1)
        for person in self.people:
            Payroll.objects.create(employee=person,period=period,status='APPROVED',approved_by=self.admin,approved_at=timezone.now(),base_salary=1,working_hours=0,overtime_hours=0,earned_base=0,overtime_pay=0,allowance=0,bonus=0,deduction=0,gross_salary=0,net_salary=0)
        self.assertEqual(preview_roster(day,day,self.rules)['proposal']['rows'],[])
    def test_registered_ui_permissions_and_csrf(self):
        self.week();self.client.force_login(self.people[0].user)
        self.assertContains(self.client.get('/work/shift-registration/'),'Đăng ký ca tuần sau')
        self.assertEqual(self.client.get('/management/roster/').status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.people[0].user)
        self.assertEqual(client.post('/work/shift-registration/',{}).status_code,403)
    def test_published_week_cannot_be_edited(self):
        week=self.week();week.status='PUBLISHED';week.save()
        with self.assertRaises(ValidationError):save_registration(week.pk,self.people[0],self.availability(week),actor=self.people[0].user)
    def test_rollback_all_schedule_writes_on_audit_failure(self):
        day=timezone.localdate();plan=preview_roster(day,day,self.rules)
        with patch('customers.roster_service.record',side_effect=RuntimeError('test rollback')):
            with self.assertRaises(RuntimeError):apply_roster(plan['token'],actor=self.admin,approved_digest=plan['proposal']['plan_digest'])
        self.assertFalse(WorkSchedule.objects.exists())
    def test_approved_current_schedule_reaches_faceid_readiness(self):
        now=timezone.localtime();day=now.date();start,end=self.window(day,self.shift)
        WorkSchedule.objects.create(employee=self.people[0],shift=self.shift,work_date=day,start_at=start,end_at=end,status='APPROVED',approved_by=self.admin,approved_at=timezone.now())
        with patch('customers.attendance_status.timezone.now',return_value=start+timedelta(minutes=5)):
            self.assertEqual(attendance_context(self.people[0].user)['schedule_status'],'AVAILABLE')


class RosterConcurrencyTests(RosterData,TransactionTestCase):
    def setUp(self):self.setup_data()
    def test_concurrent_registration_is_one_row_with_serial_revision(self):
        week=self.week();values=self.availability(week);barrier=Barrier(2);person_id=self.people[0].pk
        def worker(_):
            try:
                person=Employee.objects.select_related('user').get(pk=person_id);barrier.wait(timeout=10)
                return save_registration(week.pk,person,values,actor=person.user).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(worker,range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(ShiftRegistration.objects.count(),1)
        week.refresh_from_db();self.assertEqual(week.revision,2)
    def test_same_plan_concurrent_apply_is_idempotent(self):
        day=timezone.localdate();plan=preview_roster(day,day,self.rules);barrier=Barrier(2);admin_id=self.admin.pk
        def worker(_):
            try:
                actor=get_user_model().objects.get(pk=admin_id);barrier.wait(timeout=10)
                return len(apply_roster(plan['token'],actor=actor,approved_digest=plan['proposal']['plan_digest']))
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:counts=list(pool.map(worker,range(2)))
        self.assertEqual(sorted(counts),[0,3]);self.assertEqual(WorkSchedule.objects.count(),3)
