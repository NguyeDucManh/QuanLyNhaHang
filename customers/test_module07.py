"""Business integration, ownership, money, locks and authenticated ASGI chat."""
import uuid
from calendar import monthrange
from datetime import time,timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User,Group
from django.core.exceptions import ValidationError,PermissionDenied
from django.core.management import call_command
from django.db import transaction,IntegrityError,connections,connection
from django.test import TestCase,TransactionTestCase,Client,RequestFactory
from django.urls import reverse
from django.utils import timezone
from .test_business import BusinessData
from .models import *
from .module07_forms import ScheduleForm,AttendanceForm,ShiftForm,EmployeeForm,PromotionForm
from .commerce_service import apply_voucher,write_review,add_toppings_to_line,add_combo_to_order
from .booking_service import create_booking
from .order_service import open_order_from_booking,transition_order,update_order_item,add_order_item
from .kitchen_service import transition_kitchen_item
from .payment_service import issue_invoice,create_payment,confirm_payment
from .chat_service import create_conversation,send_message
from .report_service import report_data
from . import personnel_service as hr
from restaurant_system.asgi import application

class Module07Fixtures(BusinessData):
    def personnel(self):
        self.position=Position.objects.create(name='Bếp')
        self.employee=Employee.objects.create(user=self.staff,employee_code='EMP1',full_name='Staff one',position=self.position,hire_date=timezone.localdate(),base_salary=Decimal('20800000'))
        self.shift=Shift.objects.create(name='Day',start_time=time(8),end_time=time(16),required_staff=1)
        self.day=timezone.localdate()
        self.period=PayrollPeriod.objects.create(name='October',start_date=self.day.replace(day=1),end_date=self.day.replace(day=monthrange(self.day.year,self.day.month)[1]),standard_hours=208,overtime_multiplier=Decimal('1.50'))
    def schedule(self,date=None,shift=None,employee=None):
        form=ScheduleForm({'employee':(employee or self.employee).pk,'shift':(shift or self.shift).pk,'work_date':str(date or self.day),'note':'Manual'})
        self.assertTrue(form.is_valid(),form.errors)
        return hr.save_schedule(form,actor=self.manager)
    def approved_schedule(self): return hr.schedule_state(self.schedule().pk,'APPROVED',actor=self.manager)
    def manual_attendance(self,schedule,extra=0):
        form=AttendanceForm({'work_schedule':schedule.pk,'check_in_time':schedule.start_at.isoformat(),'check_out_time':(schedule.end_at+timedelta(hours=extra)).isoformat(),'status':'PRESENT','note':'Verified'})
        self.assertTrue(form.is_valid(),form.errors)
        return hr.save_attendance(form,actor=self.manager)
    def promotion(self,**values):
        defaults=dict(code='SAVE',name='Save',discount_type='PERCENT',discount_value=10,min_order_amount=0,start_at=timezone.now()-timedelta(days=1),end_at=timezone.now()+timedelta(days=1))
        defaults.update(values); return Promotion.objects.create(**defaults)
    def reserve(self,**extra):
        values=dict(user=self.customer,name='Customer',phone='0912345678',date=timezone.localdate()+timedelta(days=2),time=time(18),guests=2,food_cart={str(self.menu.pk):2})
        values.update(extra); return create_booking(**values)

