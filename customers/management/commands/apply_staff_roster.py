import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from customers.roster_service import apply_roster

class Command(BaseCommand):
    help='Apply exactly an approved signed roster preview; defaults to no writes.'
    def add_arguments(self,p):
        p.add_argument('--plan',required=True)
        p.add_argument('--actor',required=True)
        p.add_argument('--approved-digest')
        p.add_argument('--approve-current',action='store_true')
        p.add_argument('--apply',action='store_true')
    def handle(self,*args,**o):
        data=json.loads(Path(o['plan']).read_text(encoding='utf-8'))
        if not o['apply']:
            self.stdout.write(json.dumps({'applied':False,'rows':len(data['proposal']['rows']),'digest':data['proposal']['plan_digest']}));return
        if not o['approved_digest']:raise CommandError('Cần phê duyệt đúng --approved-digest; chưa ghi dữ liệu.')
        actor=get_user_model().objects.get(username=o['actor'])
        rows=apply_roster(data['token'],actor=actor,approved_digest=o['approved_digest'],approve_current=o['approve_current'])
        self.stdout.write(json.dumps({'applied':True,'created':len(rows),'attendance_created':False}))
