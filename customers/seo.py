"""Public SEO policy. Authentication and role checks remain in their existing views."""
import json
from types import SimpleNamespace
from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_safe
from .models import MenuItem


PUBLIC_PAGES = {
    'customer_home': ('Smart Restaurant | Thực đơn và đặt bàn trực tuyến',
                      'Khám phá thực đơn Smart Restaurant, xem món ăn, combo và ưu đãi đang phục vụ. Chọn món và đặt bàn trực tuyến theo nhu cầu của bạn.'),
    'customer_menu': ('Thực đơn | Smart Restaurant',
                      'Xem thực đơn Smart Restaurant với hình ảnh, giá niêm yết và thông tin từng món. Tìm kiếm, chọn món và chuẩn bị cho bữa ăn của bạn.'),
    'customer_about': ('Thông tin nhà hàng | Smart Restaurant',
                       'Tìm hiểu Smart Restaurant, thông tin liên hệ, địa chỉ và giờ mở cửa được nhà hàng cập nhật.'),
    'customer_offers': ('Ưu đãi đang áp dụng | Smart Restaurant',
                        'Xem ưu đãi Smart Restaurant đang áp dụng, mã khuyến mãi và điều kiện sử dụng được nhà hàng công bố.'),
    'customer_combos': ('Combo nhà hàng | Smart Restaurant',
                        'Khám phá combo Smart Restaurant đang phục vụ, thành phần và giá niêm yết. Chọn lựa phù hợp cho bữa ăn cùng gia đình và bạn bè.'),
}
PUBLIC_ROUTES = {*PUBLIC_PAGES, 'customer_food_detail'}
DISCOVERY_ROUTES = {'seo_robots', 'seo_sitemap'}


def absolute(path):
    return settings.SEO_SITE_URL + path


def route(request):
    match = getattr(request, 'resolver_match', None)
    return match.url_name if match else None


def indexable(request):
    # Search/filter/booking/cart-context variants have a clean canonical, but no index entry.
    ignored = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'fbclid'}
    return (settings.SEO_INDEXING_ENABLED and route(request) in PUBLIC_ROUTES
            and request.method in ('GET', 'HEAD') and not (set(request.GET) - ignored))


class IndexingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (response.status_code != 200 or
                (route(request) not in DISCOVERY_ROUTES and not indexable(request)) or
                not settings.SEO_INDEXING_ENABLED):
            response['X-Robots-Tag'] = 'noindex, nofollow, nosnippet'
        return response


class CanonicalSitemap(Sitemap):
    def get_urls(self, page=1, site=None, protocol=None):
        origin = urlsplit(settings.SEO_SITE_URL)
        return super().get_urls(page=page, site=SimpleNamespace(domain=origin.netloc), protocol=origin.scheme)


class PublicSitemap(CanonicalSitemap):
    def items(self):
        return list(PUBLIC_PAGES)

    def location(self, item):
        return reverse(item)


class MenuSitemap(CanonicalSitemap):
    def items(self):
        return MenuItem.objects.filter(is_available=True, category__is_active=True).order_by('pk')

    def location(self, item):
        return reverse('customer_food_detail', args=[item.pk])

    def lastmod(self, item):
        # Category visibility is filtered above; do not fabricate modification timestamps.
        return item.updated_at


SITEMAPS = {'pages': PublicSitemap, 'menu': MenuSitemap}


@require_safe
def robots(request):
    lines = ['User-agent: *', 'Disallow:' if settings.SEO_INDEXING_ENABLED else 'Disallow: /']
    if settings.SEO_INDEXING_ENABLED:
        lines += ['Allow: /static/', 'Sitemap: ' + absolute(reverse('seo_sitemap'))]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


def clean(value, limit=160):
    return ' '.join(strip_tags(str(value or '')).split())[:limit]