class Module07CommerceTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def test_recipe_seed_15_idempotent_no_stock_mutation(self):
        old=list(MenuItem.objects.order_by('id').values()); stocks=list(Ingredient.objects.order_by('id').values('id','current_stock'))
        call_command('seed_module07_recipes',stdout=StringIO()); lines=RecipeIngredient.objects.count(); count=Ingredient.objects.count()
        self.assertEqual(MenuItem.objects.filter(recipe_lines__isnull=False).distinct().count(),15)
        call_command('seed_module07_recipes',stdout=StringIO()); self.assertEqual(RecipeIngredient.objects.count(),lines); self.assertEqual(Ingredient.objects.count(),count)
        self.assertEqual(list(MenuItem.objects.order_by('id').values()),old)
        self.assertEqual(list(Ingredient.objects.filter(pk__in=[x['id'] for x in stocks]).order_by('id').values('id','current_stock')),stocks)
        self.assertEqual(StockMovement.objects.count(),0)
    def test_topping_snapshot_booking_order_and_fake_prices(self):
        top=Topping.objects.create(name='Cheese',price=15); top.menu_items.add(self.menu)
        booking=self.reserve(topping_cart={str(self.menu.pk):[top.pk]})
        line=booking.preorder_items.get(); self.assertEqual(line.unit_price,115); self.assertEqual(booking.food_subtotal,230)
        top.price=999; top.save()
        order=open_order_from_booking(booking.pk,actor=self.staff); self.assertEqual(order.subtotal,230)
        self.assertEqual(order.items.get().extras['toppings'][0]['price'],'15.00')
        c=Client(); response=c.post(reverse('update_cart',args=[self.menu.pk]),{'topping_selection':'1','toppings':[top.pk],'price':'1','total':'1'},HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code,200); self.assertEqual(c.session['topping_cart'][str(self.menu.pk)],[top.pk])
    def test_invalid_topping_rolls_back_booking(self):
        top=Topping.objects.create(name='Invalid',price=10)
        with self.assertRaises(ValidationError): self.reserve(topping_cart={str(self.menu.pk):[top.pk]})
        self.assertEqual(Booking.objects.count(),0)
        top.menu_items.add(self.menu); top.is_available=False; top.save()
        with self.assertRaises(ValidationError): self.reserve(topping_cart={str(self.menu.pk):[top.pk]})
    def test_order_topping_draft_snapshot_quantity(self):
        top=Topping.objects.create(name='Extra',price=12); top.menu_items.add(self.menu)
        order=self.order(); line=order.items.get(); add_toppings_to_line(order.pk,line.pk,[top.pk],actor=self.staff)
        top.price=500; top.save(); update_order_item(order.pk,line.pk,actor=self.staff,quantity=3)
        line.refresh_from_db(); order.refresh_from_db(); self.assertEqual((line.unit_price,order.total_amount),(112,336))
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        with self.assertRaises(ValidationError): add_toppings_to_line(order.pk,line.pk,[],actor=self.staff)
    def test_combo_snapshot_cents_and_physical_recipe_consumption(self):
        combo=Combo.objects.create(name='Combo',price=Decimal('101.01')); ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=2); ComboItem.objects.create(combo=combo,menu_item=self.second,quantity=1)
        booking=self.reserve(food_cart={},combo_cart={str(combo.pk):2})
        self.assertEqual(booking.food_subtotal,Decimal('202.02')); self.assertEqual(booking.preorder_items.count(),3)
        combo.price=999; combo.name='Edited'; combo.save(); order=open_order_from_booking(booking.pk,actor=self.staff)
        self.assertEqual(order.total_amount,Decimal('202.02')); self.assertEqual(order.items.first().extras['combo']['name'],'Combo')
        self.import_stock(5); RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        for line in order.items.all():
            transition_kitchen_item(order.pk,line.pk,'PREPARING',actor=self.staff); transition_kitchen_item(order.pk,line.pk,'READY',actor=self.staff)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,4)
    def test_combo_inactive_and_empty_rejected(self):
        combo=Combo.objects.create(name='Empty',price=1)
        with self.assertRaises(ValidationError): self.reserve(food_cart={},combo_cart={str(combo.pk):1})
        ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=1); combo.is_active=False; combo.save()
        with self.assertRaises(ValidationError): self.reserve(food_cart={},combo_cart={str(combo.pk):1})
    def test_direct_order_combo_group_quantity_remove_price_snapshot(self):
        from .order_service import remove_order_item
        combo=Combo.objects.create(name='Direct',price=Decimal('100.01'))
        ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=2);ComboItem.objects.create(combo=combo,menu_item=self.second,quantity=1)
        order=self.order(quantity=1);add_combo_to_order(order.pk,combo.pk,2,actor=self.staff)
        order.refresh_from_db();self.assertEqual(order.total_amount,Decimal('300.02'))
        line=order.items.exclude(extras={}).first();update_order_item(order.pk,line.pk,actor=self.staff,quantity=3)
        order.refresh_from_db();self.assertEqual(order.total_amount,Decimal('400.03'))
        remove_order_item(order.pk,line.pk,actor=self.staff);order.refresh_from_db();self.assertEqual(order.total_amount,100);self.assertEqual(order.items.count(),1)
    def test_topping_order_create_and_add_ignore_client_money(self):
        top=Topping.objects.create(name='New extra',price=10);top.menu_items.add(self.menu)
        order=self.order(items=[{'menu_item':self.menu,'quantity':2,'toppings':[top.pk],'unit_price':1}]);self.assertEqual(order.total_amount,220)
        add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1,toppings=[top.pk]);order.refresh_from_db();self.assertEqual(order.total_amount,330)
    def test_voucher_percent_fixed_cap_and_snapshot(self):
        promo=self.promotion(max_discount_amount=15); order=self.order(customer=self.customer)
        apply_voucher(order.pk,' save ',actor=self.customer); order.refresh_from_db(); self.assertEqual(order.discount_amount,15)
        apply_voucher(order.pk,'SAVE',actor=self.customer); promo.refresh_from_db(); self.assertEqual(promo.used_count,1)
        promo.discount_value=90; promo.save(); add_order_item(order.pk,actor=self.staff,menu_item_id=self.second.pk,quantity=1)
        order.refresh_from_db(); self.assertEqual(order.discount_amount,15)
        self.promotion(code='FIX',discount_type='FIXED',discount_value=1000)
        another=self.order(customer=self.customer); apply_voucher(another.pk,'FIX',actor=self.customer); another.refresh_from_db(); self.assertEqual(another.total_amount,0)
    def test_voucher_invalid_expired_inactive_min_limit_owner(self):
        order=self.order(customer=self.customer)
        for values in ({'is_active':False},{'end_at':timezone.now()-timedelta(hours=1),'start_at':timezone.now()-timedelta(days=3)},{'min_order_amount':999},{'usage_limit':1,'used_count':1}):
            promo=self.promotion(code='BAD'+str(Promotion.objects.count()),**values)
            with self.assertRaises(ValidationError): apply_voucher(order.pk,promo.code,actor=self.customer)
        with self.assertRaises(PermissionDenied): apply_voucher(order.pk,'SAVE',actor=User.objects.create_user('other'))
        order.refresh_from_db(); self.assertEqual(order.discount_amount,0)
    def test_review_requires_completed_owned_purchased_rating_unique(self):
        order=self.order(customer=self.customer)
        with self.assertRaises(ValidationError): write_review(actor=self.customer,order_id=order.pk,menu_item_id=self.menu.pk,rating=5)
        self.prepare(order); transition_order(order.pk,'COMPLETED',actor=self.staff)
        for menu,rating in ((self.second,5),(self.menu,0),(self.menu,6)):
            with self.assertRaises(ValidationError): write_review(actor=self.customer,order_id=order.pk,menu_item_id=menu.pk,rating=rating)
        review=write_review(actor=self.customer,order_id=order.pk,menu_item_id=self.menu.pk,rating=5,comment='<script>x</script>')
        with self.assertRaises(ValidationError): write_review(actor=self.customer,order_id=order.pk,menu_item_id=self.menu.pk,rating=4)
        c=Client(); c.force_login(self.customer); self.assertContains(c.get(reverse('reviews')),'&lt;script&gt;')
    def test_history_ownership_real_invoice_and_payment(self):
        order=self.order(customer=self.customer); other=self.order(customer=self.manager)
        c=Client(); c.force_login(self.customer); self.assertContains(c.get(reverse('purchase_history')),order.order_number)
        self.assertNotContains(c.get(reverse('purchase_history')),other.order_number)
        self.assertEqual(c.get(reverse('purchase_detail',args=[other.pk])).status_code,404)
    def test_restaurant_info_single_active_and_customer_read(self):
        info=RestaurantInfo.objects.create(name='Real Restaurant',address='Real Address',opening_time=time(8),closing_time=time(22))
        with self.assertRaises(IntegrityError),transaction.atomic(): RestaurantInfo.objects.create(name='Another',opening_time=time(8),closing_time=time(22))
        self.assertContains(Client().get(reverse('customer_about')),'Real Address')
    def test_rbac_new_pages_no_staff_crud_and_csrf(self):
        for actor,status in ((self.admin,200),(self.manager,200),(self.staff,403),(self.customer,403)):
            c=Client(); c.force_login(actor)
            for resource in ('topping','combo','promotion','employee','position','shift','workschedule','attendance','payrollperiod','restaurantinfo'):
                self.assertEqual(c.get(reverse('module07_list',args=[resource])).status_code,status)
        c=Client(enforce_csrf_checks=True);c.force_login(self.manager)
        self.assertEqual(c.post(reverse('module07_add',args=['position']),{'name':'Test'}).status_code,403)
    def test_promotion_and_combo_database_constraints(self):
        with self.assertRaises(IntegrityError),transaction.atomic(): self.promotion(discount_value=101)
        combo=Combo.objects.create(name='Test',price=1); ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=1)
        with self.assertRaises(IntegrityError),transaction.atomic(): ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=2)

