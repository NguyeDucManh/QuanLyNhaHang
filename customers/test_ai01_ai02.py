import json,random,uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.core.exceptions import ValidationError,PermissionDenied
from django.core.management import call_command,CommandError
from django.test import TestCase,Client,TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from django.db import connections,transaction
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from .test_module07 import Module07Fixtures
from .test_business import BusinessData
from .models import *
from .rbac import assign_role
from .management.commands.seed_initial_inventory import REQUEST_KEY,MARKER
from .order_service import transition_order,create_order
from .kitchen_service import transition_kitchen_item
from .ga_service import load_problem,run_ga,initialize_population,fitness,repair,evaluate_chromosome,save_proposal,crossover,mutation
from .module07_forms import ScheduleForm
from .personnel_service import save_schedule,schedule_state
from .recommendation_service import item_vectors,recommend,user_profile,purchase_history,precision_recall_at_k,evaluate_recommendations

class InitialInventoryTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def seed(self):call_command('seed_initial_inventory',stdout=StringIO())
    def test_receipt_movements_balances_low_stock_and_exact_rerun(self):
        for name in ('Bơ','Chanh dây','Nấm'):Ingredient.objects.create(code='LOW'+str(Ingredient.objects.count()),name=name,unit='kg',minimum_stock=1)
        self.seed();receipt=StockReceipt.objects.get(request_key=REQUEST_KEY);self.assertEqual(receipt.status,'CONFIRMED')
        self.assertEqual(receipt.items.count(),Ingredient.objects.count());self.assertEqual(StockMovement.objects.filter(receipt=receipt).count(),receipt.items.count())
        for m in StockMovement.objects.all():self.assertEqual(m.stock_before+m.quantity,m.stock_after);self.assertEqual(m.movement_type,'IMPORT')
        from django.db.models import F
        self.assertEqual(Ingredient.objects.filter(current_stock__lte=F('minimum_stock')).count(),3)
        models=[Ingredient,StockReceipt,StockReceiptItem,StockMovement];before=[list(m.objects.order_by('pk').values()) for m in models]
        self.seed();self.assertEqual([list(m.objects.order_by('pk').values()) for m in models],before)
    def test_manual_receipts_not_overwritten_and_stock_not_reset(self):
        self.import_stock(10);before=list(StockMovement.objects.order_by('pk').values());self.seed()
        self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,10)
        self.assertEqual(list(StockMovement.objects.filter(pk__in=[r['id'] for r in before]).order_by('pk').values()),before)
        self.assertEqual(StockReceipt.objects.count(),2)
    def test_ready_uses_seed_stock_once_and_no_negative(self):
        self.seed();RecipeIngredient.objects.create(menu_item=self.menu,ingredient=self.fish,quantity_required=Decimal('.25'))
        order=self.order();transition_order(order.pk,'CONFIRMED',actor=self.staff);line=order.items.get()
        transition_kitchen_item(order.pk,line.pk,'PREPARING',actor=self.staff);transition_kitchen_item(order.pk,line.pk,'READY',actor=self.staff)
        self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,Decimal('4.5'))
        with self.assertRaises(ValidationError):transition_kitchen_item(order.pk,line.pk,'READY',actor=self.staff)
        self.seed();self.fish.refresh_from_db();self.assertEqual(self.fish.current_stock,Decimal('4.5'))
        self.assertEqual(StockMovement.objects.filter(order_item=line).count(),1)
    def test_no_supplier_rollback_and_same_key_manual_draft_not_touched(self):
        Supplier.objects.all().update(is_active=False)
        with self.assertRaises(CommandError):self.seed()
        self.assertFalse(StockReceipt.objects.exists());self.assertFalse(Ingredient.objects.exclude(current_stock=0).exists())
        Supplier.objects.all().update(is_active=True)
        self.receipt(request_key=REQUEST_KEY,note='Manual data')
        with self.assertRaises(CommandError):self.seed()
        self.assertEqual(StockReceipt.objects.get().status,'DRAFT')

