"""Local test sandbox only; never select this settings module on Render."""
from restaurant_system.settings import *
assert not ON_RENDER
assert DATABASES['default']['HOST'] in ('localhost','127.0.0.1','::1')
assert DATABASES['default']['NAME'].startswith('test_issue10_sandbox_')
ISSUE10_TEST_FIXTURES_ENABLED=True
SECRET_KEY='issue10-local-sandbox-only-not-a-production-key-0123456789'
SESSION_COOKIE_NAME='issue10_sandbox_session'
CSRF_COOKIE_NAME='issue10_sandbox_csrf'
STRIPE_SECRET_KEY=''
STRIPE_WEBHOOK_SECRET=''
STRIPE_PUBLISHABLE_KEY=''
STRIPE_PUBLIC_BASE_URL='http://127.0.0.1:8001'
