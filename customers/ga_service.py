"""Genetic search over vacant staffing seats. Preview is pure; save is atomic."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime,timedelta
import hashlib,json,math,random
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Employee,Shift,WorkSchedule,Payroll
from .rbac import get_role,has_capability

WEIGHTS={'missing_seat':10000,'hard':1000000,'imbalance':10,'weekly_overwork':30,'short_rest_hour':20}
MIN_REST_HOURS=11

@dataclass(frozen=True)
class Seat:
    day:object
    shift_id:int
    number:int
    start:object
    end:object

@dataclass
class Problem:
    employees:dict
    shifts:dict
    seats:list
    blocks:dict
    coverage:dict
    windows:dict
    frozen:dict
    fingerprint:str
    start_date:object
    end_date:object
    cutoff:object

def shift_window(day,shift):
    start=timezone.make_aware(datetime.combine(day,shift.start_time))
    end=timezone.make_aware(datetime.combine(day,shift.end_time))
    return start,end if end>start else end+timedelta(days=1)

def load_problem(start_date,end_date):
    if start_date<timezone.localdate() or end_date<start_date or (end_date-start_date).days>13:
        raise ValidationError('Chọn khoảng từ hôm nay, tối đa 14 ngày.')
    employees={e.pk:e for e in Employee.objects.select_related('user','position').filter(is_active=True,employment_status='ACTIVE',user__is_active=True,position__is_active=True).order_by('pk') if get_role(e.user) in ('ADMIN','MANAGER','STAFF')}
    shifts={s.pk:s for s in Shift.objects.filter(is_active=True).order_by('pk')}
    begin=timezone.make_aware(datetime.combine(start_date,datetime.min.time()))
    finish=timezone.make_aware(datetime.combine(end_date+timedelta(days=2),datetime.min.time()))
    records=list(WorkSchedule.objects.filter(employee_id__in=employees).exclude(status='CANCELLED').filter(start_at__lt=finish,end_at__gt=begin-timedelta(days=7)).order_by('pk'))
    blocks=defaultdict(list);coverage=defaultdict(set)
    for row in records:
        blocks[row.employee_id].append((row.start_at,row.end_at))
        if row.status=='APPROVED':coverage[(row.work_date,row.shift_id)].add(row.employee_id)
    frozen=defaultdict(list)
    salaries=list(Payroll.objects.filter(employee_id__in=employees,status__in=['APPROVED','PAID']).values('employee_id','period__start_date','period__end_date').order_by('employee_id','period__start_date'))
    for row in salaries:frozen[row['employee_id']].append((row['period__start_date'],row['period__end_date']))
    seats=[];windows={}
    for i in range((end_date-start_date).days+1):
        day=start_date+timedelta(days=i)
        for shift in shifts.values():
            start,end=shift_window(day,shift);windows[(day,shift.pk)]=(start,end)
            required=max(0,shift.required_staff-len(coverage[(day,shift.pk)]))
            seats.extend(Seat(day,shift.pk,n,start,end) for n in range(required))
    if len(seats)>400:raise ValidationError('Khoảng chọn có quá nhiều suất ca (tối đa 400).')
    cutoff=timezone.now()
    state={'range':[start_date,end_date],'elapsed':[(str(day),pk) for (day,pk),(a,b) in windows.items() if a<=cutoff],
        'employees':[(e.pk,e.hire_date,e.position_id,e.user_id,get_role(e.user)) for e in employees.values()],
        'shifts':[(s.pk,s.start_time,s.end_time,s.required_staff) for s in shifts.values()],
        'records':[(r.pk,r.employee_id,r.shift_id,r.work_date,r.start_at,r.end_at,r.status,r.source) for r in records],
        'frozen':salaries}
    fingerprint=hashlib.sha256(json.dumps(state,default=str,sort_keys=True).encode()).hexdigest()
    return Problem(employees,shifts,seats,blocks,coverage,windows,frozen,fingerprint,start_date,end_date,cutoff)

def eligible(problem,seat,employee_id,assigned):
    employee=problem.employees.get(employee_id)
    if not employee or employee.hire_date>seat.day or seat.start<=problem.cutoff:return False
    if any(a<=seat.day<=b for a,b in problem.frozen.get(employee_id,[])):return False
    return not any(start<seat.end and end>seat.start for start,end in [*problem.blocks.get(employee_id,[]),*assigned.get(employee_id,[])])

def repair(problem,chromosome,rng,*,fill=True):
    result=[None]*len(problem.seats);assigned=defaultdict(list)
    # Keep inherited feasible assignments; fill the remaining seats in random order.
    for i,(seat,employee_id) in enumerate(zip(problem.seats,chromosome)):
        if employee_id is not None and eligible(problem,seat,employee_id,assigned):
            result[i]=employee_id;assigned[employee_id].append((seat.start,seat.end))
    if fill:
        order=list(range(len(result)));rng.shuffle(order)
        for i in order:
            if result[i] is not None:continue
            candidates=[pk for pk in problem.employees if eligible(problem,problem.seats[i],pk,assigned)]
            if candidates:
                rng.shuffle(candidates)
                employee_id=min(candidates,key=lambda pk:len(assigned[pk]))
                result[i]=employee_id;assigned[employee_id].append((problem.seats[i].start,problem.seats[i].end))
    return tuple(result)

def initialize_population(problem,population_size,rng):
    return [repair(problem,[None]*len(problem.seats),rng) for _ in range(population_size)]

def evaluate_chromosome(problem,chromosome):
    assigned=defaultdict(list);hard=0;missing=0;coverage={k:len(v) for k,v in problem.coverage.items()}
    if len(chromosome)!=len(problem.seats):raise ValidationError('Chromosome có số gene không hợp lệ.')
    for seat,pk in zip(problem.seats,chromosome):
        if pk is None:missing+=1;continue
        if not eligible(problem,seat,pk,assigned):hard+=1;continue
        assigned[pk].append((seat.start,seat.end));coverage[(seat.day,seat.shift_id)]=coverage.get((seat.day,seat.shift_id),0)+1
    loads=[sum((end-start).total_seconds()/3600 for start,end in assigned.get(pk,[])) for pk in problem.employees]
    average=sum(loads)/len(loads) if loads else 0
    imbalance=sum((x-average)**2 for x in loads)/len(loads) if loads else 0
    overwork=0;short_rest=0
    for pk,proposals in assigned.items():
        weekly=defaultdict(float)
        for start,end in [*problem.blocks.get(pk,[]),*proposals]:
            weekly[timezone.localtime(start).date().isocalendar()[:2]]+=(end-start).total_seconds()/3600
        overwork+=sum(max(0,hours-48) for hours in weekly.values())
        intervals=sorted([*problem.blocks.get(pk,[]),*proposals])
        for left,right in zip(intervals,intervals[1:]):
            # Only penalize rest touching a proposed shift, not immutable old schedules.
            if left in proposals or right in proposals:
                gap=(right[0]-left[1]).total_seconds()/3600
                if gap>=0:short_rest+=max(0,MIN_REST_HOURS-gap)
    score=-(WEIGHTS['hard']*hard+WEIGHTS['missing_seat']*missing+WEIGHTS['imbalance']*imbalance+WEIGHTS['weekly_overwork']*overwork+WEIGHTS['short_rest_hour']*short_rest)
    full=sum(coverage.get(key,0)>=problem.shifts[key[1]].required_staff for key in problem.windows)
    return {'score':round(score,6),'hard_violations':hard,'missing_seats':missing,'full_shifts':full,'short_shifts':len(problem.windows)-full,'coverage_rate':full/len(problem.windows) if problem.windows else 0,'imbalance':round(imbalance,4),'overwork_hours':round(overwork,4),'short_rest_hours':round(short_rest,4)}

def fitness(problem,chromosome):return evaluate_chromosome(problem,chromosome)['score']

def selection(population,scores,rng):
    contenders=rng.sample(range(len(population)),min(3,len(population)))
    return population[max(contenders,key=lambda i:scores[i])]

def crossover(left,right,rng,rate):
    if len(left)<2 or rng.random()>=rate:return left,right
    point=rng.randrange(1,len(left))
    return left[:point]+right[point:],right[:point]+left[point:]

def mutation(chromosome,employee_ids,rng,rate):
    return tuple(rng.choice([None,*employee_ids]) if rng.random()<rate else pk for pk in chromosome)

def run_ga(problem,*,population_size=50,generations=80,mutation_rate=.08,crossover_rate=.8,random_seed=42):
    if not 4<=population_size<=200 or not 1<=generations<=300 or not 0<=mutation_rate<=1 or not 0<=crossover_rate<=1:raise ValidationError('Tham số GA ngoài giới hạn.')
    rng=random.Random(random_seed);population=initialize_population(problem,population_size,rng)
    best=None;best_score=-math.inf;stale=0;trace=[]
    for generation in range(generations):
        scores=[fitness(problem,c) for c in population];index=max(range(len(scores)),key=lambda i:scores[i])
        trace.append({'generation':generation,'best':scores[index],'mean':round(sum(scores)/len(scores),6)})
        if scores[index]>best_score:best=population[index];best_score=scores[index];stale=0
        else:stale+=1
        if stale>=20:break
        elites=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)[:2]
        children=[population[i] for i in elites]
        while len(children)<population_size:
            left,right=crossover(selection(population,scores,rng),selection(population,scores,rng),rng,crossover_rate)
            for child in (left,right):
                children.append(repair(problem,mutation(child,list(problem.employees),rng,mutation_rate),rng))
                if len(children)==population_size:break
        population=children
    rows=[{'employee_id':pk,'shift_id':seat.shift_id,'work_date':seat.day.isoformat()} for seat,pk in zip(problem.seats,best or ()) if pk is not None]
    return {'rows':rows,'metrics':evaluate_chromosome(problem,best or tuple(None for s in problem.seats)),'trace':trace,'best_fitness':best_score,'mean_fitness':trace[-1]['mean'],'generations_run':len(trace),'random_seed':random_seed,'fingerprint':problem.fingerprint,'start_date':problem.start_date.isoformat(),'end_date':problem.end_date.isoformat()}

def require_ga(actor):
    if get_role(actor) not in ('ADMIN','MANAGER') or not all(has_capability(actor,'customers.'+p) for p in ('view_workschedule','add_workschedule','change_workschedule')):raise PermissionDenied

@transaction.atomic
def save_proposal(proposal,*,actor):
    require_ga(actor)
    # Share Employee -> Shift locks with manual scheduling; re-read state after waiting.
    list(Employee.objects.select_for_update().order_by('pk'))
    list(Shift.objects.select_for_update().order_by('pk'))
    start=datetime.fromisoformat(proposal['start_date']).date();end=datetime.fromisoformat(proposal['end_date']).date()
    problem=load_problem(start,end)
    if problem.fingerprint!=proposal['fingerprint']:raise ValidationError('Dữ liệu nhân viên/ca/lịch đã đổi; hãy tạo đề xuất mới.')
    from .module07_forms import ScheduleForm
    from .personnel_service import save_schedule
    created=[]
    for row in proposal['rows']:
        if row['employee_id'] not in problem.employees or row['shift_id'] not in problem.shifts or not start<=datetime.fromisoformat(row['work_date']).date()<=end:raise ValidationError('Lịch đề xuất không hợp lệ.')
        form=ScheduleForm({'employee':row['employee_id'],'shift':row['shift_id'],'work_date':row['work_date'],'note':f'Đề xuất GA · random seed {proposal["random_seed"]}'})
        if not form.is_valid():raise ValidationError('Lịch đề xuất trùng hoặc không hợp lệ.')
        created.append(save_schedule(form,actor=actor,source='AI'))
    return created
