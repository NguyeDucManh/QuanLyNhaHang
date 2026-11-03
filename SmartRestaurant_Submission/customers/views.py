import unicodedata
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_POST
from .menu_service import get_dishes, get_categories, menu_items, serialize_item, session_cart, format_money, booking_cart_preview
from .models import MenuItem
from .forms import CustomerRegistrationForm, BookingForm, MenuItemForm
from .rbac import get_role, is_admin, can_manage, has_capability, assign_role, role_required, capability_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db import IntegrityError


def role_home(user):
    role = get_role(user)
    if role in ('ADMIN', 'MANAGER'):
        return 'admin_home'
    if role == 'STAFF':
        return 'staff_home'
    return 'customer_home'


def home(request):
    if get_role(request.user) in ("ADMIN", "MANAGER", "STAFF"):
        return redirect(role_home(request.user))
    dishes = get_dishes()
    from .ai.hybrid_service import recommend
    result=recommend(request.user,n=4)
    suggestions=[{**serialize_item(row['item']),'recommendation_reason':row['reason']} for row in result['recommendations']]
    from .models import Combo,Promotion,RestaurantInfo,Review
    from django.utils import timezone
    now=timezone.now()
    return render(request, "customer/home.html", {"featured": dishes[:4], "suggestions": suggestions, "page": "home",'home_combos':Combo.objects.filter(is_active=True)[:3],'home_promotions':Promotion.objects.filter(is_active=True,start_at__lte=now,end_at__gte=now)[:3],'home_info':RestaurantInfo.objects.filter(is_active=True).first(),'home_reviews':Review.objects.filter(is_visible=True).select_related('customer','menu_item').order_by('-created_at')[:3]})


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower().replace("đ", "d")) if not unicodedata.combining(c))


