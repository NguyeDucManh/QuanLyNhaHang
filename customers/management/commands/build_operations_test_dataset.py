import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from customers.operations_test_dataset import require_test_database,build_dataset

class Command(BaseCommand):
    help='Rich copied-catalog fixtures ONLY on explicitly enabled local test DB; no seed_menu.'
    def add_arguments(self,p):
        p.add_argument('--actor',required=True)
        p.add_argument('--apply',action='store_true')
        p.add_argument('--output',required=True)
    def handle(self,*args,**o):
        require_test_database()
        result=build_dataset(actor=get_user_model().objects.get(username=o['actor'])) if o['apply'] else {'applied':False,'test_database_only':True}
        Path(o['output']).write_text(json.dumps(result,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in result.items() if k not in ('before','after','counts','menu_before','menu_after')}))
