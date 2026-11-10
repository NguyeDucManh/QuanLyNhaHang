"""SEO regression tests; all data lives in a separate PostgreSQL test database."""
import json
import re
from datetime import time
from decimal import Decimal
from html import unescape
from unittest.mock import patch
from xml.etree import ElementTree
from django.test import Client, TestCase, override_settings
from django.urls import path, reverse
from restaurant_system.urls import urlpatterns as application_urls
from .models import Category, MenuItem, RestaurantInfo
from .seo import PUBLIC_PAGES

handler404 = 'restaurant_system.errors.page_not_found'


def broken_view(request):
    raise RuntimeError('private-exception-detail')


urlpatterns = [path('raise-error/', broken_view), *application_urls]


def head(response):
    html = response.content.decode()
    return {
        'titles': re.findall(r'<title>(.*?)</title>', html, re.S),
        'description': unescape(re.search(r'<meta name="description" content="([^"]*)"', html)[1]),
        'canonical': re.findall(r'<link rel="canonical" href="([^"]*)"', html),
        'graph': [row for data in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S) for row in json.loads(data)['@graph']],
        'html': html,
    }


@override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://smart-restaurant-demo.onrender.com')
class SEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name='Món QA', slug='mon-qa')
        hidden = Category.objects.create(name='Ẩn QA', slug='an-qa', is_active=False)
        cls.dish = MenuItem.objects.create(name='Món có giá QA', category=category, price=Decimal('125000'),
            description='Mô tả thực tế trong fixture QA.', image='ui/images/dish-placeholder.svg')
        cls.unpriced = MenuItem.objects.create(name='Món chưa niêm yết QA', category=category, image='ui/images/dish-placeholder.svg')
        cls.hidden = MenuItem.objects.create(name='Ngừng bán QA', category=category, price=1, is_available=False, image='ui/images/dish-placeholder.svg')
        cls.hidden_category = MenuItem.objects.create(name='Món ẩn QA', category=hidden, price=1, image='ui/images/dish-placeholder.svg')
        cls.info = RestaurantInfo.objects.create(name='Nhà hàng QA', address='Địa chỉ QA', phone='0900000000', opening_time=time(9), closing_time=time(22))

    def test_public_pages_have_unique_metadata_and_one_h1(self):
        titles, descriptions = [], []
        for name in PUBLIC_PAGES:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                data = head(response)
                self.assertEqual(len(data['titles']), 1)
                self.assertEqual(len(re.findall(r'<h1\b', data['html'])), 1)
                self.assertEqual(data['canonical'], ['https://smart-restaurant-demo.onrender.com' + reverse(name)])
                self.assertGreater(len(data['description']), 50)
                self.assertContains(response, '<meta name="robots" content="index, follow">')
                self.assertContains(response, 'property="og:title"')
                self.assertContains(response, 'name="twitter:card" content="summary_large_image"')
                titles += data['titles']; descriptions.append(data['description'])
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(len(descriptions), len(set(descriptions)))

    def test_detail_uses_real_price_description_and_breadcrumbs(self):
        response = self.client.get(reverse('customer_food_detail', args=[self.dish.pk]))
        data = head(response)
        self.assertEqual(data['titles'], [self.dish.name + ' | Smart Restaurant'])
        self.assertEqual(data['description'], self.dish.description)
        dish = next(row for row in data['graph'] if row['@type'] == 'MenuItem')
        self.assertEqual(Decimal(dish['offers']['price']), self.dish.price)
        self.assertEqual(dish['offers']['priceCurrency'], 'VND')
        self.assertNotIn('aggregateRating', dish)
        crumbs = next(row for row in data['graph'] if row['@type'] == 'BreadcrumbList')
        self.assertEqual([row['position'] for row in crumbs['itemListElement']], [1, 2, 3])

    def test_menu_schema_contains_only_visible_items_and_no_fake_prices(self):
        data = head(self.client.get('/menu/'))
        menu = next(row for row in data['graph'] if row['@type'] == 'Menu')
        self.assertEqual({row['name'] for row in menu['hasMenuItem']}, {self.dish.name, self.unpriced.name})
        self.assertNotIn('offers', next(row for row in menu['hasMenuItem'] if row['name'] == self.unpriced.name))

    def test_restaurant_schema_requires_active_info(self):
        info = next(row for row in head(self.client.get('/'))['graph'] if row['@type'] == 'Restaurant')
        self.assertEqual(info['address'], self.info.address)
        self.assertNotIn('aggregateRating', info)
        self.assertNotIn('priceRange', info)
        RestaurantInfo.objects.update(is_active=False)
        self.assertFalse(any(row['@type'] == 'Restaurant' for row in head(self.client.get('/'))['graph']))

    def test_placeholder_restaurant_contacts_never_enter_schema(self):
        RestaurantInfo.objects.update(name='Nhà hàng DEMO', address='123 Đường DEMO', phone='0000000000', email='demo@restaurant.example')
        data = head(self.client.get('/'))
        self.assertFalse(any(row['@type'] == 'Restaurant' for row in data['graph']))
        self.assertNotIn('demo@', json.dumps(data['graph']))
        RestaurantInfo.objects.update(name='Nhà hàng có tên thật')
        info = next(row for row in head(self.client.get('/'))['graph'] if row['@type'] == 'Restaurant')
        self.assertNotIn('email', info)
        self.assertNotIn('telephone', info)
        self.assertNotIn('address', info)

    def test_canonical_ignores_host_and_query_variants_are_noindex(self):
        with override_settings(ALLOWED_HOSTS=['testserver', 'alternate.example']):
            response = self.client.get('/menu/?q=secret&from=booking', HTTP_HOST='alternate.example')
        self.assertEqual(head(response)['canonical'], ['https://smart-restaurant-demo.onrender.com/menu/'])
        self.assertIn('noindex', response['X-Robots-Tag'])
        self.assertNotIn('noindex', self.client.get('/menu/?utm_source=qa').get('X-Robots-Tag', ''))

    def test_private_routes_have_noindex_and_keep_authentication(self):
        for url in ['/login/', '/register/', '/cart/', '/booking/', '/account/', '/staff/', '/management/', '/ai/chat/', '/booking/availability/', '/stripe/webhook/']:
            with self.subTest(url=url):
                self.assertIn('noindex', self.client.get(url)['X-Robots-Tag'])
        self.assertEqual(self.client.get('/management/').status_code, 302)
        self.assertEqual(head(self.client.get('/login/'))['canonical'], [])
        self.assertEqual(head(self.client.get('/login/'))['graph'], [])

    def test_sitemap_only_canonical_public_urls(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/xml', response['Content-Type'])
        xml = ElementTree.fromstring(response.content)
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [row.text for row in xml.findall('s:url/s:loc', ns)]
        expected = [reverse(name) for name in PUBLIC_PAGES]
        expected += [reverse('customer_food_detail', args=[item.pk]) for item in [self.dish, self.unpriced]]
        self.assertCountEqual(urls, ['https://smart-restaurant-demo.onrender.com' + path for path in expected])
        for path in expected:
            self.assertEqual(self.client.get(path).status_code, 200)
        with override_settings(ALLOWED_HOSTS=['testserver', 'alternate.example']):
            self.assertNotContains(self.client.get('/sitemap.xml', HTTP_HOST='alternate.example'), 'alternate.example')

    def test_robots_and_staging_noindex(self):
        response = self.client.get('/robots.txt')
        self.assertContains(response, 'Sitemap: https://smart-restaurant-demo.onrender.com/sitemap.xml')
        self.assertIn('text/plain', response['Content-Type'])
        self.assertEqual(self.client.head('/robots.txt').status_code, 200)
        with override_settings(SEO_INDEXING_ENABLED=False):
            self.assertContains(self.client.get('/robots.txt'), 'Disallow: /')
            self.assertIn('noindex', self.client.get('/')['X-Robots-Tag'])

    def test_schema_cannot_terminate_script_element(self):
        MenuItem.objects.filter(pk=self.dish.pk).update(description='</script><script>alert(1)</script> & text')
        response = self.client.get(reverse('customer_food_detail', args=[self.dish.pk]))
        scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)
        self.assertEqual(len(scripts), 1)
        self.assertNotIn('<', scripts[0])
        self.assertEqual(json.loads(scripts[0])['@context'], 'https://schema.org')

    @override_settings(DEBUG=False, ROOT_URLCONF=__name__)
    def test_error_status_noindex_no_database_or_exception_leak(self):
        with self.assertNumQueries(0):
            response = self.client.get('/nonexistent-qa/')
        self.assertContains(response, 'Không tìm thấy trang', status_code=404)
        self.assertIn('noindex', response['X-Robots-Tag'])
        response = Client(raise_request_exception=False).get('/raise-error/')
        self.assertContains(response, 'Hệ thống tạm gián đoạn', status_code=500)
        self.assertNotContains(response, 'private-exception-detail', status_code=500)
        self.assertIn('noindex', response['X-Robots-Tag'])

    def test_home_keeps_ai_lazy(self):
        with patch('customers.ai.hybrid_service.recommend', side_effect=AssertionError('unused ML')) as recommend:
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'name="guests" type="number" min="1" max="20"')
            recommend.assert_not_called()

    @override_settings(GOOGLE_SITE_VERIFICATION='qa-verification-token')
    def test_optional_search_console_verification_only_on_home(self):
        self.assertContains(self.client.get('/'), 'content="qa-verification-token"')
        self.assertNotContains(self.client.get('/menu/'), 'qa-verification-token')

    def test_csrf_still_blocks_mutations(self):
        response = Client(enforce_csrf_checks=True).post(reverse('update_cart', args=[self.dish.pk]), {'quantity': 1})
        self.assertEqual(response.status_code, 403)
        self.assertIn('noindex', response['X-Robots-Tag'])

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_proxy_https_redirect_without_loop(self):
        self.assertEqual(self.client.get('/menu/').status_code, 301)
        self.assertEqual(self.client.get('/menu/', HTTP_X_FORWARDED_PROTO='https').status_code, 200)

    def test_hidden_dish_404_noindex(self):
        for item in [self.hidden, self.hidden_category]:
            response = self.client.get(reverse('customer_food_detail', args=[item.pk]))
            self.assertEqual(response.status_code, 404)
            self.assertIn('noindex', response['X-Robots-Tag'])