class GATests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        self.personnel();self.start=timezone.localdate()+timedelta(days=2);self.end=self.start+timedelta(days=2)
    def problem(self):return load_problem(self.start,self.end)
    def result(self,problem=None):return run_ga(problem or self.problem(),population_size=8,generations=8,random_seed=123)
    def test_population_fitness_missing_hard_and_genetic_operators(self):
        problem=self.problem();pop=initialize_population(problem,8,random.Random(1));self.assertEqual(len(pop),8)
        self.assertEqual(fitness(problem,(None,)*len(problem.seats)),-30000)
        self.assertEqual(evaluate_chromosome(problem,(999999,)*3)['hard_violations'],3)
        self.assertTrue(all(evaluate_chromosome(problem,c)['hard_violations']==0 for c in pop))
        left,right=crossover((1,2,3),(4,5,6),random.Random(4),1);self.assertEqual(len(left),3);self.assertNotEqual(left,(1,2,3))
        self.assertEqual(mutation((1,2),[1,2],random.Random(0),0),(1,2))
    def test_reproducible_trace_coverage_elitism_no_preview_writes(self):
        problem=self.problem();one=self.result(problem);two=self.result(problem)
        self.assertEqual(one,two);self.assertEqual(one['metrics']['hard_violations'],0);self.assertEqual(one['metrics']['full_shifts'],3)
        self.assertEqual(WorkSchedule.objects.count(),0)
        scores=[r['best'] for r in one['trace']];self.assertEqual(scores,sorted(scores))
    def test_inactive_employee_and_shift_not_assigned(self):
        self.employee.is_active=False;self.employee.save();result=self.result();self.assertEqual(result['rows'],[]);self.assertEqual(result['metrics']['missing_seats'],3)
        self.employee.is_active=True;self.employee.save();self.shift.is_active=False;self.shift.save();self.assertEqual(self.result()['rows'],[])
    def test_overlapping_shifts_and_overnight_repair_never_overlap(self):
        from datetime import time
        Shift.objects.create(name='Overlap',start_time=time(12),end_time=time(20),required_staff=1)
        Shift.objects.create(name='Night',start_time=time(22),end_time=time(9),required_staff=1)
        problem=self.problem();result=self.result(problem);self.assertEqual(result['metrics']['hard_violations'],0);self.assertGreater(result['metrics']['short_shifts'],0)
        assignments=[]
        from .ga_service import shift_window
        for row in result['rows']:
            from datetime import date
            begin,end=shift_window(date.fromisoformat(row['work_date']),problem.shifts[row['shift_id']])
            self.assertFalse(any(a<end and b>begin for a,b in assignments));assignments.append((begin,end))
    def test_existing_approved_counts_coverage_draft_blocks_and_required_staff(self):
        form=ScheduleForm({'employee':self.employee.pk,'shift':self.shift.pk,'work_date':self.start});self.assertTrue(form.is_valid())
        old=save_schedule(form,actor=self.manager);problem=self.problem();self.assertEqual(self.result(problem)['metrics']['short_shifts'],1)
        schedule_state(old.pk,'APPROVED',actor=self.manager);problem=self.problem();self.assertEqual(len(problem.seats),2);self.assertEqual(self.result(problem)['metrics']['full_shifts'],3)
        self.shift.required_staff=2;self.shift.save();self.assertGreater(self.result()['metrics']['missing_seats'],0)
    def test_save_ai_draft_approve_and_edit_preserves_ai_origin(self):
        result=self.result();rows=save_proposal(result,actor=self.manager);self.assertEqual(len(rows),3)
        self.assertTrue(all(r.source=='AI' and r.status=='DRAFT' and r.approved_by is None for r in rows))
        row=rows[0];form=ScheduleForm({'employee':row.employee_id,'shift':row.shift_id,'work_date':row.work_date,'note':'Edited'},instance=row)
        self.assertTrue(form.is_valid());row=save_schedule(form,actor=self.manager);self.assertEqual(row.source,'AI')
        row=schedule_state(row.pk,'APPROVED',actor=self.manager);self.assertEqual(row.approved_by_id,self.manager.pk)
        self.assertEqual(WorkSchedule.objects.filter(status='APPROVED').count(),1)
        with self.assertRaises(ValidationError):save_proposal(result,actor=self.manager)
    def test_stale_preview_roster_changes_rejected_and_atomic_bad_row(self):
        result=self.result();self.shift.required_staff=2;self.shift.save()
        with self.assertRaises(ValidationError):save_proposal(result,actor=self.manager)
        self.shift.required_staff=1;self.shift.save();result=self.result();result['rows'].append(result['rows'][0].copy())
        with self.assertRaises(ValidationError):save_proposal(result,actor=self.manager)
        self.assertEqual(WorkSchedule.objects.count(),0)
    def test_soft_fairness_rest_weights_and_payroll_freeze(self):
        for i in range(2):
            u=User.objects.create_user('ga-staff-'+str(i));assign_role(u,'STAFF');Employee.objects.create(user=u,employee_code='GA'+str(i),full_name='GA fixture',position=self.position,hire_date=self.day)
        p=self.problem();ids=list(p.employees);concentrated=(ids[0],)*3;balanced=tuple(ids)
        self.assertGreater(fitness(p,balanced),fitness(p,concentrated))
        from .personnel_service import calculate_payroll,payroll_state
        # Cover the proposal range explicitly, including near month boundaries.
        self.period.start_date=self.start;self.period.end_date=self.end
        self.period.save(update_fields=['start_date','end_date'])
        payroll=calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager);payroll_state(payroll.pk,'APPROVED',actor=self.manager)
        self.assertFalse(any(r['employee_id']==self.employee.pk for r in self.result()['rows']))
    def test_payroll_freeze_does_not_block_days_outside_period(self):
        from .personnel_service import calculate_payroll,payroll_state
        self.period.start_date=self.start;self.period.end_date=self.start
        self.period.save(update_fields=['start_date','end_date'])
        payroll=calculate_payroll(self.employee.pk,self.period.pk,actor=self.manager)
        payroll_state(payroll.pk,'APPROVED',actor=self.manager)
        rows=[r for r in self.result()['rows'] if r['employee_id']==self.employee.pk]
        self.assertTrue(rows)
        self.assertTrue(all(r['work_date']>self.start.isoformat() for r in rows))
    def test_http_preview_no_writes_server_owned_save_post_csrf_rbac(self):
        for u in (self.customer,self.staff):
            c=Client();c.force_login(u);self.assertEqual(c.get(reverse('ai_schedules')).status_code,403)
        c=Client();c.force_login(self.manager)
        data={'action':'preview','start_date':str(self.start),'end_date':str(self.end),'population_size':8,'generations':8,'mutation_rate':.1,'crossover_rate':.8,'random_seed':123}
        self.assertEqual(c.post(reverse('ai_schedules'),data).status_code,200);self.assertEqual(WorkSchedule.objects.count(),0)
        self.assertEqual(c.post(reverse('ai_schedules'),{'action':'save','source':'MANUAL','status':'APPROVED','employee':self.customer.pk}).status_code,302)
        self.assertEqual(WorkSchedule.objects.filter(source='AI',status='DRAFT').count(),3)
        secured=Client(enforce_csrf_checks=True);secured.force_login(self.manager);self.assertEqual(secured.post(reverse('ai_schedules'),data).status_code,403)
    def test_limits_and_past_dates_invalid(self):
        with self.assertRaises(ValidationError):load_problem(self.start,self.start+timedelta(days=14))
        with self.assertRaises(ValidationError):run_ga(self.problem(),population_size=201)