class Module07PersonnelTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def setUp(self): self.personnel()
    def test_employee_one_to_one_position_independent(self):
        with self.assertRaises(IntegrityError),transaction.atomic(): Employee.objects.create(user=self.staff,employee_code='X',full_name='X',position=self.position,hire_date=self.day)
        self.assertEqual(list(self.staff.groups.values_list('name',flat=True)),['STAFF']); self.assertEqual(self.employee.position.name,'Bếp')
    def test_shift_invalid_zero_equal_time(self):
        for values in ({'required_staff':0,'end_time':'16:00'},{'required_staff':1,'end_time':'08:00'}):
            self.assertFalse(ShiftForm({'name':'Bad','start_time':'08:00',**values}).is_valid())
    def test_schedule_manual_overlap_overnight_and_inactive(self):
        form=ScheduleForm({'employee':self.employee.pk,'shift':self.shift.pk,'work_date':self.day,'source':'AI','status':'APPROVED','approved_by':self.staff.pk})
        self.assertTrue(form.is_valid());schedule=hr.save_schedule(form,actor=self.manager)
        self.assertEqual(schedule.source,'MANUAL');self.assertEqual(schedule.status,'DRAFT');self.assertIsNone(schedule.approved_by_id)
        overlap=Shift.objects.create(name='Overlap',start_time=time(15),end_time=time(20))
        with self.assertRaises(ValidationError): self.schedule(shift=overlap)
        night=Shift.objects.create(name='Night',start_time=time(22),end_time=time(9))
        with self.assertRaises(ValidationError): self.schedule(date=self.day-timedelta(days=1),shift=night)
    def test_overnight_overlap_adjacent_day_rejected(self):
        night=Shift.objects.create(name='Night',start_time=time(22),end_time=time(9)); obj=self.schedule(date=self.day-timedelta(days=1),shift=night)
        self.assertEqual(obj.end_at.date(),self.day)
        with self.assertRaises(ValidationError): self.schedule()
    def test_schedule_inactive_employee_shift_and_duplicate(self):
        self.employee.is_active=False; self.employee.save()
        with self.assertRaises(ValidationError): self.schedule()
        self.employee.is_active=True; self.employee.save(); self.shift.is_active=False; self.shift.save()
        with self.assertRaises(ValidationError): self.schedule()
        self.shift.is_active=True;self.shift.save(); self.schedule()
        with self.assertRaises(ValidationError): self.schedule()
    def test_punch_checkin_checkout_duplicate_and_hours(self):
        schedule=self.approved_schedule()
        with patch('customers.personnel_service.timezone.now',return_value=schedule.start_at):
            with self.assertRaises(ValidationError): hr.punch(schedule.pk,'out',actor=self.staff)
            attendance=hr.punch(schedule.pk,'in',actor=self.staff)
            with self.assertRaises(ValidationError): hr.punch(schedule.pk,'in',actor=self.staff)
        with patch('customers.personnel_service.timezone.now',return_value=schedule.end_at): hr.punch(schedule.pk,'out',actor=self.staff)
        attendance.refresh_from_db(); self.assertEqual(attendance.working_hours,8)
        with self.assertRaises(ValidationError): hr.punch(schedule.pk,'out',actor=self.staff)
        hr.confirm_attendance(attendance.pk,actor=self.manager); attendance.refresh_from_db(); self.assertIsNotNone(attendance.confirmed_at)
    def test_punch_owner_active_and_approved(self):
        schedule=self.schedule()
        with self.assertRaises(PermissionDenied): hr.punch(schedule.pk,'in',actor=self.manager)
        with self.assertRaises(ValidationError): hr.punch(schedule.pk,'in',actor=self.staff)
        hr.schedule_state(schedule.pk,'APPROVED',actor=self.manager); self.employee.is_active=False; self.employee.save()
        with self.assertRaises(ValidationError): hr.punch(schedule.pk,'in',actor=self.staff)
    def test_attendance_manual_times_constraints_absent(self):
        schedule=self.approved_schedule(); attendance=self.manual_attendance(schedule)
        self.assertEqual(attendance.confirmed_by_id,self.manager.pk); self.assertEqual(attendance.working_hours,8)
        with self.assertRaises(IntegrityError),transaction.atomic(): Attendance.objects.filter(pk=attendance.pk).update(check_out_time=attendance.check_in_time)
    def test_payroll_hours_overtime_allowance_bonus_deduction_snapshot(self):
        attendance=self.manual_attendance(self.approved_schedule(),extra=2)
        payroll=hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager,allowance=100000,bonus=50000,deduction=25000)
        self.assertEqual((payroll.working_hours,payroll.overtime_hours),(8,2)); self.assertEqual(payroll.earned_base,800000); self.assertEqual(payroll.overtime_pay,300000)
        self.assertEqual((payroll.gross_salary,payroll.net_salary),(1250000,1225000)); self.assertEqual(payroll.calculation_snapshot['attendance'][0]['id'],attendance.pk)
        self.assertEqual(hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager).pk,payroll.pk)
    def test_payroll_unconfirmed_ignored_approval_freezes_edits(self):
        schedule=self.approved_schedule()
        Attendance.objects.create(employee=self.employee,work_schedule=schedule,work_date=self.day,check_in_time=schedule.start_at,check_out_time=schedule.end_at)
        payroll=hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager); self.assertEqual(payroll.working_hours,0)
        hr.payroll_state(payroll.pk,'APPROVED',actor=self.manager)
        with self.assertRaises(ValidationError): hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager)
        with self.assertRaises(ValidationError): hr.confirm_attendance(Attendance.objects.get().pk,actor=self.manager)
        with self.assertRaises(ValidationError): hr.payroll_state(payroll.pk,'APPROVED',actor=self.manager)
        hr.payroll_state(payroll.pk,'PAID',actor=self.manager); payroll.refresh_from_db(); self.assertIsNotNone(payroll.paid_at)
    def test_payroll_stale_hours_requires_recalculate_and_overlapping_period_rejected(self):
        payroll=hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager)
        self.manual_attendance(self.approved_schedule())
        with self.assertRaises(ValidationError):hr.payroll_state(payroll.pk,'APPROVED',actor=self.manager)
        hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager);hr.payroll_state(payroll.pk,'APPROVED',actor=self.manager)
        other=PayrollPeriod.objects.create(name='Overlap',start_date=self.period.start_date,end_date=self.period.end_date)
        with self.assertRaises(ValidationError):hr.calculate_payroll(self.employee.pk,other.pk,actor=self.manager)
    def test_attendance_manual_overlapping_actual_hours_rejected(self):
        first=self.approved_schedule();self.manual_attendance(first,extra=2)
        late=Shift.objects.create(name='Evening',start_time=time(16),end_time=time(22))
        second=hr.schedule_state(self.schedule(shift=late).pk,'APPROVED',actor=self.manager)
        with self.assertRaises(ValidationError):self.manual_attendance(second)
    def test_staff_personal_work_payroll_ownership(self):
        payroll=hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager)
        c=Client(); c.force_login(self.staff); self.assertContains(c.get(reverse('my_work')),'Staff one')
        self.assertEqual(c.get(reverse('payroll_detail',args=[payroll.pk])).status_code,200); self.assertEqual(c.get(reverse('payroll_list')).status_code,403)
        c.force_login(self.customer); self.assertEqual(c.get(reverse('payroll_detail',args=[payroll.pk])).status_code,404); self.assertEqual(c.get(reverse('my_work')).status_code,403)
    def test_dashboard_revenue_order_stock_employee_attendance_real(self):
        self.manual_attendance(self.approved_schedule()); self.order(customer=self.customer)
        sections=dict(report_data(self.manager)); self.assertEqual(dict(sections['Đơn / Khách / Đặt bàn'])['Order'],1)
        self.assertEqual(dict(sections['Doanh thu Payment SUCCEEDED'])['Thực thu'],0)
        self.assertEqual(dict(sections['Nhân sự'])['Employee active'],1)
        self.assertEqual(dict(sections['Chấm công'])['Giờ thực tế xác nhận'],8)
        self.assertEqual(dict(sections['Kho — không cộng lẫn đơn vị'])['Tồn thấp'],2)
        self.prepare(Order.objects.get()); inv=issue_invoice(transition_order(Order.objects.get().pk,'COMPLETED',actor=self.staff).pk,actor=self.staff)
        payment=create_payment(invoice_id=inv.pk,actor=self.staff,payment_method='CASH',request_key=uuid.uuid4()); self.assertEqual(dict(dict(report_data(self.manager))['Doanh thu Payment SUCCEEDED'])['Thực thu'],0)
        confirm_payment(payment.pk,actor=self.staff); self.assertEqual(dict(dict(report_data(self.manager))['Doanh thu Payment SUCCEEDED'])['Thực thu'],200)

