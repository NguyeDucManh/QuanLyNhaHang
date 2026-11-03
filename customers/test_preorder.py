from datetime import timedelta,time
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from .models import Booking,BookingItem,MenuItem,Category,Area,RestaurantTable,Order,OrderItem
from .rbac import assign_role
from .menu_service import CATALOG_VERSION
from .booking_service import create_booking


class BookingPreorderTests(TransactionTestCase):
    def setUp(self):
        call_command('seed_menu',stdout=StringIO())
        call_command('seed_rbac',stdout=StringIO())
        self.customer=User.objects.create_user('preorder-customer'); assign_role(self.customer,'CUSTOMER')
        self.manager=User.objects.create_user('preorder-manager'); assign_role(self.manager,'MANAGER')
        self.other=User.objects.create_user('preorder-other'); assign_role(self.other,'CUSTOMER')
        self.staff=User.objects.create_user('preorder-staff'); assign_role(self.staff,'STAFF')
        self.area=Area.objects.create(name='Preorder Area')
        self.table=RestaurantTable.objects.create(area=self.area,code='B01',capacity=4)
        self.one=MenuItem.objects.get(pk=1); self.two=MenuItem.objects.get(pk=2)
        self.day=timezone.localdate()+timedelta(days=1)
        self.client.force_login(self.customer)

    def set_cart(self,cart):
        session=self.client.session; session['catalog_version']=CATALOG_VERSION; session['cart']=cart; session['prices']={'1':'1'}; session.save()

    def submit(self,**extra):
        data={'name':'Khách','phone':'0912345678','date':self.day.isoformat(),'time':'18:00','guests':2}
        data.update(extra)
        return self.client.post('/booking/',data)

    def test_preview_two_items_preserves_cart_and_navigation(self):
        self.set_cart({'1':2,'2':1})
        self.client.get('/menu/'); self.client.get('/cart/')
        response=self.client.get('/booking/')
        self.assertEqual(len(response.context['selected_food']),2)
        self.assertContains(response,self.one.name); self.assertContains(response,self.two.name)
        self.assertContains(response,'Đặt bàn &amp; đặt trước món')
        self.assertEqual(self.client.session['cart'],{'1':2,'2':1})

    def test_empty_cart_still_books_without_items(self):
        self.set_cart({})
        self.assertContains(self.client.get('/booking/'),'Bạn chưa chọn món trước.')
        self.assertEqual(self.submit().status_code,302)
        booking=Booking.objects.get(); self.assertEqual(booking.status,'PENDING_DEPOSIT')
        self.assertEqual(booking.food_subtotal,0); self.assertEqual(BookingItem.objects.count(),0)

    def test_success_snapshots_quantities_db_prices_totals_and_clears_cart(self):
        self.set_cart({'1':2,'2':3})
        self.assertEqual(self.submit(unit_price='1',line_total='1',subtotal='1',food_subtotal='1',status='CANCELLED').status_code,302)
        booking=Booking.objects.get(); self.assertEqual(booking.status,'PENDING_DEPOSIT'); self.assertEqual(booking.table_id,self.table.pk)
        lines={line.menu_item_id:line for line in booking.preorder_items.all()}
        self.assertEqual(len(lines),2)
        self.assertEqual((lines[1].quantity,lines[1].unit_price,lines[1].line_total,lines[1].item_name),(2,self.one.price,self.one.price*2,self.one.name))
        self.assertEqual(booking.food_subtotal,self.one.price*2+self.two.price*3)
        self.assertEqual(self.client.session['cart'],{})
        self.assertEqual((Order.objects.count(),OrderItem.objects.count()),(0,0))

    def test_history_keeps_price_and_name_snapshot_after_menu_changes(self):
        self.set_cart({'1':2}); self.submit()
        old_name=self.one.name; old_price=self.one.price
        self.one.name='New Menu Name'; self.one.price=999999; self.one.save()
        item=BookingItem.objects.get(); self.assertEqual(item.item_name,old_name); self.assertEqual(item.unit_price,old_price)
        response=self.client.get('/booking/',follow=True)
        self.assertContains(response,old_name); self.assertNotContains(response,'New Menu Name')
        self.assertEqual(Booking.objects.get().food_subtotal,old_price*2)

    def test_no_table_keeps_cart_and_creates_no_booking_items(self):
        self.table.is_active=False; self.table.save(); self.set_cart({'1':2})
        self.assertContains(self.submit(),'Không còn bàn phù hợp')
        self.assertEqual((Booking.objects.count(),BookingItem.objects.count()),(0,0))
        self.assertEqual(self.client.session['cart'],{'1':2})

    def test_invalid_date_and_form_keep_cart(self):
        self.set_cart({'1':2})
        self.assertEqual(self.submit(date=(self.day-timedelta(days=3)).isoformat()).status_code,200)
        self.assertEqual(self.submit(phone='bad').status_code,200)
        self.assertEqual(self.client.session['cart'],{'1':2})
        self.assertFalse(Booking.objects.exists())

    def test_item_write_failure_rolls_back_booking_and_partial_items(self):
        self.set_cart({'1':2,'2':1})
        original=BookingItem.save
        counter=[]
        def fail_second(instance,*args,**kwargs):
            counter.append(instance.menu_item_id)
            if len(counter)==2: raise IntegrityError('simulated item write failure')
            return original(instance,*args,**kwargs)
        with patch.object(BookingItem,'save',fail_second):
            response=self.submit()
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(counter),2)
        self.assertEqual((Booking.objects.count(),BookingItem.objects.count()),(0,0))
        self.assertEqual(self.client.session['cart'],{'1':2,'2':1})

    def test_cancel_preserves_items_and_frees_slot(self):
        self.set_cart({'1':2}); self.submit()
        booking=Booking.objects.get()
        self.client.post(reverse('customer_booking_cancel',args=[booking.pk]))
        booking.refresh_from_db(); self.assertEqual(booking.status,'CANCELLED')
        self.assertEqual(booking.preorder_items.count(),1)
        self.assertEqual(booking.food_subtotal,self.one.price*2)
        self.assertContains(self.client.get('/booking/',follow=True),self.one.name)
        self.submit(); self.assertEqual(Booking.objects.filter(status='PENDING_DEPOSIT').get().table_id,self.table.pk)

    def test_other_customer_cannot_view_preorder_history_or_admin_detail(self):
        self.set_cart({'1':2}); self.submit(); booking=Booking.objects.get()
        self.client.force_login(self.other)
        response=self.client.get('/booking/')
        self.assertNotContains(response,self.one.name)
        self.assertEqual(self.client.get(reverse('admin_booking_detail',args=[booking.pk])).status_code,403)

    def test_admin_manager_can_view_snapshot_but_staff_customer_cannot(self):
        self.set_cart({'1':2}); self.submit(); booking=Booking.objects.get()
        admin=User.objects.create_user('preorder-admin'); assign_role(admin,'ADMIN')
        for user in (admin,self.manager):
            self.client.force_login(user)
            self.assertContains(self.client.get('/management/bookings/'),'Chi tiết / Món đặt trước')
            response=self.client.get(reverse('admin_booking_detail',args=[booking.pk]))
            self.assertContains(response,self.one.name)
            self.assertContains(response,'Món đặt trước')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin_booking_detail',args=[booking.pk])).status_code,403)

    def test_invalid_quantities_rejected_and_cart_preserved(self):
        for quantity in (0,-1,100,True,'2',1.5,{'quantity':2,'unit_price':1}):
            with self.subTest(quantity=quantity):
                self.set_cart({'1':quantity}); response=self.submit()
                self.assertEqual(response.status_code,200)
                self.assertEqual(self.client.session['cart'],{'1':quantity})
                self.assertFalse(Booking.objects.exists()); self.assertFalse(BookingItem.objects.exists())

    def test_unavailable_item_or_category_keeps_cart_and_rolls_back(self):
        self.set_cart({'1':2})
        self.one.is_available=False; self.one.save()
        self.assertContains(self.submit(),'ngừng phục vụ')
        self.one.is_available=True; self.one.save()
        self.one.category.is_active=False; self.one.category.save()
        self.assertContains(self.submit(),'ngừng phục vụ')
        self.assertFalse(Booking.objects.exists()); self.assertFalse(BookingItem.objects.exists())
        self.assertEqual(self.client.session['cart'],{'1':2})

    def test_unknown_item_rejected_not_silently_omitted(self):
        self.set_cart({'999999':1})
        self.assertEqual(self.submit().status_code,200)
        self.assertEqual(self.client.session['cart'],{'999999':1}); self.assertFalse(Booking.objects.exists())

    def test_unpriced_item_is_not_snapshotted_as_free(self):
        self.one.price=None; self.one.save(); self.set_cart({'1':1})
        self.assertContains(self.submit(),'chưa niêm yết giá')
        self.assertEqual(self.client.session['cart'],{'1':1}); self.assertFalse(Booking.objects.exists())

    def test_reuses_cart_endpoint_and_returns_only_to_booking(self):
        self.set_cart({'1':2})
        for action,expected in [('add',{'1':3}),('decrease',{'1':2}),('remove',{})]:
            self.assertRedirects(self.client.post('/cart/1/',{'action':action,'return_to':'booking'}),'/booking/')
            self.assertEqual(self.client.session['cart'],expected)
        self.assertRedirects(self.client.post('/cart/1/',{'action':'add','return_to':'https://example.com'}),'/cart/')

    def test_legacy_booking_without_food_still_renders(self):
        booking=Booking.objects.create(user=self.customer,name='Legacy',phone='0912345678',date=self.day,time=time(18),guests=2)
        self.assertContains(self.client.get('/booking/'),'Legacy')
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse('admin_booking_detail',args=[booking.pk])),'không có món đặt trước')

    def test_existing_menu_and_category_are_unchanged(self):
        before=list(MenuItem.objects.order_by('pk').values()); categories=list(Category.objects.order_by('pk').values())
        self.set_cart({'1':2,'2':1}); self.submit()
        self.assertEqual(list(MenuItem.objects.order_by('pk').values()),before)
        self.assertEqual(list(Category.objects.order_by('pk').values()),categories)
        self.assertEqual((MenuItem.objects.count(),Category.objects.count()),(45,19))
