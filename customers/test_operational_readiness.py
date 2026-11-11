import json
from io import StringIO
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.core.management import call_command,CommandError


@override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=False,TABLE_SERVICE_LIFECYCLE_ENABLED=False)
class OperationalReadinessTests(TestCase):
    def test_default_readonly_reports_flags_and_scheduler_unknown(self):
        output=StringIO();call_command('check_operational_readiness',stdout=output)
        report=json.loads(output.getvalue())
        self.assertTrue(report['read_only']);self.assertTrue(report['map_vendor_hashes'])
        self.assertFalse(report['deposits']['external_schedule_verified'])
        self.assertTrue(report['deposits']['scheduler_command_present'])
    def test_require_flags_fails_instead_of_claiming_scope_is_enabled(self):
        with self.assertRaises(CommandError):call_command('check_operational_readiness',require_enabled=True,stdout=StringIO())
    @override_settings(TABLE_SERVICE_ASSIGNMENTS_ENABLED=True,TABLE_SERVICE_LIFECYCLE_ENABLED=True)
    def test_missing_schema_with_flag_on_is_failure(self):
        with patch('django.db.connection.introspection.table_names',return_value=[]):
            with self.assertRaises(CommandError):call_command('check_operational_readiness',stdout=StringIO())
    @override_settings(CHANNEL_LAYERS={'default':{'BACKEND':'channels.layers.InMemoryChannelLayer'}})
    def test_redis_required_does_not_accept_inmemory(self):
        with self.assertRaises(CommandError):call_command('check_operational_readiness',require_redis=True,stdout=StringIO())
