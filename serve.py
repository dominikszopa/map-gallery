#!/usr/bin/env python3
"""Simple HTTP server for local testing.

Serves index.html from the project root (for live editing) and all other
files from media/dist/.
"""

import http.server
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "media", "dist")


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Serve index.html from project root, everything else from media/dist/
        rel = super().translate_path(path)
        name = os.path.relpath(rel, os.getcwd())
        if name in (".", "index.html"):
            return os.path.join(ROOT, "index.html")
        return os.path.join(DIST, name)


os.chdir(DIST)
with http.server.HTTPServer(("", PORT), Handler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    httpd.serve_forever()
