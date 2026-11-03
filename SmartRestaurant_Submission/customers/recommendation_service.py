"""Item content vectors and chronological evaluation, without fabricated history."""
from collections import Counter,defaultdict
from decimal import Decimal
import math,os
# A 45-item catalog needs no multi-core BLAS workspace. Avoid allocating one
# large buffer per hardware thread on this local Django/Chrome demo machine.
for _thread_env in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(_thread_env,'1')
import numpy as np
import pandas as pd
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from threadpoolctl import threadpool_limits
from django.db.models import Sum,Avg,Count
from .models import MenuItem,Order,OrderItem,Review

def price_band(price):
    if price is None:return 'unknown'
    for threshold,name in [(200000,'under200k'),(400000,'200to400k'),(700000,'400to700k')]:
        if price<Decimal(threshold):return name
    return '700kplus'

@threadpool_limits.wrap(limits=1,user_api='blas')
def item_vectors():
    items=list(MenuItem.objects.select_related('category').prefetch_related('recipe_lines__ingredient').order_by('pk'))
    frame=pd.DataFrame([{'id':m.pk,'category':m.category_id,'price_band':price_band(m.price),'ingredients':[r.ingredient_id for r in m.recipe_lines.all()]} for m in items],columns=['id','category','price_band','ingredients'])
    if not items:return items,frame,None,None
    frequencies=Counter(pk for row in frame['ingredients'] for pk in set(row))
    features=[]
    for row in frame.itertuples(index=False):
        values={f'category:{row.category}':2.0,f'price:{row.price_band}':.6}
        count=max(1,len(row.ingredients))
        for pk in row.ingredients:values[f'ingredient:{pk}']=(1+math.log((len(items)+1)/(frequencies[pk]+1)))/math.sqrt(count)
        features.append(values)
    encoder=DictVectorizer(sparse=True)
    return items,frame,normalize(encoder.fit_transform(features)),encoder

def purchase_history(user_id,order_ids=None):
    qs=OrderItem.objects.filter(order__customer_id=user_id,order__status='COMPLETED').exclude(kitchen_status='CANCELLED')
    if order_ids is not None:qs=qs.filter(order_id__in=order_ids)
    return {r['menu_item_id']:r['quantity'] for r in qs.values('menu_item_id').annotate(quantity=Sum('quantity'))}

def user_profile(user_id,items,matrix,order_ids=None):
    history=purchase_history(user_id,order_ids)
    reviews=Review.objects.filter(customer_id=user_id,order__customer_id=user_id,order__status='COMPLETED')
    if order_ids is not None:reviews=reviews.filter(order_id__in=order_ids)
    ratings={r['menu_item_id']:r['rating'] for r in reviews.values('menu_item_id').annotate(rating=Avg('rating'))}
    ids={m.pk:i for i,m in enumerate(items)}
    weights=np.zeros(len(items))
    for pk,quantity in history.items():
        if pk in ids:weights[ids[pk]]=quantity*(1+.125*(ratings.get(pk,3)-3))
    if weights.sum()==0:return None,history
    profile=np.asarray(matrix.T.dot(weights)).ravel()/weights.sum()
    return profile,history

def valid(item):return item.is_available and item.category.is_active and item.price is not None and item.price>=0

def cold_start(items,n):
    sales={r['menu_item_id']:r['n'] for r in OrderItem.objects.filter(order__status='COMPLETED').exclude(kitchen_status='CANCELLED').values('menu_item_id').annotate(n=Sum('quantity'))}
    ratings={r['menu_item_id']:r['rating'] for r in Review.objects.filter(is_visible=True).values('menu_item_id').annotate(rating=Avg('rating'),n=Count('id')).filter(n__gte=2)}
    choices=sorted((m for m in items if valid(m)),key=lambda m:(-sales.get(m.pk,0),-ratings.get(m.pk,0),m.pk))[:n]
    return [{'item':m,'score':None,'reason':'Món được khách lựa chọn' if sales.get(m.pk,0)>0 else 'Được khách đánh giá cao' if ratings.get(m.pk,0)>0 else 'Khám phá từ thực đơn nhà hàng'} for m in choices]

