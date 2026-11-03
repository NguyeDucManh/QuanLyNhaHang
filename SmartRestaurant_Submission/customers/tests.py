from datetime import timedelta
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Booking, Category, MenuItem, Area, RestaurantTable
from django.core.management import call_command
from io import StringIO
from .rbac import assign_role, get_role, get_assigned_role


class SeedMenuMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        call_command("seed_menu", stdout=StringIO())



class CustomerFlowTests(SeedMenuMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.password = "Restaurant-test-93!"
        cls.customer = User.objects.create_user("customer", password=cls.password, first_name="Khách hàng")
        cls.staff = User.objects.create_user("manager", password=cls.password, is_staff=True)
        cls.superuser = User.objects.create_user("owner", password=cls.password, is_superuser=True)
        cls.inactive = User.objects.create_user("inactive", password=cls.password, is_staff=True, is_active=False)
        assign_role(cls.customer, "CUSTOMER")
        assign_role(cls.staff, "MANAGER")

    def test_public_pages_render(self):
        for url in ("/", "/menu/", "/login/", "/register/", "/cart/", "/about/", "/offers/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get("/"), "MÓN ĂN NỔI BẬT")

    def test_login_redirects_by_role(self):
        for user, destination in ((self.customer, "/"), (self.staff, "/management/"), (self.superuser, "/management/")):
            with self.subTest(user=user.username):
                self.client.logout()
                response = self.client.post("/login/?next=https://example.com", {"username": user.username, "password": self.password})
                self.assertRedirects(response, destination)

    def test_admin_requires_authentication_and_role(self):
        self.assertRedirects(self.client.get("/management/"), "/login/?next=/management/")
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get("/management/").status_code, 403)
        self.client.force_login(self.staff)
        response = self.client.get("/management/")
        self.assertContains(response, "admin-identity")
        self.assertContains(response, "manager")
        self.assertRedirects(self.client.get("/"), "/management/")

    def test_invalid_and_inactive_logins_are_rejected(self):
        for username, password in (("manager", "wrong"), ("inactive", self.password)):
            response = self.client.post("/login/", {"username": username, "password": password})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("_auth_user_id", self.client.session)
            self.assertTrue(response.context["form"].errors)

    def test_registration_cannot_set_admin_role(self):
        response = self.client.post("/register/", {
            "username": "newcustomer", "first_name": "Khách mới", "email": "guest@example.com",
            "password1": self.password, "password2": self.password, "is_staff": "true", "is_superuser": "true",
        })
        self.assertRedirects(response, "/")
        user = User.objects.get(username="newcustomer")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(self.client.get("/management/").status_code, 403)

    def test_duplicate_and_weak_registration_rejected(self):
        response = self.client.post("/register/", {
            "username": "customer", "first_name": "Khách", "email": "guest@example.com",
            "password1": "123", "password2": "123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(User.objects.count(), 4)

    def test_logout_requires_post(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertRedirects(self.client.post("/logout/"), "/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_protects_login_and_cart(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/login/", {"username": "manager", "password": self.password}).status_code, 403)
        self.assertEqual(client.post("/cart/1/").status_code, 403)
        client.get("/login/")
        token = client.cookies["csrftoken"].value
        response = client.post("/login/", {"username": "customer", "password": self.password, "csrfmiddlewaretoken": token})
        self.assertRedirects(response, "/")

    def test_cart_prices_and_quantities_from_server(self):
        response = self.client.post("/cart/1/", {"price": "1"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["count"], 1)
        self.client.post("/cart/1/")
        self.assertContains(self.client.get("/cart/"), "578.000")
        self.client.post("/cart/1/", {"action": "decrease"})
        self.assertEqual(self.client.session["cart"]["1"], 1)
        self.client.post("/cart/1/", {"action": "remove"})
        self.assertEqual(self.client.session["cart"], {})
        self.assertEqual(self.client.post("/cart/999/").status_code, 404)
        self.assertEqual(self.client.get("/cart/1/").status_code, 405)

    def test_cart_isolated_per_session(self):
        self.client.post("/cart/1/")
        self.assertNotIn("cart", Client().session)

    def test_menu_search_without_accents_and_category(self):
        response = self.client.get("/menu/", {"q": "sup bao ngu", "category": "sup"})
        self.assertEqual([d["id"] for d in response.context["dishes"]], [1])
        response = self.client.get("/menu/", {"q": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_booking_saved_and_scoped_to_customer(self):
        area = Area.objects.create(name="Booking regression fixture")
        RestaurantTable.objects.create(area=area, code="TEST-4", capacity=4)
        self.assertRedirects(self.client.get("/booking/"), "/login/?next=/booking/")
        self.client.force_login(self.customer)
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.client.post("/booking/", {
            "name": "Khách hàng", "phone": "0912345678", "date": tomorrow.isoformat(),
            "time": "19:00", "guests": 4, "note": "Gần cửa sổ", "user": self.staff.pk,
        })
        self.assertRedirects(response, "/booking/")
        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.customer)
        self.assertEqual(booking.guests, 4)
        self.client.force_login(self.staff)
        self.assertEqual(list(self.client.get("/booking/").context["reservations"]), [])

    def test_booking_rejects_past_dates_and_invalid_guests(self):
        self.client.force_login(self.customer)
        response = self.client.post("/booking/", {
            "name": "Khách", "phone": "not-a-phone", "date": "2000-01-01", "time": "19:00", "guests": 21,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Booking.objects.count(), 0)


class OfficialCatalogTests(SeedMenuMixin, TestCase):
    def test_all_products_render_and_categories_filter(self):
        from .menu_service import get_dishes, get_categories
        DISHES, CATEGORIES = get_dishes(), get_categories()
        response = self.client.get('/menu/')
        self.assertEqual(len(response.context['dishes']), 45)
        self.assertEqual(len({d['image_path'] for d in DISHES}), 45)
        for dish in DISHES:
            with self.subTest(product=dish['id']):
                self.assertContains(response, dish['name'])
                detail = self.client.get(f"/menu/{dish['id']}/")
                self.assertContains(detail, dish['name'])
                self.assertContains(detail, dish['category_label'])
                self.assertContains(detail, dish['price_display'])
                self.assertContains(detail, dish['image'])
        for key, label in CATEGORIES[1:]:
            with self.subTest(category=label):
                filtered = self.client.get('/menu/', {'category': key})
                self.assertTrue(filtered.context['dishes'])
                self.assertTrue(all(d['category_label'] == label for d in filtered.context['dishes']))
        self.assertEqual(self.client.get('/menu/999/').status_code, 404)
        self.assertNotContains(response, 'images.unsplash.com')

    def test_admin_receives_identical_catalog(self):
        import json, re
        from .menu_service import get_dishes
        DISHES = get_dishes()
        manager = User.objects.create_user('catalog-manager', is_staff=True)
        assign_role(manager, 'MANAGER')
        self.client.force_login(manager)
        response = self.client.get('/management/')
        from .menu_service import get_dishes
        DISHES = get_dishes(include_unavailable=True)
        self.assertEqual(response.context['dishes'], DISHES)
        payload = re.search(r'<script id="restaurant-catalog" type="application/json">(.*?)</script>', response.content.decode(), re.S)
        from django.core.serializers.json import DjangoJSONEncoder
        self.assertEqual(json.loads(payload[1]), json.loads(json.dumps(DISHES, cls=DjangoJSONEncoder)))

    def test_unpriced_drinks_and_official_cart_prices(self):
        self.client.post('/cart/36/')
        self.client.post('/cart/1/', {'price': '1'})
        self.client.post('/cart/1/')
        response = self.client.get('/cart/')
        self.assertContains(response, 'Rượu vang đỏ Bordeaux (18+)')
        self.assertContains(response, 'Liên hệ')
        self.assertContains(response, '578.000')
        self.assertTrue(response.context['has_unpriced'])
        self.assertEqual(response.context['total'], '578.000')

    def test_legacy_demo_cart_is_not_remapped(self):
        session = self.client.session
        session['cart'] = {'1': 3}
        session.save()
        response = self.client.get('/cart/')
        self.assertEqual(response.context['rows'], [])
        self.client.post('/cart/1/')
        self.assertEqual(self.client.session['cart'], {'1': 1})


from django.contrib.staticfiles.testing import StaticLiveServerTestCase


class CatalogImageHTTPTests(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def setUp(self):
        call_command("seed_rbac", stdout=StringIO())
        call_command("seed_menu", stdout=StringIO())

    def test_every_image_url_is_served_without_404(self):
        from urllib.request import build_opener, ProxyHandler
        from django.contrib.staticfiles import finders
        from pathlib import Path
        from .menu_service import get_dishes
        DISHES = get_dishes()
        files = set(p.name for p in Path('static/Image').iterdir() if p.is_file())
        mapped = set()
        for dish in DISHES:
            with self.subTest(product=dish['id'], image=dish['image_path']):
                resolved = finders.find(dish['image_path'])
                self.assertIsNotNone(resolved)
                mapped.add(Path(resolved).name)
                with build_opener(ProxyHandler({})).open(self.live_server_url + dish['image'], timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), 'image/jpeg')
                    self.assertTrue(response.read().startswith(b'\xff\xd8\xff'))
        self.assertEqual(mapped, files)





class MenuDatabaseTests(SeedMenuMixin, TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('menu-staff', is_staff=True)
        assign_role(self.staff, 'ADMIN')
        self.client.force_login(self.staff)

    def payload(self, item=None, **overrides):
        item = item or MenuItem.objects.get(pk=1)
        data = {'name': item.name, 'category': item.category_id, 'price': item.price or '',
                'image': item.image, 'description': item.description, 'is_available': 'on'}
        data.update(overrides)
        return data

    def test_seed_exact_mapping_and_idempotence(self):
        from .catalog import PRODUCTS  # Chỉ kiểm chứng seed backup, không runtime.
        from decimal import Decimal
        before = list(MenuItem.objects.values())
        call_command('seed_menu', stdout=StringIO())
        self.assertEqual(list(MenuItem.objects.values()), before)
        self.assertEqual(MenuItem.objects.count(), 45)
        self.assertEqual(Category.objects.count(), len({r[2] for r in PRODUCTS}))
        for item_id, name, category, price, image in PRODUCTS:
            item = MenuItem.objects.select_related('category').get(pk=item_id)
            self.assertEqual((item.name, item.category.name, item.price, item.image),
                             (name, category, Decimal(price) if price is not None else None, image))

    def test_admin_edit_immediately_changes_customer_and_cart(self):
        self.client.post('/cart/1/')
        item = MenuItem.objects.get(pk=1)
        response = self.client.post('/management/menu/1/edit/', self.payload(item, price='310123.50', description='Mô tả từ database'))
        self.assertRedirects(response, '/management/#menu')
        self.assertContains(self.client.get('/menu/1/'), '310.123,50')
        self.assertContains(self.client.get('/menu/1/'), 'Mô tả từ database')
        self.client.post('/cart/1/', {'price': '1'})
        self.assertContains(self.client.get('/cart/'), '620.247')
        item.refresh_from_db()
        self.assertEqual(str(item.price), '310123.50')
        call_command('seed_menu', stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(str(item.price), '310123.50')

    def test_add_item_sequence_and_category_change(self):
        response = self.client.post('/management/menu/add/', self.payload(name='Món thử trong test', price='200000'))
        self.assertRedirects(response, '/management/#menu')
        item = MenuItem.objects.get(name='Món thử trong test')
        self.assertGreater(item.pk, 45)
        other = Category.objects.exclude(pk=item.category_id).first()
        self.client.post(f'/management/menu/{item.pk}/edit/', self.payload(item, category=other.pk))
        self.client.logout()
        self.assertContains(self.client.get('/menu/', {'category': other.slug, 'q': 'mon thu'}), item.name)

    def test_disable_hides_item_and_prevents_cart_add_without_deleting(self):
        self.client.post('/cart/1/')
        self.assertEqual(self.client.get('/management/menu/1/availability/').status_code, 405)
        self.client.post('/management/menu/1/availability/', {'is_available': 'false'})
        self.assertEqual(MenuItem.objects.count(), 45)
        self.assertFalse(MenuItem.objects.get(pk=1).is_available)
        self.assertEqual(self.client.get('/menu/1/').status_code, 404)
        self.assertEqual(self.client.post('/cart/1/').status_code, 400)
        self.assertEqual(self.client.get('/cart/').context['rows'], [])
        data = self.client.get('/management/').context['dishes']
        self.assertEqual(len(data), 45)
        self.assertEqual(data[0]['status'], 'Ngừng phục vụ')
        self.client.post('/management/menu/1/availability/', {'is_available': 'true'})
        self.assertEqual(self.client.get('/menu/1/').status_code, 200)

    def test_inactive_category_hides_products(self):
        category = MenuItem.objects.get(pk=1).category
        category.is_active = False
        category.save()
        self.assertEqual(self.client.get('/menu/1/').status_code, 404)
        self.assertEqual(self.client.post('/cart/1/').status_code, 400)
        self.assertFalse(any(d['category'] == category.slug for d in self.client.get('/menu/').context['dishes']))

    def test_admin_mutations_require_role_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.post('/management/menu/add/', self.payload(name='Unauthorized')).status_code, 302)
        customer = User.objects.create_user('menu-customer')
        self.client.force_login(customer)
        for url in ('/management/menu/add/', '/management/menu/1/edit/', '/management/menu/1/availability/'):
            self.assertEqual(self.client.post(url, self.payload()).status_code, 403)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.staff)
        self.assertEqual(protected.post('/management/menu/1/availability/', {'is_available': 'false'}).status_code, 403)
        self.assertTrue(MenuItem.objects.get(pk=1).is_available)

    def test_invalid_price_image_and_duplicate_rejected(self):
        for overrides in ({'price': '-1'}, {'image': '../db.sqlite3'}, {'image': 'https://example.com/image.jpg'}, {'name': MenuItem.objects.get(pk=2).name}):
            with self.subTest(overrides=overrides):
                response = self.client.post('/management/menu/1/edit/', self.payload(**overrides))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
        self.assertEqual(MenuItem.objects.get(pk=1).name, 'Súp bào ngư hải sâm')

    def test_runtime_database_only_without_backup_import(self):
        import sys
        from unittest.mock import patch
        item = MenuItem.objects.get(pk=1)
        item.name = 'Tên cập nhật từ PostgreSQL'
        item.save()
        with patch.dict(sys.modules, {'customers.catalog': None}):
            for route in ('/', '/menu/', '/menu/1/', '/offers/', '/cart/', '/management/'):
                self.assertEqual(self.client.get(route, follow=True).status_code, 200)
            self.assertContains(self.client.get('/menu/'), item.name)



class RBACTests(SeedMenuMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Group
        super().setUpTestData()
        cls.password = 'Rbac-testing-pass-73!'
        cls.users = {}
        for role in ('ADMIN', 'MANAGER', 'STAFF', 'CUSTOMER'):
            user = User.objects.create_user(role.lower(), password=cls.password, email=role.lower()+'@example.test')
            assign_role(user, role)
            cls.users[role] = user
        cls.owner = User.objects.create_superuser('rbac-owner', password=cls.password)

    def edit_url(self, user):
        return reverse('admin_account_edit', args=[user.pk])

    def test_registration_always_assigns_customer_and_hashed_password(self):
        from django.contrib.auth.models import Group
        response = self.client.post('/register/', {
            'username': 'newrbac', 'first_name': 'Customer', 'email': 'new@example.test',
            'password1': self.password, 'password2': self.password,
            'role': 'ADMIN', 'groups': [Group.objects.get(name='ADMIN').pk],
            'is_staff': True, 'is_superuser': True,
        })
        self.assertRedirects(response, '/')
        user = User.objects.get(username='newrbac')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['CUSTOMER'])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))

    def test_login_destination_for_each_role(self):
        for role, url in [('ADMIN', '/management/'), ('MANAGER', '/management/'), ('STAFF', '/staff/'), ('CUSTOMER', '/')]:
            with self.subTest(role=role):
                self.client.logout()
                self.assertRedirects(self.client.post('/login/', {'username': self.users[role].username, 'password': self.password}), url)

    def test_management_and_staff_access(self):
        self.assertRedirects(self.client.get('/management/'), '/login/?next=/management/')
        for role in ('ADMIN', 'MANAGER', 'STAFF', 'CUSTOMER'):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get('/management/').status_code, 200 if role in ('ADMIN','MANAGER','STAFF') else 403)
            self.assertEqual(self.client.get('/staff/').status_code, 403 if role == 'CUSTOMER' else 200)

    def test_is_staff_flag_alone_never_grants_management_or_admin(self):
        user = User.objects.create_user('flag-only', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/management/').status_code, 403)
        self.assertEqual(self.client.post('/management/menu/1/availability/', {'is_available':'false'}).status_code, 403)
        self.assertEqual(self.client.get('/django-admin/').status_code, 302)
        self.assertTrue(MenuItem.objects.get(pk=1).is_available)

    def test_manager_menu_permissions_and_staff_explicit_permission(self):
        from django.contrib.auth.models import Permission
        manager = self.users['MANAGER']
        self.client.force_login(manager)
        self.assertEqual(len(self.client.get('/management/').context['dishes']), 45)
        for route in ('/management/menu/add/', '/management/menu/1/edit/'):
            self.assertEqual(self.client.post(route, {'is_available':'false'}).status_code, 200)
        self.assertRedirects(self.client.post('/management/menu/1/availability/', {'is_available':'true'}),'/management/#menu')
        staff = self.users['STAFF']
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='customers',codename='view_menuitem'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/management/').status_code, 200)
        self.assertEqual(self.client.post('/management/menu/1/availability/', {'is_available':'false'}).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='customers',codename='change_menuitem'))
        self.assertRedirects(self.client.post('/management/menu/1/availability/', {'is_available':'false'}), '/management/#menu')
        self.assertFalse(MenuItem.objects.get(pk=1).is_available)

    def test_admin_account_list_search_and_password_not_exposed(self):
        self.client.force_login(self.users['ADMIN'])
        response = self.client.get('/management/accounts/', {'q':'staff@example.test'})
        self.assertContains(response, 'staff@example.test')
        self.assertNotContains(response, 'customer@example.test')
        self.assertNotContains(response, self.users['STAFF'].password)
        self.assertNotContains(response, self.password)
        self.assertContains(response, 'STAFF')

    def test_admin_assign_role_and_lock_unlock_without_changing_password(self):
        target = self.users['CUSTOMER']
        password_hash = target.password
        self.client.force_login(self.users['ADMIN'])
        self.assertRedirects(self.client.post(self.edit_url(target), {'role':'MANAGER','is_active':'on','is_staff':'on','is_superuser':'on','password':'plaintext'}), '/management/accounts/')
        target.refresh_from_db()
        self.assertEqual(get_role(target), 'MANAGER')
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertEqual(target.password, password_hash)
        self.client.post(self.edit_url(target), {'role':'MANAGER'})
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertEqual(get_assigned_role(target), 'MANAGER')
        locked_client = Client()
        response = locked_client.post('/login/', {'username':target.username,'password':self.password})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', locked_client.session)
        self.client.post(self.edit_url(target), {'role':'MANAGER','is_active':'on'})
        self.assertTrue(User.objects.get(pk=target.pk).is_active)
        self.assertRedirects(locked_client.post('/login/', {'username':target.username,'password':self.password}), '/management/')

    def test_locked_existing_session_loses_access(self):
        manager_client = Client()
        manager_client.force_login(self.users['MANAGER'])
        self.client.force_login(self.users['ADMIN'])
        self.client.post(self.edit_url(self.users['MANAGER']), {'role':'MANAGER'})
        self.assertRedirects(manager_client.get('/management/'), '/login/?next=/management/')

    def test_non_admin_cannot_escalate_even_with_auth_permission(self):
        from django.contrib.auth.models import Permission
        for role in ('MANAGER','STAFF','CUSTOMER'):
            user = self.users[role]
            user.user_permissions.add(Permission.objects.get(content_type__app_label='auth', codename='change_user'))
            self.client.force_login(user)
            self.assertEqual(self.client.get('/management/accounts/').status_code, 403)
            self.assertEqual(self.client.post(self.edit_url(user), {'role':'ADMIN','is_active':'on','is_superuser':'on'}).status_code, 403)
            user.refresh_from_db()
            self.assertEqual(get_role(user), role)
            self.assertFalse(user.is_superuser)

    def test_superuser_protected_and_full_access(self):
        self.client.force_login(self.users['ADMIN'])
        self.assertEqual(self.client.get(self.edit_url(self.owner)).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url(self.owner), {'role':'CUSTOMER'}).status_code, 403)
        self.assertEqual(self.client.get(f'/django-admin/auth/user/{self.owner.pk}/change/').status_code, 403)
        self.client.force_login(self.owner)
        for route in ('/management/','/management/accounts/','/django-admin/','/management/menu/1/edit/'):
            self.assertEqual(self.client.get(route).status_code, 200)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_superuser)
        self.assertTrue(self.owner.is_active)

    def test_account_get_safe_and_csrf_required(self):
        target = self.users['CUSTOMER']
        self.client.force_login(self.users['ADMIN'])
        self.client.get(self.edit_url(target), {'role':'ADMIN','is_active':'on'})
        self.assertEqual(get_role(User.objects.get(pk=target.pk)), 'CUSTOMER')
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.users['ADMIN'])
        self.assertEqual(protected.post(self.edit_url(target), {'role':'ADMIN','is_active':'on'}).status_code, 403)
        self.assertEqual(get_role(User.objects.get(pk=target.pk)), 'CUSTOMER')

    def test_no_self_lock_or_self_demotion_and_invalid_role(self):
        admin_user = self.users['ADMIN']
        self.client.force_login(admin_user)
        for payload in ({'role':'ADMIN'}, {'role':'CUSTOMER','is_active':'on'}, {'role':'SUPERUSER','is_active':'on'}):
            response = self.client.post(self.edit_url(admin_user), payload)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            admin_user.refresh_from_db()
            self.assertTrue(admin_user.is_active)
            self.assertEqual(get_role(admin_user), 'ADMIN')

    def test_ambiguous_roles_fail_closed_and_seed_idempotent(self):
        from django.contrib.auth.models import Group
        snapshot = list(Group.objects.order_by('id').values_list('id','name'))
        call_command('seed_rbac', stdout=StringIO())
        call_command('seed_rbac', stdout=StringIO())
        self.assertEqual(list(Group.objects.order_by('id').values_list('id','name')), snapshot)
        staff = self.users['STAFF']
        staff.groups.add(Group.objects.get(name='ADMIN'))
        self.client.force_login(staff)
        self.assertIsNone(get_role(staff))
        self.assertEqual(self.client.get('/management/accounts/').status_code, 403)

    def test_role_change_revokes_access_in_existing_session(self):
        manager_client = Client()
        manager_client.force_login(self.users['MANAGER'])
        self.client.force_login(self.users['ADMIN'])
        self.client.post(self.edit_url(self.users['MANAGER']), {'role':'CUSTOMER','is_active':'on'})
        self.assertEqual(manager_client.get('/management/').status_code, 403)
        self.assertEqual(MenuItem.objects.count(), 45)
        self.assertEqual(Booking.objects.count(), 0)

    def test_legacy_seed_does_not_promote_staff_flag_to_admin(self):
        legacy = User.objects.create_user('legacy-flag', is_staff=True)
        call_command('seed_rbac', stdout=StringIO())
        legacy.refresh_from_db()
        self.assertEqual(get_role(legacy), 'STAFF')
        self.assertFalse(legacy.is_staff)
        self.assertFalse(legacy.is_superuser)

    def test_minimum_group_permissions_no_future_module_grants(self):
        from django.contrib.auth.models import Group
        from .rbac import MANAGER_PERMISSIONS
        self.assertEqual(set(Group.objects.get(name='MANAGER').permissions.values_list('codename', flat=True)), MANAGER_PERMISSIONS)
        from .rbac import STAFF_ORDER_PERMISSIONS, STAFF_PAYMENT_PERMISSIONS
        self.assertEqual(set(Group.objects.get(name='STAFF').permissions.values_list('codename',flat=True)), STAFF_ORDER_PERMISSIONS | STAFF_PAYMENT_PERMISSIONS)
        self.assertEqual(Group.objects.get(name='CUSTOMER').permissions.count(), 0)
        self.assertFalse(Group.objects.get(name='ADMIN').permissions.filter(codename='add_user').exists())
        self.assertFalse(Group.objects.get(name='ADMIN').permissions.filter(codename='delete_user').exists())


