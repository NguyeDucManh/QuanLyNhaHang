from django import template
from customers.menu_service import format_money
register = template.Library()


@register.filter
def money(value):
    return 'Liên hệ' if value is None else format_money(value) + ' ₫'
