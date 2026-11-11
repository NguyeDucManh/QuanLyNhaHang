from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from .rbac import capability_required
from .table_session_service import release


@require_POST
@capability_required('customers.change_order')
def release_order_table(request,pk):
    try:
        release(actor=request.user,order_id=pk,reason=request.POST.get('reason',''),
                override=request.POST.get('override')=='on',confirm=request.POST.get('confirm')=='on')
    except ValidationError as exc:messages.error(request,' '.join(exc.messages))
    else:messages.success(request,'Đã xác nhận trả bàn; dữ liệu thanh toán giữ nguyên.')
    return redirect('admin_order_detail',pk=pk)
