from .operational_labels import operational_text
from .menu_service import session_cart
from .rbac import get_role, can_manage, management_access
from django.urls import reverse
from .models import RestaurantTable,Order,Payment,Ingredient
from django.db.models import F,Sum
from django.utils import timezone
from datetime import timedelta

def customer_context(request):
    from .models import RestaurantInfo
    cart = session_cart(request)
    access = management_access(request.user)
    summary = {'total': 0, 'available': 0, 'occupied': 0, 'maintenance': 0, 'inactive': 0}
    if access['view_tables']:
        summary['total'] = RestaurantTable.objects.count()
        active = RestaurantTable.objects.filter(is_active=True, area__is_active=True)
        for label in ('available', 'occupied', 'maintenance'):
            summary[label] = active.filter(status=label.upper()).count()
        summary['inactive'] = summary['total'] - sum(summary[label] for label in ('available', 'occupied', 'maintenance'))
    from .module07_views import RESOURCES
    routes={page:reverse('module07_list',args=[resource]) for resource,(_,_,page,_,_) in RESOURCES.items()}
    routes.update(payroll=reverse('payroll_list'),messages=reverse('chat'),reports=reverse('admin_reports'))
    routes['reviews']=reverse('reviews')
    routes.update({'categories':reverse('admin_categories'),'location-settings':reverse('location_settings'),'ai-chatbot':reverse('ai_chatbot_management')})
    routes.update({'ai-schedule':reverse('ai_schedules'),'recommendation-demo':reverse('recommendation_demo'),'ai-dashboard':reverse('ai_dashboard'),'ai-forecast':reverse('ai_forecast'),'ai-inventory':reverse('ai_inventory'),'ai-faces':reverse('ai_faces')})
    combo_cart=request.session.get('combo_cart',{})
    combo_count=sum(q for q in combo_cart.values() if isinstance(q,int) and not isinstance(q,bool) and 1<=q<=20) if isinstance(combo_cart,dict) else 0
    return {
        'footer_restaurant':RestaurantInfo.objects.filter(is_active=True).first(),
        "cart_count": (sum(value for value in cart.values() if isinstance(value,int) and not isinstance(value,bool) and 1 <= value <= 99) if isinstance(cart,dict) else 0)+combo_count, "business_role": get_role(request.user), "can_access_management": can_manage(request.user),
        "rbac_access": access, "table_summary": summary,
        "admin_identity": {"name": request.user.get_full_name() or request.user.username} if request.user.is_authenticated else {},
        "admin_routes": {key: reverse(name) for key, name in {
            'home': 'admin_home', 'accounts': 'admin_accounts', 'areas': 'admin_areas', 'tables': 'admin_tables', 'bookings': 'admin_bookings',
            'menu':'admin_menu_list','orders':'admin_orders','kitchen':'admin_kitchen','payments':'admin_invoices','ingredients':'admin_ingredients','transactions':'admin_transactions','suppliers':'admin_suppliers','recipes':'admin_recipes','stock-alerts':'admin_stock_alerts',
        }.items()} | routes,
    }


def business_dashboard(request):
    access=management_access(request.user)
    today=timezone.localdate()
    summary={'revenue_today':0,'order_count_today':0,'low_stock_count':0,'revenue_days':[]}
    orders=[]
    stocks=[]
    if access['view_orders']:
        from .models import Booking,OrderItem
        from django.db.models import Count
        summary['booking_today']=Booking.objects.filter(date=today).exclude(status='CANCELLED').count()
        summary['customers']=Order.objects.exclude(customer_id=None).values('customer_id').distinct().count()
        summary['order_status']=[{'label':r['status'],'value':r['count']} for r in Order.objects.values('status').annotate(count=Count('pk'))]
        summary['upcoming_bookings']=[{'name':r.name,'time':str(r.start_time),'guests':r.guests,'url':reverse('admin_booking_detail',args=[r.pk])} for r in Booking.objects.filter(start_time__gte=timezone.now(),status__in=['PENDING','CONFIRMED']).order_by('start_time')[:5]]
        summary['kitchen_count']=OrderItem.objects.filter(kitchen_status__in=['QUEUED','PREPARING']).count()
        summary['pending_orders']=Order.objects.filter(status='PENDING').count()
        summary['top_items']=[{'name':r['menu_item__name'],'quantity':r['quantity'],'image':r['menu_item__image']} for r in OrderItem.objects.filter(order__invoice__status='PAID',order__created_at__date__gte=today-timedelta(days=29)).exclude(kitchen_status='CANCELLED').values('menu_item__name','menu_item__image').annotate(quantity=Sum('quantity')).order_by('-quantity')[:5]]
        summary['order_count_today']=Order.objects.filter(created_at__date=today).count()
        for order in Order.objects.select_related('customer','table').order_by('-created_at')[:7]:
            orders.append({'id':order.pk,'order_number':order.order_number,'time':timezone.localtime(order.created_at).strftime('%H:%M'),'table':order.table.code if order.table else 'Mang đi',
                'customer':order.customer.username if order.customer else 'Khách vãng lai','total':order.total_amount,'status':order.status,'url':reverse('admin_order_detail',args=[order.pk])})
    if access['view_payments'] and has_payment_permission(request):
        paid=Payment.objects.filter(status='SUCCEEDED')
        summary['revenue_today']=paid.filter(paid_at__date=today).aggregate(total=Sum('amount'))['total'] or 0
        summary['paid_invoices_today']=paid.filter(paid_at__date=today).values('invoice_id').distinct().count()
        daily={row['paid_at__date']:row['total'] for row in paid.filter(paid_at__date__gte=today-timedelta(days=29)).values('paid_at__date').annotate(total=Sum('amount'))}
        summary['revenue_days']=[daily.get(today-timedelta(days=i),0) for i in range(29,-1,-1)]
    if access['view_ingredients']:
        low=Ingredient.objects.filter(is_active=True,current_stock__lte=F('minimum_stock')).order_by('code')
        summary['low_stock_count']=low.count()
        stocks=[[row.name,row.current_stock,row.minimum_stock,row.get_unit_display()] for row in low[:5]]
    if access['view_transactions']:
        from .models import StockMovement
        summary['recent_stock']=[{'ingredient':operational_text(row.ingredient.name),'kind':row.get_movement_type_display(),'quantity':str(row.quantity),'unit':row.ingredient.get_unit_display(),'time':timezone.localtime(row.created_at).strftime('%d/%m/%Y %H:%M')} for row in StockMovement.objects.select_related('ingredient').order_by('-created_at','-pk')[:5]]
    from .models import Employee,WorkSchedule,Attendance
    from .employee_identity import operational_employees
    summary['employee_active']=operational_employees().count() if access.get('employees') else 0
    summary['employee_present']=Attendance.objects.filter(employee_id__in=operational_employees().values("pk"),work_date=today,check_in_time__isnull=False,check_out_time__isnull=True).count() if access.get('attendance') else 0
    summary['shifts_today']=[{'name':operational_text(s.shift.name),'employee':operational_text(s.employee.full_name),'start':timezone.localtime(s.start_at).strftime('%H:%M'),'end':timezone.localtime(s.end_at).strftime('%H:%M')} for s in WorkSchedule.objects.select_related('shift','employee').filter(employee_id__in=operational_employees().values('pk'),work_date=today,status='APPROVED').order_by('start_at')[:10]] if access.get('schedules') else []
    return {'business_summary':summary,'recent_orders':orders,'low_stocks':stocks}


def has_payment_permission(request):
    from .rbac import has_capability
    return has_capability(request.user,'customers.view_payment')

