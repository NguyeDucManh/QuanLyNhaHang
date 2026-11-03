"""Customer draft navigation and payment composition around existing services."""
from datetime import timedelta, time
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from .test_module07 import Module07Fixtures
from .models import Booking, BookingItem, Order, Invoice, Payment, Topping, Combo, ComboItem
from .customer_booking_workspace import DRAFT_KEY, payment_state


class CustomerBookingWorkspaceTests(Module07Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def setUp(self):
        self.client.force_login(self.customer)
        self.data = dict(name='Khách đặt bàn', phone='0912345678', date=str(timezone.localdate()+timedelta(days=4)), time='18:00', guests='2', note='Bàn yên tĩnh')

    def save_draft(self, **extra):
        return self.client.post('/booking/?view=new', {**self.data, 'intent': 'menu', **extra})

    def test_default_is_new_without_history(self):
        self.reserve(name='Private booked name')
        r=self.client.get('/booking/')
        self.assertEqual(r.context['booking_view'], 'new')
        self.assertContains(r, 'id="booking-form"')
        self.assertEqual(r.context['form']['name'].value(), 'Private booked name')
        self.assertNotContains(r, 'booking-record-actions')
        self.assertNotContains(r, 'id="booking-list"')

    def test_mine_does_not_render_creation(self):
        r=self.client.get('/booking/?view=mine')
        self.assertContains(r, 'id="booking-list"')
        self.assertNotContains(r, 'id="booking-form"')

    def test_history_includes_future_and_cancelled_owned_only(self):
        a=self.reserve(name='Own future')
        b=self.reserve(name='Other secret',user=self.manager,time=time(21))
        r=self.client.get('/booking/?view=mine&tab=history')
        self.assertContains(r, a.name);self.assertNotContains(r, b.name)

    def test_partial_draft_does_not_create_or_hold(self):
        r=self.save_draft(date='',phone='')
        self.assertEqual(r.url, '/menu/?from=booking')
        self.assertEqual(Booking.objects.count(),0);self.assertEqual(Order.objects.count(),0)
        self.assertEqual(self.client.session[DRAFT_KEY]['fields']['note'],self.data['note'])

    def test_draft_restores_all_fields(self):
        self.save_draft()
        r=self.client.get('/booking/?view=new')
        for key,value in self.data.items():self.assertEqual(str(r.context['form'][key].value()),value)

    def test_draft_is_owner_scoped(self):
        s=self.client.session;s[DRAFT_KEY]={'owner':self.manager.pk,'fields':{'name':'Foreign draft'}};s.save()
        self.assertNotContains(self.client.get('/booking/?view=new'),'Foreign draft')

    def test_normal_menu_has_no_booking_bar(self):
        self.save_draft()
        self.assertNotContains(self.client.get('/menu/'),'data-booking-menu-bar')

    def test_booking_menu_filter_and_detail_keep_context(self):
        self.save_draft()
        r=self.client.get('/menu/?from=booking')
        self.assertContains(r, 'data-booking-menu-done')
        self.assertContains(r, 'name="from" value="booking"')
        self.assertContains(self.client.get(reverse('customer_food_detail',args=[self.menu.pk])+'?from=booking'),'value="booking_menu"')

    def select_extras(self):
        top=Topping.objects.create(name='Bơ tỏi',price=15);top.menu_items.add(self.menu)
        combo=Combo.objects.create(name='Combo cho hai người',price=150)
        ComboItem.objects.create(combo=combo,menu_item=self.menu,quantity=2)
        self.client.post(reverse('update_cart',args=[self.menu.pk]),{'quantity':2,'topping_selection':'1','toppings':[top.pk]},HTTP_ACCEPT='application/json')
        self.client.post(reverse('combo_cart',args=[combo.pk]),{'return_to':'booking_menu'})
        return top,combo

    def test_return_preserves_quantity_topping_combo_and_draft(self):
        self.save_draft();top,combo=self.select_extras()
        r=self.client.get('/booking/?view=new')
        self.assertEqual(r.context['selected_food'][0]['quantity'],2)
        self.assertEqual(r.context['selected_food'][0]['selected_toppings'][0].pk,top.pk)
        self.assertEqual(r.context['combo_rows'][0]['combo'].pk,combo.pk)
        self.assertEqual(r.context['form']['note'].value(),self.data['note'])

    def confirm(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/booking/?view=new',{**self.data,'intent':'confirm'})
        # TestCase defers commit past SessionMiddleware; persist the executed callback's session.
        response.wsgi_request.session.save()
        return response

    def test_empty_cart_optional_and_clears_draft(self):
        self.save_draft();r=self.confirm()
        self.assertEqual(r.status_code,302);self.assertEqual(Booking.objects.count(),1)
        self.assertNotIn(DRAFT_KEY,self.client.session);self.assertEqual(BookingItem.objects.count(),0)

    def test_snapshots_once_and_reload_does_not_write(self):
        self.save_draft();self.select_extras();r=self.confirm()
        count=BookingItem.objects.count();self.assertGreater(count,0)
        self.client.get(r.url);self.client.get(r.url)
        self.assertEqual(Booking.objects.count(),1);self.assertEqual(BookingItem.objects.count(),count)
        self.assertEqual(Order.objects.count(),0);self.assertEqual(Invoice.objects.count(),0);self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(self.client.session['cart'],{})

    def test_failure_retains_draft_and_cart(self):
        self.save_draft();self.select_extras()
        self.table.is_active=False;self.table.save()
        r=self.confirm();self.assertEqual(r.status_code,200)
        self.assertIn(DRAFT_KEY,self.client.session);self.assertTrue(self.client.session['cart'])
        self.assertEqual(Booking.objects.count(),0)

    def test_confirmation_has_payment_disabled_and_no_form(self):
        r=self.client.get(self.confirm().url)
        self.assertContains(r,'data-booking-confirmation');self.assertContains(r,'CHƯA THỂ THANH TOÁN')
        self.assertNotContains(r,'id="booking-form"');self.assertNotContains(r,'id="booking-list"')

    def test_foreign_confirmation_is_404(self):
        b=self.reserve(user=self.manager)
        self.assertEqual(self.client.get('/booking/?view=success&id='+str(b.pk)).status_code,404)

    def test_malformed_confirmation_is_404(self):
        self.assertEqual(self.client.get('/booking/?view=success&id=invalid').status_code,404)

    def test_draft_navigation_requires_csrf(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True);client.force_login(self.customer)
        self.assertEqual(client.post('/booking/?view=new',{**self.data,'intent':'menu'}).status_code,403)

    def invoice(self):
        from .order_service import open_order_from_booking
        from .payment_service import issue_invoice
        b=self.reserve();o=open_order_from_booking(b.pk,actor=self.manager)
        Order.objects.filter(pk=o.pk).update(status='COMPLETED')
        i=issue_invoice(o.pk,actor=self.manager)
        return b,i

    def test_payable_invoice_uses_existing_owned_page(self):
        b,i=self.invoice();r=self.client.get('/booking/?view=mine')
        self.assertContains(r,'THANH TOÁN NGAY');self.assertContains(r,reverse('customer_invoice_detail',args=[i.pk]))

    def test_paid_invoice_status(self):
        b,i=self.invoice();Invoice.objects.filter(pk=i.pk).update(status='PAID')
        r=self.client.get('/booking/?view=mine');self.assertContains(r,'ĐÃ THANH TOÁN');self.assertNotContains(r,'THANH TOÁN NGAY')

    def test_pending_payment_has_tracking_without_second_pay_cta(self):
        from .payment_service import create_payment
        import uuid
        b,i=self.invoice();create_payment(invoice_id=i.pk,actor=self.customer,customer_initiated=True,payment_method='CASH',request_key=uuid.uuid4())
        r=self.client.get('/booking/?view=mine');self.assertContains(r,'Chờ thanh toán');self.assertNotContains(r,'THANH TOÁN NGAY')

    def test_invoice_and_payment_owner_checks_retained(self):
        b,i=self.invoice();self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('customer_invoice_detail',args=[i.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('customer_payment_start',args=[i.pk]),{}).status_code,404)

    def test_mobile_hooks_and_done_is_read_only(self):
        self.save_draft();self.assertContains(self.client.get('/menu/?from=booking'),'booking-menu-mode')
        self.client.get('/booking/?view=new');self.assertFalse(Booking.objects.exists())
