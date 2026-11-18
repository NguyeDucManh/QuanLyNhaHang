# MediaPipe TCMalloc abort on Render

The Render log for a274f56 ends with `NumCPUs: maybe_cpus.has_value()` and exit
134 while `check_face_native.py` loads the native library. This is SIGABRT, not
a Python exception, a missing GLES library, or evidence of an OOM kill.

The official Linux MediaPipe 1.1.0 wheel embeds TCMalloc in
`mediapipe/tasks/c/libmediapipe.so`. Binary inspection finds the exact assertion
and `/sys/devices/system/cpu/possible`. Upstream TCMalloc's
`NumPossibleCPUsNoCache()` reads that sysfs file and returns an empty optional on
read/parse failure; `NumCPUs()` then aborts. Render's actual sysfs visibility has
not been inspected directly; the CI negative test reproduces this failure with
an empty sysfs mount. Do not call a missing sysfs file a measured Render fact
without shell diagnostics.

Sources:
- https://github.com/google/tcmalloc/blob/master/tcmalloc/internal/sysinfo.cc
- https://github.com/google/tcmalloc/blob/master/tcmalloc/internal/sysinfo.h
- https://github.com/google-ai-edge/mediapipe/issues/6371
- https://pypi.org/pypi/mediapipe/0.10.35/json

## Fix

Pin Linux to the official MediaPipe **0.10.35** Tasks C API wheel, without the
embedded TCMalloc present in 1.1.0. Keep the existing Windows/macOS pin 1.1.0.
Python 3.14.8, ONNX Runtime, NumPy, FaceNet/landmarker binaries and their hashes,
model_version, thresholds, liveness and all business logic stay unchanged.
The Linux wheel is py3-none-manylinux_2_28_x86_64 and accepts the existing NumPy
pin; real API/model compatibility still must pass CI, not just metadata checks.

Linux 0.10.35 wheel SHA256:
`db9a579df48cffe9570cd3e93f6a5d2dd089a1103b846c60c5b5de8a21c38db0`.
Baseline 1.1.0 wheel SHA256:
`f6830aa5fbe87ab49e5eacd36a66611f9788819b45999fb76e9f5beb4638762b`.

Do not fabricate `/sys` CPU files, override CPU IDs, preload allocator shims,
ignore SIGABRT, or skip native validation. The Docker image still supplies GLES,
EGL and other dependencies. build.sh and start_render.sh still run the native
check and stop on failure. Native checks now flush stage/version diagnostics
before dlopen so subsequent fatal errors identify the library being loaded.

## Required CI

- Build the production Dockerfile with the entire build RUN using an empty
  BuildKit tmpfs /sys: dependencies, native load, models, Django check, static.
- Against that image and an empty read-only /sys, load the SHA-pinned old Linux
  library: require fatal exit 134 (SIGABRT) or 139 (SIGSEGV) and the exact NumCPUs
  assertion. Render reported 134; the first CI reproduction reported 139.
  Load the installed
  fixed library: require success and actual ONNX CPU provider.
- Start the production CMD with flags OFF and disposable PostgreSQL; verify
  health, proxy/HTTPS, static, non-root and no OOM.
- Run the existing real 5/25-frame detector/embedding and Django HTTP probe with
  empty /sys/devices/system/cpu, 512 MiB, no swap and one CPU. Preserve
  /sys/fs/cgroup to publish actual peak memory/OOM counters.
- Ubuntu full regression, system checks and migration drift on test PostgreSQL.

Repeated sample frames validate runtime compatibility, not employee identity,
liveness accuracy, camera hardware or production recognition quality. CI is not
Render; a passing check still requires an approved deployment and real logs.

## Scope and rollout

No new migration, no production DB access, no secret/flag changes. Migration
0022–0024 remains unapproved. This PR must be reviewed before merge; do not deploy
again until the final head's required CI succeeds. Existing Render Docker fields
and start command remain as prepared for PR7. No new service or paid plan.
Do not roll back by restoring databases or dropping tables.
