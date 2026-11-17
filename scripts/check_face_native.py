"""Fail the build if the pinned MediaPipe native runtime cannot load; no DB access."""
from importlib.metadata import version
import ctypes
import json
import sys
import os

libraries = ('libGLESv2.so.2', 'libEGL.so.1', 'libGL.so.1', 'libgomp.so.1')
if sys.platform == 'linux':
    for name in libraries:
        try:
            ctypes.CDLL(name)
        except OSError as error:
            raise RuntimeError(
                f'Missing Linux runtime library {name}. Use the production Dockerfile '
                'with libgles2/libegl1/libgl1/libgomp1; do not skip MediaPipe validation.'
            ) from error

# Both platform-specific pins expose the Tasks C API below.
# Importing mediapipe alone does not load its native library and misses absent EGL.
print(json.dumps({'stage':'mediapipe_native_load','mediapipe':version('mediapipe'),
    'cpu_possible_readable':os.access('/sys/devices/system/cpu/possible',os.R_OK) if sys.platform=='linux' else None,
    'os_cpu_count':os.cpu_count()}),flush=True)
from mediapipe.tasks.python.core.mediapipe_c_bindings import load_raw_library

load_raw_library()
print(json.dumps({'stage':'mediapipe_native_loaded'}),flush=True)
import onnxruntime as ort
if 'CPUExecutionProvider' not in ort.get_available_providers():
    raise RuntimeError('ONNX Runtime CPUExecutionProvider unavailable.')
print(json.dumps({'mediapipe':version('mediapipe'),'onnxruntime':ort.__version__,
    'native_library_ready':True,'cpu_provider_ready':True,
    'linux_libraries_checked':list(libraries) if sys.platform=='linux' else []}))
