"""Local dev static file server for frontend/.

Plain `python -m http.server` lets browsers cache index.html/app.js/
styles.css between edits, which makes UI changes appear to not take
effect until a hard reload. This sends Cache-Control: no-store on every
response so a normal refresh always picks up the latest files.
"""

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    HTTPServer(("", port), NoCacheHandler).serve_forever()
