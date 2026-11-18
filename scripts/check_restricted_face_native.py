"""CI-only negative/positive native test; no DB, production data or credentials.

Mask sysfs with an empty mount, not a fabricated CPU count. The old official
wheel must reproduce SIGABRT; the production image must run real native checks.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

IMAGE='smart-restaurant-release:ci'
URL='https://files.pythonhosted.org/packages/10/1d/ae070817ebc1b9500cec3f83faeeed1a405dcb764c23738a87726d96432c/mediapipe-1.1.0-py3-none-manylinux_2_28_x86_64.whl'
SHA='f6830aa5fbe87ab49e5eacd36a66611f9788819b45999fb76e9f5beb4638762b'
report={'environment':'production image; empty read-only /sys; 512 MiB; no swap; 1 CPU',
        'production_data_used':False,'passed':False}
try:
    with urllib.request.urlopen(URL,timeout=120) as response: wheel=response.read()
    assert hashlib.sha256(wheel).hexdigest()==SHA,'Baseline wheel SHA256 mismatch'
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        binary=archive.read('mediapipe/tasks/c/libmediapipe.so')
    assert b'maybe_cpus.has_value()' in binary and b'third_party/tcmalloc' in binary
    baseline=Path('.ci-libmediapipe-1.1.0.so').resolve();baseline.write_bytes(binary)
    del wheel,binary
    common=['docker','run','--rm','--memory=512m','--memory-swap=512m','--cpus=1',
            '--ulimit','core=0','--tmpfs','/sys:ro']
    old=subprocess.run([*common,'--mount',f'type=bind,source={baseline},target=/tmp/libmediapipe-baseline.so,readonly',
        IMAGE,'python','-c',"import ctypes;ctypes.CDLL('/tmp/libmediapipe-baseline.so')"],
        capture_output=True,text=True,timeout=90)
    report['baseline']={'version':'1.1.0','wheel_sha256':SHA,'exit_code':old.returncode,
        'numcpus_check_seen':'CHECK in NumCPUs: maybe_cpus.has_value() (false)' in old.stderr}
    # Fatal native CHECK can terminate with SIGABRT (Render) or SIGSEGV (this
    # wheel/CI). Require the exact assertion AND a fatal signal, never any error.
    assert old.returncode in (134,139) and report['baseline']['numcpus_check_seen'],old.stderr[-3000:]
    fixed=subprocess.run([*common,IMAGE,'python','scripts/check_face_native.py'],
        capture_output=True,text=True,timeout=90)
    report['fixed']={'exit_code':fixed.returncode,'stdout':fixed.stdout,'stderr':fixed.stderr}
    assert fixed.returncode==0,fixed.stderr[-3000:]
    assert json.loads(fixed.stdout.splitlines()[-1])['native_library_ready'] is True
    report['passed']=True
finally:
    Path('restricted-native-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