@threadpool_limits.wrap(limits=1,user_api='blas')
def recommend(user=None,*,n=4,order_ids=None,catalog=None):
    n=max(1,min(int(n),20));items,frame,matrix,encoder=catalog or item_vectors()
    if not items:return {'mode':'cold_start','recommendations':[]}
    profile,history=user_profile(user.pk,items,matrix,order_ids) if user is not None and user.is_authenticated and user.is_active else (None,{})
    if profile is None:return {'mode':'cold_start','recommendations':cold_start(items,n)}
    scores=cosine_similarity(profile.reshape(1,-1),matrix).ravel()
    indexes=sorted((i for i,m in enumerate(items) if valid(m)),key=lambda i:(-float(scores[i]),items[i].pk))
    unseen=[i for i in indexes if items[i].pk not in history]
    chosen=(unseen+[i for i in indexes if items[i].pk in history])[:n]
    bought=[m for m in items if m.pk in history]
    categories={m.category_id for m in bought};bands={price_band(m.price) for m in bought}
    ingredients={r.ingredient_id for m in bought for r in m.recipe_lines.all()}
    recommendations=[]
    for i in chosen:
        item=items[i]
        if item.category_id in categories:reason=f'Cùng nhóm {item.category.name} với món bạn đã chọn'
        elif ingredients.intersection(r.ingredient_id for r in item.recipe_lines.all()):reason='Có nguyên liệu tương tự món bạn từng chọn'
        elif price_band(item.price) in bands:reason='Trong khoảng giá món bạn thường chọn'
        else:reason='Khám phá thêm từ thực đơn'
        recommendations.append({'item':item,'score':float(scores[i]),'reason':reason})
    return {'mode':'personalized','recommendations':recommendations}

def precision_recall_at_k(predicted,relevant,k):
    if k<=0:raise ValueError('K must be positive')
    relevant=set(relevant);hits=len(set(predicted[:k])&relevant)
    return {'precision':hits/k,'recall':hits/len(relevant) if relevant else 0.0}

def evaluate_recommendations(*,k=5):
    """Last completed order held out, at least two earlier orders and two train items.

    Uses only each user's training-order ratings; no held-out purchase popularity.
    Evaluates current active catalog; reports insufficient data rather than a score.
    """
    catalog=item_vectors();items=catalog[0];eligible={m.pk for m in items if valid(m)}
    histories=defaultdict(list)
    for order in Order.objects.filter(status='COMPLETED',customer__is_active=True).select_related('customer').order_by('created_at','pk'):
        from .rbac import get_role
        if get_role(order.customer)!='CUSTOMER':continue
        histories[order.customer_id].append(order)
    results=[]
    for orders in histories.values():
        if len(orders)<3:continue
        training=[o.pk for o in orders[:-1]];held=orders[-1]
        if len(purchase_history(held.customer_id,training))<2:continue
        relevant=set(purchase_history(held.customer_id,[held.pk]))&eligible
        if not relevant:continue
        output=recommend(held.customer,n=k,order_ids=training,catalog=catalog)
        predicted=[r['item'].pk for r in output['recommendations']]
        results.append(precision_recall_at_k(predicted,relevant,k))
    if not results:return {'available':False,'users':0,'k':k,'precision':None,'recall':None,'reason':'Chưa đủ dữ liệu thật: cần mỗi khách có ≥ 3 Order COMPLETED, ≥ 2 món trong tập train và món test đang phục vụ.'}
    return {'available':True,'users':len(results),'k':k,'precision':float(np.mean([r['precision'] for r in results])),'recall':float(np.mean([r['recall'] for r in results])),'reason':'Hold-out theo thời gian: Order COMPLETED cuối làm test; chỉ dùng lịch sử/đánh giá trước đó làm train. Features từ menu hiện tại.'}
