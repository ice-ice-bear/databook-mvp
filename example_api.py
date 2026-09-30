"""Fictional shop analytics API, reachable only inside the demo Compose network."""
import json
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from pipeline import mock_rows


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != '/daily':
            self.send_error(404)
            return
        try:
            days = [date.fromisoformat(d) for d in parse_qs(url.query)['dates'][0].split(',')]
            if len(days) != 2 or len(set(days)) != 2:
                raise ValueError('Two distinct dates required')
            rows = [dict(day=r['date'], source=r['channel'], device_type=r['device'],
                         sessions=r['visits'], views=r['page_views'], purchases=r['orders'],
                         sales_krw=r['revenue_krw']) for r in mock_rows(days)]
        except (ValueError, KeyError):
            self.send_error(400, 'Expected dates=YYYY-MM-DD,YYYY-MM-DD')
            return
        content = json.dumps({'provider': 'example_shop', 'rows': rows}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
