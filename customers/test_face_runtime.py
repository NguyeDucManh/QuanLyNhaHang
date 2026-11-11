import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, RequestFactory
from django.core.exceptions import PermissionDenied
from .ai.face.runtime import FaceServiceUnavailable, asset_path, face_api


class FaceRuntimeTests(SimpleTestCase):
    def test_quality_reports_real_frame_relative_detection_geometry(self):
        import numpy as np
        import threading
        from types import SimpleNamespace
        from .ai.face.facenet_service import FaceNet
        points = [SimpleNamespace(x=.5,y=.5) for _ in range(468)]
        points[234]=SimpleNamespace(x=.2,y=.5)
        points[454]=SimpleNamespace(x=.8,y=.5)
        points[10]=SimpleNamespace(x=.5,y=.2)
        points[152]=SimpleNamespace(x=.5,y=.8)
        result=SimpleNamespace(face_landmarks=[points],face_blendshapes=[])
        net=FaceNet.__new__(FaceNet);net.lock=threading.Lock()
        net.mp=SimpleNamespace(Image=lambda **kwargs:kwargs,ImageFormat=SimpleNamespace(SRGB='SRGB'))
        net.landmarker=SimpleNamespace(detect=lambda image:result)
        _,quality=net.analyze(np.random.default_rng(1).integers(0,256,(480,320,3),dtype=np.uint8))
        self.assertEqual((quality['frame_width'],quality['frame_height']),(320,480))
        self.assertEqual((quality['face_x'],quality['face_y']),(64,96))
        self.assertEqual((quality['face_width'],quality['face_height']),(192,288))
        self.assertEqual((quality['center_x'],quality['center_y']),(.5,.5))

    def test_concurrent_initialization_loads_only_one_model(self):
        from concurrent.futures import ThreadPoolExecutor
        from .ai.face import facenet_service
        facenet_service._cached_engine.cache_clear()
        try:
            with patch.object(facenet_service, 'FaceNet') as constructor:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    models = list(pool.map(lambda _: facenet_service.engine(), range(4)))
                self.assertEqual(constructor.call_count, 1)
                self.assertTrue(all(model is models[0] for model in models))
        finally:
            facenet_service._cached_engine.cache_clear()

    def test_low_variance_frame_still_uses_onnx_float32_input(self):
        import numpy as np
        from types import SimpleNamespace
        from .ai.face.facenet_service import FaceNet
        net = FaceNet.__new__(FaceNet)
        def run(outputs, inputs):
            tensor = inputs['image']
            self.assertEqual(tensor.dtype, np.float32)
            self.assertEqual(tensor.shape, (1, 160, 160, 3))
            return [np.ones((1, 128), dtype=np.float32)]
        net.session = SimpleNamespace(get_inputs=lambda: [SimpleNamespace(shape=[None,160,160,3],name='image')], run=run)
        self.assertEqual(len(net.embedding(np.zeros((160,160,3), dtype=np.uint8))), 128)

    def test_deployment_asset_wins_over_windows_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            local = folder / 'facenet.onnx'
            local.write_bytes(b'test fixture')
            self.assertEqual(asset_path(folder, 'facenet.onnx', {'local_path': r'D:\cache\facenet.onnx'}), local)
            local.unlink()
            with self.assertRaises(FaceServiceUnavailable):
                asset_path(folder, 'facenet.onnx', {'local_path': r'D:\missing\facenet.onnx'})

    def test_dependency_and_permission_errors_have_json_status(self):
        request = RequestFactory().post('/work/faceid/quality/')
        request.user = AnonymousUser()
        for failure, status in [(FaceServiceUnavailable('Missing model'), 503),
                (ImportError('internal path'), 503), (PermissionDenied(), 403),
                (RuntimeError('internal path'), 500)]:
            @face_api
            def view(request):
                raise failure
            with self.assertLogs('customers.ai.face.runtime', level='ERROR') if status in (500, 503) else __import__('contextlib').nullcontext():
                response = view(request)
            self.assertEqual(response.status_code, status)
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertTrue(response['Content-Type'].startswith('application/json'))
            self.assertNotIn('internal path', json.loads(response.content)['error'])

    def test_actual_quality_endpoint_handles_missing_engine(self):
        from .ai_phase_views import face_quality
        request = RequestFactory().post('/work/faceid/quality/', '{}', content_type='application/json')
        request.user = type('Admin', (), {'is_authenticated': True, 'is_active': True, 'is_superuser': True})()
        with patch('customers.ai.face.facenet_service.engine', side_effect=FaceServiceUnavailable('Missing model')):
            with self.assertLogs('customers.ai.face.runtime', level='ERROR'):
                response = face_quality(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)['code'], 'FACE_RUNTIME_UNAVAILABLE')
