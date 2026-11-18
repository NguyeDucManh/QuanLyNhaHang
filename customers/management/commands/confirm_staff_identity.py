import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from customers.models import Employee
from customers.employee_identity import confirm_identity

class Command(BaseCommand):
    help='Preview explicit staff identity confirmation; --apply records an audit, never renames users/codes.'
    def add_arguments(self,p):
        p.add_argument('--employee',type=int,required=True)
        p.add_argument('--actor',required=True)
        p.add_argument('--reason',required=True)
        p.add_argument('--apply',action='store_true')
    def handle(self,*args,**o):
        employee=Employee.objects.select_related('user').get(pk=o['employee'])
        actor=get_user_model().objects.get(username=o['actor'])
        if o['apply']:confirm_identity(employee.pk,actor=actor,reason=o['reason'])
        self.stdout.write(json.dumps({'employee_id':employee.pk,'user_id':employee.user_id,
            'code_preserved':True,'applied':o['apply'],'attendance_created':False},ensure_ascii=False))
