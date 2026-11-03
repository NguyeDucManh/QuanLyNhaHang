"""Kitchen lifecycle, serving additions, HTTP protection and real PostgreSQL races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
from unittest.mock import patch
from datetime import timedelta, time
from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, connections, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Order, OrderItem, BookingItem, MenuItem, Ingredient, StockMovement, Invoice, Payment
from .test_module03 import OrderFixtures
from .order_service import transition_order, add_order_item, update_order_item, remove_order_item
from .kitchen_service import transition_kitchen_item, send_order_to_kitchen, TRANSITIONS


class KitchenFixtures(OrderFixtures):
    def confirmed(self):
        order=self.open(); transition_order(order.pk,'CONFIRMED',actor=self.staff)
        return Order.objects.get(pk=order.pk)

    def ready(self,order):
        for item in order.items.exclude(kitchen_status='CANCELLED'):
            transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
            transition_kitchen_item(order.pk,item.pk,'READY',actor=self.staff)


class Module04ServiceTests(KitchenFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_new_preorder_and_direct_draft_null_times(self):
        order=self.open(); direct=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        for line in order.items.all():
            self.assertEqual((line.kitchen_status,line.queued_at,line.preparing_at,line.ready_at),('DRAFT',None,None,None))
        self.assertEqual(direct.source,'DIRECT')

    def test_confirm_queues_all_drafts_and_preserves_snapshots(self):
        order=self.open(); original=[(i.item_name,i.unit_price,i.quantity,i.line_total) for i in order.items.order_by('pk')]
        before=timezone.now(); transition_order(order.pk,'CONFIRMED',actor=self.staff)
        for line,values in zip(order.items.order_by('pk'),original):
            self.assertEqual(line.kitchen_status,'QUEUED'); self.assertGreaterEqual(line.queued_at,before)
            self.assertEqual((line.item_name,line.unit_price,line.quantity,line.line_total),values)
        self.assertEqual(len(set(order.items.values_list('queued_at',flat=True))),1)

    def test_confirmation_queue_failure_rolls_back_everything(self):
        order=self.open()
        from . import kitchen_service
        original=kitchen_service.change_item_state
        calls=[]
        def fail_second(item,status,**kwargs):
            calls.append(item.pk)
            if len(calls)==2: raise ValidationError('forced queue failure')
            return original(item,status,**kwargs)
        with patch.object(kitchen_service,'change_item_state',side_effect=fail_second),self.assertRaises(ValidationError): transition_order(order.pk,'CONFIRMED',actor=self.staff)
        order.refresh_from_db(); self.assertEqual(order.status,'PENDING')
        self.assertEqual(order.items.filter(kitchen_status='DRAFT',queued_at=None).count(),2)

    def test_kitchen_lifecycle_sets_times_and_auto_prepares_order(self):
        order=self.confirmed(); item=order.items.first(); number=order.order_number
        queued=item.queued_at
        item=transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
        self.assertGreaterEqual(item.preparing_at,queued)
        order.refresh_from_db(); self.assertEqual(order.status,'PREPARING')
        prepared=item.preparing_at
        item=transition_kitchen_item(order.pk,item.pk,'READY',actor=self.manager)
        self.assertGreaterEqual(item.ready_at,prepared); self.assertEqual(item.queued_at,queued)
        order.refresh_from_db(); self.assertEqual(order.order_number,number)
        self.assertEqual(order.items.exclude(pk=item.pk).get().kitchen_status,'QUEUED')

    def test_every_kitchen_state_pair_allowed_or_rejected(self):
        order=self.confirmed(); item=order.items.first()
        for old in OrderItem.KitchenStatus.values:
            for new in OrderItem.KitchenStatus.values+['UNKNOWN']:
                now=timezone.now()
                Order.objects.filter(pk=order.pk).update(status='PREPARING')
                OrderItem.objects.filter(pk=item.pk).update(kitchen_status=old,
                    inventory_status='LEGACY' if old=='READY' else 'NOT_PROCESSED',inventory_processed_at=None,
                    queued_at=now if old in ('QUEUED','PREPARING','READY') else None,
                    preparing_at=now if old in ('PREPARING','READY') else None,ready_at=now if old=='READY' else None)
                if new in TRANSITIONS[old]:
                    result=transition_kitchen_item(order.pk,item.pk,new,actor=self.staff)
                    self.assertEqual(result.kitchen_status,new)
                else:
                    with self.subTest(old=old,new=new),self.assertRaises(ValidationError): transition_kitchen_item(order.pk,item.pk,new,actor=self.staff)

    def test_serving_additions_stay_draft_use_db_price_update_total(self):
        order=self.confirmed(); old=list(order.items.order_by('pk').values())
        for status in ('CONFIRMED','PREPARING'):
            Order.objects.filter(pk=order.pk).update(status=status)
            before=Order.objects.get(pk=order.pk).total_amount
            MenuItem.objects.filter(pk=self.menu.pk).update(price=Decimal('599000.25'),name='Món gọi thêm')
            line=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=2,note='Không cay')
            self.assertEqual((line.source,line.kitchen_status,line.item_name,line.unit_price,line.line_total),('DIRECT','DRAFT','Món gọi thêm',Decimal('599000.25'),Decimal('1198000.50')))
            order.refresh_from_db(); self.assertEqual(order.total_amount,before+line.line_total); self.assertEqual(order.status,status)
        self.assertEqual(list(order.items.filter(pk__in=[row['id'] for row in old]).order_by('pk').values()),old)

    def test_send_only_new_drafts_and_retry_never_overwrites_queue_time(self):
        order=self.confirmed(); old=list(order.items.order_by('pk').values())
        line=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        self.assertEqual(send_order_to_kitchen(order.pk,actor=self.staff),1)
        line.refresh_from_db(); queued=line.queued_at
        self.assertEqual((line.kitchen_status,send_order_to_kitchen(order.pk,actor=self.staff)),('QUEUED',0))
        line.refresh_from_db(); self.assertEqual(line.queued_at,queued)
        self.assertEqual(list(order.items.filter(pk__in=[row['id'] for row in old]).order_by('pk').values()),old)

    def test_send_pending_or_terminal_orders_rejected(self):
        order=self.open()
        for status in ('PENDING','COMPLETED','CANCELLED'):
            Order.objects.filter(pk=order.pk).update(status=status)
            with self.assertRaises(ValidationError): send_order_to_kitchen(order.pk,actor=self.staff)
        with self.assertRaises(ValidationError): transition_kitchen_item(order.pk,order.items.first().pk,'QUEUED',actor=self.staff)

    def test_pending_cannot_start_or_send_individual_draft(self):
        order=self.open(); item=order.items.first()
        for status in ('QUEUED','PREPARING','READY'):
            with self.assertRaises(ValidationError): transition_kitchen_item(order.pk,item.pk,status,actor=self.staff)

    def test_serving_draft_update_and_remove_keep_sent_history(self):
        order=self.confirmed(); old=order.items.first()
        draft=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        update_order_item(order.pk,draft.pk,actor=self.staff,quantity=3)
        draft.refresh_from_db(); self.assertEqual(draft.line_total,self.menu.price*3)
        remove_order_item(order.pk,draft.pk,actor=self.staff)
        self.assertFalse(OrderItem.objects.filter(pk=draft.pk).exists())
        self.assertTrue(OrderItem.objects.filter(pk=old.pk).exists())

    def test_every_nondraft_item_cannot_edit_or_delete_even_admin(self):
        order=self.confirmed(); item=order.items.first()
        for status in ('QUEUED','PREPARING','READY','CANCELLED'):
            now=timezone.now()
            OrderItem.objects.filter(pk=item.pk).update(kitchen_status=status,queued_at=now,
                inventory_status='LEGACY' if status=='READY' else 'NOT_PROCESSED',inventory_processed_at=None,
                preparing_at=now if status in ('PREPARING','READY') else None,ready_at=now if status=='READY' else None)
            for callback in (lambda:update_order_item(order.pk,item.pk,actor=self.admin,quantity=5),lambda:remove_order_item(order.pk,item.pk,actor=self.admin)):
                with self.subTest(status=status),self.assertRaises(ValidationError): callback()
        self.assertTrue(OrderItem.objects.filter(pk=item.pk).exists())

    def test_cancel_queued_keeps_original_preorder_and_excludes_money(self):
        order=self.confirmed(); item=order.items.get(menu_item=self.menu)
        booking=order.booking; original=list(booking.preorder_items.values())
        queued=item.queued_at; price=item.unit_price; amount=item.line_total
        transition_kitchen_item(order.pk,item.pk,'CANCELLED',actor=self.staff)
        item.refresh_from_db(); order.refresh_from_db()
        self.assertEqual((item.kitchen_status,item.unit_price,item.line_total,item.queued_at),('CANCELLED',price,amount,queued))
        self.assertEqual((order.subtotal,order.total_amount),(self.second.price,self.second.price))
        self.assertEqual(list(booking.preorder_items.values()),original)

    def test_cancel_draft_preserves_row_and_cooking_cannot_cancel(self):
        order=self.open(); first=order.items.first()
        transition_kitchen_item(order.pk,first.pk,'CANCELLED',actor=self.staff)
        self.assertTrue(OrderItem.objects.filter(pk=first.pk).exists())
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        item=order.items.exclude(pk=first.pk).get()
        transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
        with self.assertRaises(ValidationError): transition_kitchen_item(order.pk,item.pk,'CANCELLED',actor=self.admin)
        transition_kitchen_item(order.pk,item.pk,'READY',actor=self.staff)
        with self.assertRaises(ValidationError): transition_kitchen_item(order.pk,item.pk,'CANCELLED',actor=self.admin)

    def test_completion_blocks_draft_queued_preparing_empty_all_cancelled(self):
        order=self.confirmed()
        Order.objects.filter(pk=order.pk).update(status='PREPARING')
        for status in ('DRAFT','QUEUED','PREPARING','CANCELLED'):
            now=timezone.now()
            order.items.update(kitchen_status=status,queued_at=now if status in ('QUEUED','PREPARING') else None,
                preparing_at=now if status=='PREPARING' else None,ready_at=None)
            with self.subTest(status=status),self.assertRaises(ValidationError): transition_order(order.pk,'COMPLETED',actor=self.staff)
        empty=self.open(self.reserve(time=time(20),food_cart={}))
        transition_order(empty.pk,'CONFIRMED',actor=self.staff); transition_order(empty.pk,'PREPARING',actor=self.staff)
        with self.assertRaises(ValidationError): transition_order(empty.pk,'COMPLETED',actor=self.staff)

    def test_ready_and_cancelled_can_complete_without_inventory_or_payment(self):
        order=self.confirmed(); item=order.items.first()
        transition_kitchen_item(order.pk,item.pk,'CANCELLED',actor=self.staff)
        self.ready(order)
        ingredient=Ingredient.objects.create(code='KITCHEN',name='Untouched stock',unit='kg',current_stock=10)
        with patch('customers.inventory_service.consume_order',side_effect=AssertionError('No stock deduction')):
            order=transition_order(order.pk,'COMPLETED',actor=self.staff)
        self.assertEqual(order.status,'COMPLETED'); ingredient.refresh_from_db(); self.assertEqual(ingredient.current_stock,10)
        self.assertFalse(StockMovement.objects.exists()); self.assertFalse(Invoice.objects.exists()); self.assertFalse(Payment.objects.exists())

    def test_cancel_whole_pending_and_queued_orders_retains_rows_zero_total(self):
        first=self.open(); second=self.open(self.reserve(time=time(20)))
        transition_order(second.pk,'CONFIRMED',actor=self.staff)
        for order in (first,second):
            result=transition_order(order.pk,'CANCELLED',actor=self.staff)
            self.assertEqual((result.subtotal,result.total_amount,result.status),(0,0,'CANCELLED'))
            self.assertEqual(order.items.filter(kitchen_status='CANCELLED').count(),2)
            self.assertEqual(order.booking.preorder_items.count(),2)

    def test_whole_cancel_with_cooking_or_ready_rejected_atomically(self):
        order=self.confirmed(); item=order.items.first()
        transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
        # Even a stale/corrupt CONFIRMED parent cannot bypass the per-item guard.
        for status in ('PREPARING','READY'):
            if status=='READY': transition_kitchen_item(order.pk,item.pk,status,actor=self.staff)
            Order.objects.filter(pk=order.pk).update(status='CONFIRMED')
            original=list(order.items.order_by('pk').values())
            with self.assertRaises(ValidationError): transition_order(order.pk,'CANCELLED',actor=self.admin)
            self.assertEqual(list(order.items.order_by('pk').values()),original)

    def test_database_state_and_timestamp_constraints(self):
        order=self.open(); item=order.items.first(); now=timezone.now()
        for values in ({'kitchen_status':'FAKE'},{'kitchen_status':'QUEUED'},{'queued_at':now},{'kitchen_status':'READY','queued_at':now,'preparing_at':now,'ready_at':now-timedelta(seconds=1)}):
            with self.subTest(values=values),self.assertRaises(IntegrityError),transaction.atomic(): OrderItem.objects.filter(pk=item.pk).update(**values)

    def test_services_check_permission_and_item_ownership(self):
        order=self.confirmed(); other=self.open(self.reserve(time=time(20)))
        with self.assertRaises(ValidationError): transition_kitchen_item(order.pk,other.items.first().pk,'CANCELLED',actor=self.staff)
        for callback in (lambda:send_order_to_kitchen(order.pk,actor=self.customer),lambda:transition_kitchen_item(order.pk,order.items.first().pk,'PREPARING',actor=self.customer)):
            with self.assertRaises(PermissionDenied): callback()


class Module04HTTPTests(KitchenFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_queue_rbac_shared_shell_and_no_prices(self):
        order=self.confirmed()
        for actor in (self.staff,self.manager,self.admin):
            self.client.force_login(actor); response=self.client.get('/management/kitchen/')
            self.assertEqual(response.status_code,200); self.assertEqual(response.context['admin_page'],'kitchen')
            self.assertContains(response,order.order_number); self.assertContains(response,'Bắt đầu')
            self.assertContains(response,'server-content'); self.assertNotContains(response,'349.000,50')
            self.assertTrue(response.context['rbac_access']['view_kitchen'])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/management/kitchen/').status_code,403)

    def test_queue_oldest_send_first_filter_pagination_excludes_draft_ready_cancelled(self):
        order=self.confirmed(); items=list(order.items.order_by('pk'))
        first=timezone.now()-timedelta(minutes=5)
        OrderItem.objects.filter(pk=items[1].pk).update(queued_at=first)
        self.client.force_login(self.staff)
        response=self.client.get('/management/kitchen/')
        self.assertEqual([i.pk for i in response.context['pagination']],[items[1].pk,items[0].pk])
        transition_kitchen_item(order.pk,items[1].pk,'PREPARING',actor=self.staff)
        self.assertEqual(len(self.client.get('/management/kitchen/',{'status':'PREPARING'}).context['pagination']),1)
        transition_kitchen_item(order.pk,items[1].pk,'READY',actor=self.staff)
        transition_kitchen_item(order.pk,items[0].pk,'CANCELLED',actor=self.staff)
        draft=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        self.assertEqual(len(self.client.get('/management/kitchen/').context['pagination']),0)
        for _ in range(31): add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        send_order_to_kitchen(order.pk,actor=self.staff)
        response=self.client.get('/management/kitchen/')
        self.assertEqual(len(response.context['pagination']),30); self.assertEqual(response.context['pagination'].paginator.count,32)

    def test_full_staff_http_soup_then_call_more_send_ready_complete(self):
        order=self.confirmed(); self.client.force_login(self.staff)
        original_number=order.order_number
        for item in order.items.all():
            for status in ('PREPARING','READY'):
                response=self.client.post(reverse('admin_kitchen_item_status',args=[order.pk,item.pk]),{'status':status,'return_to':'kitchen','queued_at':'1999-01-01','preparing_at':'1999-01-01','ready_at':'1999-01-01'})
                self.assertRedirects(response,'/management/kitchen/')
        order.refresh_from_db(); self.assertEqual(order.status,'PREPARING')
        old=list(order.items.values())
        self.client.post(reverse('admin_order_item_add',args=[order.pk]),{'menu_item':self.menu.pk,'quantity':1,'note':'Gọi thêm','unit_price':1,'line_total':1,'source':'PREORDER','kitchen_status':'READY','total_amount':1,'discount_amount':1})
        new=order.items.get(source='DIRECT')
        self.assertEqual((new.kitchen_status,new.unit_price,new.source),('DRAFT',self.menu.price,'DIRECT'))
        self.assertEqual(list(order.items.filter(pk__in=[i['id'] for i in old]).values()),old)
        response=self.client.get(reverse('admin_order_detail',args=[order.pk]))
        self.assertContains(response,'Gửi món mới vào bếp'); self.assertContains(response,'Thêm món</button>')
        self.assertNotContains(response,'name="status" value="COMPLETED"')
        self.client.post(reverse('admin_order_send_kitchen',args=[order.pk]))
        for status in ('PREPARING','READY'):
            self.client.post(reverse('admin_kitchen_item_status',args=[order.pk,new.pk]),{'status':status})
        self.client.post(reverse('admin_order_status',args=[order.pk]),{'status':'COMPLETED'})
        order.refresh_from_db(); self.assertEqual((order.status,order.order_number),('COMPLETED',original_number))

    def test_get_and_csrf_block_all_new_mutations(self):
        order=self.confirmed(); item=order.items.first()
        urls=[reverse('admin_order_send_kitchen',args=[order.pk]),reverse('admin_kitchen_item_status',args=[order.pk,item.pk])]
        self.client.force_login(self.staff); protected=Client(enforce_csrf_checks=True); protected.force_login(self.staff)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code,405); self.assertEqual(protected.post(url,{'status':'PREPARING'}).status_code,403)
        protected.get('/management/kitchen/'); token=protected.cookies['csrftoken'].value
        self.assertEqual(protected.post(urls[1],{'status':'PREPARING','csrfmiddlewaretoken':token}).status_code,302)

    def test_item_permissions_cannot_be_bypassed(self):
        order=self.confirmed(); item=order.items.first()
        Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='view_orderitem',content_type__app_label='customers'))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/management/kitchen/').status_code,403)
        self.assertFalse(self.client.get('/management/orders/').context['rbac_access']['view_kitchen'])
        Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='change_orderitem',content_type__app_label='customers'))
        self.assertEqual(self.client.post(reverse('admin_order_send_kitchen',args=[order.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('admin_kitchen_item_status',args=[order.pk,item.pk]),{'status':'PREPARING'}).status_code,403)

    def test_wrong_order_item_and_fake_status_rejected(self):
        order=self.confirmed(); other=self.open(self.reserve(time=time(20)))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('admin_kitchen_item_status',args=[other.pk,order.items.first().pk]),{'status':'PREPARING'}).status_code,404)
        self.client.post(reverse('admin_kitchen_item_status',args=[order.pk,order.items.first().pk]),{'status':'READY'})
        self.assertEqual(order.items.filter(kitchen_status='QUEUED').count(),2)


class Module04ConcurrencyTests(KitchenFixtures,TransactionTestCase):
    def setUp(self): self.initialize()

    def race(self,callbacks):
        barrier=Barrier(2)
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10); actor=User.objects.get(pk=self.staff.pk)
                return callbacks[index](actor)
            except ValidationError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(worker,[0,1]))

    def test_two_starts_only_one_transition_timestamp_stable(self):
        self.assertEqual(connection.vendor,'postgresql'); order=self.confirmed(); item=order.items.first(); queued=item.queued_at
        results=self.race([lambda actor:transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=actor).preparing_at]*2)
        self.assertEqual(results.count('rejected'),1); item.refresh_from_db()
        self.assertIn(item.preparing_at,results); self.assertEqual(item.queued_at,queued)

    def test_two_ready_requests_only_one_transition(self):
        order=self.confirmed(); item=order.items.first(); item=transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
        prepared=item.preparing_at
        results=self.race([lambda actor:transition_kitchen_item(order.pk,item.pk,'READY',actor=actor).ready_at]*2)
        self.assertEqual(results.count('rejected'),1); item.refresh_from_db()
        self.assertIn(item.ready_at,results); self.assertEqual(item.preparing_at,prepared)

    def test_simultaneous_adds_have_no_lost_total(self):
        order=self.confirmed(); old=order.total_amount
        results=self.race([lambda actor:add_order_item(order.pk,actor=actor,menu_item_id=self.menu.pk,quantity=2).pk]*2)
        self.assertNotIn('rejected',results); order.refresh_from_db()
        self.assertEqual(order.total_amount,old+4*self.menu.price)
        self.assertEqual(order.items.filter(source='DIRECT',kitchen_status='DRAFT').count(),2)

    def test_simultaneous_send_queues_each_draft_once(self):
        order=self.confirmed(); line=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
        self.assertCountEqual(self.race([lambda actor:send_order_to_kitchen(order.pk,actor=actor)]*2),[1,0])
        line.refresh_from_db(); queued=line.queued_at
        self.assertEqual(send_order_to_kitchen(order.pk,actor=self.staff),0)
        line.refresh_from_db(); self.assertEqual(line.queued_at,queued)

    def test_cancel_vs_start_cannot_lose_history_or_money(self):
        order=self.confirmed(); line=order.items.first()
        results=self.race([lambda actor:transition_kitchen_item(order.pk,line.pk,'CANCELLED',actor=actor).kitchen_status,
                           lambda actor:transition_kitchen_item(order.pk,line.pk,'PREPARING',actor=actor).kitchen_status])
        self.assertEqual(results.count('rejected'),1); order.refresh_from_db(); line.refresh_from_db()
        self.assertTrue(OrderItem.objects.filter(pk=line.pk).exists())
        self.assertEqual(order.total_amount,sum(order.items.exclude(kitchen_status='CANCELLED').values_list('line_total',flat=True)))


class Module04MigrationTests(TransactionTestCase):
    def test_backfill_all_legacy_states_preserves_old_snapshots_and_money(self):
        from django.db.migrations.executor import MigrationExecutor
        old_target=[('customers','0009_order_booking_snapshots')]
        new_target=[('customers','0011_legacy_kitchen_states')]
        MigrationExecutor(connection).migrate(old_target)
        try:
            executor=MigrationExecutor(connection); old=executor.loader.project_state(old_target).apps
            user=old.get_model('auth','User').objects.create(username='kitchen-migration')
            category=old.get_model('customers','Category').objects.create(name='Legacy kitchen',slug='legacy-kitchen')
            menu=old.get_model('customers','MenuItem').objects.create(name='Renamed current name',category=category,price=999)
            keys={}
            for status in ('PENDING','CONFIRMED','PREPARING','COMPLETED','CANCELLED'):
                order=old.get_model('customers','Order').objects.create(created_by_id=user.pk,status=status,subtotal=200,discount_amount=20,total_amount=180)
                item=old.get_model('customers','OrderItem').objects.create(order=order,menu_item=menu,item_name='Original snapshot',unit_price=100,quantity=2,line_total=200,source='PREORDER',note='Original note')
                keys[status]=(order.pk,item.pk)
            executor=MigrationExecutor(connection); executor.migrate(new_target)
            new=executor.loader.project_state(new_target).apps
            for old_status,kitchen in {'PENDING':'DRAFT','CONFIRMED':'QUEUED','PREPARING':'PREPARING','COMPLETED':'READY','CANCELLED':'CANCELLED'}.items():
                order_pk,item_pk=keys[old_status]
                order=new.get_model('customers','Order').objects.get(pk=order_pk); item=new.get_model('customers','OrderItem').objects.get(pk=item_pk)
                self.assertEqual((item.kitchen_status,item.item_name,item.source,item.unit_price,item.quantity,item.line_total,item.note),(kitchen,'Original snapshot','PREORDER',100,2,200,'Original note'))
                self.assertEqual((order.subtotal,order.discount_amount,order.total_amount),(200,20,180))
                self.assertEqual(item.queued_at is not None,kitchen in ('QUEUED','PREPARING','READY'))
                self.assertEqual(item.preparing_at is not None,kitchen in ('PREPARING','READY'))
                self.assertEqual(item.ready_at is not None,kitchen=='READY')
        finally:
            restore=MigrationExecutor(connection)
            restore.migrate(restore.loader.graph.leaf_nodes())
