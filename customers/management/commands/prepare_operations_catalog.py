import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from customers.operational_catalog import preview_catalog,apply_catalog

class Command(BaseCommand):
    help='Preview verified non-menu catalog only; no stock/history/menu updates.'
    def add_arguments(self,p):
        p.add_argument('--manifest',required=True)
        p.add_argument('--actor')
        p.add_argument('--approved-digest')
        p.add_argument('--apply',action='store_true')
        p.add_argument('--dry-run',action='store_true')
    def handle(self,*args,**o):
        entries=json.loads(Path(o['manifest']).read_text(encoding='utf-8'))
        preview=preview_catalog(entries)
        if o['apply']:
            if o['dry_run'] or not o['actor'] or not o['approved_digest']:raise CommandError('Apply cần actor/hash đã duyệt và không đi cùng dry-run.')
            actor=get_user_model().objects.get(username=o['actor'])
            created=apply_catalog(entries,actor=actor,approved_digest=o['approved_digest']);preview['created']=len(created)
        preview['applied']=o['apply'];self.stdout.write(json.dumps(preview,ensure_ascii=True))
