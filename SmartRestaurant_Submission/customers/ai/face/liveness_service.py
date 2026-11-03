import secrets
from django.utils import timezone
from django.core.exceptions import ValidationError
from customers.models import FaceChallenge

def issue(actor,require_liveness=True):
    action=secrets.choice(['blink','left','right']) if require_liveness else 'straight'
    challenge=FaceChallenge.objects.create(actor=actor,action=action,expires_at=timezone.now()+timezone.timedelta(seconds=90))
    return {'id':str(challenge.pk),'action':action,'require_liveness':require_liveness,'instruction':{'straight':'Nhìn thẳng vào camera.','blink':'Nhìn thẳng, chớp mắt rồi mở mắt.','left':'Nhìn thẳng, quay đầu nhẹ sang trái rồi nhìn thẳng.','right':'Nhìn thẳng, quay đầu nhẹ sang phải rồi nhìn thẳng.'}[action]}

def validate_sequence(action,observations):
    if len(observations)<8: raise ValidationError('Cần chuỗi camera nhiều frame.')
    # Require neutral → action → neutral; score extracted by server only.
    if action=='blink':
        values=[r['blink'] for r in observations]; neutral=lambda x:x<.3; active=lambda x:x>.55
    else:
        values=[r['yaw'] for r in observations]; neutral=lambda x:abs(x)<.10
        active=(lambda x:x<-.16) if action=='left' else (lambda x:x>.16)
    stage=0
    for value in values:
        if stage==0 and neutral(value): stage=1
        elif stage==1 and active(value): stage=2
        elif stage==2 and neutral(value): return True
    raise ValidationError('Chưa hoàn thành thử thách liveness.')
