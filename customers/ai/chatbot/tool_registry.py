"""Closed tools. No SQL, arbitrary ORM paths, eval, or LLM-written code."""
import re
from datetime import date,time
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from customers.models import MenuItem,Combo,Promotion,RestaurantInfo,Order,Booking,Invoice
from customers.menu_service import format_money,session_cart,validated_cart_quantities
from .intent_router import normalize
from .answer_guard import NO_DATA
from .memory_service import booking_entities,booking_followup
from .normalization import price_entities

SCHEMAS={
 'search_menu':{'input':['query','keyword','category','min_price','max_price','availability','limit'],'output':['answer','menu_ids']},
 'get_menu_price':{'input':['query','menu_item_id'],'output':['answer','menu_ids']},
 'get_menu_detail':{'input':['query','menu_item_id'],'output':['answer','menu_ids']},
 'get_combo_info':{'input':['query'],'output':['answer','combo_ids']},
 'get_current_promotions':{'input':[],'output':['answer','promotion_ids']},
 'get_restaurant_info':{'input':['field'],'output':['answer','source_id']},
 'check_booking_availability':{'input':['date','time','guests'],'output':['answer','available']},
 'get_my_booking':{'input':['booking_id'],'output':['answer']},
 'get_my_order_status':{'input':['order_id'],'output':['answer']},
 'get_my_payment_status':{'input':['invoice_id'],'output':['answer']},
 'get_my_cart':{'input':[],'output':['answer']},
 'add_to_cart':{'input':['menu_item_id','quantity'],'output':['answer']},
 'recommend_for_current_user':{'input':['query'],'output':['answer','menu_ids']},
}
TOOLS={'MENU_SEARCH':'search_menu','MENU_PRICE':'get_menu_price','MENU_DETAIL':'get_menu_detail','COMBO_INFO':'get_combo_info','PROMOTION_INFO':'get_current_promotions','RESTAURANT_INFO':'get_restaurant_info','OPENING_HOURS':'get_restaurant_info','BOOKING_AVAILABILITY':'check_booking_availability','MY_BOOKING':'get_my_booking','MY_ORDER_STATUS':'get_my_order_status','MY_PAYMENT_STATUS':'get_my_payment_status','CART_VIEW':'get_my_cart','CART_ADD':'add_to_cart','MENU_RECOMMENDATION':'recommend_for_current_user'}

def active_menu():
    return MenuItem.objects.filter(is_available=True,category__is_active=True,price__isnull=False).select_related('category')

def resolve_menu(query,memory):
    from rapidfuzz import fuzz
    items=list(active_menu()); value=normalize(query)
    ordinal=re.search(r'\bmon\s+(?:thu|so)\s*(\d+)\b',value)
    if ordinal:
        ids=memory.get('last_menu_ids',[]); index=int(ordinal[1])-1
        return next((m for m in items if 0<=index<len(ids) and m.pk==ids[index]),None),False
    if re.fullmatch(r'them(?:\s+\d+)?(?:\s+phan)?[.!?]*',value) and memory.get('menu_item_id'):
        return next((m for m in items if m.pk==memory['menu_item_id']),None),False
    if re.search(r'\b(no|mon do|gia no)\b',value) and memory.get('menu_item_id'):
        return next((m for m in items if m.pk==memory['menu_item_id']),None),False
    exact=[m for m in items if normalize(m.name) in value]
    if exact:
        exact.sort(key=lambda m:len(normalize(m.name)),reverse=True)
        return exact[0], len(exact)>1 and len(exact[0].name)==len(exact[1].name)
    tokens=re.sub(r'\b(them|phan|vao|gio|gia|mon|bao|nhieu|chi|tiet|cua|la|gi|duoi|tren|tu)\b|\d+', ' ',value)
    tokens=re.sub(r'\s+',' ',tokens).strip()
    tokens=re.sub(r'[^\w\s]','',tokens)
    scores=sorted([(max(fuzz.ratio(tokens,normalize(m.name)),fuzz.WRatio(tokens,normalize(m.name))*.92),m) for m in items],key=lambda r:r[0],reverse=True)
    if scores and scores[0][0]>=78:
        return scores[0][1],len(scores)>1 and scores[0][0]-scores[1][0]<5
    return None,False

