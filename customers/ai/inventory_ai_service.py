from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from customers.models import Ingredient, RecipeIngredient

def calculate(forecast,*,days=7,safety_days=3,demand_increase=0):
    if days not in [7,14,30] or safety_days not in [3,5,7] or demand_increase not in [0,10,20]: raise ValueError('Policy không hợp lệ.')
    usage=defaultdict(lambda:Decimal(0)); factor=Decimal(1)+Decimal(demand_increase)/100
    keys=forecast['series']; menu_ids=[int(key[5:]) for key in keys if key.startswith('menu_')]
    for line in RecipeIngredient.objects.filter(menu_item_id__in=menu_ids,ingredient__is_active=True):
        quantity=sum((Decimal(str(max(0,r['predicted']))) for r in keys[f'menu_{line.menu_item_id}'][:days]),Decimal(0))
        usage[line.ingredient_id]+=quantity*line.quantity_required*factor
    rows=[]; covered_ids=set(usage)
    for ingredient in Ingredient.objects.filter(is_active=True).select_related('ai_supply_policy__supplier'):
        policy=getattr(ingredient,'ai_supply_policy',None); lead=policy.lead_time_days if policy else 2
        safety=policy.safety_days if policy else safety_days; demand=usage[ingredient.pk]; average=demand/Decimal(days)
        buffer=average*safety; reorder=average*lead+max(buffer,ingredient.minimum_stock)
        required=demand+max(buffer,ingredient.minimum_stock); stock=ingredient.current_stock
        purchase=max(Decimal(0),required-stock); shortage=max(Decimal(0),demand-stock)
        risk='CRITICAL' if shortage>0 else 'HIGH' if stock<average*lead else 'LOW' if stock<reorder else 'NORMAL'
        if ingredient.unit in ['piece','portion']: purchase=purchase.to_integral_value(rounding=ROUND_CEILING)
        else: purchase=purchase.quantize(Decimal('.001'),rounding=ROUND_CEILING)
        rows.append({'ingredient':ingredient,'current_stock':stock,'minimum_stock':ingredient.minimum_stock,'predicted_usage':demand,'safety_stock':buffer,'lead_time':lead,'reorder_point':reorder,'expected_remaining':max(Decimal(0),stock-demand),'shortage':shortage,'recommended_purchase':purchase,'risk':risk,'supplier':policy.supplier if policy else None,'covered':ingredient.pk in covered_ids})
    return rows
