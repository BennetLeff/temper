#!/usr/bin/env python3
"""Local sink: POST /<name> body -> runs-native21/s23cmp/dl/<name>/<name>.pdf (browser-fetched datasheets)."""
import http.server, os, re
DL = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s23cmp/dl"
class H(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()
    def do_POST(self):
        name = re.sub(r"[^a-z0-9_-]", "", self.path.strip("/").lower())
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        os.makedirs(f"{DL}/{name}", exist_ok=True)
        open(f"{DL}/{name}/{name}.pdf", "wb").write(body)
        self.send_response(200); self._cors(); self.end_headers(); self.wfile.write(f"{name} {n}".encode())
http.server.HTTPServer(("127.0.0.1", 8765), H).serve_forever()
