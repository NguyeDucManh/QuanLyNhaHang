"""Shared validation and PostgreSQL idempotency locks for business mutations."""
from decimal import Decimal, InvalidOperation
import uuid
from django.core.exceptions import ValidationError
from django.db import connection


def decimal_value(value, places=3, *, positive=False):
    try:
        number=Decimal(str(value))
        precision=Decimal(1).scaleb(-places)
        if not number.is_finite() or number < 0 or (positive and number <= 0) or number != number.quantize(precision):
            raise ValueError
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f'Số lượng/số tiền không hợp lệ (tối đa {places} chữ số thập phân).')


def lock_request(namespace, key):
    try:
        key=uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('Mã yêu cầu không hợp lệ. Hãy tải lại form.')
    # The request row does not exist yet; transaction-level advisory lock protects
    # duplicate submissions before INSERT. Existing documents use row locks.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',[namespace+':'+str(key)])
    return key


def existing_request(model, key, actor):
    obj=model.objects.filter(request_key=key).first()
    if obj and obj.created_by_id != actor.pk:
        raise ValidationError('Mã yêu cầu đã được sử dụng.')
    return obj


def save_validated(obj):
    obj.full_clean()
    obj.save()
    return obj
