import hashlib
import json
import uuid
from pathlib import Path
from django.conf import settings
from django.utils import timezone

def root():
    return Path(getattr(settings, 'AI_MODEL_ROOT', settings.BASE_DIR / 'ai_models'))

def new_version(kind):
    version = timezone.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    folder = root() / kind / version
    folder.mkdir(parents=True, exist_ok=False)
    return folder

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def publish(folder, metadata):
    metadata = {**metadata, 'version': folder.name, 'created_at': timezone.now().isoformat(), 'trained_at':timezone.now().isoformat()}
    write_json(folder / 'metadata.json', metadata)
    write_json(folder.parent / 'latest.json', {'version': folder.name})
    return metadata

def latest(kind):
    pointer = root() / kind / 'latest.json'
    if not pointer.exists():
        raise ValueError(f'Chưa có artifact {kind}; chạy command chuẩn bị/train trước.')
    version = read_json(pointer)['version']
    if Path(version).name != version:
        raise ValueError('Artifact version không hợp lệ.')
    return pointer.parent / version

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()
