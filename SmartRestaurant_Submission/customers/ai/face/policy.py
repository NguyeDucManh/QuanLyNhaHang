"""Cosine thresholds: operational provisional policy, separate from calibration."""
import math
from django.conf import settings
from django.core.exceptions import ValidationError

def effective_threshold(profile):
    value=profile.threshold if profile.threshold is not None else settings.FACEID_DEFAULT_THRESHOLD
    try: value=float(value)
    except (TypeError,ValueError): raise ValidationError('Cấu hình threshold không hợp lệ.')
    if not math.isfinite(value) or not -1 < value <= 1:
        raise ValidationError('Cosine threshold phải nằm trong (-1, 1].')
    return value, 'CALIBRATED' if profile.threshold is not None else 'PROVISIONAL'

def verification_options():
    return {'require_liveness':settings.FACEID_REQUIRE_LIVENESS,'allow_provisional':True,'operational_only':True}

def face_result(profile,score):
    from django.utils import timezone
    threshold,kind=effective_threshold(profile)
    return {'employee':profile.employee.full_name,'username':profile.employee.user.username,'employee_code':profile.employee.employee_code,'position':profile.employee.position.name,'similarity':score,'threshold':threshold,'threshold_type':kind,'liveness':bool(settings.FACEID_REQUIRE_LIVENESS),'timestamp':timezone.now().isoformat()}