from django.test import SimpleTestCase


class EnvironmentConfigTests(SimpleTestCase):
    def test_dotenv_preserves_environment_precedence_and_quoted_values(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from restaurant_system.environment import load_environment
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'.env'
            path.write_text('# comment\nRBAC_TEST_VALUE="a#b=c"\nRBAC_TEST_OVERRIDE=file\n', encoding='utf-8')
            with patch.dict(os.environ, {'RBAC_TEST_OVERRIDE':'process'}, clear=False):
                os.environ.pop('RBAC_TEST_VALUE', None)
                load_environment(path)
                self.assertEqual(os.environ['RBAC_TEST_VALUE'], 'a#b=c')
                self.assertEqual(os.environ['RBAC_TEST_OVERRIDE'], 'process')

    def test_settings_use_environment_and_example_contains_no_password(self):
        import os
        from pathlib import Path
        from django.conf import settings
        source = (settings.BASE_DIR/'restaurant_system/settings.py').read_text(encoding='utf-8')
        example = (settings.BASE_DIR/'.env.example').read_text(encoding='utf-8')
        self.assertIn("os.environ['DB_PASSWORD']", source)
        if os.environ.get('DB_PASSWORD'):
            self.assertNotIn(os.environ['DB_PASSWORD'], example)
        self.assertIn('.env', (settings.BASE_DIR/'.gitignore').read_text(encoding='utf-8'))
