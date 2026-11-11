import base64
import hashlib
import threading
from functools import lru_cache
import cv2
import numpy as np
from django.core.exceptions import ValidationError
from customers.ai.artifacts import root, read_json, sha256
from .runtime import FaceServiceUnavailable, asset_path

def decode_frame(data):
    if not isinstance(data,str) or len(data)>1500000: raise ValidationError('Ảnh quá lớn/không hợp lệ.')
    try: raw=base64.b64decode(data.split(',')[-1],validate=True)
    except (ValueError,TypeError): raise ValidationError('Ảnh không hợp lệ.')
    image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if image is None or image.shape[0]*image.shape[1]>1920*1080: raise ValidationError('Ảnh phải là JPEG/PNG tối đa 1920×1080.')
    return image,hashlib.sha256(raw).hexdigest()

_engine_lock = threading.Lock()

def engine():
    # functools' cache alone permits duplicate concurrent first initialization.
    with _engine_lock:
        return _cached_engine()

@lru_cache(maxsize=1)
def _cached_engine():
    try:
        return FaceNet()
    except FaceServiceUnavailable:
        raise
    except Exception as error:
        raise FaceServiceUnavailable('Không khởi tạo được FaceNet/MediaPipe trên máy chủ. Cần kiểm tra model, thư viện và Render Logs.') from error

class FaceNet:
    def __init__(self):
        import onnxruntime as ort
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        folder=root()/'pretrained'
        if not (folder/'manifest.json').exists(): raise FaceServiceUnavailable('Thiếu manifest.json của FaceID trên máy chủ.')
        manifest=read_json(folder/'manifest.json')
        try:
            paths={name:asset_path(folder,name,manifest[name]) for name in ['facenet.onnx','face_landmarker.task']}
        except (KeyError, TypeError) as error:
            raise FaceServiceUnavailable('Manifest FaceID không hợp lệ.') from error
        for name in ['facenet.onnx','face_landmarker.task']:
            if sha256(paths[name])!=manifest[name]['sha256']: raise FaceServiceUnavailable('Model hash không khớp manifest: '+name)
        options=ort.SessionOptions(); options.intra_op_num_threads=1; options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(paths['facenet.onnx']),options,providers=['CPUExecutionProvider'])
        self.model_version=manifest['facenet.onnx']['sha256']
        self.landmarker=vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_buffer=paths['face_landmarker.task'].read_bytes()),num_faces=2,output_face_blendshapes=True))
        self.mp=mp; self.lock=threading.Lock()
        # MediaPipe uses a ThreadPoolExecutor for its C API. Close before Python
        # shuts down that executor; normal atexit runs too late on Python 3.14.
        threading._register_atexit(self.landmarker.close)

    def analyze(self,image):
        rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
        with self.lock:
            result=self.landmarker.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=rgb))
        if not result.face_landmarks: raise ValidationError('Không phát hiện khuôn mặt.')
        if len(result.face_landmarks)!=1: raise ValidationError('Phát hiện nhiều khuôn mặt; cần đúng một người.')
        landmarks=result.face_landmarks[0]; height,width=image.shape[:2]
        xs=[p.x for p in landmarks]; ys=[p.y for p in landmarks]
        x1=max(0,int(min(xs)*width)); x2=min(width,int(max(xs)*width))
        y1=max(0,int(min(ys)*height)); y2=min(height,int(max(ys)*height))
        if min(x2-x1,y2-y1)<80: raise ValidationError('Khuôn mặt quá nhỏ; tiến gần camera.')
        face=rgb[y1:y2,x1:x2]; gray=cv2.cvtColor(face,cv2.COLOR_RGB2GRAY)
        blur=float(cv2.Laplacian(gray,cv2.CV_64F).var()); brightness=float(gray.mean())
        if blur<35: raise ValidationError('Ảnh quá mờ; giữ camera ổn định.')
        if not 40<brightness<220: raise ValidationError('Ánh sáng không đạt; điều chỉnh ánh sáng.')
        nose=landmarks[1]; left=landmarks[234]; right=landmarks[454]
        yaw=(nose.x-(left.x+right.x)/2)/max(abs(right.x-left.x),.001)
        if abs(yaw)>.38: raise ValidationError('Quay đầu quá xa; nhìn gần thẳng vào camera.')
        blends={c.category_name:float(c.score) for c in result.face_blendshapes[0]} if result.face_blendshapes else {}
        blink=(blends.get('eyeBlinkLeft',0)+blends.get('eyeBlinkRight',0))/2
        return face,{'blur':blur,'brightness':brightness,'yaw':float(yaw),'blink':blink,'faces':1,'face_width':x2-x1,'face_height':y2-y1,
            'frame_width':width,'frame_height':height,'face_x':x1,'face_y':y1,
            'center_x':(x1+x2)/(2*width),'center_y':(y1+y2)/(2*height)}

    def embedding(self,face):
        input_info=self.session.get_inputs()[0]; shape=input_info.shape
        nhwc=shape[-1]==3
        size=int(shape[1] if nhwc else shape[2])
        image=cv2.resize(face,(size,size)).astype(np.float32)
        # Keras FaceNet exported upstream: per-image standardization.
        image=(image-image.mean())/max(float(image.std()),1/np.sqrt(image.size))
        tensor=(image[None] if nhwc else image.transpose(2,0,1)[None]).astype(np.float32,copy=False)
        output=np.asarray(self.session.run(None,{input_info.name:tensor})[0],np.float32).ravel()
        norm=float(np.linalg.norm(output))
        if not np.isfinite(output).all() or norm<1e-9: raise ValidationError('Embedding không hợp lệ.')
        return output/norm

    def process(self,data):
        image,digest=decode_frame(data); face,quality=self.analyze(image)
        return self.embedding(face),quality,digest