class Module07ChatTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def test_chat_database_idempotency_ownership_history(self):
        conv=create_conversation(actor=self.manager,recipient_id=self.staff.pk); key=uuid.uuid4()
        msg=send_message(actor=self.staff,conversation_id=conv.pk,content='Hello',request_key=key)
        self.assertEqual(send_message(actor=self.staff,conversation_id=conv.pk,content='Hello',request_key=key).pk,msg.pk)
        with self.assertRaises(PermissionDenied): send_message(actor=self.customer,conversation_id=conv.pk,content='Spy',request_key=uuid.uuid4())
        c=Client(); c.force_login(self.customer); self.assertEqual(c.get(reverse('chat_detail',args=[conv.pk])).status_code,404)
        c.force_login(self.staff); self.assertContains(c.get(reverse('chat_detail',args=[conv.pk])),'Hello')
    def test_support_customer_staff_and_escape_content(self):
        conv=create_conversation(actor=self.customer,recipient_id=self.staff.pk); self.assertTrue(conv.is_support)
        send_message(actor=self.customer,conversation_id=conv.pk,content='<script>unsafe</script>',request_key=uuid.uuid4())
        c=Client(); c.force_login(self.staff); self.assertContains(c.get(reverse('chat_detail',args=[conv.pk])),'&lt;script&gt;')
        self.assertEqual(create_conversation(actor=self.customer,recipient_id=self.staff.pk).pk,conv.pk)
    def test_customer_cannot_create_customer_chat_blank_or_fake_owner(self):
        other=User.objects.create_user('othercustomer')
        with self.assertRaises(PermissionDenied): create_conversation(actor=self.customer,recipient_id=other.pk)
        conv=create_conversation(actor=self.manager,recipient_id=self.staff.pk)
        with self.assertRaises(ValidationError): send_message(actor=self.staff,conversation_id=conv.pk,content=' ',request_key=uuid.uuid4())
        c=Client(); c.force_login(self.staff)
        self.assertEqual(c.post(reverse('chat_detail',args=[conv.pk]),{'content':'HTTP','request_key':uuid.uuid4(),'sender':self.customer.pk},HTTP_ACCEPT='application/json').status_code,201)
        self.assertEqual(Message.objects.get().sender_id,self.staff.pk)
    def test_csrf_post_only_message(self):
        conv=create_conversation(actor=self.manager,recipient_id=self.staff.pk)
        c=Client(enforce_csrf_checks=True); c.force_login(self.staff)
        self.assertEqual(c.post(reverse('chat_detail',args=[conv.pk]),{'content':'x','request_key':uuid.uuid4()}).status_code,403)
        self.assertEqual(Message.objects.count(),0)
    def test_chat_older_history_pagination_keeps_ownership(self):
        conv=create_conversation(actor=self.manager,recipient_id=self.staff.pk)
        Message.objects.bulk_create([Message(conversation=conv,sender=self.staff,content=f'History {i}',request_key=uuid.uuid4()) for i in range(51)])
        c=Client();c.force_login(self.staff)
        self.assertContains(c.get(reverse('chat_detail',args=[conv.pk])+'?page=2'),'History 0')
        self.assertNotContains(c.get(reverse('chat_detail',args=[conv.pk])),'History 0')
        c.force_login(self.customer);self.assertEqual(c.get(reverse('chat_detail',args=[conv.pk])+'?page=2').status_code,404)

