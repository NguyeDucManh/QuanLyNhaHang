import os,json
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from scripts.stripe_local_listener import verified_cli_environment


class StripeLocalListenerTests(SimpleTestCase):
    @patch('stripe.Account.retrieve',return_value=SimpleNamespace(id='acct_test_fixture'))
    def test_cli_login_must_match_account_and_test_mode(self,account):
        for identity in ({'account_id':'acct_other','mode':'test'},{'account_id':'acct_test_fixture','mode':'live'},{'account_id':'acct_test_fixture'}):
            with self.subTest(identity=identity),patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(identity))):
                with self.assertRaises(ValueError):verified_cli_environment('sk_test_fixture','cli-login','stripe')
    @patch('stripe.Account.retrieve',return_value=SimpleNamespace(id='acct_test_fixture'))
    def test_cli_does_not_inherit_another_api_key(self,account):
        with patch.dict(os.environ,{'STRIPE_API_KEY':'different-key'}),patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{"account_id":"acct_test_fixture","mode":"test"}')) as call:
            env=verified_cli_environment('sk_test_fixture','cli-login','stripe')
        self.assertNotIn('STRIPE_API_KEY',env);self.assertNotIn('STRIPE_API_KEY',call.call_args.kwargs['env'])
    @patch('stripe.Account.retrieve',return_value=SimpleNamespace(id='acct_test_fixture'))
    def test_application_mode_passes_exact_test_key_in_environment_only(self,account):
        env=verified_cli_environment('sk_test_fixture','application-key','stripe');self.assertEqual(env['STRIPE_API_KEY'],'sk_test_fixture')
    def test_live_or_missing_key_rejected_before_any_api(self):
        with patch('stripe.Account.retrieve') as call:
            for key in ('','sk_live_fixture'):
                with self.assertRaises(ValueError):verified_cli_environment(key,'cli-login','stripe')
            call.assert_not_called()
