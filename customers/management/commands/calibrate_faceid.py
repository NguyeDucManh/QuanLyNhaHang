"""Private image directories; enrollment/validation/test must be disjoint."""
import base64
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from customers.models import FaceProfile
from customers.ai.face.facenet_service import engine
from customers.ai.face.evaluation import select_threshold,confusion
from customers.ai.artifacts import new_version,publish,sha256
import numpy as np

class Command(BaseCommand):
    help='Calibrate FaceID against real held-out images; publishes no metric without sufficient data.'
    def add_arguments(self,p):
        p.add_argument('--employee',type=int,required=True)
        for name in ['validation-genuine','validation-impostor','test-genuine','test-impostor']: p.add_argument('--'+name,required=True)
    def handle(self,*args,**options):
        try: profile=FaceProfile.objects.get(employee_id=options['employee'])
        except FaceProfile.DoesNotExist: raise CommandError('Nhân viên chưa đăng ký FaceID.')
        net=engine()
        if profile.model_version!=net.model_version: raise CommandError('Model version khác enrollment; đăng ký lại trước.')
        samples=list(profile.samples.all()); hashes={s.image_hash for s in samples}
        if not samples: raise CommandError('Không có embedding enrollment.')
        center=np.asarray([s.vector for s in samples]).mean(axis=0); center/=np.linalg.norm(center)
        groups={}; all_hashes=set(hashes)
        for name in ['validation_genuine','validation_impostor','test_genuine','test_impostor']:
            folder=Path(options[name]); paths=sorted(p for p in folder.iterdir() if p.suffix.lower() in ['.jpg','.jpeg','.png'])
            if len(paths)<5: raise CommandError(f'{name}: cần ≥5 ảnh thật khác nhau.')
            scores=[]
            for path in paths:
                digest=sha256(path)
                if digest in all_hashes: raise CommandError('Ảnh trùng giữa enrollment/validation/test.')
                all_hashes.add(digest); vector,quality,_=net.process(base64.b64encode(path.read_bytes()).decode())
                scores.append(float(vector@center))
            groups[name]=scores
        best,candidates=select_threshold(groups['validation_genuine'],groups['validation_impostor'])
        test=confusion(groups['test_genuine'],groups['test_impostor'],best['threshold'])
        metadata=publish(new_version('face_evaluation'),{'model_name':'FaceNet ONNX 128-d','model_version':net.model_version,'employee_id':profile.employee_id,'threshold':best['threshold'],'validation_candidates':candidates,'metrics':test,'image_hashes':sorted(all_hashes-hashes),'limitation':'Single-profile real-image evaluation; basic challenge liveness; not bank-grade anti-spoofing.'})
        profile.threshold=best['threshold']; profile.calibration=metadata; profile.save()
        self.stdout.write(str(test))
