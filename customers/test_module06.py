"""Per-item atomic inventory consumption, ledger, permissions and migration."""
import uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,IntegrityError,connection,connections
from django.test import TestCase,TransactionTestCase,Client
from django.urls import reverse
from django.utils import timezone
from .test_business import BusinessData
from .models import Ingredient,RecipeIngredient,OrderItem,StockMovement,StockReceipt,StockIssue,Supplier,Order
from .business_forms import IngredientForm,RecipeForm,SupplierForm
from .order_service import transition_order
from .kitchen_service import transition_kitchen_item
from .inventory_service import create_document,confirm_document,save_recipe,consume_order


class InventoryFixtures(BusinessData):
    def cooking(self,menu=None,quantity=2):
        order=self.order(items=[{'menu_item':menu or self.menu,'quantity':quantity}])
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        item=order.items.get(); transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
        return order,item
    def recipe(self,menu=None,ingredient=None,quantity='.25'):
        return RecipeIngredient.objects.create(menu_item=menu or self.menu,ingredient=ingredient or self.fish,quantity_required=Decimal(quantity))
    def ready(self,order,item,actor=None):
        return transition_kitchen_item(order.pk,item.pk,'READY',actor=actor or self.staff)


class Module06Tests(InventoryFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_supplier_contact_and_disable_preserves_protected_documents(self):
        doc=self.receipt()
        form=SupplierForm({'code':self.supplier.code,'name':'Supplier updated','contact_name':'Người liên hệ','phone':'0912345678','email':'test@example.test','address':'Address'},instance=self.supplier)
        self.assertTrue(form.is_valid()); form.save(); self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.contact_name,'Người liên hệ'); self.assertFalse(self.supplier.is_active)
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError): self.supplier.delete()
        with self.assertRaises(ValidationError): self.receipt()
        self.assertTrue(StockReceipt.objects.filter(pk=doc.pk).exists())

    def test_stock_minimum_and_recipe_constraints(self):
        self.assertFalse(IngredientForm({'code':'BAD','name':'Bad','unit':'kg','minimum_stock':'-1'}).is_valid())
        for field in ('current_stock','minimum_stock'):
            with self.assertRaises(IntegrityError),transaction.atomic(): Ingredient.objects.filter(pk=self.fish.pk).update(**{field:-1})
        self.recipe()
        for quantity in ('0','-1'):
            with self.assertRaises(IntegrityError),transaction.atomic(): RecipeIngredient.objects.create(menu_item=self.second,ingredient=self.fish,quantity_required=quantity)
        with self.assertRaises(IntegrityError),transaction.atomic(): self.recipe()

    def test_ready_multiplies_recipe_qty_and_writes_ledger(self):
        self.import_stock(2); self.recipe(); order,item=self.cooking(quantity=3)
        item=self.ready(order,item); self.fish.refresh_from_db()
        self.assertEqual(self.fish.current_stock,Decimal('1.250'))
        movement=StockMovement.objects.get(order_item=item)
        self.assertEqual((movement.quantity,movement.stock_before,movement.stock_after),(Decimal('.750'),Decimal('2'),Decimal('1.250')))
        self.assertEqual((movement.order_id,movement.created_by_id),(order.pk,self.staff.pk))
        self.assertEqual((movement.reference_type,movement.reference_id),('ORDER_ITEM',item.pk))
        self.assertIn(f'ITEM-{item.pk}',movement.reference)
        self.assertEqual(item.inventory_status,'DEDUCTED'); self.assertEqual(item.inventory_processed_at,item.ready_at)

    def test_retry_ready_and_order_completion_never_deduct_twice(self):
        self.import_stock(1); self.recipe(); order,item=self.cooking(); self.ready(order,item)
        with self.assertRaises(ValidationError): self.ready(order,item)
        transition_order(order.pk,'COMPLETED',actor=self.staff)
        with self.assertRaises(ValidationError): self.ready(order,item)
        with self.assertRaises(ValidationError): consume_order(order,self.admin)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('.5'))
        self.assertEqual(StockMovement.objects.filter(order_item=item).count(),1)

    def test_same_ingredient_two_items_same_order_have_separate_ledger(self):
        self.import_stock(2); self.recipe(); self.recipe(menu=self.second,quantity='.1')
        order=self.order(items=[{'menu_item':self.menu,'quantity':2},{'menu_item':self.second,'quantity':3}])
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        for item in order.items.all():
            transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff); self.ready(order,item)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('1.2'))
        self.assertEqual(StockMovement.objects.filter(order=order).count(),2)

    def test_missing_one_ingredient_rolls_back_state_stock_ledger_and_event(self):
        self.import_stock(1); self.recipe(); self.recipe(ingredient=self.butter,quantity='.02')
        order,item=self.cooking()
        with patch('customers.realtime.broadcast_order') as broadcast:
            with self.assertRaises(ValidationError): self.ready(order,item)
            self.assertEqual(broadcast.call_count,0)
        item.refresh_from_db(); self.fish.refresh_from_db(); self.butter.refresh_from_db()
        self.assertEqual((self.fish.current_stock,self.butter.current_stock),(1,0))
        self.assertEqual((item.kitchen_status,item.inventory_status),('PREPARING','NOT_PROCESSED'))
        self.assertIsNone(item.inventory_processed_at); self.assertIsNone(item.ready_at)
        self.assertFalse(StockMovement.objects.filter(order_item=item).exists())

    def test_inactive_ingredient_rejects_ready_without_partial_deduction(self):
        self.import_stock(1); self.recipe(); Ingredient.objects.filter(pk=self.fish.pk).update(is_active=False)
        order,item=self.cooking()
        with self.assertRaises(ValidationError): self.ready(order,item)
        item.refresh_from_db(); self.assertEqual(item.kitchen_status,'PREPARING')

    def test_no_recipe_ready_records_warning_no_guessing_or_retroactive_deduction(self):
        self.import_stock(1); order,item=self.cooking(); item=self.ready(order,item)
        self.assertEqual(item.inventory_status,'NO_RECIPE'); self.assertIsNotNone(item.inventory_processed_at)
        self.assertFalse(StockMovement.objects.filter(order_item=item).exists())
        self.recipe()
        with self.assertRaises(ValidationError): self.ready(order,item)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,1)
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse('admin_order_detail',args=[order.pk])),'Chưa có công thức')

    def test_cancelled_draft_queued_do_not_consume(self):
        self.import_stock(1); self.recipe(); order=self.order(); item=order.items.get()
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        transition_kitchen_item(order.pk,item.pk,'CANCELLED',actor=self.staff)
        with self.assertRaises(ValidationError): self.ready(order,item)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,1)
        self.assertFalse(StockMovement.objects.filter(order_item=item).exists())

    def test_recipe_edit_after_ready_keeps_original_movement(self):
        self.import_stock(1); line=self.recipe(); order,item=self.cooking(); self.ready(order,item)
        form=RecipeForm({'menu_item':self.menu.pk,'ingredient':self.fish.pk,'quantity_required':'.4'},instance=line)
        self.assertTrue(form.is_valid()); save_recipe(form)
        self.assertEqual(StockMovement.objects.get(order_item=item).quantity,Decimal('.5'))

    def test_receipt_and_issue_retries_once_reason_and_balances(self):
        receipt=self.receipt(2); confirm_document(receipt.pk,kind='receipt',actor=self.manager); confirm_document(receipt.pk,kind='receipt',actor=self.manager)
        issue=self.issue('.75',reason='Sơ chế hao hụt'); confirm_document(issue.pk,kind='issue',actor=self.manager); confirm_document(issue.pk,kind='issue',actor=self.manager)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('1.25'))
        self.assertEqual(StockMovement.objects.filter(receipt=receipt).count(),1)
        movement=StockMovement.objects.get(issue=issue); self.assertEqual((movement.stock_before,movement.stock_after),(Decimal('2'),Decimal('1.25')))
        self.assertEqual(issue.reason,'Sơ chế hao hụt'); self.assertEqual(movement.reference_type,'STOCK_ISSUE')

    def test_issue_overdraw_rolls_back_all_and_keeps_draft(self):
        self.import_stock(1); issue=self.issue(items=[{'ingredient':self.fish,'quantity':'.5'},{'ingredient':self.butter,'quantity':1}])
        with self.assertRaises(ValidationError): confirm_document(issue.pk,kind='issue',actor=self.manager)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,1)
        issue.refresh_from_db(); self.assertEqual(issue.status,'DRAFT'); self.assertFalse(StockMovement.objects.filter(issue=issue).exists())

    def test_per_item_duplicate_movement_database_constraint(self):
        self.import_stock(1); self.recipe(); order,item=self.cooking(); self.ready(order,item)
        with self.assertRaises(IntegrityError),transaction.atomic(): StockMovement.objects.create(ingredient=self.fish,movement_type='ORDER_USAGE',quantity='.1',stock_before='.5',stock_after='.4',order=order,order_item=item,reference='duplicate',created_by=self.admin)

    def test_supplier_ingredient_recipe_stock_pages_real_filters_and_permissions(self):
        self.import_stock(3)
        urls=[reverse('admin_suppliers'),reverse('admin_ingredients'),reverse('admin_recipes'),reverse('admin_transactions'),reverse('admin_stock_alerts')]
        for actor in (self.admin,self.manager):
            self.client.force_login(actor)
            for url in urls: self.assertEqual(self.client.get(url).status_code,200)
            self.assertContains(self.client.get(reverse('admin_recipes')),self.menu.name)
        for actor in (self.staff,self.customer):
            self.client.force_login(actor)
            for url in urls: self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.manager)
        all_rows=self.client.get(reverse('admin_stock_alerts'),{'state':''}).context['rows']
        low=self.client.get(reverse('admin_stock_alerts'),{'state':'low'}).context['rows']
        out=self.client.get(reverse('admin_stock_alerts'),{'state':'out'}).context['rows']
        self.assertEqual((len(all_rows),len(low),len(out)),(2,1,1))
        Ingredient.objects.filter(pk=self.fish.pk).update(current_stock=1)
        self.assertEqual(len(self.client.get(reverse('admin_stock_alerts'),{'state':'low'}).context['rows']),2)

    def test_no_staff_stock_crud_but_staff_can_consume_via_kitchen(self):
        for actor in (self.staff,self.customer):
            with self.assertRaises(PermissionDenied): self.receipt(actor=actor)
        doc=self.receipt()
        with self.assertRaises(PermissionDenied): confirm_document(doc.pk,kind='receipt',actor=self.staff)
        self.import_stock(1); self.recipe(); order,item=self.cooking(); self.assertEqual(self.ready(order,item).inventory_status,'DEDUCTED')

    def test_csrf_and_http_cannot_set_stock_or_inventory_flags(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('business_edit',args=['ingredient',self.fish.pk]),{'code':self.fish.code,'name':'Fish','unit':'kg','minimum_stock':1,'is_active':'on','current_stock':999})
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,0)
        protected=Client(enforce_csrf_checks=True); protected.force_login(self.manager)
        doc=self.receipt(); url=reverse('admin_stock_confirm',args=['receipt',doc.pk])
        self.assertEqual(protected.get(url).status_code,405); self.assertEqual(protected.post(url).status_code,403)
        order,item=self.cooking()
        self.client.post(reverse('admin_kitchen_item_status',args=[order.pk,item.pk]),{'status':'READY','inventory_status':'DEDUCTED','inventory_processed_at':'2099-01-01'})
        item.refresh_from_db(); self.assertEqual(item.inventory_status,'NO_RECIPE')


