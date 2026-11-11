"""Fail the build if the pinned MediaPipe native runtime cannot load; no DB access."""
from importlib.metadata import version

# This binding belongs to mediapipe==1.1.0, pinned in requirements.txt.
# Importing mediapipe alone does not load its native library and misses absent EGL.
from mediapipe.tasks.python.core.mediapipe_c_bindings import load_raw_library

load_raw_library()
print(f"MediaPipe {version('mediapipe')} native library: ready")
