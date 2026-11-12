"""Bounded catalog math over real purchases; no research rows or ML runtime imports."""
import math
from collections import Counter, defaultdict
from django.db.models import Sum
from django.utils import timezone
from customers.models import MenuItem, OrderItem
from customers.recommendation_service import cold_start, price_band, valid


def unit(values):
    norm = math.sqrt(sum(x*x for x in values.values()))
    return {key: value/norm for key, value in values.items()} if norm else {}


def dot(a, b):
    return sum(value*b.get(key, 0) for key, value in a.items())


def recommend(user=None, *, n=4, **kwargs):
    n = max(1, min(int(n), 20))
    items = list(MenuItem.objects.select_related('category').prefetch_related('recipe_lines').order_by('pk'))
    if not user or not user.is_authenticated or not user.is_active:
        return {'mode': 'cold_start', 'recommendations': cold_start(items, n), 'provenance': 'REAL_LIVE'}
    histories = defaultdict(dict)
    now = timezone.now()
    rows = OrderItem.objects.filter(order__status='COMPLETED', order__customer__isnull=False).exclude(kitchen_status='CANCELLED')
    for row in rows.values('order__customer_id', 'menu_item_id', 'order__created_at').annotate(quantity=Sum('quantity')).iterator(chunk_size=500):
        age = max(0, (now-row['order__created_at']).total_seconds()/86400)
        weight = (1+math.log1p(row['quantity']))*math.exp(-math.log(2)*age/90)
        customer = histories[row['order__customer_id']]
        customer[row['menu_item_id']] = customer.get(row['menu_item_id'], 0)+weight
    own = histories.get(user.pk, {})
    if not own:
        return {'mode': 'cold_start', 'recommendations': cold_start(items, n), 'provenance': 'REAL_LIVE'}
    frequencies = Counter(line.ingredient_id for item in items for line in item.recipe_lines.all())
    vectors = {}
    for item in items:
        ingredients = [line.ingredient_id for line in item.recipe_lines.all()]
        values = {f'category:{item.category_id}': 2., f'price:{price_band(item.price)}': .6}
        for key in ingredients:
            values[f'ingredient:{key}'] = (1+math.log((len(items)+1)/(frequencies[key]+1)))/math.sqrt(max(1, len(ingredients)))
        vectors[item.pk] = unit(values)
    profile = defaultdict(float)
    for pk, weight in own.items():
        for key, value in vectors.get(pk, {}).items():
            profile[key] += weight*value
    profile = unit(profile)
    columns = defaultdict(dict)
    for customer, history in histories.items():
        for pk, value in history.items():
            columns[pk][customer] = value
    columns = {pk: unit(values) for pk, values in columns.items()}
    content = {item.pk: dot(profile, vectors[item.pk]) for item in items}
    collaborative = {item.pk: sum(weight*dot(columns.get(pk, {}), columns.get(item.pk, {})) for pk, weight in own.items()) for item in items}
    max_collab = max(collaborative.values(), default=1) or 1
    alpha = .5 if len(own) >= 2 else 0
    scores = {item.pk: alpha*collaborative[item.pk]/max_collab+(1-alpha)*content[item.pk] for item in items}
    candidates = [item for item in items if valid(item)]
    selected, categories = [], Counter()
    while candidates and len(selected) < n:
        unseen = [item for item in candidates if item.pk not in own]
        chosen = max(unseen or candidates, key=lambda item: (scores[item.pk]-.12*categories[item.category_id], -item.pk))
        selected.append({'item': chosen, 'score': scores[chosen.pk], 'reason': 'Phù hợp với lịch sử món đã mua của bạn.'})
        categories[chosen.category_id] += 1
        candidates.remove(chosen)
    return {'mode': 'hybrid' if alpha else 'content', 'recommendations': selected, 'provenance': 'REAL_LIVE'}
