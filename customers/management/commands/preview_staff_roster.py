from datetime import date,timedelta
import json
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from customers.models import Employee,Shift
from customers.roster_service import preview_roster,monday

class Command(BaseCommand):
    help='Read-only five-week roster preview. No schedules, attendance, menu or users are created.'
    def add_arguments(self,p):
        p.add_argument('--reference-date',type=date.fromisoformat)
        p.add_argument('--policy',required=True,help='JSON rules reviewed against positions/shift demand.')
        p.add_argument('--output',required=True)
    def handle(self,*args,**o):
        day=o['reference_date'] or timezone.localdate();start=monday(day)-timedelta(weeks=4)
        rules=json.loads(Path(o['policy']).read_text(encoding='utf-8'))
        preview=preview_roster(start,start+timedelta(days=34),rules)
        Path(o['output']).write_text(json.dumps(preview,ensure_ascii=False,indent=2),encoding='utf-8')
        p=preview['proposal']
        self.stdout.write(json.dumps({'preview_only':True,'start':p['start_date'],'end':p['end_date'],
            'proposed_rows':len(p['rows']),'staff':p['staff'],'metrics':p['metrics'],
            'plan_digest':p['plan_digest'],'output':o['output']},ensure_ascii=True))