class Module07CartTransactionTests(Module07Fixtures,TransactionTestCase):
    def setUp(self): self.initialize()
    def test_combo_only_cart_booking_and_public_voucher_pages(self):
        combo=Combo.objects.create(name='Combo only',price=120);ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=2)
        self.promotion();c=Client();c.force_login(self.customer)
        self.assertEqual(c.post(reverse('combo_cart',args=[combo.pk]),{}).status_code,302)
        cart=c.get(reverse('customer_cart'));self.assertContains(cart,'Combo only');self.assertNotContains(cart,'Giỏ món đang chờ bạn')
        self.assertContains(c.get(reverse('customer_booking')),'120')
        data={'name':'Customer','phone':'0912345678','date':str(timezone.localdate()+timedelta(days=2)),'time':'18:00','guests':'2'}
        self.assertEqual(c.post(reverse('customer_booking'),data).status_code,302);self.assertEqual(Booking.objects.get().food_subtotal,120)
        self.assertEqual(c.session.get('combo_cart'),{});self.assertContains(c.get(reverse('customer_offers')),'SAVE')

class Module07ConcurrencyTests(Module07Fixtures,TransactionTestCase):
    def setUp(self): self.initialize(); self.personnel()
    def race(self,fn):
        barrier=Barrier(2)
        def run(i):
            connections.close_all()
            try:
                barrier.wait(timeout=15)
                try: fn(i); return 'ok'
                except ValidationError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(run,[0,1]))
    def test_voucher_last_use_two_orders_one_success(self):
        promo=self.promotion(usage_limit=1); orders=[self.order(customer=self.customer) for i in range(2)]
        result=self.race(lambda i:apply_voucher(orders[i].pk,promo.code,actor=User.objects.get(pk=self.customer.pk)))
        self.assertEqual(sorted(result),['ok','rejected']); promo.refresh_from_db(); self.assertEqual(promo.used_count,1)
    def test_schedule_overlap_concurrent_same_employee_one_success(self):
        def create(i):
            form=ScheduleForm({'employee':self.employee.pk,'shift':self.shift.pk,'work_date':self.day}); assert form.is_valid()
            hr.save_schedule(form,actor=User.objects.get(pk=self.manager.pk))
        result=self.race(create); self.assertEqual(sorted(result),['ok','rejected']); self.assertEqual(WorkSchedule.objects.count(),1)
    def test_payroll_approve_two_connections_one_success(self):
        payroll=hr.calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager)
        result=self.race(lambda i:hr.payroll_state(payroll.pk,'APPROVED',actor=User.objects.get(pk=self.manager.pk)))
        self.assertEqual(sorted(result),['ok','rejected'])