def menu_search(query,*,keyword=None,category=None,min_price=None,max_price=None,availability=True,limit=5):
    if not isinstance(availability,bool): raise ValidationError('Availability phải là boolean.')
    value=normalize(query); items=list(MenuItem.objects.filter(is_available=availability,category__is_active=True,price__isnull=False).select_related('category')); prices=price_entities(query)
    if min_price is not None: prices['min_price']=min_price
    if max_price is not None: prices['max_price']=max_price
    if any(v<0 for v in prices.values()) or not 1<=limit<=45: raise ValidationError('Bộ lọc món không hợp lệ.')
    items=[m for m in items if ('min_price' not in prices or m.price>=prices['min_price']) and ('max_price' not in prices or m.price<=prices['max_price'])]
    if category: items=[m for m in items if normalize(category) in normalize(m.category.name) or category==m.category.slug]
    if keyword: items=[m for m in items if normalize(keyword) in normalize(m.name+' '+m.description)]
    exclusions=[]
    for match in re.finditer(r'khong\s+(?:co\s+)?(hai san|bo|ga|heo|cay)',value): exclusions.append(match[1])
    for word in exclusions:
        items=[m for m in items if word not in normalize(m.name+' '+m.category.name+' '+m.description)]
    cleaned=re.sub(r'khong\s+(?:co\s+)?(hai san|bo|ga|heo|cay)','',value)
    for word in ['hai san','bo','ga','heo','cay','chay']:
        if re.search(r'\b'+word+r'\b',cleaned): items=[m for m in items if re.search(r'\b'+word+r'\b',normalize(m.name+' '+m.category.name+' '+m.description))]
    if re.search(r'\bre re|mon re\b',value): items.sort(key=lambda m:m.price)
    return items[:limit]