class RecommendationTests(BusinessData,TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.initialize()
        cls.second.category=cls.menu.category;cls.second.price=100;cls.second.save()
        cls.third=MenuItem.objects.get(pk=3);cls.third.category=cls.menu.category;cls.third.price=100;cls.third.save()
        for menu in (cls.menu,cls.second,cls.third):RecipeIngredient.objects.create(menu_item=menu,ingredient=cls.fish,quantity_required=Decimal('.25'))
    def completed(self,menu=None,customer=None):
        self.import_stock(10)
        order=self.order(customer=customer or self.customer,items=[{'menu_item':menu or self.menu,'quantity':1}]);self.prepare(order)
        return transition_order(order.pk,'COMPLETED',actor=self.admin)
    def test_vectors_real_category_price_ingredient_and_cosine(self):
        from sklearn.metrics.pairwise import cosine_similarity
        items,frame,matrix,encoder=item_vectors();self.assertEqual(len(frame),45);self.assertIn('ingredients',frame)
        indexes={m.pk:i for i,m in enumerate(items)}
        self.assertIn(f'ingredient:{self.fish.pk}',encoder.get_feature_names_out())
        self.assertAlmostEqual(cosine_similarity(matrix[indexes[1]],matrix[indexes[1]])[0,0],1)
        self.assertAlmostEqual(cosine_similarity(matrix[indexes[1]],matrix[indexes[2]])[0,0],1)
    def test_history_personalized_frequency_own_profile_avoid_seen(self):
        self.completed();result=recommend(self.customer,n=2)
        self.assertEqual(result['mode'],'personalized');self.assertEqual(result['recommendations'][0]['item'].pk,2)
        self.assertNotIn(1,[r['item'].pk for r in result['recommendations']])
        other=User.objects.create_user('another-customer');self.assertEqual(recommend(other,n=2)['mode'],'cold_start')
    def test_cancelled_orders_items_not_profile_or_popularity(self):
        order=self.order(customer=self.customer);transition_order(order.pk,'CANCELLED',actor=self.admin)
        self.assertEqual(purchase_history(self.customer.pk),{})
        self.import_stock();order=self.order(customer=self.customer,items=[{'menu_item':self.menu,'quantity':1},{'menu_item':self.third,'quantity':1}])
        transition_order(order.pk,'CONFIRMED',actor=self.admin)
        line=order.items.get(menu_item=self.third);transition_kitchen_item(order.pk,line.pk,'CANCELLED',actor=self.admin)
        line=order.items.get(menu_item=self.menu);transition_kitchen_item(order.pk,line.pk,'PREPARING',actor=self.admin);transition_kitchen_item(order.pk,line.pk,'READY',actor=self.admin);transition_order(order.pk,'COMPLETED',actor=self.admin)
        self.assertEqual(purchase_history(self.customer.pk),{1:1})
    def test_cold_start_sales_real_and_active_valid_filter(self):
        self.completed();result=recommend(None,n=4);self.assertEqual(result['recommendations'][0]['item'].pk,1);self.assertIsNone(result['recommendations'][0]['score'])
        self.menu.is_available=False;self.menu.save();self.second.price=None;self.second.save()
        output=recommend(None,n=20);self.assertNotIn(1,[r['item'].pk for r in output['recommendations']]);self.assertNotIn(2,[r['item'].pk for r in output['recommendations']])
    def test_inactive_category_never_recommended_empty_catalog(self):
        self.menu.category.is_active=False;self.menu.category.save()
        result=recommend(None,n=20);self.assertTrue(all(r['item'].category.is_active for r in result['recommendations']))
        MenuItem.objects.all().update(is_available=False);self.assertEqual(recommend(None)['recommendations'],[])
    def test_precision_recall_fixture_and_real_data_insufficient(self):
        metrics=precision_recall_at_k([1,2,3],{2,3,4},3);self.assertAlmostEqual(metrics['precision'],2/3);self.assertAlmostEqual(metrics['recall'],2/3)
        self.completed();evaluation=evaluate_recommendations();self.assertFalse(evaluation['available']);self.assertIsNone(evaluation['precision'])
    def test_chronological_evaluation_fixture_excludes_heldout_ratings(self):
        self.completed();self.completed(self.third);held=self.completed(self.second)
        result=evaluate_recommendations(k=1);self.assertTrue(result['available']);self.assertEqual(result['users'],1);self.assertEqual(result['precision'],1)
        Review.objects.create(customer=self.customer,order=held,menu_item=self.second,rating=1)
        self.assertEqual(evaluate_recommendations(k=1),result)
    def test_public_no_technical_scores_or_client_customer_override_manager_only(self):
        self.completed();c=Client();c.force_login(self.customer)
        response=c.get(reverse('customer_home'));self.assertContains(response,'Gợi ý dành cho bạn');self.assertNotContains(response,'cosine_similarity');self.assertNotContains(response,'similarity score')
        self.assertEqual(c.get('/management/recommendations/').status_code,404)
        self.assertEqual(c.get(reverse('customer_recommendations')+'?customer='+str(self.manager.pk)).status_code,200)
        c.force_login(self.staff);self.assertEqual(c.get('/management/recommendations/').status_code,404)
        c.force_login(self.manager);self.assertEqual(c.get('/management/recommendations/').status_code,404)

class AISaveConcurrencyTests(Module07Fixtures,TransactionTestCase):
    def setUp(self):self.initialize();self.personnel()
    def test_two_saves_of_same_preview_one_batch_no_duplicate(self):
        day=timezone.localdate()+timedelta(days=2);proposal=run_ga(load_problem(day,day),population_size=4,generations=2,random_seed=1);barrier=Barrier(2)
        def save(i):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:save_proposal(proposal,actor=User.objects.get(pk=self.manager.pk));return 'ok'
                except ValidationError:return 'stale'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,[0,1]))
        self.assertEqual(sorted(results),['ok','stale']);self.assertEqual(WorkSchedule.objects.count(),1)