class Module07SocketTests(Module07Fixtures,TransactionTestCase):
    def setUp(self):
        self.initialize(); self.conv=create_conversation(actor=self.manager,recipient_id=self.staff.pk); self.clients={}
        for role in ('manager','staff','customer'):
            c=Client();c.force_login(getattr(self,role)); self.clients[role]=c
    def socket(self,role='staff',origin=b'http://localhost'):
        headers=[(b'origin',origin)]
        if role: headers.append((b'cookie',('sessionid='+self.clients[role].cookies['sessionid'].value).encode()))
        return WebsocketCommunicator(application,f'/ws/chat/{self.conv.pk}/',headers=headers)
    async def test_chat_two_participants_live_and_reconnect_history(self):
        a=self.socket('staff');b=self.socket('manager'); self.assertTrue((await a.connect())[0]);self.assertTrue((await b.connect())[0])
        msg=await database_sync_to_async(send_message)(actor=self.staff,conversation_id=self.conv.pk,content='Realtime',request_key=uuid.uuid4())
        self.assertEqual((await a.receive_json_from())['conversation_id'],self.conv.pk);self.assertEqual((await b.receive_json_from())['type'],'chat.updated')
        await a.disconnect(); a=self.socket();self.assertTrue((await a.connect())[0])
        count=await database_sync_to_async(lambda:Message.objects.filter(conversation=self.conv).count())(); self.assertEqual(count,1)
        await a.disconnect();await b.disconnect()
    async def test_chat_nonparticipant_anonymous_origin_and_read_only(self):
        for role in ('customer',None):
            s=self.socket(role);self.assertFalse((await s.connect())[0]);await s.disconnect()
        s=self.socket(origin=b'http://evil.example');self.assertFalse((await s.connect())[0]);await s.disconnect()
        s=self.socket();self.assertTrue((await s.connect())[0]);await s.send_json_to({'content':'WS write'})
        self.assertEqual((await s.receive_output())['code'],4400);await s.disconnect()
        self.assertEqual(await database_sync_to_async(Message.objects.count)(),0)
    async def test_chat_revoked_participation_closes_before_next_event(self):
        s=self.socket();self.assertTrue((await s.connect())[0])
        await database_sync_to_async(lambda:ConversationParticipant.objects.filter(conversation=self.conv,user=self.staff).delete())()
        await database_sync_to_async(send_message)(actor=self.manager,conversation_id=self.conv.pk,content='Private',request_key=uuid.uuid4())
        self.assertEqual((await s.receive_output())['code'],4403);await s.disconnect()
    def test_chat_only_commit_rollback_no_message_event(self):
        with patch('customers.chat_service.broadcast') as broadcast:
            with self.assertRaises(RuntimeError),transaction.atomic():
                send_message(actor=self.staff,conversation_id=self.conv.pk,content='Rollback',request_key=uuid.uuid4());raise RuntimeError
            broadcast.assert_not_called();self.assertEqual(Message.objects.count(),0)

