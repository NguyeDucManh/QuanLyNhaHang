"""Server-generated, stable order references; uniqueness is enforced by PostgreSQL."""
import uuid
from django.utils import timezone


def generate_order_number():
    return f'ORD-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex}'
