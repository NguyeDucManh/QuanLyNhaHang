from datetime import date
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import render,redirect
from django.urls import reverse
from django.utils import timezone
from .rbac import role_required,capability_required,get_role
from .ga_service import require_ga,load_problem,run_ga,save_proposal,WEIGHTS
from .ai_forms import GAForm
from .menu_service import serialize_item

@role_required('ADMIN','MANAGER')
def ai_schedules(request):
    require_ga(request.user)
    proposal=request.session.get('ga_proposal')
    if proposal and (proposal.get('owner')!=request.user.pk or timezone.now().timestamp()-proposal.get('created_at',0)>1800):proposal=None
    form=GAForm(request.POST if request.method=='POST' and request.POST.get('action')=='preview' else None)
    if request.method=='POST':
        action=request.POST.get('action')
        if action=='preview' and form.is_valid():
            values=form.cleaned_data.copy()
            try:
                problem=load_problem(values.pop('start_date'),values.pop('end_date'))
                proposal=run_ga(problem,**values);proposal.update(owner=request.user.pk,created_at=timezone.now().timestamp())
                request.session['ga_proposal']=proposal
            except ValidationError as exc:form.add_error(None,exc)
        elif action=='save':
            if proposal is None:messages.error(request,'Đề xuất hết hạn/không tồn tại; tạo lại trước khi lưu.')
            else:
                try:created=save_proposal(proposal,actor=request.user)
                except ValidationError as exc:messages.error(request,' '.join(exc.messages))
                else:
                    request.session.pop('ga_proposal',None);messages.success(request,f'Đã lưu {len(created)} lịch AI/DRAFT. Cần chỉnh/duyệt tại Lịch làm việc.')
                    return redirect('module07_list',resource='workschedule')
        elif action=='discard':
            request.session.pop('ga_proposal',None);return redirect('ai_schedules')
    rows=[]
    if proposal:
        from .models import Employee,Shift
        employees={e.pk:e for e in Employee.objects.select_related('position').filter(pk__in=[r['employee_id'] for r in proposal['rows']])}
        shifts={s.pk:s for s in Shift.objects.filter(pk__in=[r['shift_id'] for r in proposal['rows']])}
        rows=[{'day':r['work_date'],'employee':employees.get(r['employee_id']),'shift':shifts.get(r['shift_id'])} for r in proposal['rows']]
    return render(request,'admin/ai/schedules.html',{'admin_page':'ai-schedule','form':form,'proposal':proposal,'rows':rows,'weights':WEIGHTS})

def customer_recommendations(request):
    from .ai.hybrid_service import recommend
    result=recommend(request.user,n=12)
    dishes=[{**serialize_item(row['item']),'recommendation_reason':row['reason']} for row in result['recommendations']]
    return render(request,'customer/ai/recommendations.html',{'dishes':dishes,'page':'recommendations'})
