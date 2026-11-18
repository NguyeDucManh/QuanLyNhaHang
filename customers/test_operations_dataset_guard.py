from django.test import SimpleTestCase
from .operations_test_dataset import fixture_database_allowed

class DatasetSafetyTests(SimpleTestCase):
    def test_original_local_and_render_are_always_rejected(self):
        for name in ('smart_restaurant','smart_restaurant_demo','postgres'):
            self.assertFalse(fixture_database_allowed(name,'localhost',False,True))
        self.assertFalse(fixture_database_allowed('test_issue10_sandbox','remote-host',False,True))
        self.assertFalse(fixture_database_allowed('test_issue10_sandbox','localhost',True,True))
        self.assertFalse(fixture_database_allowed('test_issue10_sandbox','localhost',False,False))
    def test_only_explicit_isolated_test_target_is_accepted(self):
        self.assertTrue(fixture_database_allowed('test_issue10_sandbox','127.0.0.1',False,True))
