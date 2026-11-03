"""Latest confirmed purchase price per ingredient in its canonical stock unit."""
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery, Sum
from .models import Ingredient, StockReceiptItem, MenuItem, OrderItem


def convert_quantity(quantity, source, target):
    units = {'kg':('mass',Decimal(1000)), 'g':('mass',Decimal(1)), 'l':('volume',Decimal(1000)), 'ml':('volume',Decimal(1)), 'piece':('piece',Decimal(1)), 'portion':('portion',Decimal(1))}
    if source not in units or target not in units or units[source][0] != units[target][0]: raise ValidationError('Đơn vị không tương thích.')
    try: quantity = Decimal(str(quantity))
    except (InvalidOperation,TypeError,ValueError): raise ValidationError('Lượng không hợp lệ.')
    if not quantity.is_finite() or quantity < 0: raise ValidationError('Lượng không hợp lệ.')
    return quantity * units[source][1] / units[target][1]


def latest_costs():
    latest = StockReceiptItem.objects.filter(ingredient_id=OuterRef('pk'), receipt__status='CONFIRMED').order_by('-receipt__date','-receipt__confirmed_at','-pk')
    return dict(Ingredient.objects.annotate(cost=Subquery(latest.values('unit_price')[:1])).values_list('pk','cost'))


def calculate_food_cost(menu, costs=None):
    costs = latest_costs() if costs is None else costs
    lines = list(menu.recipe_lines.all()) if 'recipe_lines' in getattr(menu,'_prefetched_objects_cache',{}) else list(menu.recipe_lines.select_related('ingredient'))
    contributions, missing = [], []
    for line in lines:
        cost = costs.get(line.ingredient_id)
        if cost is None:
            missing.append(line.ingredient.name)
        else:
            # Recipe quantities already use Ingredient.unit, as does the inventory engine.
            contributions.append({'ingredient':line.ingredient.name, 'quantity':line.quantity_required, 'unit':line.ingredient.unit, 'cost':line.quantity_required * cost})
    complete = bool(lines) and not missing
    value = sum((i['cost'] for i in contributions), Decimal(0)) if complete else None
    profit = menu.price-value if value is not None and menu.price is not None else None
    percentage = value/menu.price*100 if value is not None and menu.price is not None and menu.price>0 else None
    threshold = getattr(settings,'FOOD_COST_WARNING_PERCENT',None)
    status = 'Chưa đủ dữ liệu' if not complete else ('Food cost cao' if threshold is not None and percentage is not None and percentage>Decimal(str(threshold)) else 'Đã tính theo giá nhập gần nhất')
    return {'menu':menu,'cost':value,'profit':profit,'percentage':percentage,'status':status,'missing':missing,'contributions':sorted(contributions,key=lambda i:i['cost'],reverse=True)}


def food_cost_report(query='', category=''):
    menus = MenuItem.objects.select_related('category').prefetch_related('recipe_lines__ingredient').filter(name__icontains=query)
    if category: menus = menus.filter(category_id=category)
    costs = latest_costs()
    sales = dict(OrderItem.objects.filter(order__invoice__status='PAID').exclude(kitchen_status='CANCELLED').values('menu_item_id').annotate(total=Sum('quantity')).values_list('menu_item_id','total'))
    return [dict(calculate_food_cost(menu,costs), sold=sales.get(menu.pk,0)) for menu in menus]
