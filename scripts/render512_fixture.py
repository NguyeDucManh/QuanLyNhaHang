"""Disposable CI DB only. Never invoke against local/production business data."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['NAME']=='restaurant_ci512'
assert settings.DATABASES['default']['HOST']=='127.0.0.1'
from django.core.management import call_command
call_command('migrate',interactive=False,verbosity=0)
from customers.test_module07 import Module07Fixtures
from django.utils import timezone
class Fixture(Module07Fixtures,unittest.TestCase):pass
Fixture.initialize()
fixture=Fixture();fixture.personnel()
now=timezone.localtime()
fixture.shift.start_time=now.replace(minute=0,second=0,microsecond=0).time()
fixture.shift.end_time=(now+timezone.timedelta(hours=8)).replace(minute=0,second=0,microsecond=0).time()
fixture.shift.save()
fixture.approved_schedule()
for user in (fixture.admin,fixture.manager,fixture.staff,fixture.customer):
    user.set_password('CI-resource-probe-only-2026!');user.save(update_fields=['password'])
fixture.order(customer=fixture.customer)
print('512MiB probe fixture created only in restaurant_ci512.')
