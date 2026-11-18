"""Preview-first staffing. No attendance, payroll, menu or provider writes."""
from collections import defaultdict,Counter
from dataclasses import dataclass
from datetime import date,datetime,timedelta
import hashlib,json
from django.core import signing
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import Employee,Shift,WorkSchedule,Payroll,RestaurantInfo,RosterWeek,ShiftRegistration
from .ga_service import Problem,Seat,shift_window,run_ga,require_ga,eligible
from .rbac import get_role
from .audit_service import record


def monday(day):return day-timedelta(days=day.weekday())
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
def weekly_hours(intervals):
    result=defaultdict(float)
    for start,end in intervals:
        cursor=start
        while cursor<end:
            local=timezone.localtime(cursor);boundary=timezone.make_aware(datetime.combine(local.date()+timedelta(days=1),datetime.min.time()))
            stop=min(end,boundary);result[monday(local.date())]+=(stop-cursor).total_seconds()/3600;cursor=stop
    return result


def validate_rules(rules,shifts):
    try:
        rest=float(rules.get('min_rest_hours',11));hours=float(rules.get('max_weekly_hours',48));count=int(rules.get('max_weekly_shifts',6))
        positions={int(k):set(map(int,v)) for k,v in rules['allowed_positions'].items()}
    except (TypeError,ValueError,KeyError):raise ValidationError('Cần quy tắc chuyên môn theo ca và giới hạn làm việc hợp lệ.')
    if not 11<=rest<=48 or not 1<=hours<=48 or not 1<=count<=6 or any(s not in positions or not positions[s] for s in shifts):
        raise ValidationError('Nghỉ tối thiểu 11 giờ, tối đa 48 giờ và 6 ca/tuần; phải có chuyên môn cho mỗi ca.')
    return rest,hours,count,positions


@dataclass
class Policy:
    rules:dict
    registrations:dict|None
    def allows(self,problem,seat,pk,assigned):
        rest,hours,count,positions=validate_rules(self.rules,problem.shifts)
        employee=problem.employees[pk]
        if employee.position_id not in positions[seat.shift_id]:return False
        if self.registrations is not None:
            day=self.registrations.get(pk,{}).get(seat.day.isoformat(),{})
            if day.get('unavailable',False) or seat.shift_id not in day.get('shifts',[]):return False
        intervals=[*problem.blocks.get(pk,[]),*assigned.get(pk,[])]
        for start,end in intervals:
            if start<seat.end and end>seat.start:return False
            gap=(seat.start-end if end<=seat.start else start-seat.end).total_seconds()/3600
            if gap<rest:return False
        proposed=[*intervals,(seat.start,seat.end)]
        touched=set(weekly_hours([(seat.start,seat.end)]))
        if any(h>hours+.00001 for week,h in weekly_hours(proposed).items() if week in touched):return False
        days=Counter(monday(timezone.localtime(a).date()) for a,b in proposed)
        if days[monday(seat.day)]>count:return False
        # At least one calendar day off; overnight shifts occupy both days.
        occupied=defaultdict(set)
        for start,end in proposed:
            day=timezone.localtime(start).date();last=timezone.localtime(end-timedelta(microseconds=1)).date()
            while day<=last:occupied[monday(day)].add(day);day+=timedelta(days=1)
        return all(len(days)<=6 for week,days in occupied.items() if week in touched)
    def balance_key(self,problem,seat,pk,assigned):
        begin=problem.start_date;end=problem.end_date
        existing=sum(begin<=timezone.localtime(a).date()<=end for a,b in problem.blocks.get(pk,[]))
        priority=(self.registrations or {}).get(pk,{}).get(seat.day.isoformat(),{}).get('priority',2)
        week=monday(seat.day)
        weekly=sum(monday(timezone.localtime(a).date())==week for a,b in [*problem.blocks.get(pk,[]),*assigned.get(pk,[])])
        return weekly,existing+len(assigned[pk]),priority
    def fairness_penalty(self,problem,assigned):
        weeks={monday(s.day) for s in problem.seats};penalty=0
        for week in weeks:
            counts=[sum(monday(timezone.localtime(a).date())==week for a,b in [*problem.blocks.get(pk,[]),*assigned.get(pk,[])]) for pk in problem.employees]
            average=sum(counts)/len(counts) if counts else 0
            penalty+=sum((v-average)**2 for v in counts)
        return 100*penalty


