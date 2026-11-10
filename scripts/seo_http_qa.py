"""Read-only SEO inspection for local or deployed URLs. No indexation claims."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urljoin
from xml.etree import ElementTree


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.canonical, self.graphs, self.titles = {}, [], [], []
        self.mode, self.text = '', []
        self.h1s = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('name', attrs.get('property'))] = attrs.get('content')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs['href'])
        if tag == 'h1':
            self.h1s += 1
        if tag == 'title' or (tag == 'script' and attrs.get('type') == 'application/ld+json'):
            self.mode, self.text = tag, []

    def handle_data(self, text):
        if self.mode:
            self.text.append(text)

    def handle_endtag(self, tag):
        if self.mode == tag:
            text = ''.join(self.text)
            if tag == 'title':
                self.titles.append(text)
            else:
                self.graphs += json.loads(text).get('@graph', [])
            self.mode = ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--render-proxy', action='store_true')
    args = parser.parse_args()
    rows = []
    paths = ['/', '/menu/', '/about/', '/offers/', '/combos/', '/robots.txt', '/sitemap.xml', '/login/', '/cart/']
    detail = None
    for path in paths:
        url = args.base.rstrip('/') + path
        headers = {'X-Forwarded-Proto': 'https'} if args.render_proxy else {}
        try:
            try:
                response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=35)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                body = response.read().decode('utf-8')
                row = {'path': path, 'status': response.status, 'content_type': response.headers.get_content_type(),
                       'x_robots_tag': response.headers.get('X-Robots-Tag'), 'final_url': response.url}
            if row['content_type'] == 'text/html':
                head = Head(); head.feed(body)
                row.update(titles=head.titles, description=head.meta.get('description'),
                           canonical=head.canonical, robots=head.meta.get('robots'), h1_count=head.h1s,
                           schema_types=[node.get('@type') for node in head.graphs],
                           og_image=head.meta.get('og:image'), twitter_card=head.meta.get('twitter:card'))
                if path == '/menu/' and not detail:
                    for node in head.graphs:
                        if node.get('@type') == 'Menu' and node.get('hasMenuItem'):
                            from urllib.parse import urlsplit
                            detail = urlsplit(node['hasMenuItem'][0]['url']).path
                            paths.append(detail)
                            break
            elif path == '/sitemap.xml' and row['status'] == 200:
                xml = ElementTree.fromstring(body)
                row['locations'] = [node.text for node in xml.findall('{*}url/{*}loc')]
            elif path == '/robots.txt':
                row['body'] = body
            rows.append(row)
        except (OSError, ValueError, ElementTree.ParseError) as error:
            rows.append({'path': path, 'error': type(error).__name__})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{'path': row['path'], 'status': row.get('status'), 'error': row.get('error')} for row in rows]))


if __name__ == '__main__':
    main()
