"""MODULE 03 behavior, HTTP permissions, snapshots and PostgreSQL races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier
from unittest.mock import patch
import uuid
from django.apps import apps
from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.management import call_command
from django.db import connection, connections, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Booking, BookingItem, Area, RestaurantTable, MenuItem, Category, Order, OrderItem, Invoice, Payment, StockMovement, Ingredient
from .rbac import assign_role, STAFF_ORDER_PERMISSIONS, STAFF_PAYMENT_PERMISSIONS
from .booking_service import create_booking, transition_booking
from .kitchen_service import transition_kitchen_item
from .order_service import open_order_from_booking, add_order_item, update_order_item, remove_order_item, transition_order, TRANSITIONS


class OrderFixtures:
    @classmethod
    def initialize(cls):
        call_command('seed_rbac', stdout=StringIO())
        call_command('seed_menu', stdout=StringIO())
        for role in ('ADMIN','MANAGER','STAFF','CUSTOMER'):
            user=User.objects.create_user('module03-'+role.lower())
            assign_role(user,role)
            setattr(cls,role.lower(),user)
        cls.area=Area.objects.create(name='Module03 Area')
        cls.table=RestaurantTable.objects.create(area=cls.area,code='M03-B01',capacity=4)
        cls.menu=MenuItem.objects.get(pk=1)
        cls.menu.price=Decimal('349000.50'); cls.menu.save()
        cls.second=MenuItem.objects.get(pk=2)
        cls.second.price=Decimal('289000'); cls.second.save()
        cls.day=timezone.localdate()+timedelta(days=2)

    def reserve(self, **kwargs):
        data=dict(user=self.customer,name='Khách Module03',phone='0912345678',date=self.day,time=time(18),guests=2,food_cart={str(self.menu.pk):2,str(self.second.pk):1})
        data.update(kwargs)
        return create_booking(**data)

    def open(self, booking=None, actor=None):
        return open_order_from_booking((booking or self.reserve()).pk,actor=actor or self.staff)

    def advance(self,order,status):
        for state in ('CONFIRMED','PREPARING','COMPLETED'):
            if state=='COMPLETED':
                for item in order.items.all():
                    transition_kitchen_item(order.pk,item.pk,'PREPARING',actor=self.staff)
                    transition_kitchen_item(order.pk,item.pk,'READY',actor=self.staff)
            transition_order(order.pk,state,actor=self.staff)
            if state==status: break


class Module03ServiceTests(OrderFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_open_links_customer_table_actor_and_default_money(self):
        booking=self.reserve(); order=self.open(booking)
        self.assertEqual((order.booking_id,order.customer_id,order.table_id,order.created_by_id),(booking.pk,self.customer.pk,self.table.pk,self.staff.pk))
        self.assertEqual((order.status,order.order_type,order.discount_amount),('PENDING','DINE_IN',0))
        self.assertEqual((order.subtotal,order.total_amount),(Decimal('987001'),Decimal('987001')))
        self.assertTrue(order.order_number.startswith('ORD-'))
        original=order.order_number
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        order.refresh_from_db(); self.assertEqual(order.order_number,original)

    def test_one_to_one_and_unique_number_database_constraints(self):
        booking=self.reserve(); order=self.open(booking)
        values=dict(created_by=self.admin,table=self.table,order_type='DINE_IN')
        with self.assertRaises(IntegrityError),transaction.atomic(): Order.objects.create(booking=booking,**values)
        with self.assertRaises(IntegrityError),transaction.atomic(): Order.objects.create(order_number=order.order_number,**values)

    def test_open_twice_returns_existing_without_duplicate_copy(self):
        booking=self.reserve(); original=list(booking.preorder_items.values())
        first=self.open(booking); second=self.open(booking,actor=self.manager)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual((Order.objects.count(),OrderItem.objects.count()),(1,2))
        self.assertEqual(list(booking.preorder_items.values()),original)

    def test_exact_preorder_snapshots_survive_price_name_and_availability_changes(self):
        booking=self.reserve(); snapshots=list(booking.preorder_items.order_by('pk'))
        MenuItem.objects.filter(pk=self.menu.pk).update(name='Đổi tên sau đặt',price=399000,is_available=False)
        Category.objects.filter(pk=self.menu.category_id).update(is_active=False)
        order=self.open(booking)
        for old,new in zip(snapshots,order.items.order_by('pk')):
            self.assertEqual((new.menu_item_id,new.item_name,new.unit_price,new.quantity,new.line_total,new.source),
                (old.menu_item_id,old.item_name,old.unit_price,old.quantity,old.unit_price*old.quantity,'PREORDER'))

    def test_invalid_booking_statuses_no_order(self):
        booking=self.reserve()
        for status in ('PENDING','CANCELLED','COMPLETED'):
            Booking.objects.filter(pk=booking.pk).update(status=status)
            with self.subTest(status=status),self.assertRaises(ValidationError): self.open(booking)
        self.assertFalse(Order.objects.exists())

    def test_missing_or_unavailable_table_rejected(self):
        booking=self.reserve()
        for changes in ({'is_active':False},{'status':'MAINTENANCE'},{'capacity':1}):
            RestaurantTable.objects.filter(pk=self.table.pk).update(**changes)
            with self.assertRaises(ValidationError): self.open(booking)
            RestaurantTable.objects.filter(pk=self.table.pk).update(is_active=True,status='AVAILABLE',capacity=4)
        Area.objects.filter(pk=self.area.pk).update(is_active=False)
        with self.assertRaises(ValidationError): self.open(booking)
        Booking.objects.filter(pk=booking.pk).update(table=None)
        with self.assertRaises(ValidationError): self.open(booking)

    def test_empty_preorder_opens_empty_order_then_adds_direct(self):
        order=self.open(self.reserve(food_cart={}))
        self.assertEqual(order.total_amount,0); self.assertFalse(order.items.exists())
        line=add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=3,note='Không cay')
        order.refresh_from_db()
        self.assertEqual((line.source,line.item_name,line.unit_price,line.line_total),('DIRECT',self.menu.name,self.menu.price,self.menu.price*3))
        self.assertEqual((order.subtotal,order.total_amount),(line.line_total,line.line_total))

    def test_direct_same_menu_keeps_preorder_and_new_price_separate(self):
        order=self.open(); old=order.items.get(menu_item=self.menu)
        MenuItem.objects.filter(pk=self.menu.pk).update(price=399000,name='Tên mới')
        new=add_order_item(order.pk,actor=self.manager,menu_item_id=self.menu.pk,quantity=1)
        self.assertNotEqual(old.pk,new.pk)
        self.assertEqual((old.source,old.unit_price,new.source,new.unit_price,new.item_name),('PREORDER',Decimal('349000.50'),'DIRECT',399000,'Tên mới'))

    def test_direct_unavailable_unpriced_unknown_and_inactive_category(self):
        order=self.open()
        for changes in ({'is_available':False},{'price':None}):
            MenuItem.objects.filter(pk=self.menu.pk).update(**changes)
            with self.assertRaises(ValidationError): add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
            MenuItem.objects.filter(pk=self.menu.pk).update(is_available=True,price=349000)
        Category.objects.filter(pk=self.menu.category_id).update(is_active=False)
        for pk in (self.menu.pk,999999):
            with self.assertRaises(ValidationError): add_order_item(order.pk,actor=self.staff,menu_item_id=pk,quantity=1)

    def test_add_and_update_reject_invalid_quantities(self):
        order=self.open(); item=order.items.first()
        for quantity in (0,-1,True,1.5,'2',1001):
            for callback in (lambda:add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=quantity),lambda:update_order_item(order.pk,item.pk,actor=self.staff,quantity=quantity)):
                with self.subTest(quantity=quantity),self.assertRaises(ValidationError): callback()

    def test_pending_update_remove_recalculate_using_snapshot(self):
        booking=self.reserve(); order=self.open(booking); line=order.items.get(menu_item=self.menu)
        MenuItem.objects.filter(pk=self.menu.pk).update(price=999999)
        update_order_item(order.pk,line.pk,actor=self.staff,quantity=3)
        line.refresh_from_db(); self.assertEqual(line.line_total,Decimal('1047001.50'))
        remove_order_item(order.pk,line.pk,actor=self.staff)
        order.refresh_from_db(); self.assertEqual((order.subtotal,order.total_amount),(289000,289000))
        remove_order_item(order.pk,order.items.get().pk,actor=self.staff)
        order.refresh_from_db(); self.assertEqual(order.total_amount,0)
        self.assertEqual(booking.preorder_items.count(),2)

    def test_all_state_machine_pairs_exactly_match_policy(self):
        order=self.open()
        for old in Order.Status.values:
            for new in Order.Status.values+['INVALID']:
                Order.objects.filter(pk=order.pk).update(status=old)
                # Each transition starts with a consistent independent kitchen fixture.
                now=timezone.now()
                kitchen={'PENDING':'DRAFT','CONFIRMED':'QUEUED','PREPARING':'READY','COMPLETED':'READY','CANCELLED':'CANCELLED'}[old]
                order.items.update(kitchen_status=kitchen,queued_at=now if kitchen in ('QUEUED','READY') else None,preparing_at=now if kitchen=='READY' else None,ready_at=now if kitchen=='READY' else None,inventory_status='LEGACY' if kitchen=='READY' else 'NOT_PROCESSED',inventory_processed_at=None)
                if new in TRANSITIONS[old]:
                    self.assertEqual(transition_order(order.pk,new,actor=self.staff).status,new)
                else:
                    with self.subTest(old=old,new=new),self.assertRaises(ValidationError): transition_order(order.pk,new,actor=self.staff)

    def test_nonpending_items_read_only_for_all_three_mutations(self):
        # MODULE 04 allows new DRAFT lines on serving orders, but never edits sent lines.
        order=self.open(); line=order.items.first()
        transition_order(order.pk,'CONFIRMED',actor=self.staff)
        for status in ('CONFIRMED','PREPARING','COMPLETED','CANCELLED'):
            Order.objects.filter(pk=order.pk).update(status=status)
            for callback in (lambda:update_order_item(order.pk,line.pk,actor=self.staff,quantity=1),lambda:remove_order_item(order.pk,line.pk,actor=self.staff)):
                with self.subTest(status=status),self.assertRaises(ValidationError): callback()
            if status in ('COMPLETED','CANCELLED'):
                with self.assertRaises(ValidationError): add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1)
            else:
                self.assertEqual(add_order_item(order.pk,actor=self.staff,menu_item_id=self.menu.pk,quantity=1).kitchen_status,'DRAFT')
        line.refresh_from_db(); self.assertEqual(line.quantity,2)

    def test_foreign_item_cannot_be_changed(self):
        order=self.open(); other=self.open(self.reserve(time=time(20)))
        item=other.items.first()
        with self.assertRaises(ValidationError): update_order_item(order.pk,item.pk,actor=self.admin,quantity=4)
        with self.assertRaises(ValidationError): remove_order_item(order.pk,item.pk,actor=self.admin)

    def test_customer_cancel_before_open_but_blocked_after_even_cancelled_order(self):
        booking=self.reserve(); transition_booking(booking.pk,'CANCELLED',owner=self.customer)
        with self.assertRaises(ValidationError): self.open(booking)
        booking=self.reserve(); order=self.open(booking)
        with self.assertRaises(ValidationError): transition_booking(booking.pk,'CANCELLED',owner=self.customer)
        with self.assertRaises(ValidationError): transition_booking(booking.pk,'CANCELLED')
        transition_order(order.pk,'CANCELLED',actor=self.staff)
        with self.assertRaises(ValidationError): transition_booking(booking.pk,'CANCELLED',owner=self.customer)
        self.assertEqual(transition_booking(booking.pk,'CANCELLED').status,'CANCELLED')
        self.assertEqual(self.open(booking).pk,order.pk) # Retry returns existing, never opens a new one.

    def test_completion_neither_consumes_stock_nor_issues_payment(self):
        ingredient=Ingredient.objects.create(code='M03',name='Ingredient',unit='kg',current_stock=10)
        order=self.open()
        with patch('customers.inventory_service.consume_order',side_effect=AssertionError('Must not consume')):
            self.advance(order,'COMPLETED')
        ingredient.refresh_from_db(); self.assertEqual(ingredient.current_stock,10)
        self.assertFalse(StockMovement.objects.exists()); self.assertFalse(Invoice.objects.exists()); self.assertFalse(Payment.objects.exists())

    def test_database_rejects_bad_item_money_source_and_order_status(self):
        order=self.open(); item=order.items.first()
        for values in ({'quantity':0},{'unit_price':-1},{'line_total':-1},{'line_total':1},{'source':'INVALID'},{'item_name':' '}):
            with self.subTest(values=values),self.assertRaises(IntegrityError),transaction.atomic(): OrderItem.objects.filter(pk=item.pk).update(**values)
        for values in ({'status':'INVALID'},{'subtotal':-1},{'discount_amount':-1},{'total_amount':-1}):
            with self.assertRaises(IntegrityError),transaction.atomic(): Order.objects.filter(pk=order.pk).update(**values)

    def test_open_failure_rolls_back_order_and_all_copies(self):
        booking=self.reserve()
        from . import order_service
        original=order_service.save_validated
        def fail_second_line(obj):
            if isinstance(obj,OrderItem) and obj.menu_item_id==self.second.pk: raise ValidationError('forced')
            return original(obj)
        with patch.object(order_service,'save_validated',side_effect=fail_second_line),self.assertRaises(ValidationError): self.open(booking)
        self.assertFalse(Order.objects.exists()); self.assertFalse(OrderItem.objects.exists()); self.assertEqual(booking.preorder_items.count(),2)

    def test_customer_and_inactive_actor_cannot_use_services(self):
        booking=self.reserve()
        with self.assertRaises(PermissionDenied): self.open(booking,actor=self.customer)
        self.staff.is_active=False; self.staff.save()
        with self.assertRaises(PermissionDenied): self.open(booking,actor=self.staff)

    def test_new_booking_does_not_create_order_or_change_cart(self):
        cart={str(self.menu.pk):2}; self.reserve(food_cart=cart)
        self.assertEqual(cart,{str(self.menu.pk):2}); self.assertFalse(Order.objects.exists())
        self.assertEqual(MenuItem.objects.count(),45); self.assertEqual(Category.objects.count(),19)


class Module03HTTPTests(OrderFixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def test_seed_staff_exact_grants_idempotent_without_account_access(self):
        call_command('seed_rbac',stdout=StringIO())
        self.assertEqual(set(Group.objects.get(name='STAFF').permissions.values_list('codename',flat=True)),STAFF_ORDER_PERMISSIONS | STAFF_PAYMENT_PERMISSIONS)
        self.client.force_login(self.staff)
        for url in ('/management/','/management/orders/','/management/orders/from-booking/'):
            self.assertEqual(self.client.get(url).status_code,200)
        for url in ('/management/accounts/','/management/bookings/','/management/areas/','/management/tables/'):
            self.assertEqual(self.client.get(url).status_code,403)
        self.assertFalse(self.staff.is_staff)

    def test_admin_manager_staff_open_and_detail_use_shared_shell(self):
        booking=self.reserve()
        for actor in (self.admin,self.manager,self.staff):
            self.client.force_login(actor)
            response=self.client.post(reverse('admin_booking_open_order',args=[booking.pk]),{'table_id':999,'customer_id':self.admin.pk,'order_number':'FAKE','status':'COMPLETED','discount_amount':999})
            order=Order.objects.get(); self.assertRedirects(response,reverse('admin_order_detail',args=[order.pk]))
            self.assertEqual((order.table_id,order.customer_id,order.status,order.discount_amount),(self.table.pk,self.customer.pk,'PENDING',0))
            response=self.client.get(response.url)
            self.assertContains(response,order.order_number); self.assertContains(response,'server-content')
            self.assertEqual(response.context['admin_page'],'orders')
        self.assertEqual(OrderItem.objects.count(),2)

    def test_booking_ui_open_becomes_view_and_customer_cancel_hidden(self):
        booking=self.reserve(); self.client.force_login(self.manager)
        for url in ('/management/bookings/',reverse('admin_booking_detail',args=[booking.pk])):
            self.assertContains(self.client.get(url),'Mở đơn hàng')
        order=self.open(booking)
        for url in ('/management/bookings/',reverse('admin_booking_detail',args=[booking.pk])):
            response=self.client.get(url); self.assertContains(response,'Xem đơn hàng'); self.assertNotContains(response,'Mở đơn hàng')
        self.client.force_login(self.customer)
        response=self.client.get('/booking/'); self.assertContains(response,'Đặt bàn đã mở đơn hàng')
        self.assertNotContains(response,reverse('customer_booking_cancel',args=[booking.pk]))
        self.client.post(reverse('customer_booking_cancel',args=[booking.pk]))
        booking.refresh_from_db(); order.refresh_from_db()
        self.assertEqual((booking.status,order.status),('CONFIRMED','PENDING'))

    def test_direct_post_ignores_prices_sources_and_totals(self):
        order=self.open(); self.client.force_login(self.staff)
        self.client.post(reverse('admin_order_item_add',args=[order.pk]),{'menu_item':self.menu.pk,'quantity':3,'unit_price':1,'item_name':'FAKE','source':'PREORDER','line_total':1,'subtotal':1,'discount_amount':1,'total_amount':1})
        line=order.items.get(source='DIRECT'); self.assertEqual((line.item_name,line.unit_price,line.line_total),(self.menu.name,self.menu.price,self.menu.price*3))
        order.refresh_from_db(); self.assertEqual(order.total_amount,Decimal('2034002.50')); self.assertEqual(order.discount_amount,0)

    def test_all_mutations_post_only_and_csrf(self):
        booking=self.reserve(); order=self.open(booking); line=order.items.first()
        urls=[reverse('admin_booking_open_order',args=[booking.pk]),reverse('admin_order_item_add',args=[order.pk]),reverse('admin_order_item_quantity',args=[order.pk,line.pk]),reverse('admin_order_item_remove',args=[order.pk,line.pk]),reverse('admin_order_status',args=[order.pk])]
        self.client.force_login(self.staff)
        protected=Client(enforce_csrf_checks=True); protected.force_login(self.staff)
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code,405)
                self.assertEqual(protected.post(url,{}).status_code,403)
        response=protected.get(reverse('admin_order_detail',args=[order.pk]))
        token=protected.cookies['csrftoken'].value
        self.assertEqual(protected.post(reverse('admin_order_status',args=[order.pk]),{'status':'CONFIRMED','csrfmiddlewaretoken':token}).status_code,302)

    def test_customer_no_order_endpoints_and_cross_order_item_404(self):
        booking=self.reserve(); order=self.open(booking); line=order.items.first()
        self.client.force_login(self.customer)
        for url in ('/management/orders/',reverse('admin_order_detail',args=[order.pk]),reverse('admin_booking_open_order',args=[booking.pk]),reverse('admin_order_item_add',args=[order.pk]),reverse('admin_order_status',args=[order.pk])):
            self.assertEqual(self.client.get(url).status_code,403); self.assertEqual(self.client.post(url,{}).status_code,403)
        other=self.open(self.reserve(time=time(20)))
        self.client.force_login(self.staff)
        for route in ('admin_order_item_quantity','admin_order_item_remove'):
            self.assertEqual(self.client.post(reverse(route,args=[other.pk,line.pk]),{'quantity':3}).status_code,404)

    def test_revoked_item_permission_blocks_post_and_service(self):
        order=self.open()
        Group.objects.get(name='STAFF').permissions.remove(Permission.objects.get(codename='add_orderitem',content_type__app_label='customers'))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('admin_order_item_add',args=[order.pk]),{'menu_item':1,'quantity':1}).status_code,403)
        actor=User.objects.get(pk=self.staff.pk)
        with self.assertRaises(PermissionDenied): add_order_item(order.pk,actor=actor,menu_item_id=1,quantity=1)

    def test_read_only_http_cannot_mutate_confirmed_order(self):
        order=self.open(); line=order.items.first(); self.advance(order,'CONFIRMED')
        original=list(order.items.values()); self.client.force_login(self.staff)
        response=self.client.get(reverse('admin_order_detail',args=[order.pk]))
        self.assertContains(response,'Thêm món</button>'); self.assertNotContains(response,'Xóa món</button>')
        for route,args,data in [('admin_order_item_add',[order.pk],{'menu_item':1,'quantity':3}),('admin_order_item_quantity',[order.pk,line.pk],{'quantity':3}),('admin_order_item_remove',[order.pk,line.pk],{})]:
            self.client.post(reverse(route,args=args),data)
        self.assertEqual(list(order.items.filter(pk__in=[row['id'] for row in original]).values()),original)
        self.assertEqual(order.items.filter(source='DIRECT',kitchen_status='DRAFT').count(),1)

    def test_orders_search_status_pagination_and_dashboard_actual_data(self):
        order=self.open(); self.client.force_login(self.staff)
        for query in (order.order_number,self.customer.username,self.table.code,'Khách Module03'):
            response=self.client.get('/management/orders/',{'q':query}); self.assertEqual(len(response.context['rows']),1)
        self.assertEqual(len(self.client.get('/management/orders/',{'status':'COMPLETED'}).context['rows']),0)
        for _ in range(31): Order.objects.create(created_by=self.admin)
        response=self.client.get('/management/orders/'); self.assertEqual(response.context['pagination'].paginator.count,32)
        self.assertEqual(len(response.context['rows']),30)
        self.assertEqual(len(self.client.get('/management/orders/',{'page':2}).context['rows']),2)
        dashboard=self.client.get('/management/')
        self.assertEqual(dashboard.context['business_summary']['order_count_today'],32)
        self.assertEqual(dashboard.context['business_summary']['revenue_today'],0)


class Module03ConcurrencyTests(OrderFixtures,TransactionTestCase):
    def setUp(self): self.initialize()

    def race(self, callbacks):
        barrier=Barrier(2)
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                actor=User.objects.get(pk=self.staff.pk)
                return callbacks[index](actor)
            except ValidationError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(worker,[0,1]))

    def test_two_open_requests_create_one_order_and_one_copy(self):
        self.assertEqual(connection.vendor,'postgresql'); booking=self.reserve()
        callbacks=[lambda actor:open_order_from_booking(booking.pk,actor=actor).pk]*2
        result=self.race(callbacks)
        self.assertEqual(result[0],result[1]); self.assertEqual(Order.objects.count(),1)
        self.assertEqual(OrderItem.objects.count(),2); self.assertEqual(BookingItem.objects.count(),2)

    def test_open_races_customer_cancel_without_inconsistent_order(self):
        booking=self.reserve()
        result=self.race([lambda actor:open_order_from_booking(booking.pk,actor=actor).pk,
            lambda actor:transition_booking(booking.pk,'CANCELLED',owner=User.objects.get(pk=self.customer.pk)).status])
        self.assertIn('rejected',result); booking.refresh_from_db()
        if Order.objects.exists(): self.assertEqual(booking.status,'CONFIRMED')
        else: self.assertEqual(booking.status,'CANCELLED')

    def test_two_quantity_changes_keep_totals_consistent(self):
        order=self.open(); item=order.items.first()
        result=self.race([lambda actor:update_order_item(order.pk,item.pk,actor=actor,quantity=3).pk,
                          lambda actor:update_order_item(order.pk,item.pk,actor=actor,quantity=4).pk])
        self.assertEqual(result,[item.pk,item.pk]); order.refresh_from_db(); item.refresh_from_db()
        self.assertIn(item.quantity,(3,4))
        self.assertEqual(order.total_amount,sum(order.items.values_list('line_total',flat=True)))


class Module03MigrationTests(TransactionTestCase):
    def test_existing_orders_backfill_without_touching_old_money_or_bookings(self):
        from django.db.migrations.executor import MigrationExecutor
        old_target=[('customers','0008_bookingitem_booking_food_subtotal_and_more')]
        new_target=[('customers','0009_order_booking_snapshots')]
        executor=MigrationExecutor(connection)
        executor.migrate(old_target)
        try:
            old=executor.loader.project_state(old_target).apps
            user=old.get_model('auth','User').objects.create(username='migration-order-owner')
            category=old.get_model('customers','Category').objects.create(name='Legacy',slug='legacy')
            menu=old.get_model('customers','MenuItem').objects.create(name='Legacy name',category=category,price=999,image='original.jpg')
            order=old.get_model('customers','Order').objects.create(created_by_id=user.pk,subtotal=200,discount_amount=20,total_amount=180)
            item=old.get_model('customers','OrderItem').objects.create(order=order,menu_item=menu,quantity=2,unit_price=100,line_total=200,note='Keep note')
            executor=MigrationExecutor(connection); executor.migrate(new_target)
            new=executor.loader.project_state(new_target).apps
            current=new.get_model('customers','Order').objects.get(pk=order.pk)
            line=new.get_model('customers','OrderItem').objects.get(pk=item.pk)
            self.assertEqual((current.subtotal,current.discount_amount,current.total_amount,current.booking_id),(200,20,180,None))
            self.assertIn('LEGACY',current.order_number)
            self.assertEqual((line.item_name,line.source,line.unit_price,line.line_total,line.note),('Legacy name','DIRECT',100,200,'Keep note'))
            self.assertEqual((line.created_at,line.updated_at),(order.created_at,order.updated_at))
            self.assertFalse(new.get_model('customers','Booking').objects.exists())
        finally:
            restore=MigrationExecutor(connection)
            restore.migrate(restore.loader.graph.leaf_nodes())