def load_roster(start,end,rules,*,week=None):
    if end<start or (end-start).days>34:raise ValidationError('Khoảng lịch tối đa 5 tuần.')
    employees={e.pk:e for e in Employee.objects.select_related('user','position').filter(is_active=True,user__is_active=True,employment_status='ACTIVE',position__is_active=True).order_by('pk') if get_role(e.user) in ('ADMIN','MANAGER','STAFF')}
    shifts={s.pk:s for s in Shift.objects.filter(is_active=True).order_by('pk')};validate_rules(rules,shifts)
    begin=timezone.make_aware(datetime.combine(start-timedelta(days=7),datetime.min.time()))
    finish=timezone.make_aware(datetime.combine(end+timedelta(days=8),datetime.min.time()))
    # Existing seats remain occupied even if their employee is now inactive;
    # report/review those records instead of silently overbooking the shift.
    records=list(WorkSchedule.objects.filter(start_at__lt=finish,end_at__gt=begin).exclude(status='CANCELLED').order_by('pk'))
    blocks=defaultdict(list);coverage=defaultdict(set);frozen=defaultdict(list)
    for row in records:
        blocks[row.employee_id].append((row.start_at,row.end_at));coverage[(row.work_date,row.shift_id)].add(row.employee_id)
    salaries=list(Payroll.objects.filter(employee_id__in=employees,status__in=['APPROVED','PAID']).values('employee_id','period__start_date','period__end_date'))
    for row in salaries:frozen[row['employee_id']].append((row['period__start_date'],row['period__end_date']))
    restaurant=RestaurantInfo.objects.filter(is_active=True).first()
    if not restaurant:raise ValidationError('Cần cấu hình giờ mở cửa nhà hàng.')
    registrations=None
    if week:
        if start!=week.start_date or end!=start+timedelta(days=6):raise ValidationError('Khoảng tuần đăng ký không hợp lệ.')
        registrations={v.employee_id:v.availability for v in week.registrations.all()}
    seats=[];windows={}
    for offset in range((end-start).days+1):
        day=start+timedelta(days=offset)
        for shift in shifts.values():
            a,b=shift_window(day,shift);opening=timezone.make_aware(datetime.combine(day,restaurant.opening_time));closing=timezone.make_aware(datetime.combine(day,restaurant.closing_time))
            if closing<=opening:closing+=timedelta(days=1)
            if a<opening or b>closing:raise ValidationError('Giờ ca nằm ngoài giờ mở cửa; cần quản lý đối chiếu trước.')
            windows[(day,shift.pk)]=(a,b)
            seats.extend(Seat(day,shift.pk,n,a,b) for n in range(max(0,shift.required_staff-len(coverage[(day,shift.pk)]))))
    state={'employees':[(e.pk,e.user_id,e.employee_code,e.full_name,e.user.username,e.hire_date,e.position_id,get_role(e.user)) for e in employees.values()],
        'shifts':[(s.pk,s.start_time,s.end_time,s.required_staff) for s in shifts.values()],
        'records':[(v.pk,v.employee_id,v.shift_id,v.work_date,v.start_at,v.end_at,v.status) for v in records],
        'frozen':salaries,'rules':rules,'registrations':registrations,'week_revision':week.revision if week else None,
        'range':[start,end],'opening':[restaurant.opening_time,restaurant.closing_time]}
    cutoff=timezone.make_aware(datetime(2000,1,1)) if week is None else timezone.now()
    return Problem(employees,shifts,seats,blocks,coverage,windows,frozen,digest(state),start,end,cutoff,Policy(rules,registrations))


def preview_roster(start,end,rules,*,week=None):
    problem=load_roster(start,end,rules,week=week)
    from .employee_identity import operational_employees
    confirmed_ids=set(operational_employees().values_list('pk',flat=True))
    proposal=run_ga(problem,population_size=12,generations=16,random_seed=42)
    for row in proposal['rows']:
        row['employee_name']=problem.employees[row['employee_id']].full_name
        row['shift_name']=problem.shifts[row['shift_id']].name
    counts=Counter({pk:sum(start<=timezone.localtime(a).date()<=end for a,b in intervals) for pk,intervals in problem.blocks.items()})
    counts.update(v['employee_id'] for v in proposal['rows'])
    proposal.update(rules=rules,week_id=week.pk if week else None,
        staff=[{'employee_id':e.pk,'name':e.full_name,'existing_and_proposed':counts[e.pk],
                'identity_review_required':e.pk not in confirmed_ids} for e in problem.employees.values()],
        missing_by_day=[{'date':day.isoformat(),'shift_id':sid,'shift_name':problem.shifts[sid].name,'missing':max(0,problem.shifts[sid].required_staff-len(problem.coverage[(day,sid)])-sum(v['shift_id']==sid and v['work_date']==day.isoformat() for v in proposal['rows']))} for day,sid in problem.windows],
        retrospective=True if week is None else False,created_at=timezone.now().isoformat())
    proposal['plan_digest']=digest(proposal)
    return {'proposal':proposal,'token':signing.dumps(proposal,salt='staff-roster',compress=True)}


