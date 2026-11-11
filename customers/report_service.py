from . import service_scope
"""PostgreSQL facts; financial data is restricted independently of the dashboard."""
from decimal import Decimal
from django.db.models import Count,Sum,Avg,F
from django.db.models.functions import TruncDate,TruncMonth
from .models import Order,OrderItem,Invoice,Payment,Booking,RestaurantTable,Ingredient,StockMovement,Employee,WorkSchedule,Attendance,Payroll,Review,MenuItem,RecipeIngredient,Topping,Combo,Promotion,Position,Shift
from .rbac import has_capability

def report_data(user):
    sections=[]
    if has_capability(user,'customers.view_order'):
        sections.append(('Đơn / Khách / Đặt bàn', [('Order',service_scope.orders(user).count()),('Customer có Order',service_scope.orders(user).exclude(customer=None).values('customer').distinct().count()),('Booking',service_scope.bookings(user).count()),*[(f'Order {x["status"]}',x['n']) for x in service_scope.orders(user).values('status').annotate(n=Count('id')).order_by('status')],*[(f'Booking {x["date"]}',x['n']) for x in service_scope.bookings(user).values('date').annotate(n=Count('id')).order_by('-date')[:31]]]))
        best=OrderItem.objects.filter(order__in=service_scope.orders(user),order__invoice__status='PAID').exclude(kitchen_status='CANCELLED').values('menu_item__name').annotate(n=Sum('quantity')).order_by('-n')[:10]
        sections.append(('Món bán chạy (đơn đã thanh toán)',[(r['menu_item__name'],r['n']) for r in best]))
    if has_capability(user,'customers.view_invoice') and has_capability(user,'customers.view_payment'):
        paid=service_scope.payments(user).filter(status='SUCCEEDED')
        from .models import BookingDeposit
        deposits=BookingDeposit.objects.filter(booking__in=service_scope.bookings(user),status='SUCCEEDED')
        settled=service_scope.invoices(user).filter(status='PAID')
        extra_cash=paid.aggregate(n=Sum('amount'))['n'] or Decimal(0)
        deposit_cash=deposits.aggregate(n=Sum('amount'))['n'] or Decimal(0)
        revenue=settled.aggregate(n=Sum('total_amount'))['n'] or Decimal(0)
        applied=settled.aggregate(n=Sum('deposit_applied_amount'))['n'] or Decimal(0)
        sections.append(('Đối chiếu thu tiền và doanh thu',[
            ('Thu cọc thành công (gồm khoản cần đối soát)',deposit_cash),
            ('Thu bổ sung Payment thành công',extra_cash),('Tổng tiền thu gộp, chưa trừ hoàn tiền',deposit_cash+extra_cash),
            ('Doanh thu hóa đơn PAID',revenue),('Cọc đã áp dụng vào hóa đơn PAID',applied),
            ('Cọc chờ xử lý/hoàn phần dư: không cộng thêm vào doanh thu',deposit_cash-applied)]))
        rows=[('Thực thu',paid.aggregate(n=Sum('amount'))['n'] or Decimal(0)),('Invoice PAID',service_scope.invoices(user).filter(status='PAID').count()),('Invoice UNPAID',service_scope.invoices(user).filter(status='UNPAID').count())]
        rows.extend((f'Ngày {r["day"]}',r['n']) for r in paid.annotate(day=TruncDate('paid_at')).values('day').annotate(n=Sum('amount')).order_by('-day')[:31])
        rows.extend((f'Tháng {r["month"].strftime("%m/%Y")}',r['n']) for r in paid.annotate(month=TruncMonth('paid_at')).values('month').annotate(n=Sum('amount')).order_by('-month')[:12])
        sections.append(('Doanh thu Payment SUCCEEDED',rows))
        sections.append(('Thực thu theo phương thức thanh toán',[(Payment.Method(r['payment_method']).label,r['n']) for r in paid.values('payment_method').annotate(n=Sum('amount')).order_by('payment_method')]))
        if has_capability(user,'customers.view_order'):
            category_sales=OrderItem.objects.filter(order__in=service_scope.orders(user),order__invoice__status='PAID').exclude(kitchen_status='CANCELLED').values('menu_item__category__name').annotate(n=Sum('line_total')).order_by('-n')
            sections.append(('Doanh số món theo danh mục — trước giảm giá, không gồm topping/combo',[(r['menu_item__category__name'] or 'Không có danh mục',r['n']) for r in category_sales]))
    if has_capability(user,'customers.view_restauranttable'):
        sections.append(('Bàn',[('Tổng bàn',service_scope.tables(user).count()),('Bàn active',service_scope.tables(user).filter(is_active=True,area__is_active=True).count())]))
    if has_capability(user,'customers.view_ingredient'):
        active=Ingredient.objects.filter(is_active=True)
        rows=[('Tổng nguyên liệu',Ingredient.objects.count()),('Tồn thấp',active.filter(current_stock__lte=F('minimum_stock')).count()),('Hết hàng',active.filter(current_stock=0).count())]
        if has_capability(user,'customers.view_stockmovement'):
            rows.extend((f'{r["ingredient__name"]} ({r["ingredient__unit"]}) / {r["movement_type"]}',r['n']) for r in StockMovement.objects.values('ingredient__name','ingredient__unit','movement_type').annotate(n=Sum('quantity')).order_by('ingredient__name'))
        sections.append(('Kho — không cộng lẫn đơn vị',rows))
    if has_capability(user,'customers.view_employee'):
        sections.append(('Nhân sự',[('Employee active',Employee.objects.filter(is_active=True).count()),*[(r['position__name'],r['n']) for r in Employee.objects.values('position__name').annotate(n=Count('id'))]]))
    if has_capability(user,'customers.view_position'):
        sections.append(('Chức vụ',[('Position',Position.objects.count()),('Position active',Position.objects.filter(is_active=True).count())]))
    if has_capability(user,'customers.view_shift'):
        sections.append(('Ca làm việc',[('Shift active',Shift.objects.filter(is_active=True).count()),*[(s.name,f'{s.start_time:%H:%M}–{s.end_time:%H:%M} / yêu cầu {s.required_staff}') for s in Shift.objects.filter(is_active=True).order_by('pk')]]))
    if has_capability(user,'customers.view_recipeingredient'):
        sections.append(('Công thức',[('Món có recipe',MenuItem.objects.filter(recipe_lines__isnull=False).distinct().count()),('RecipeIngredient',RecipeIngredient.objects.count())]))
    for model,permission,title,active_field in [(Topping,'view_topping','Topping','is_available'),(Combo,'view_combo','Combo','is_active'),(Promotion,'view_promotion','Promotion / Voucher','is_active')]:
        if has_capability(user,'customers.'+permission):
            sections.append((title,[('Tổng',model.objects.count()),('Đang bật',model.objects.filter(**{active_field:True}).count())]))
    if has_capability(user,'customers.view_workschedule'):
        sections.append(('Lịch làm việc',[(r['status'],r['n']) for r in WorkSchedule.objects.values('status').annotate(n=Count('id'))]))
    if has_capability(user,'customers.view_attendance'):
        rows=list(Attendance.objects.filter(confirmed_at__isnull=False))
        sections.append(('Chấm công',[('Bản ghi',Attendance.objects.count()),('Đã xác nhận',len(rows)),('Giờ thực tế xác nhận',sum((r.working_hours for r in rows),Decimal(0)).quantize(Decimal('.01')))]))
    if has_capability(user,'customers.view_payroll'):
        sections.append(('Payroll',[(r['status'],f'{r["n"]} bảng / {r["money"]} VND') for r in Payroll.objects.values('status').annotate(n=Count('id'),money=Sum('net_salary'))]))
    if has_capability(user,'customers.view_review'):
        sections.append(('Đánh giá',[('Số review',Review.objects.count()),('Rating hiển thị',Review.objects.filter(is_visible=True).aggregate(n=Avg('rating'))['n'] or 0)]))
    return sections
