import json
from pathlib import Path
from django.core.management.base import BaseCommand
from customers.employee_identity import account_audit

class Command(BaseCommand):
    help='Read-only User/Employee/role/seed/reference audit. Never changes database.'
    def add_arguments(self,parser):
        parser.add_argument('--output',help='Optional JSON report path (no passwords or biometric vectors).')
    def handle(self,*args,**options):
        result=account_audit()
        content=json.dumps(result,ensure_ascii=True,indent=2)
        if options['output']:
            Path(options['output']).write_text(content,encoding='utf-8')
        self.stdout.write(content)
