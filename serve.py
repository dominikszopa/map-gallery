#!/usr/bin/env python3
"""Simple HTTP server for local testing. Serves the media/dist/ directory."""

import http.server
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

os.chdir(os.path.join(os.path.dirname(__file__), "media", "dist"))
handler = http.server.SimpleHTTPRequestHandler
with http.server.HTTPServer(("", PORT), handler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    httpd.serve_forever()
