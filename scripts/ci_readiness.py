"""CI-only smoke against disposable DB/Redis; never imports local .env secrets."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.test import Client,override_settings

assert settings.DATABASES['default']['NAME']=='restaurant_ci','Only disposable CI database permitted'
assert settings.DATABASES['default']['HOST'] in ('127.0.0.1','localhost')

mode=sys.argv[1]
if mode in ('legacy','migrated'):
    tables=set(connection.introspection.table_names())
    expected={'customers_tableserviceassignment','customers_tablesession'}
    assert (not tables.intersection(expected)) if mode=='legacy' else expected.issubset(tables)
    with override_settings(ALLOWED_HOSTS=['testserver'],TABLE_SERVICE_ASSIGNMENTS_ENABLED=False,TABLE_SERVICE_LIFECYCLE_ENABLED=False):
        client=Client()
        for url in ('/','/menu/','/login/','/robots.txt','/sitemap.xml','/healthz/'):
            response=client.get(url)
            assert response.status_code==200,(url,response.status_code)
    print(json.dumps({'schema':mode,'flags_off_public_smoke':'PASS'}))
elif mode=='face':
    from django.core.management import call_command
    from io import StringIO
    output=StringIO();call_command('check_face_runtime',load_engine=True,stdout=output)
    report=json.loads(output.getvalue())
    assert report['engine']['ready'],report
    assert report['engine']['tensor_smoke_dimensions']==128
    assert all(report['assets'][name]['hash_matches'] for name in ('facenet.onnx','face_landmarker.task'))
    print(output.getvalue())
elif mode=='redis':
    from channels_redis.core import RedisChannelLayer
    async def smoke():
        first=RedisChannelLayer(hosts=[os.environ['CHANNEL_REDIS_URL']])
        second=RedisChannelLayer(hosts=[os.environ['CHANNEL_REDIS_URL']])
        channel=await first.new_channel()
        try:
            await first.group_add('ci.readiness',channel)
            await second.group_send('ci.readiness',{'type':'ci.smoke','value':42})
            message=await asyncio.wait_for(first.receive(channel),5)
            assert message['value']==42
            await first.group_discard('ci.readiness',channel)
        finally:
            await first.close_pools();await second.close_pools()
    asyncio.run(smoke());print('Redis independent channel-layer clients: PASS')
else:raise SystemExit('Unknown CI smoke')