def menu(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    dishes = [d for d in get_dishes() if (not category or d["category"] == category) and normalize(query) in normalize(d["name"])]
    from decimal import Decimal,InvalidOperation
    filters={}
    for key in ['min_price','max_price']:
        raw=request.GET.get(key,'').strip()
        if raw:
            try:
                value=Decimal(raw)
                if not value.is_finite() or value<0: raise InvalidOperation
                filters[key]=value
            except InvalidOperation: messages.error(request,'Khoảng giá không hợp lệ.')
    dishes=[d for d in dishes if d['price'] is not None and ('min_price' not in filters or d['price']>=filters['min_price']) and ('max_price' not in filters or d['price']<=filters['max_price'])] if filters else dishes
    sort=request.GET.get('sort','catalog')
    if sort in ['price_asc','price_desc','name']:
        dishes.sort(key=(lambda d:(d['price'] is None,d['price'] or 0)) if sort in ['price_asc','price_desc'] else lambda d:d['name'],reverse=sort=='price_desc')
    from .customer_booking_workspace import menu_context
    return render(request, "customer/menu.html", {"dishes": dishes, "categories": get_categories(), "category": category, "query": query, "page": "menu", **menu_context(request)})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(role_home(request.user))
    form = AuthenticationForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(role_home(form.get_user()))
    return render(request, "customer/auth/login.html", {"form": form, "page": "login"})


def register(request):
    if request.user.is_authenticated:
        return redirect(role_home(request.user))
    form = CustomerRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        with transaction.atomic():
            user.save()
            assign_role(user, "CUSTOMER")
        login(request, user)
        messages.success(request, "Chào mừng bạn đến với Smart Restaurant!")
        return redirect("customer_home")
    return render(request, "customer/auth/register.html", {"form": form, "page": "register"})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("customer_home")


@login_required
def management(request):
    if not can_manage(request.user):
        raise PermissionDenied("Bạn không có quyền truy cập khu vực quản lý.")
    if get_role(request.user)=='STAFF':
        from .staff_portal import dashboard
        return render(request,'staff/dashboard.html',dashboard(request))
    from .rbac import management_access
    access = management_access(request.user)
    return render(request, 'index.html', {
        'admin_identity': {'name': request.user.get_full_name() or request.user.username},
        'dishes': get_dishes(include_unavailable=True) if access['view_menu'] else [],
        'rbac_access': access,
    })


@role_required('ADMIN', 'MANAGER', 'STAFF')
def staff_home(request):
    from .staff_portal import dashboard
    return render(request, 'staff/dashboard.html',dashboard(request))


@login_required
def profile(request):
    from .rbac import get_role
    from django.forms import modelform_factory
    from django.contrib.auth import get_user_model
    Form=modelform_factory(get_user_model(),fields=['first_name','last_name','email'],labels={'first_name':'Tên','last_name':'Họ và tên đệm','email':'Thư điện tử'})
    form=Form(request.POST if request.method=='POST' else None,instance=request.user)
    if request.method=='POST' and form.is_valid():
        user=form.save(commit=False);user.save(update_fields=['first_name','last_name','email']);messages.success(request,'Đã cập nhật thông tin cá nhân.');return redirect('customer_profile')
    return render(request, 'staff/profile.html' if get_role(request.user)=='STAFF' else 'customer/account/profile.html',{'staff_page':'profile','profile_form':form})


def cart(request):
    quantities = session_cart(request)
    rows = []
    dishes = get_dishes()
    active_ids = {str(d["id"]) for d in dishes}
    quantities = {key: value for key, value in quantities.items() if key in active_ids}
    if quantities != session_cart(request):
        request.session["cart"] = quantities
    for dish in dishes:
        quantity = quantities.get(str(dish["id"]), 0)
        if quantity:
            rows.append({**dish, "quantity": quantity, "subtotal": format_money(dish["price"] * quantity) + " ₫" if dish["price"] is not None else "Liên hệ"})
    from .module07_cart import enrich_preview
    preview=enrich_preview(request,rows)
    return render(request, "customer/cart.html", {"rows": preview['rows'], "total": format_money(preview['total']), "combo_rows":preview['combo_rows'], "cart_errors":preview['errors'], "has_unpriced": any(d["price"] is None for d in rows), "page": "cart"})


@require_POST
def update_cart(request, dish_id):
    item = get_object_or_404(MenuItem.objects.select_related("category"), pk=dish_id)
    quantities = session_cart(request).copy()
    key = str(dish_id)
    action = request.POST.get("action", "add")
    current = quantities.get(key, 0)
    if isinstance(current,bool) or not isinstance(current,int) or not 0 <= current <= 99:
        current = 0
    if action == "remove":
        quantities.pop(key, None)
    elif action == "decrease":
        if current <= 1:
            quantities.pop(key, None)
        else:
            quantities[key] = current - 1
    elif action == "add":
        if not item.is_available or not item.category.is_active:
            return JsonResponse({"error": "Món đang ngừng phục vụ."}, status=400)
        from .cart_service import add_to_cart
        try:
            quantity=int(request.POST.get('quantity','1'))
            if not 1<=quantity<=99: raise ValueError
        except (ValueError,TypeError): return JsonResponse({'error':'Số lượng phải từ 1 đến 99.'},status=400)
        if request.POST.get('topping_selection')=='1':
            from .commerce_service import identifiers
            from .models import Topping
            try:
                ids=identifiers(request.POST.getlist('toppings'))
                if Topping.objects.filter(pk__in=ids,is_available=True,menu_items=item).distinct().count()!=len(ids): raise ValidationError('Topping không hợp lệ.')
            except ValidationError as exc: return JsonResponse({'error':' '.join(exc.messages)},status=400)
            selected=request.session.get('topping_cart',{}).copy(); selected[key]=ids; request.session['topping_cart']=selected
        try: quantities = add_to_cart(request,item,quantity,cap=True)
        except ValidationError as exc: return JsonResponse({'error':' '.join(exc.messages)},status=400)
    else:
        return JsonResponse({"error": "Thao tác không hợp lệ."}, status=400)
    request.session["cart"] = quantities
    if key not in quantities:
        selected=request.session.get('topping_cart',{}).copy(); selected.pop(key,None); request.session['topping_cart']=selected
    if "application/json" in request.headers.get("Accept", ""):
        from .customer_booking_workspace import cart_preview
        preview = cart_preview(request)
        return JsonResponse({"food_count": preview["food_count"], "food_total": preview["food_total"], "count": sum(quantities.values()), "message": "Đã cập nhật giỏ món."})
    if request.POST.get("return_to") == "booking_menu":
        return redirect("/menu/?from=booking")
    return redirect("customer_booking" if request.POST.get('return_to') == 'booking' else "customer_cart")


@login_required
def booking(request):
    from .customer_booking_workspace import workspace
    return workspace(request)


@login_required
@require_POST
def cancel_booking(request, booking_id):
    from .models import Booking
    from .booking_service import transition_booking
    reservation = get_object_or_404(Booking, pk=booking_id, user=request.user)
    try:
        transition_booking(reservation.pk, Booking.Status.CANCELLED, owner=request.user)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    else:
        messages.success(request, f'Đã hủy đặt bàn #{reservation.pk}. Khung giờ đã giữ được giải phóng.')
    return redirect('customer_booking')


def about(request):
    return render(request, "customer/about.html", {"page": "about"})


def offers(request):
    return render(request, "customer/recommendations.html", {"dishes": get_dishes()[4:], "page": "offers"})



def food_detail(request, dish_id):
    item = get_object_or_404(menu_items(), pk=dish_id)
    dish = serialize_item(item)
    related = [serialize_item(other) for other in menu_items().filter(category=item.category).exclude(pk=item.pk)[:4]]
    from django.db.models import Avg
    from .customer_booking_workspace import menu_context
    return render(request, "customer/food-detail.html", {"dish": dish, "related": related,'recipe_summary':item.recipe_lines.select_related('ingredient'), "toppings":item.toppings.filter(is_available=True), "rating":item.reviews.filter(is_visible=True).aggregate(n=Avg('rating'))['n'], "page": "menu", **menu_context(request)})


@role_required('ADMIN', 'MANAGER', 'STAFF')
def admin_menu_form(request, dish_id=None):
    permission = 'customers.add_menuitem' if dish_id is None else 'customers.change_menuitem'
    if not has_capability(request.user, permission):
        raise PermissionDenied("Bạn chưa được cấp quyền sửa thực đơn.")
    item = get_object_or_404(MenuItem, pk=dish_id) if dish_id is not None else None
    form = MenuItemForm(request.POST if request.method == 'POST' else None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Đã lưu món ăn / đồ uống.")
        return redirect('/management/#menu')
    return render(request, 'admin/restaurant/menu-form.html', {'form': form, 'item': item, 'admin_page':'menu'})


@capability_required('customers.change_menuitem')
@require_POST
def admin_menu_toggle(request, dish_id):
    item = get_object_or_404(MenuItem, pk=dish_id)
    value = request.POST.get('is_available')
    if value not in ('true', 'false'):
        return JsonResponse({'error': 'Trạng thái không hợp lệ.'}, status=400)
    item.is_available = value == 'true'
    item.save(update_fields=['is_available', 'updated_at'])
    return redirect('/management/#menu')


@role_required('ADMIN')
def account_list(request):
    from django.contrib.auth.models import User
    from django.db.models import Q
    from django.core.paginator import Paginator
    from .rbac import get_assigned_role
    query = request.GET.get('q', '').strip()
    users = User.objects.prefetch_related('groups').order_by('id')
    if query:
        users = users.filter(Q(username__icontains=query) | Q(email__icontains=query))
    page = Paginator(users, 30).get_page(request.GET.get('page'))
    rows = [{'user': user, 'role': get_assigned_role(user),
             'can_edit': not user.is_superuser or request.user.is_superuser} for user in page]
    return render(request, 'admin/system/accounts.html', {'rows': rows, 'pagination': page, 'query': query, 'admin_page': 'accounts'})


@role_required('ADMIN')
def account_edit(request, user_id):
    from django.contrib.auth.models import User
    from django.core.exceptions import ValidationError
    from .forms import AccountRoleForm
    from .account_service import update_account
    from .rbac import get_assigned_role
    target = get_object_or_404(User, pk=user_id)
    if target.is_superuser and not request.user.is_superuser:
        raise PermissionDenied('Chỉ superuser được quản lý superuser.')
    form = AccountRoleForm(request.POST if request.method == 'POST' else None,
                           initial={'role': get_assigned_role(target), 'is_active': target.is_active})
    if request.method == 'POST' and form.is_valid():
        try:
            update_account(request.user, target.pk, form.cleaned_data['role'], form.cleaned_data['is_active'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Đã cập nhật vai trò và trạng thái tài khoản.')
            return redirect('admin_accounts')
    return render(request, 'admin/system/account-edit.html', {'form': form, 'target': target, 'admin_page': 'accounts'})