def menu_schema(dish):
    item = {'@type': 'MenuItem', '@id': absolute(reverse('customer_food_detail', args=[dish['id']])) + '#menuitem',
            'name': clean(dish['name'], 200), 'url': absolute(reverse('customer_food_detail', args=[dish['id']]))}
    if dish.get('description'):
        item['description'] = clean(dish['description'], 500)
    if dish.get('image'):
        item['image'] = absolute(dish['image'])
    if dish.get('price') is not None and dish['price'].is_finite() and dish['price'] >= 0:
        item['offers'] = {'@type': 'Offer', 'price': str(dish['price']), 'priceCurrency': 'VND'}
    return item


def metadata(context):
    request = context.get('request')
    name = route(request)
    title, description = PUBLIC_PAGES.get(name, ('Smart Restaurant', 'Thực đơn, đặt bàn và dịch vụ nhà hàng Smart Restaurant.'))
    path = reverse(name) if name in PUBLIC_PAGES else None
    dish = context.get('dish') if name == 'customer_food_detail' else None
    if dish:
        title = clean(dish['name'], 200) + ' | Smart Restaurant'
        description = clean(dish.get('description')) or f"Khám phá {clean(dish['name'], 100)} trong nhóm {clean(dish['category_label'], 80)} tại Smart Restaurant. Xem thông tin món ăn và lựa chọn cho bữa ăn của bạn."
        path = reverse(name, args=[dish['id']])
    canonical = absolute(path) if path else ''
    from django.templatetags.static import static
    image = absolute(dish['image']) if dish else absolute(static('ui/images/garden-restaurant-hero.webp'))
    graph = []
    if name in PUBLIC_ROUTES and canonical:
        graph.append({'@type': 'WebSite', '@id': absolute('/#website'), 'url': absolute('/'),
                      'name': 'Smart Restaurant', 'inLanguage': 'vi-VN'})
        info = context.get('footer_restaurant')
        if info and info.name.strip():
            restaurant = {'@type': 'Restaurant', '@id': absolute('/#restaurant'), 'url': absolute('/'),
                          'name': clean(info.name, 150), 'hasMenu': absolute(reverse('customer_menu'))}
            # Only fields actually rendered by the public footer/about page; no made-up ratings/hours.
            if info.address.strip():
                restaurant['address'] = clean(info.address, 500)
            if info.phone.strip():
                restaurant['telephone'] = clean(info.phone, 30)
            if info.email.strip():
                restaurant['email'] = info.email
            graph.append(restaurant)
        crumbs = [{'@type': 'ListItem', 'position': 1, 'name': 'Trang chủ', 'item': absolute('/')}]
        if dish:
            crumbs.append({'@type': 'ListItem', 'position': 2, 'name': 'Thực đơn', 'item': absolute(reverse('customer_menu'))})
        if name != 'customer_home':
            crumbs.append({'@type': 'ListItem', 'position': len(crumbs) + 1,
                           'name': clean(dish['name']) if dish else title.split(' | ')[0], 'item': canonical})
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': crumbs})
        if name == 'customer_menu':
            graph.append({'@type': 'Menu', '@id': canonical + '#menu', 'name': 'Thực đơn Smart Restaurant',
                          'url': canonical, 'hasMenuItem': [menu_schema(row) for row in context.get('dishes', [])]})
        elif dish:
            graph.append(menu_schema(dish))
    # Escaping prevents restaurant/user-managed text from terminating the script element.
    serialized = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False, allow_nan=False)
    serialized = serialized.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return {'title': title, 'description': clean(description), 'canonical': canonical,
            'robots': 'index, follow' if indexable(request) else 'noindex, nofollow',
            'image': image, 'image_alt': clean(dish['name']) if dish else 'Không gian nhà hàng Smart Restaurant',
            'json_ld': mark_safe(serialized) if graph else '', 'is_home': name == 'customer_home',
            'google_verification': settings.GOOGLE_SITE_VERIFICATION}
