"""Nguồn dữ liệu runtime: ORM PostgreSQL, không import catalog backup."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.templatetags.static import static
from django.urls import reverse
from .models import Category, MenuItem

CATALOG_VERSION = 'official-45-v1'  # Giữ session hiện có vì ID/mapping không thay đổi.


def format_money(value):
    value = Decimal(value)
    rendered = format(value, ',.0f' if value == value.to_integral_value() else ',.2f')
    return rendered.replace(',', '_').replace('.', ',').replace('_', '.')


def menu_items(include_unavailable=False):
    items = MenuItem.objects.select_related('category').all()
    if not include_unavailable:
        items = items.filter(is_available=True, category__is_active=True)
    return items


def serialize_item(item, for_admin=False):
    available = item.is_available and item.category.is_active
    data = {
        'id': item.pk, 'name': item.name, 'category': item.category.slug,
        'category_label': item.category.name, 'price': item.price,
        'price_display': format_money(item.price) + ' ₫' if item.price is not None else 'Liên hệ',
        'image_path': item.image, 'image': static(item.image), 'description': item.description,
        'is_available': item.is_available,
        'status': 'Đang phục vụ' if available else 'Ngừng phục vụ',
    }
    if for_admin:
        data['edit_url'] = reverse('admin_menu_edit', args=[item.pk])
        data['toggle_url'] = reverse('admin_menu_toggle', args=[item.pk])
    return data


def get_dishes(include_unavailable=False):
    from django.db.models import Avg,Count,Q
    qs=menu_items(include_unavailable).annotate(public_rating=Avg('reviews__rating',filter=Q(reviews__is_visible=True)),public_review_count=Count('reviews',filter=Q(reviews__is_visible=True))).order_by('pk')
    return [{**serialize_item(item, for_admin=include_unavailable),'rating':item.public_rating,'review_count':item.public_review_count} for item in qs]


def get_categories():
    return [('', 'Tất cả')] + list(Category.objects.filter(is_active=True).values_list('slug', 'name'))


def session_cart(request):
    if request.session.get('catalog_version') != CATALOG_VERSION:
        request.session['cart'] = {}
        request.session['topping_cart'] = {}
        request.session['combo_cart'] = {}
        request.session['catalog_version'] = CATALOG_VERSION
    return request.session.get('cart', {})


def validated_cart_quantities(cart):
    """Only IDs and integer quantities are accepted; prices never come from session."""
    if not isinstance(cart, dict):
        raise ValidationError('Giỏ món không hợp lệ. Vui lòng mở giỏ món để kiểm tra lại.')
    result = {}
    for key, quantity in cart.items():
        try:
            item_id = int(key)
        except (ValueError, TypeError):
            raise ValidationError('Mã món trong giỏ không hợp lệ.')
        if isinstance(key, bool) or item_id <= 0 or str(item_id) != str(key) or item_id in result:
            raise ValidationError('Mã món trong giỏ không hợp lệ.')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
            raise ValidationError('Số lượng mỗi món phải từ 1 đến 99.')
        result[item_id] = quantity
    return result


def booking_cart_preview(cart):
    """Read-only preview: visiting Booking never removes anything from cart."""
    rows, errors = [], []
    try:
        quantities = validated_cart_quantities(cart)
    except ValidationError as exc:
        return {'selected_food': [], 'food_total': '0', 'food_count': 0, 'cart_errors': exc.messages, 'has_cart': bool(cart)}
    items = {item.pk: item for item in MenuItem.objects.select_related('category').filter(pk__in=quantities)}
    total = Decimal('0')
    for pk, quantity in quantities.items():
        item = items.get(pk)
        if item is None:
            errors.append(f'Món #{pk} không còn tồn tại; hãy kiểm tra giỏ món.')
            continue
        dish = serialize_item(item)
        if not item.is_available or not item.category.is_active:
            errors.append(f'{item.name} đang ngừng phục vụ. Hãy bỏ món này trước khi đặt.')
        if item.price is None:
            errors.append(f'{item.name} chưa niêm yết giá. Hãy bỏ món này hoặc liên hệ nhà hàng trước khi đặt món.')
        line_total = item.price * quantity if item.price is not None else None
        if line_total is not None:
            total += line_total
        rows.append({**dish, 'quantity': quantity, 'subtotal': format_money(line_total) + ' ₫' if line_total is not None else 'Liên hệ'})
    return {'selected_food': rows, 'food_total': format_money(total), 'food_count': sum(quantities.values()), 'cart_errors': errors, 'has_cart': bool(cart)}
