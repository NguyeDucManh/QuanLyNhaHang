"""Build-time model installation in a temporary directory, without networking or DB."""
import hashlib
import json
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings


class FaceModelInstallTests(SimpleTestCase):
    def install(self, corrupt=False):
        with tempfile.TemporaryDirectory() as directory, override_settings(AI_MODEL_ROOT=Path(directory)):
            folder = Path(directory) / 'pretrained'
            folder.mkdir()
            data = b'model test fixture, not a real biometric model'
            manifest = {name: {'local_path': 'D:\\missing\\' + name,
                'sha256': hashlib.sha256(data).hexdigest()} for name in ('facenet.onnx','face_landmarker.task')}
            path = folder / 'manifest.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            info = SimpleNamespace(name='input',shape=[None,160,160,3],type='tensor(float)')
            session = SimpleNamespace(get_inputs=lambda:[info],get_outputs=lambda:[info])
            embedding = Mock()
            with patch('urllib.request.urlopen', side_effect=lambda *a, **k: BytesIO(b'wrong' if corrupt else data)), patch('onnxruntime.InferenceSession', return_value=session), patch.dict('sys.modules', {'huggingface_hub':SimpleNamespace(snapshot_download=embedding)}):
                if corrupt:
                    with self.assertRaises(CommandError):
                        call_command('download_ai_models','--face-only', stdout=StringIO())
                    self.assertFalse((folder/'facenet.onnx').exists())
                    self.assertFalse((folder/'facenet.download').exists())
                else:
                    call_command('download_ai_models','--face-only', stdout=StringIO())
                    saved = json.loads(path.read_text(encoding='utf-8'))
                    for name in manifest:
                        self.assertEqual(Path(saved[name]['local_path']), folder/name)
                        self.assertEqual((folder/name).read_bytes(), data)
                        self.assertEqual(saved[name]['sha256'], manifest[name]['sha256'])
                embedding.assert_not_called()

    def test_face_only_ignores_old_windows_paths_and_preserves_hash(self):
        self.install()

    def test_corrupted_download_is_rejected_before_publish(self):
        self.install(corrupt=True)
