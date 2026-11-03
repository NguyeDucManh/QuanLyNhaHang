import json
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction,connection
from django.apps import apps
from customers.operational_labels import audit_labels

class Command(BaseCommand):
    help='Preview operational labels; --apply renames safe names only, never DELETE/PK/FK/identity changes.'
    def add_arguments(self,p):
        p.add_argument('--apply',action='store_true');p.add_argument('--allow-test-database',action='store_true');p.add_argument('--report')
    def handle(self,*args,**options):
        db=connection.settings_dict['NAME'];qa=any(str(db).startswith(prefix) for prefix in ['test_','sr_','qa_'])
        if options['apply'] and qa and not options['allow_test_database']:raise CommandError('QA/test DB: explicit --allow-test-database required; ordinary operational command skips it.')
        with transaction.atomic():
            rows=audit_labels();changes=[]
            if options['apply']:
                for row in rows:
                    if row['action']!='RENAME':continue
                    model=apps.get_model('customers',row['model']);obj=model.objects.select_for_update().get(pk=row['pk'])
                    if getattr(obj,row['field'])!=row['current_value']:raise CommandError('Record changed since preview; retry.')
                    setattr(obj,row['field'],row['after']);obj.full_clean();obj.save(update_fields=[row['field']]);changes.append(row)
            result={'database':str(db),'apply':options['apply'],'matched_fields':len(rows),'matched_records':len({(r['model'],r['pk']) for r in rows}),'renamed_fields':len(changes),'items':rows,'changes':changes,'deleted_records':0}
        if options.get('report'):Path(options['report']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(result,ensure_ascii=True,indent=2))