class Module06ConcurrencyTests(InventoryFixtures,TransactionTestCase):
    def setUp(self): self.initialize()
    def race(self,callbacks):
        barrier=Barrier(2)
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10); callbacks[index](User.objects.get(pk=self.staff.pk)); return 'ok'
            except ValidationError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(worker,[0,1]))

    def test_two_different_menus_shared_ingredient_no_lost_update(self):
        self.import_stock(1); self.recipe(); self.recipe(menu=self.second)
        pairs=[self.cooking(self.menu),self.cooking(self.second)]
        callbacks=[lambda actor,o=o,i=i:self.ready(o,i,actor) for o,i in pairs]
        self.assertEqual(self.race(callbacks),['ok','ok'])
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,0)
        self.assertEqual(StockMovement.objects.filter(movement_type='ORDER_USAGE').count(),2)
        self.assertEqual(sorted(StockMovement.objects.filter(movement_type='ORDER_USAGE').values_list('stock_before','stock_after')),[(Decimal('.5'),Decimal('0')),(Decimal('1'),Decimal('.5'))])

    def test_two_different_menus_insufficient_for_both_one_rejected(self):
        self.import_stock('.5'); self.recipe(); self.recipe(menu=self.second)
        pairs=[self.cooking(self.menu),self.cooking(self.second)]
        self.assertCountEqual(self.race([lambda actor,o=o,i=i:self.ready(o,i,actor) for o,i in pairs]),['ok','rejected'])
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,0)
        self.assertEqual(OrderItem.objects.filter(kitchen_status='READY').count(),1)
        self.assertEqual(OrderItem.objects.filter(kitchen_status='PREPARING').count(),1)

    def test_same_item_concurrent_ready_deducts_once(self):
        self.import_stock(1); self.recipe(); order,item=self.cooking()
        self.assertCountEqual(self.race([lambda actor:self.ready(order,item,actor)]*2),['ok','rejected'])
        self.assertEqual(StockMovement.objects.filter(order_item=item).count(),1)
        self.fish.refresh_from_db(); self.assertEqual(self.fish.current_stock,Decimal('.5'))


