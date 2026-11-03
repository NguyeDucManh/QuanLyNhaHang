import json
from datetime import date
from django.core.management.base import BaseCommand,CommandError
from customers.ai.research_data import prepare
class Command(BaseCommand):
    help='Create reproducible research artifacts without modifying operational data.'
    def add_arguments(self,parser):
        parser.add_argument('--seed',type=int,default=42); parser.add_argument('--days',type=int,default=70)
        parser.add_argument('--interactions',type=int,default=280); parser.add_argument('--end-date',type=date.fromisoformat)
    def handle(self,*args,**options):
        try: result=prepare(options['seed'],options['days'],options['interactions'],options['end_date'])
        except ValueError as exc: raise CommandError(str(exc))
        self.stdout.write(json.dumps(result,ensure_ascii=True))
