"""Loopback HTTP transport for the isolated capacity probe, never production."""
from restaurant_system.settings import *

assert DATABASES['default']['NAME'] == 'restaurant_ci512'
assert DATABASES['default']['HOST'] == '127.0.0.1'
assert not ON_RENDER
# TLS terminates at Render's proxy in production. This CI container is reachable
# only through the runner's loopback and has no proxy/certificate to terminate it.
# Keep DEBUG=False and production static storage; only transport differs.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
