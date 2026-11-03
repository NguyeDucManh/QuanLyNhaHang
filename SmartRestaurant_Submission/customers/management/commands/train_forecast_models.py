import json
from django.core.management.base import BaseCommand,CommandError
class Command(BaseCommand):
    help='Train CPU Linear Regression, Random Forest, XGBoost with temporal holdouts.'
    def handle(self,*args,**options):
        from customers.ai.forecast_service import train
        try: result=train()
        except ValueError as exc: raise CommandError(str(exc))
        self.stdout.write(json.dumps(result,ensure_ascii=True))