class Module06MigrationTests(TransactionTestCase):
    def test_ready_legacy_marked_without_retroactive_movement_or_money_changes(self):
        from django.db.migrations.executor import MigrationExecutor
        old_target=[('customers','0012_remove_invoice_invoice_amounts_status_valid_and_more')]
        executor=MigrationExecutor(connection); executor.migrate(old_target)
        try:
            old=executor.loader.project_state(old_target).apps
            user=old.get_model('auth','User').objects.create(username='legacy-inventory')
            category=old.get_model('customers','Category').objects.create(name='Legacy',slug='legacy')
            menu=old.get_model('customers','MenuItem').objects.create(name='Legacy item',category=category)
            order=old.get_model('customers','Order').objects.create(created_by_id=user.pk,status='COMPLETED',subtotal=100,discount_amount=0,total_amount=100)
            now=timezone.now()
            item=old.get_model('customers','OrderItem').objects.create(order=order,menu_item=menu,item_name='Original',quantity=1,unit_price=100,line_total=100,kitchen_status='READY',queued_at=now,preparing_at=now,ready_at=now)
            executor=MigrationExecutor(connection); executor.migrate(executor.loader.graph.leaf_nodes())
            current=OrderItem.objects.get(pk=item.pk)
            self.assertEqual((current.inventory_status,current.ready_at,current.line_total),('LEGACY',now,100))
            self.assertIsNone(current.inventory_processed_at); self.assertFalse(StockMovement.objects.exists())
            self.assertEqual(Order.objects.get(pk=order.pk).status,'COMPLETED')
        finally:
            restore=MigrationExecutor(connection); restore.migrate(restore.loader.graph.leaf_nodes())
