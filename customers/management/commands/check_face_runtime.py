"""Read-only FaceID deployment audit. No images, vectors or credentials emitted."""
import importlib.metadata
import json
import time

from django.core.management.base import BaseCommand
from django.db.models import Count
from customers.ai.artifacts import root, read_json, sha256
from customers.ai.face.runtime import asset_path
from customers.models import FaceProfile, FaceEmbedding


class Command(BaseCommand):
    help = 'Inspect FaceID assets, hashes and model compatibility without changing data.'

    def add_arguments(self, parser):
        parser.add_argument('--load-engine', action='store_true')

    def handle(self, *args, **options):
        report = {'read_only': True, 'assets': {}, 'packages': {}}
        for package in ('mediapipe', 'onnxruntime', 'opencv-contrib-python', 'numpy'):
            try:
                report['packages'][package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                report['packages'][package] = 'missing'
        folder = root() / 'pretrained'
        try:
            manifest = read_json(folder / 'manifest.json')
            for name in ('facenet.onnx', 'face_landmarker.task'):
                try:
                    path = asset_path(folder, name, manifest[name])
                    report['assets'][name] = {'present': True, 'bytes': path.stat().st_size,
                        'hash_matches': sha256(path) == manifest[name]['sha256']}
                except (OSError, RuntimeError, KeyError):
                    report['assets'][name] = {'present': False}
            report['manifest_present'] = True
            version = manifest['facenet.onnx']['sha256']
            report['model_version'] = version
            report['matching_profiles'] = FaceProfile.objects.filter(model_version=version).count()
            report['mismatched_profiles'] = FaceProfile.objects.exclude(model_version=version).count()
        except (OSError, ValueError, KeyError):
            report['manifest_present'] = False
        report['profiles'] = list(FaceProfile.objects.values('model_version').annotate(count=Count('pk')))
        report['embeddings'] = FaceEmbedding.objects.count()
        report['embedding_dimensions'] = sorted({len(vector) for vector in FaceEmbedding.objects.values_list('vector', flat=True)})
        if options['load_engine']:
            start = time.perf_counter()
            try:
                from customers.ai.face.facenet_service import engine
                net = engine()
                report['engine'] = {'ready': True, 'model_version': net.model_version,
                    'providers': net.session.get_providers()}
                import numpy as np
                started = time.perf_counter()
                vector = net.embedding(np.zeros((160, 160, 3), dtype=np.uint8))
                report['engine']['tensor_smoke_dimensions'] = len(vector)
                report['engine']['tensor_smoke_seconds'] = round(time.perf_counter() - started, 3)
                report['engine']['tensor_smoke_is_identity_test'] = False
            except Exception as error:
                report['engine'] = {'ready': False, 'error_type': type(error).__name__}
            report['engine']['load_seconds'] = round(time.perf_counter() - start, 3)
            try:
                import resource
                report['process_peak_rss_kb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            except ImportError:
                import ctypes
                from ctypes import wintypes
                class Memory(ctypes.Structure):
                    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ('peak', 'rss', 'quota_peak', 'quota', 'nonpaged_peak', 'nonpaged', 'pagefile', 'pagefile_peak')]
                memory = Memory(); memory.cb = ctypes.sizeof(memory)
                ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
                ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
                if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(memory), memory.cb):
                    report['process_rss_mb'] = round(memory.rss / 1024**2, 2)
        self.stdout.write(json.dumps(report, ensure_ascii=True, indent=2))