def call(intent,query,memory,request):
    name=TOOLS[intent]; user=request.user; authenticated=user.is_authenticated and user.is_active
    sources=[]; ids=[]; answer=NO_DATA
    if intent in ['MENU_PRICE','MENU_DETAIL','CART_ADD']:
        item,ambiguous=resolve_menu(query,memory)
        if ambiguous: answer='Có nhiều món tên gần giống; bạn cho biết tên món đầy đủ nhé.'
        elif item:
            memory['menu_item_id']=item.pk; ids=[item.pk]; sources=[{'source_type':'MENU_ITEM','source_id':item.pk}]
            if intent=='MENU_PRICE': answer=f'{item.name} hiện có giá {format_money(item.price)}đ.'
            elif intent=='MENU_DETAIL': answer=f'{item.name}: {item.description or "Chưa có mô tả chi tiết."}'
            else:
                if 'topping' in normalize(query): answer='Bạn hãy chọn topping tại trang món để tránh thêm sai tùy chọn.'
                else:
                    quantity_match=re.search(r'\bthem\s+(\d+)\b',normalize(query)); quantity=int(quantity_match[1]) if quantity_match else 1
                    from customers.cart_service import add_to_cart
                    add_to_cart(request,item,quantity); answer=f'Đã thêm {quantity} phần {item.name} vào giỏ.'
    elif intent=='MENU_SEARCH':
        items=menu_search(query); ids=[m.pk for m in items]
        if re.search(r'\b(?:nha hang|quan)\s+co\s+gi',normalize(query)):
            from customers.models import Category
            from django.db.models import Count
            categories=list(Category.objects.filter(is_active=True,menu_items__is_available=True).annotate(total=Count('menu_items')).order_by('-total','pk').values_list('name',flat=True)[:6])
            answer='Nhà hàng hiện có '+', '.join(categories)+'. Bạn muốn xem nhóm nào?' if categories else NO_DATA
        else: answer='; '.join(f'{i+1}. {m.name}: {format_money(m.price)}đ' for i,m in enumerate(items))+'.' if items else 'Hiện chưa có món đang phục vụ phù hợp với điều kiện này.'
        memory['last_menu_ids']=ids
        if len(items)==1: memory['menu_item_id']=items[0].pk
        sources=[{'source_type':'MENU_ITEM','source_id':pk} for pk in ids]
    elif intent=='COMBO_INFO':
        value=normalize(query); combos=list(Combo.objects.filter(is_active=True).order_by('pk'))
        number=re.search(r'\b(\d+)\s*(nguoi|khach)\b',value)
        matches=[c for c in combos if normalize(c.name) in value or (number and re.search(r'\b'+number[1]+r'\b',normalize(c.name)))]
        if len(matches)==1: c=matches[0]; answer=f'{c.name} hiện có giá {format_money(c.price)}đ.'; sources=[{'source_type':'COMBO','source_id':c.pk}]
        elif len(matches)>1: answer='Bạn muốn hỏi combo nào? '+ '; '.join(c.name for c in matches[:4])+'.'
        elif not number: answer='; '.join(f'{c.name}: {format_money(c.price)}đ' for c in combos[:3])+'.' if combos else NO_DATA
    elif intent=='PROMOTION_INFO':
        now=timezone.now(); promos=[p for p in Promotion.objects.filter(is_active=True,start_at__lte=now,end_at__gte=now) if p.usage_limit is None or p.used_count<p.usage_limit]
        code=re.search(r'\b(?:voucher|ma)\s+([a-z0-9_-]+)',normalize(query))
        if code: promos=[p for p in promos if p.code.lower()==code[1]]
        answer='; '.join(f'{p.code}: giảm {format_money(p.discount_value)}'+('%' if p.discount_type=='PERCENT' else 'đ')+f', đơn từ {format_money(p.min_order_amount)}đ'+(f', tối đa {format_money(p.max_discount_amount)}đ' if p.max_discount_amount is not None else '') for p in promos[:3])+'.' if promos else 'Hiện chưa có ưu đãi phù hợp đang hoạt động.'
        sources=[{'source_type':'PROMOTION','source_id':p.pk} for p in promos[:3]]
    elif intent in ['RESTAURANT_INFO','OPENING_HOURS']:
        info=RestaurantInfo.objects.filter(is_active=True).first()
        if info:
            if intent=='OPENING_HOURS': answer=f'Nhà hàng mở cửa từ {info.opening_time:%H:%M} đến {info.closing_time:%H:%M}.'
            elif 'dien thoai' in normalize(query): answer=f'Số điện thoại: {info.phone}.' if info.phone else NO_DATA
            elif 'dia chi' in normalize(query) or 'nha hang o' in normalize(query): answer=f'Địa chỉ: {info.address}.' if info.address else NO_DATA
            else: answer=f'{info.name}: {info.address}. Điện thoại: {info.phone}.'
            sources=[{'source_type':'RESTAURANT_INFO','source_id':info.pk}]
    elif intent=='BOOKING_AVAILABILITY':
        entities=booking_entities(query,memory); memory['booking']=entities; memory['pending']=intent
        if entities.get('ambiguous_time') or not all(k in entities for k in ['date','time','guests']): answer=booking_followup(entities,memory)
        else:
            if not 1<=entities['guests']<=20: raise ValidationError('Vui lòng chọn từ 1 đến 20 khách.')
            from customers.booking_service import booking_window,lock_areas,find_available_table,NO_TABLE_MESSAGE
            try:
                start,end=booking_window(date.fromisoformat(entities['date']),time.fromisoformat(entities['time']))
            except ValidationError as exc:
                # A conversational slot may become past while the user supplies
                # missing details. Preserve the slots and ask for a future time.
                memory['awaiting_slot']='date'
                return {'answer':' '.join(exc.messages),'tool':name,'sources':[],'menu_ids':[]}
            with transaction.atomic():
                try: find_available_table(start,end,entities['guests'],lock_areas())
                except ValidationError as exc:
                    if NO_TABLE_MESSAGE not in exc.messages: raise
                    answer='Không còn bàn phù hợp trong khung giờ này.'
                else: answer=f'Còn bàn cho {entities["guests"]} người lúc {start:%H:%M} ngày {entities["date"]}; bạn có thể xác nhận tại trang Đặt bàn.'
            memory.pop('pending',None); memory.pop('awaiting_slot',None); sources=[{'source_type':'LIVE_BOOKING_AVAILABILITY','source_id':entities['date']}]
    elif intent in ['MY_BOOKING','MY_ORDER_STATUS','MY_PAYMENT_STATUS']:
        if not authenticated: answer='Bạn cần đăng nhập để xem thông tin của mình.'
        else:
            number=re.search(r'#\s*(\d+)',query)
            if intent=='MY_BOOKING': qs=Booking.objects.filter(user=user).order_by('-created_at'); label='Đặt bàn'
            elif intent=='MY_ORDER_STATUS': qs=Order.objects.filter(customer=user).order_by('-created_at'); label='Đơn hàng'
            else: qs=Invoice.objects.filter(order__customer=user).order_by('-created_at'); label='Hóa đơn'
            if number: qs=qs.filter(pk=int(number[1]))
            obj=qs.first()
            answer=f'{label} #{obj.pk}: {obj.get_status_display()}.' if obj else 'Không tìm thấy thông tin trong tài khoản của bạn.'
            if obj: sources=[{'source_type':intent,'source_id':obj.pk}]
    elif intent=='CART_VIEW':
        cart=validated_cart_quantities(session_cart(request)); items={m.pk:m for m in active_menu().filter(pk__in=cart)}
        answer='; '.join(f'{qty} phần {items[pk].name}' for pk,qty in cart.items() if pk in items)+'.' if cart else 'Giỏ món của bạn đang trống.'
    elif intent=='MENU_RECOMMENDATION':
        from customers.ai.hybrid_service import recommend
        result=recommend(user,n=20); allowed={m.pk for m in menu_search(query,limit=45)} if price_entities(query) or any(w in normalize(query) for w in ['hai san','khong','bo','ga','chay']) else None
        rows=[r for r in result['recommendations'] if allowed is None or r['item'].pk in allowed][:3]
        if allowed and not rows:
            from customers.recommendation_service import cold_start
            rows=cold_start(list(active_menu().filter(pk__in=allowed)),3)
        ids=[r['item'].pk for r in rows]; memory['last_menu_ids']=ids; answer='; '.join(f'{i+1}. {r["item"].name}: {format_money(r["item"].price)}đ' for i,r in enumerate(rows))+'.' if rows else 'Hiện chưa có món phù hợp với điều kiện của bạn.'
        sources=[{'source_type':'MENU_ITEM','source_id':pk} for pk in ids]
    return {'answer':answer,'tool':name,'sources':sources,'menu_ids':ids}
