import json
from django.core.management.base import BaseCommand,CommandError
class Command(BaseCommand):
    help='Fit and evaluate temporal content/collaborative/hybrid recommendation.'
    def handle(self,*args,**options):
        from customers.ai.hybrid_service import train
        try: result=train()
        except ValueError as exc: raise CommandError(str(exc))
        self.stdout.write(json.dumps(result,ensure_ascii=True))