@transaction.atomic
def apply_roster(token,*,actor,approved_digest,approve_current=False):
    require_ga(actor)
    try:proposal=signing.loads(token,salt='staff-roster',max_age=86400)
    except signing.BadSignature as exc:raise ValidationError('Bản preview không hợp lệ hoặc quá 24 giờ; tạo lại.') from exc
    if approved_digest!=proposal['plan_digest']:raise ValidationError('Cần duyệt đúng hash của preview.')
    week=RosterWeek.objects.select_for_update().get(pk=proposal['week_id']) if proposal['week_id'] else None
    list(Employee.objects.select_for_update().order_by('pk'));list(Shift.objects.select_for_update().order_by('pk'))
    marker='Issue10 roster '+approved_digest
    rows=proposal['rows']
    if rows and all(WorkSchedule.objects.filter(employee_id=v['employee_id'],shift_id=v['shift_id'],work_date=v['work_date'],note__startswith=marker,status__in=['DRAFT','APPROVED']).exists() for v in rows):return []
    start=date.fromisoformat(proposal['start_date']);end=date.fromisoformat(proposal['end_date'])
    problem=load_roster(start,end,proposal['rules'],week=week)
    if problem.fingerprint!=proposal['fingerprint']:raise ValidationError('Dữ liệu đã đổi sau preview; tạo preview mới.')
    assigned=defaultdict(list);created=[];used=set();now=timezone.now()
    for row in rows:
        key=(date.fromisoformat(row['work_date']),row['shift_id'])
        seat=next((s for i,s in enumerate(problem.seats) if (s.day,s.shift_id)==key and i not in used),None)
        if seat is None:raise ValidationError('Đề xuất vượt nhu cầu hoặc ngày/ca không hợp lệ.')
        idx=problem.seats.index(seat);used.add(idx);pk=row['employee_id']
        if not eligible(problem,seat,pk,assigned):raise ValidationError('Ca trùng/thiếu nghỉ/vượt giờ/nguyện vọng hoặc kỳ lương khóa.')
        assigned[pk].append((seat.start,seat.end))
        obj=WorkSchedule(employee_id=pk,shift_id=seat.shift_id,work_date=seat.day,source='AI',status='DRAFT',start_at=seat.start,end_at=seat.end,
            note=marker+'; nhập bổ sung lúc '+now.isoformat()+('; lịch hồi tố, không xác nhận đã đi làm' if seat.end<now else '; chờ quản lý xác nhận'))
        if approve_current and seat.end>=now:
            from .employee_identity import require_operational
            require_operational(problem.employees[pk])
            obj.status='APPROVED';obj.approved_by=actor;obj.approved_at=now
        obj.full_clean();obj.save();created.append(obj)
        record(action='ROSTER_SCHEDULE_CREATED',entity=obj,actor=actor,after={'plan_digest':approved_digest,'retrospective':seat.end<now,'status':obj.status})
    if week:
        week.status='PUBLISHED';week.revision+=1;week.save(update_fields=['status','revision'])
    return created


@transaction.atomic
def save_registration(week_id,employee,availability,*,actor,delete=False):
    week=RosterWeek.objects.select_for_update().get(pk=week_id)
    employee=Employee.objects.select_for_update().select_related('user','position').get(pk=employee.pk)
    if employee.user_id!=actor.pk or get_role(actor) not in ('STAFF','MANAGER','ADMIN'):raise PermissionDenied
    from .employee_identity import require_operational
    require_operational(employee)
    if week.status!='OPEN' or timezone.now()>=week.registration_deadline:raise ValidationError('Đã hết hạn đăng ký hoặc lịch đã công bố.')
    if week.start_date!=monday(timezone.localdate())+timedelta(days=7):raise ValidationError('Chỉ nhận đăng ký cho tuần kế tiếp.')
    valid_shifts=set(Shift.objects.filter(is_active=True).values_list('pk',flat=True))
    if not delete:
        expected={(week.start_date+timedelta(days=i)).isoformat() for i in range(7)}
        if not isinstance(availability,dict) or set(availability)!=expected:raise ValidationError('Cần khai báo đủ 7 ngày trong tuần.')
        for day,v in availability.items():
            if not isinstance(v,dict) or set(v)!={'unavailable','shifts','priority'} or not isinstance(v.get('unavailable'),bool) or not isinstance(v.get('shifts'),list) or not all(type(s) is int for s in v['shifts']) or len(set(v['shifts']))!=len(v['shifts']) or not set(v['shifts']).issubset(valid_shifts) or type(v.get('priority')) is not int or v['priority'] not in (1,2,3):raise ValidationError('Đăng ký ngày/ca/mức ưu tiên không hợp lệ.')
            if v['unavailable'] and v['shifts']:raise ValidationError('Ngày không thể làm không được chọn ca.')
        obj,_=ShiftRegistration.objects.update_or_create(week=week,employee=employee,defaults={'availability':availability})
    else:
        ShiftRegistration.objects.filter(week=week,employee=employee).delete();obj=None
    week.revision+=1;week.save(update_fields=['revision'])
    record(action='SHIFT_REGISTRATION_REMOVED' if delete else 'SHIFT_REGISTRATION_SAVED',entity=week,actor=employee.user,after={'employee_id':employee.pk,'revision':week.revision})
    return obj
