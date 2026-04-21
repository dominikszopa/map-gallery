#!/usr/bin/env python3
"""HTTP server for the map gallery.

Local dev (no DIST_PATH set): serves index.html from the project root for live
editing and everything else from media/dist/.

Production (DIST_PATH set, e.g. on Railway with a mounted volume): serves
everything — including index.html — from DIST_PATH.
"""

import http.server
import os
import sys

PORT = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_ENV = os.environ.get("DIST_PATH")
DIST = DIST_ENV if DIST_ENV else os.path.join(ROOT, "media", "dist")
SERVE_INDEX_FROM_ROOT = DIST_ENV is None


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        rel = super().translate_path(path)
        name = os.path.relpath(rel, os.getcwd())
        if SERVE_INDEX_FROM_ROOT and name in (".", "index.html"):
            return os.path.join(ROOT, "index.html")
        return os.path.join(DIST, name)


os.chdir(DIST)
with http.server.HTTPServer(("", PORT), Handler) as httpd:
    print(f"Serving {DIST} at http://localhost:{PORT}")
    httpd.serve_forever()
