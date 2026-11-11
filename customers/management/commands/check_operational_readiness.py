"""Read-only deployment gates; never seed, migrate, expire holds or publish events."""
import hashlib,json
from pathlib import Path
from django.conf import settings
from django.core.management import BaseCommand,CommandError,get_commands
from django.db import connection,transaction
from django.utils import timezone
from customers.models import BookingDeposit,Order,RestaurantTable


class Command(BaseCommand):
    help='Inspect schema/flags, map assets, deposit backlog and optional Redis PING without writes.'
    def add_arguments(self,p):
        p.add_argument('--require-enabled',action='store_true')
        p.add_argument('--require-redis',action='store_true')
    def handle(self,*args,**options):
        failures=[]
        report={'read_only':True,'flags':{k:getattr(settings,k,False) for k in ('TABLE_SERVICE_ASSIGNMENTS_ENABLED','TABLE_SERVICE_LIFECYCLE_ENABLED')}}
        with transaction.atomic():
            with connection.cursor() as cursor:cursor.execute('SET TRANSACTION READ ONLY')
            tables=set(connection.introspection.table_names())
            required={'TABLE_SERVICE_ASSIGNMENTS_ENABLED':'customers_tableserviceassignment','TABLE_SERVICE_LIFECYCLE_ENABLED':'customers_tablesession'}
            report['schema']={table:table in tables for table in required.values()}
            for flag,table in required.items():
                if report['flags'][flag] and table not in tables:failures.append('Enabled feature schema missing: '+table)
                if options['require_enabled'] and not report['flags'][flag]:failures.append('Feature not enabled: '+flag)
            report['deposits']={'expired_unprocessed':BookingDeposit.objects.filter(status__in=['PENDING','FAILED'],expires_at__lte=timezone.now()).count(),
                                'scheduler_command_present':'expire_booking_deposits' in get_commands(),
                                'external_schedule_verified':False}
            report['legacy_review']={'occupied_tables':RestaurantTable.objects.filter(status='OCCUPIED').count(),
                                     'active_orders':Order.objects.filter(status__in=['PENDING','CONFIRMED','PREPARING']).count()}
        folder=Path(settings.BASE_DIR)/'static/vendor/maplibre'
        try:
            manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            report['map_vendor_hashes']=all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==entry['sha256'] for name,entry in manifest['files'].items())
        except (OSError,KeyError,ValueError):report['map_vendor_hashes']=False
        if not report['map_vendor_hashes']:failures.append('Map vendor assets/hash invalid')
        report['redis']={'backend':settings.CHANNEL_LAYERS['default']['BACKEND'],'ping':None}
        url=getattr(settings,'CHANNEL_LAYERS',{}).get('default',{}).get('CONFIG',{}).get('hosts',[])
        if 'RedisChannelLayer' in report['redis']['backend']:
            try:
                import redis
                client=redis.Redis.from_url(url[0],socket_connect_timeout=5,socket_timeout=5)
                try:report['redis']['ping']=bool(client.ping())
                finally:client.close()
            except Exception as exc:report['redis']['error_type']=type(exc).__name__;failures.append('Redis PING failed')
        elif options['require_redis']:failures.append('Shared Redis channel layer not configured')
        report['failures']=failures;self.stdout.write(json.dumps(report,indent=2))
        if failures:raise CommandError('Operational readiness gates failed; inspect non-sensitive JSON above.')
