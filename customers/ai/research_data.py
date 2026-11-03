"""Research-only simulations: never insert orders, users, stock or attendance."""
from collections import defaultdict
from datetime import timedelta,timezone as datetime_timezone
import math
import random
from django.utils import timezone
from customers.models import MenuItem, Order, OrderItem, Review
from .artifacts import new_version, write_json, publish, latest, read_json

def prepare(seed=42, days=70, target=280, end=None):
    if days < 35 or days > 365 or not 50 <= target <= 5000:
        raise ValueError('days phải 35–365, interactions phải 50–5000.')
    rng = random.Random(seed)
    end = end or timezone.localdate() - timedelta(days=1)
    start = end - timedelta(days=days-1)
    menus = list(MenuItem.objects.filter(is_available=True, category__is_active=True, price__isnull=False).select_related('category').order_by('pk'))
    if not menus: raise ValueError('Cần menu thật đang phục vụ và có giá.')
    prices = {m.pk: float(m.price) for m in menus}
    interactions = []
    ratings = {(r.order_id,r.menu_item_id):r for r in Review.objects.filter(is_visible=True)}
    lines = OrderItem.objects.filter(order__status='COMPLETED',order__customer__isnull=False).exclude(kitchen_status='CANCELLED').select_related('order').order_by('order__created_at','pk')
    for line in lines:
        if line.menu_item_id not in prices: continue
        review=ratings.get((line.order_id,line.menu_item_id))
        available_at=max(line.order.created_at,review.created_at) if review else line.order.created_at
        interactions.append({'customer_key':f'real:{line.order.customer_id}', 'menu_item_id':line.menu_item_id,'quantity':line.quantity,'rating':review.rating if review else 3,'purchased_at':line.order.created_at.isoformat(), 'at':available_at.astimezone(datetime_timezone.utc).isoformat(),'source':'REAL'})
    real_count = len(interactions)
    # Persistent preferences, repeat purchases and occasional exploration.
    users = max(8, math.ceil(max(0,target-real_count)/10))
    while len(interactions) < target:
        u = (len(interactions)-real_count) % users
        preferred = menus[u % len(menus)].category_id
        pool = [m for m in menus if m.category_id == preferred] if rng.random() < .75 else menus
        item = rng.choice(pool)
        day = start + timedelta(days=rng.randrange(days))
        at = timezone.make_aware(__import__('datetime').datetime.combine(day,__import__('datetime').time(12+rng.randrange(8))))
        interactions.append({'customer_key':f'simulated:{u}', 'menu_item_id':item.pk,'quantity':rng.randint(1,3),'rating':rng.choice([3,4,4,5]) if item.category_id==preferred else rng.randint(2,5),'at':at.astimezone(datetime_timezone.utc).isoformat(),'source':'SYNTHETIC'})
    interactions.sort(key=lambda r:(r['at'],r['customer_key'],r['menu_item_id']))
    recipe_ids = list(MenuItem.objects.filter(pk__in=prices,recipe_lines__isnull=False).order_by('pk').values_list('pk',flat=True).distinct())[:15]
    daily_real = defaultdict(lambda: {'order_count':0,'revenue':0.,'items_sold':0,'promotion_flag':0})
    item_real = defaultdict(lambda: defaultdict(int))
    for order in Order.objects.filter(status='COMPLETED').prefetch_related('items'):
        day = timezone.localdate(order.created_at).isoformat()
        row = daily_real[day]; row['order_count'] += 1; row['revenue'] += float(order.total_amount)
        row['promotion_flag'] = max(row['promotion_flag'],int(bool(order.promotion_id)))
        for line in order.items.exclude(kitchen_status='CANCELLED'):
            row['items_sold'] += line.quantity; item_real[day][line.menu_item_id] += line.quantity
    daily, item_daily = [], []
    for offset in range(days):
        day = start + timedelta(days=offset); key = day.isoformat()
        if key in daily_real:
            row = dict(daily_real[key]); source = 'REAL'
            demand = item_real[key]
        else:
            promo = int(offset % 13 == 4)
            orders = max(1,round((12 + 4*(day.weekday()>=5)+5*promo+offset*.02)*rng.uniform(.6,1.4)))
            demand = defaultdict(int); revenue = 0.; items_sold = 0
            for _ in range(orders):
                for item in rng.sample(menus,min(rng.randint(2,4),len(menus))):
                    quantity = rng.randint(1,3); demand[item.pk] += quantity
                    revenue += prices[item.pk]*quantity*(.9 if promo else 1); items_sold += quantity
            row = {'order_count':orders,'revenue':round(revenue,2),'items_sold':items_sold,'promotion_flag':promo}; source='SYNTHETIC'
        daily.append({'date':key,**row,'day_of_week':day.weekday(),'weekend':int(day.weekday()>=5),'avg_order_value':row['revenue']/row['order_count'] if row['order_count'] else 0,'source':source})
        item_daily.extend({'date':key,'menu_item_id':pk,'quantity_sold':demand.get(pk,0),'promotion_flag':row['promotion_flag'],'source':source} for pk in recipe_ids)
    assert len(daily)==days and all(r['revenue']>=0 and r['items_sold']>=0 for r in daily)
    assert all(r['menu_item_id'] in prices and r['quantity']>0 for r in interactions)
    folder=new_version('datasets')
    for name,data in [('interactions',interactions),('daily',daily),('item_daily',item_daily)]: write_json(folder/(name+'.json'),data)
    metadata=publish(folder,{'seed':seed,'label':'REAL + SYNTHETIC research data; not operational orders','real_interactions':real_count,'synthetic_interactions':len(interactions)-real_count,'real_days':sum(r['source']=='REAL' for r in daily),'synthetic_days':sum(r['source']=='SYNTHETIC' for r in daily),'start':start.isoformat(),'end':end.isoformat(),'recipe_menu_ids':recipe_ids,'prices':prices,'validation':'Schema, catalog FK, contiguous dates, nonnegative totals; simulated revenue = sum(menu prices × quantity × promotion discount).'})
    return metadata

def dataset(name):
    folder=latest('datasets')
    return read_json(folder/(name+'.json')),read_json(folder/'metadata.json')
