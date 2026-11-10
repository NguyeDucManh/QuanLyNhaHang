"""Verify every collected asset via HTTP against the matching deployed build."""
import argparse
import concurrent.futures
import json
import mimetypes
from pathlib import Path
import urllib.request
from urllib.parse import quote


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--manifest', type=Path, default=Path('staticfiles/staticfiles.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--render-proxy', action='store_true')
    args = parser.parse_args()
    paths = json.loads(args.manifest.read_text(encoding='utf-8'))['paths']

    def check(row):
        source, hashed = row
        # Windows collectstatic may retain native separators in manifest values;
        # Django's storage.url normalizes them before emitting HTTP URLs.
        url = args.base.rstrip('/') + '/static/' + quote(hashed.replace('\\', '/'), safe='/')
        headers = {'X-Forwarded-Proto': 'https'} if args.render_proxy else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                actual = response.headers.get_content_type()
                expected = mimetypes.guess_type(source)[0] or 'application/octet-stream'
                correct = actual == expected or (source.endswith('.js') and actual in ('text/javascript', 'application/javascript'))
                return {'source': source, 'url': url, 'status': response.status,
                        'mime': actual, 'expected_mime': expected, 'mime_ok': correct,
                        'immutable': 'immutable' in response.headers.get('Cache-Control', '')}
        except OSError as error:
            return {'source': source, 'url': url, 'error': type(error).__name__}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(check, paths.items()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    failed = [row for row in rows if row.get('status') != 200 or not row.get('mime_ok')]
    print(json.dumps({'assets': len(rows), 'failure_count': len(failed), 'failures': failed[:10]}))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