class Module07MigrationTests(TransactionTestCase):
    def test_selection_keys_backfill_preserves_combo_snapshots(self):
        from django.db.migrations.executor import MigrationExecutor
        target=[('customers','0014_attendance_combo_comboitem_conversation_and_more')]
        executor=MigrationExecutor(connection);executor.migrate(target)
        try:
            old=executor.loader.project_state(target).apps
            user=old.get_model('auth','User').objects.create(username='selection-legacy')
            category=old.get_model('customers','Category').objects.create(name='Migration',slug='migration')
            menu=old.get_model('customers','MenuItem').objects.create(name='Migration dish',category=category,price=10,image='unchanged.jpg')
            booking=old.get_model('customers','Booking').objects.create(user=user,name='Legacy',phone='0912345678',date=timezone.localdate(),time=time(18),guests=2,food_subtotal=20)
            saved=[];selection=str(uuid.uuid4())
            for n in range(2):
                extras={'combo':{'selection_id':selection,'portion':n,'name':'Saved combo','price':'20.00'}}
                line=old.get_model('customers','BookingItem').objects.create(booking=booking,menu_item=menu,item_name='Saved name',quantity=1,unit_price=10,line_total=10,extras=extras)
                saved.append((line.pk,extras))
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
            for pk,extras in saved:
                line=BookingItem.objects.get(pk=pk);self.assertEqual(line.extras,extras);self.assertEqual(line.item_name,'Saved name');self.assertEqual(line.unit_price,10)
                self.assertEqual(line.selection_key,f'{selection}:{extras["combo"]["portion"]}')
        finally:
            restore=MigrationExecutor(connection);restore.migrate(restore.loader.graph.leaf_nodes())
