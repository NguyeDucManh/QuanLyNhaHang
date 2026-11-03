from decimal import Decimal
from .models import Topping,Combo
from .menu_service import format_money

def enrich_preview(request,rows):
    total=Decimal(0); errors=[]; combos=[];combo_parts=0
    selected=request.session.get('topping_cart',{})
    for row in rows:
        ids=selected.get(str(row['id']),[]) if isinstance(selected,dict) else []
        tops=list(Topping.objects.filter(pk__in=ids,is_available=True,menu_items__pk=row['id']).distinct())
        if len(tops)!=len(ids): errors.append(f'{row["name"]}: topping không còn phục vụ; chọn lại topping.')
        row['selected_toppings']=tops
        price=(row['price'] or Decimal(0))+sum((t.price for t in tops),Decimal(0))
        row['subtotal']=format_money(price*row['quantity'])+' ₫'; total+=price*row['quantity']
    cart=request.session.get('combo_cart',{})
    if not isinstance(cart,dict): cart={}; errors.append('Giỏ combo không hợp lệ.')
    for combo in Combo.objects.filter(pk__in=[int(k) for k in cart if str(k).isdigit()]):
        qty=cart.get(str(combo.pk),0)
        if not isinstance(qty,int) or isinstance(qty,bool) or not 1<=qty<=20: errors.append('Số lượng combo không hợp lệ.'); continue
        if not combo.is_active: errors.append(f'{combo.name} đã ngừng phục vụ.')
        combos.append({'combo':combo,'quantity':qty,'total':combo.price*qty}); total+=combo.price*qty
        combo_parts+=sum(combo.items.values_list('quantity',flat=True))*qty
    return {'rows':rows,'total':total,'combo_rows':combos,'errors':errors,'combo_parts':combo_parts}
