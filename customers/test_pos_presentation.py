"""Presentation invariants: real table identities, counters and access isolation."""
from django.contrib.auth.models import User, Permission
from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta
from .models import Area, RestaurantTable, Booking
from .pos_presentation import workspace


class PosPresentationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('pos-review', password='test-only')
        self.area = Area.objects.create(name='Real area')
        self.request = RequestFactory().get('/staff/')
        self.request.user = self.user

    def test_empty_database_has_no_generated_tables(self):
        data = workspace(self.request)
        self.assertEqual(data['pos_tables'], [])
        self.assertEqual(sum(data['pos_counts'].values()), 0)

    def test_exact_table_ids_and_counters_include_reservation_and_inactive(self):
        tables = [RestaurantTable.objects.create(area=self.area, code=f'R{i}', capacity=4, status=status)
                  for i, status in enumerate(['AVAILABLE', 'OCCUPIED', 'MAINTENANCE', 'AVAILABLE'])]
        now = timezone.now()
        Booking.objects.create(user=self.user, table=tables[3], name='Actual reservation', phone='0901234567',
                               date=now.date(), time=now.time(), guests=2, status='CONFIRMED',
                               start_time=now-timedelta(minutes=10), end_time=now+timedelta(hours=1))
        data = workspace(self.request)
        self.assertEqual({t.pk for t in data['pos_tables']}, {t.pk for t in tables})
        for status, count in data['pos_counts'].items():
            self.assertEqual(count, sum(t.visual_status == status for t in data['pos_tables']))
        self.assertEqual(data['pos_counts']['RESERVED'], 1)
        self.area.is_active = False
        self.area.save()
        self.assertEqual(workspace(self.request)['pos_counts']['INACTIVE'], 4)

    def test_selection_uses_actual_primary_key_and_empty_table_has_no_order(self):
        table = RestaurantTable.objects.create(area=self.area, code='OnlyRealTable', capacity=2)
        self.request.GET = {'table': str(table.pk)}
        selected = workspace(self.request)['pos_selected']
        self.assertEqual(selected.pk, table.pk)
        self.assertIsNone(selected.live_order)

    def test_no_permission_exposes_no_table_data(self):
        self.request.user = User.objects.create_user('pos-no-access')
        self.assertEqual(workspace(self.request), {})

    def test_menu_permission_is_independent_of_table_permission(self):
        from .rbac import assign_role
        from .models import Category, MenuItem
        user = User.objects.create_user('menu-only-staff')
        assign_role(user, 'STAFF')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='customers', codename='view_menuitem'))
        category = Category.objects.create(name='Visible category', slug='visible-category')
        item = MenuItem.objects.create(name='Permitted menu item', category=category, price=25000, image='test-food.jpg')
        self.request.user = User.objects.get(pk=user.pk)
        data = workspace(self.request)
        self.assertFalse(data['pos_enabled'])
        self.assertEqual(data['pos_tables'], [])
        self.assertEqual([row['id'] for row in data['pos_dishes']], [item.pk])

    def test_order_permission_is_independent_of_table_permission(self):
        from .rbac import assign_role
        user = User.objects.create_user('orders-only-staff')
        assign_role(user, 'STAFF')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='customers', codename='view_order'))
        self.request.user = User.objects.get(pk=user.pk)
        data = workspace(self.request)
        self.assertTrue(data['pos_can_orders'])
        self.assertFalse(data['pos_enabled'])
        self.assertEqual(data['pos_tables'], [])
