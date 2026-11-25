"""Local demo server: the static UI plus POST /api/analyze (paste a dossier) and GET /api/sample.
  uv run python -m vestigium.serve        then open http://127.0.0.1:8000/index.html
Gemini keys stay server-side (.env); the browser never sees them.
"""
import json, pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .dossier import dossier
from .generator import all_cases
from .intake import analyze

DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
CASES = {c["id"]: c for c in all_cases()}


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(DEMO), **k)

    def _json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/sample":
            q = parse_qs(u.query); cid = q.get("case", ["prop-014"])[0]; style = q.get("style", ["messy"])[0]
            if cid not in CASES or style not in ("clean", "messy"): return self._json({"error": "unknown sample"}, 404)
            return self._json({"case": cid, "style": style, "text": dossier(CASES[cid], style)})
        if u.path == "/api/ping": return self._json({"ok": True})
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/analyze": return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        if n > 200_000: return self._json({"error": "dossier too large"}, 413)
        try: body = json.loads(self.rfile.read(n))
        except Exception: return self._json({"error": "bad request"}, 400)
        text = (body.get("text") or "").strip()
        if not text: return self._json({"error": "Paste a dossier first."}, 400)
        self._json(analyze(text, reader=body.get("reader", "auto"), as_of=body.get("as_of") or None))

    def log_message(self, *a): pass


if __name__ == "__main__":
    print("Vestigium demo: http://127.0.0.1:8000/index.html  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
