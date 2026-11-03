"""Add demo operation data without overwriting existing rows or business history."""
import calendar
import hashlib
import json
import secrets
from datetime import time,timedelta
from decimal import Decimal,ROUND_DOWN
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand,CommandError
from django.db import connection,transaction
from django.utils import timezone
from customers.models import (MenuItem,Ingredient,RecipeIngredient,RestaurantInfo,Position,Employee,Shift,WorkSchedule,Attendance,PayrollPeriod,Payroll,Topping,Combo,ComboItem,Promotion,Review,Order)
from customers.rbac import get_role,assign_role
from customers.business_service import save_validated
from customers.module07_forms import ScheduleForm,AttendanceForm
from customers.personnel_service import save_schedule,schedule_state,save_attendance,calculate_payroll
from customers.commerce_service import write_review
from customers.chat_service import create_conversation
from customers.operational_seed_data import ALL_RECIPES,MARKER,POSITIONS,SALARIES,TOPPINGS,COMBOS,VOUCHERS,BOTTLED_MENU_IDS

MODELS=(RestaurantInfo,Position,Employee,Shift,WorkSchedule,Attendance,PayrollPeriod,Payroll,Topping,Combo,ComboItem,Promotion,Review,Ingredient,RecipeIngredient)

class Command(BaseCommand):
    help='Atomic, additive, idempotent operational DEMO data for MODULE 07. No orders/payments/stock seeding.'

    def handle(self,*args,**options):
        if not str(connection.settings_dict["NAME"]).startswith(("test_","sr_","qa_")):
            from customers.operational_reference_seed import seed_reference
            self.stdout.write(json.dumps(seed_reference(),ensure_ascii=True))
            return
        try:
            with transaction.atomic(): result=self.seed()
        except ValidationError as exc: raise CommandError(' '.join(exc.messages)) from exc
        self.stdout.write(json.dumps(result,ensure_ascii=False,default=str,indent=2))

    def seed(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',['module07-operational-seed'])
            cursor.execute('SELECT current_database()');database=cursor.fetchone()[0]
        before={m.__name__:m.objects.count() for m in MODELS}
        self.skipped=[];self.accounts=[];self.passwords={};today=timezone.localdate();start=today-timedelta(days=6)
        users=list(get_user_model().objects.select_for_update(no_key=True).filter(is_active=True).order_by('pk'))
        actor=next((u for u in users if get_role(u)=='ADMIN'),None)
        if actor is None: raise CommandError('Cần một ADMIN active để xác nhận dữ liệu demo; không tự nâng role.')
        self.recipes()
        if not RestaurantInfo.objects.filter(is_active=True).exists():
            if RestaurantInfo.objects.filter(name='Smart Restaurant DEMO').exists(): self.skipped.append('Hồ sơ DEMO đã bị tắt; giữ trạng thái người dùng chọn.')
            else: save_validated(RestaurantInfo(name='Smart Restaurant DEMO',description='Nhà hàng minh họa ẩm thực hải sản và món Âu. Hồ sơ DEMO, không sử dụng thông tin liên hệ cá nhân.',address='123 Đường Nhà Hàng DEMO, TP.HCM (địa chỉ minh họa)',phone='0000000000',email='demo@smart-restaurant.example',opening_time=time(8),closing_time=time(23),latitude=Decimal('10.776900'),longitude=Decimal('106.700900')))
        positions={}
        for name in POSITIONS:
            positions[name],_=Position.objects.get_or_create(name=name,defaults={'description':f'{MARKER} Vị trí công việc, độc lập quyền hệ thống.','is_active':True})
        employees=[];staff_index=0
        for user in users:
            role=get_role(user)
            if role not in ('MANAGER','STAFF'): continue
            position_name='Quản lý' if role=='MANAGER' else ('Phục vụ','Bếp','Thu ngân')[staff_index%3]
            if role=='STAFF':staff_index+=1
            existing=Employee.objects.filter(user=user).first()
            if existing:
                if existing.is_active and existing.employment_status=='ACTIVE': employees.append(existing)
                else:self.skipped.append(f'Employee #{existing.pk} inactive/on-leave: không sửa hoặc tạo lịch.')
                continue
            if not positions[position_name].is_active:
                self.skipped.append(f'Position {position_name} inactive: bỏ qua User #{user.pk}.');continue
            employee=save_validated(Employee(user=user,employee_code=f'DEMO-U{user.pk:04}',full_name=f'Nhân viên DEMO {user.pk:02}',phone='',position=positions[position_name],hire_date=start,base_salary=Decimal(SALARIES[position_name])))
            employees.append(employee)
        # Create clearly labelled accounts only if existing active staff do not cover a position.
        for position_name in POSITIONS:
            if any(e.position.name==position_name for e in employees) or not positions[position_name].is_active:continue
            suffix={'Quản lý':'manager','Phục vụ':'service','Bếp':'kitchen','Thu ngân':'cashier'}[position_name]
            username='demo_m07_'+suffix;user=get_user_model().objects.filter(username=username).first()
            if user:
                self.skipped.append(f'Account {username} đã tồn tại nhưng không đủ điều kiện; không đổi role/password.');continue
            password=secrets.token_urlsafe(18)
            user=get_user_model().objects.create_user(username=username,password=password,first_name='DEMO',last_name=position_name)
            assign_role(user,'MANAGER' if position_name=='Quản lý' else 'STAFF')
            self.accounts.append(username);self.passwords[username]=password
            employees.append(save_validated(Employee(user=user,employee_code=f'DEMO-U{user.pk:04}',full_name=f'Nhân viên DEMO {suffix}',position=positions[position_name],hire_date=start,base_salary=Decimal(SALARIES[position_name]))))
        shifts=[]
        for name,begin,end,required in [('Ca sáng (DEMO)',time(8),time(14),1),('Ca chiều (DEMO)',time(14),time(20),1),('Ca tối (DEMO)',time(17),time(23),1)]:
            shift,_=Shift.objects.get_or_create(name=name,defaults={'start_time':begin,'end_time':end,'required_staff':required,'is_active':True});shifts.append(shift)
        new_schedules=[]
        for i,employee in enumerate(employees):
            shift=shifts[{'Quản lý':0,'Bếp':2,'Thu ngân':1}.get(employee.position.name,0 if i%2 else 2)]
            if not shift.is_active or not employee.position.is_active:
                self.skipped.append(f'Employee #{employee.pk}: ca/chức vụ inactive, giữ nguyên.');continue
            for offset in range(7):
                day=start+timedelta(days=offset)
                if employee.hire_date>day:
                    self.skipped.append(f'Employee #{employee.pk}, {day}: trước ngày vào làm.');continue
                if WorkSchedule.objects.filter(employee=employee,work_date=day,shift=shift).exists():continue
                form=ScheduleForm({'employee':employee.pk,'shift':shift.pk,'work_date':day,'note':MARKER})
                if not form.is_valid():raise CommandError(str(form.errors))
                try:
                    with transaction.atomic():
                        schedule=save_schedule(form,actor=actor);schedule_state(schedule.pk,'APPROVED',actor=actor)
                except ValidationError as exc:self.skipped.append(f'Employee #{employee.pk}, {day}: '+ ' '.join(exc.messages));continue
                new_schedules.append(schedule.pk)
        attendance_count=0
        for employee in employees:
            for schedule in WorkSchedule.objects.filter(employee=employee,work_date__range=(start,start+timedelta(days=2)),note=MARKER,status='APPROVED').order_by('work_date','pk'):
                if Attendance.objects.filter(work_schedule=schedule).exists() or schedule.end_at>timezone.now():continue
                late=(employee.pk+schedule.work_date.day)%3==0
                checkin=schedule.start_at+(timedelta(minutes=10) if late else timedelta(0))
                form=AttendanceForm({'work_schedule':schedule.pk,'check_in_time':checkin.isoformat(),'check_out_time':schedule.end_at.isoformat(),'status':'LATE' if late else 'PRESENT','note':MARKER})
                if not form.is_valid():raise CommandError(str(form.errors))
                try:
                    with transaction.atomic():save_attendance(form,actor=actor)
                except ValidationError as exc:self.skipped.append(f'Attendance ca #{schedule.pk}: '+' '.join(exc.messages));continue
                attendance_count+=1
        month=start.replace(day=1);last=month.replace(day=calendar.monthrange(month.year,month.month)[1])
        period,_=PayrollPeriod.objects.get_or_create(name=f'DEMO - Lương {month:%m/%Y}',defaults={'start_date':month,'end_date':last,'standard_hours':Decimal(208),'overtime_multiplier':Decimal('1.50')})
        for employee in employees:
            if Payroll.objects.filter(employee=employee,period=period).exists():continue
            if not Attendance.objects.filter(employee=employee,work_date__range=(period.start_date,period.end_date),confirmed_at__isnull=False).exists():
                self.skipped.append(f'Payroll Employee #{employee.pk}: chưa có giờ công xác nhận trong kỳ.');continue
            try:
                with transaction.atomic():calculate_payroll(employee.pk,period.pk,actor=actor,allowance=Decimal(100000),bonus=0,deduction=0)
            except ValidationError as exc:self.skipped.append(f'Payroll Employee #{employee.pk}: '+' '.join(exc.messages))
        self.commerce(today)
        reviews_created=0;review_candidates=0
        for order in Order.objects.filter(status='COMPLETED',customer__is_active=True).select_related('customer').order_by('pk'):
            if get_role(order.customer)!='CUSTOMER':continue
            for menu_id in order.items.exclude(kitchen_status='CANCELLED').values_list('menu_item_id',flat=True).distinct().order_by('menu_item_id')[:2]:
                if review_candidates>=2:break
                review_candidates+=1
                if Review.objects.filter(order=order,menu_item_id=menu_id).exists():continue
                write_review(actor=order.customer,order_id=order.pk,menu_item_id=menu_id,rating=5,comment='Đánh giá DEMO: món trình bày đẹp, khẩu vị phù hợp.');reviews_created+=1
            if review_candidates>=2:break
        if not Review.objects.exists():self.skipped.append('Review: không có Order COMPLETED thuộc Customer với món đã mua phù hợp.')
        manager=next((e.user for e in employees if get_role(e.user)=='MANAGER'),None)
        staff=next((e.user for e in employees if get_role(e.user)=='STAFF'),None)
        customer=next((u for u in users if get_role(u)=='CUSTOMER'),None)
        if manager and staff:create_conversation(actor=manager,recipient_id=staff.pk)
        if customer and staff:create_conversation(actor=customer,recipient_id=staff.pk)
        have=MenuItem.objects.filter(recipe_lines__isnull=False).distinct().count()
        return {'database':database,'counts':{m.__name__:{'before':before[m.__name__],'after':m.objects.count()} for m in MODELS},'recipe_food_count':MenuItem.objects.filter(name__in=ALL_RECIPES,recipe_lines__isnull=False).distinct().count(),'packaged_drinks_no_recipe':list(BOTTLED_MENU_IDS),'employees':list(Employee.objects.select_related('user','position').values('employee_code','user__username','position__name')),'new_accounts':self.accounts,'new_account_passwords':self.passwords,'schedule_range':[start,today],'schedules_created':len(new_schedules),'attendance_created':attendance_count,'payroll_period':period.name,'toppings':[x[0] for x in TOPPINGS],'combos':[x[0] for x in COMBOS],'vouchers':[x[0] for x in VOUCHERS],'skipped':self.skipped}

    def recipes(self):
        menus=list(MenuItem.objects.select_for_update().filter(name__in=ALL_RECIPES).order_by('pk'))
        if len(menus)!=35:raise CommandError('Không đủ 35 tên món ăn chính thức; rollback, không seed nhầm ID.')
        list(Ingredient.objects.select_for_update().order_by('pk'))
        for menu in menus:
            if menu.recipe_lines.exists():continue
            for name,(quantity,unit) in ALL_RECIPES[menu.name].items():
                matches=list(Ingredient.objects.filter(name=name).order_by('pk'))
                if len(matches)>1 or (matches and (matches[0].unit!=unit or not matches[0].is_active)):raise CommandError(f'Nguyên liệu {name} trùng tên/sai unit/inactive; rollback.')
                ingredient=matches[0] if matches else save_validated(Ingredient(code='M07-'+hashlib.sha256(name.encode()).hexdigest()[:10].upper(),name=name,unit=unit,current_stock=0,minimum_stock=0))
                save_validated(RecipeIngredient(menu_item=menu,ingredient=ingredient,quantity_required=Decimal(quantity)))

    def commerce(self,today):
        menus={m.pk:m for m in MenuItem.objects.select_for_update().order_by('pk')}
        for name,price,ids in TOPPINGS:
            top,created=Topping.objects.get_or_create(name=name,defaults={'price':Decimal(price),'is_available':True})
            if created:top.menu_items.set(ids)
        for name,parts,ratio in COMBOS:
            if Combo.objects.filter(name=name).exists():continue
            if any(pk not in menus or menus[pk].price is None or not menus[pk].is_available or not menus[pk].category.is_active for pk,qty in parts):
                self.skipped.append(f'{name}: có món chưa có giá/ngừng phục vụ; không tự sửa MenuItem.');continue
            total=sum((menus[pk].price*qty for pk,qty in parts),Decimal(0))
            price=(total*Decimal(ratio)/10000).quantize(Decimal(1),rounding=ROUND_DOWN)*10000
            if price<=0:self.skipped.append(f'{name}: tổng giá không phù hợp.');continue
            combo=save_validated(Combo(name=name,description=f'{MARKER} Giá khởi tạo ưu đãi so với tổng món lẻ; không thay đổi giá menu.',price=price,is_active=True))
            for pk,qty in parts:save_validated(ComboItem(combo=combo,menu_item=menus[pk],quantity=qty))
        now=timezone.now()
        for code,kind,value,minimum,cap,limit in VOUCHERS:
            if Promotion.objects.filter(code=code).exists():continue
            save_validated(Promotion(code=code,name=f'DEMO - {code}',discount_type=kind,discount_value=Decimal(value),min_order_amount=Decimal(minimum),max_discount_amount=Decimal(cap) if cap else None,start_at=now-timedelta(days=1),end_at=now+timedelta(days=90),usage_limit=limit,is_active=True))
