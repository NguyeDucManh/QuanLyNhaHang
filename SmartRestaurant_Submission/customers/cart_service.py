"""Shared cart mutation adapter used by HTTP and restaurant AI tools."""
from django.core.exceptions import ValidationError
from .menu_service import session_cart,validated_cart_quantities

def add_to_cart(request,item,quantity=1,*,cap=False):
    if not item.is_available or not item.category.is_active: raise ValidationError('Món đang ngừng phục vụ.')
    if isinstance(quantity,bool) or not isinstance(quantity,int) or not 1<=quantity<=99: raise ValidationError('Số lượng mỗi món phải từ 1 đến 99.')
    cart=validated_cart_quantities(session_cart(request)); value=cart.get(item.pk,0)+quantity
    if value>99 and not cap: raise ValidationError('Số lượng mỗi món phải từ 1 đến 99.')
    values={str(pk):count for pk,count in cart.items()}; values[str(item.pk)]=min(99,value)
    request.session['cart']=values
    return values
