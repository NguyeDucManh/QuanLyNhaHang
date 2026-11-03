"""Run Web backend checks against existing configuration, without reseeding data."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
output = root / 'artifacts'
output.mkdir(exist_ok=True)
env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'}
commands = [
    ('check', ['manage.py', 'check']),
    ('migration-check', ['manage.py', 'makemigrations', '--check', '--dry-run']),
    ('migrate', ['manage.py', 'migrate', '--noinput']),
    ('regression', ['manage.py', 'test', '--noinput']),
    ('pip-check', ['-m', 'pip', 'check']),
]
failed = False
for name, args in commands:
    path = output / f'web-only-{name}.log'
    with path.open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, *args], cwd=root, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
    print(f'{name}: exit={result.returncode}; log=artifacts/{path.name}', flush=True)
    failed |= result.returncode != 0
    if name in {'migration-check', 'migrate'} and result.returncode:
        sys.exit(result.returncode)
sys.exit(1 if failed else 0)
