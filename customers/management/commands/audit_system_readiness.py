"""Read-only inventory; never imports AI engines or prints customer/biometric data."""
import json,inspect
from django.core.management.base import BaseCommand
from django.apps import apps
from django.urls import get_resolver,URLResolver
from django.db import transaction
from django.db.models import Count
from django.conf import settings
from customers.models import MenuItem,Booking,Order


class Command(BaseCommand):
    help='Read-only module/routes/model/recipe readiness inventory without PII.'
    def add_arguments(self,p):p.add_argument('--database',action='store_true')
    def handle(self,*args,**options):
        routes=[]
        def walk(patterns,prefix=''):
            for p in patterns:
                if isinstance(p,URLResolver):walk(p.url_patterns,prefix+str(p.pattern))
                else:
                    f=inspect.unwrap(p.callback)
                    routes.append({'route':prefix+str(p.pattern),'name':p.name,'view':f.__module__+'.'+getattr(f,'__name__',type(f).__name__)})
        walk(get_resolver().url_patterns)
        models=[{'name':m._meta.label,'table':m._meta.db_table,'fields':[f.name for f in m._meta.fields],
                 'permissions':list(m._meta.permissions)} for m in apps.get_app_config('customers').get_models()]
        result={'routes':routes,'models':models,'route_count':len(routes),'customer_model_count':len(models),
                'flags':{k:getattr(settings,k,False) for k in ['TABLE_SERVICE_ASSIGNMENTS_ENABLED','TABLE_SERVICE_LIFECYCLE_ENABLED']},
                'channel_backend':settings.CHANNEL_LAYERS['default']['BACKEND']}
        if options['database']:
            with transaction.atomic():
                from django.db import connection
                with connection.cursor() as c:c.execute('SET TRANSACTION READ ONLY')
                result['recipe_coverage']=list(MenuItem.objects.annotate(recipe_count=Count('recipe_lines')).values('id','name','recipe_count','is_available'))
                result['booking_counts']=list(Booking.objects.values('status').annotate(count=Count('pk')))
                result['order_counts']=list(Order.objects.values('status').annotate(count=Count('pk')))
                result['booking_missing_table']=Booking.objects.filter(table__isnull=True).count()
        self.stdout.write(json.dumps(result,ensure_ascii=False,indent=2))
