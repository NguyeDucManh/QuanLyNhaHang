"""Read-only HTTP evidence. Never authenticates or creates bookings/payments."""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--render-proxy', action='store_true', help='Local Render simulation only')
    args = parser.parse_args()
    rows = []
    for path in ['/', '/menu/', '/login/', '/register/', '/cart/', '/offers/', '/combos/',
                 '/booking/', '/staff/', '/management/', '/healthz/', '/not-found/',
                 '/static/customer/css/style.css', '/static/ui/design-system.css',
                 '/static/ui/reference-match.css', '/static/customer/js/main.js',
                 '/static/admin/css/style.css', '/static/ui/staff-pos.css',
                 '/static/ui/favicon.svg', '/static/ui/images/garden-restaurant-hero.png']:
        headers = {'X-Forwarded-Proto': 'https'} if args.render_proxy else {}
        started = perf_counter()
        try:
            request = urllib.request.Request(args.base.rstrip('/') + path, headers=headers)
            try:
                response = urllib.request.urlopen(request, timeout=35)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                rows.append({'path': path, 'status': response.code, 'final_url': response.url,
                             'content_type': response.headers.get('Content-Type'),
                             'cache': response.headers.get('Cache-Control'),
                             'elapsed_ms': round((perf_counter() - started) * 1000)})
        except OSError as error:
            rows.append({'path': path, 'error_type': type(error).__name__})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
