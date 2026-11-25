"""Local demo server: the static UI plus POST /api/analyze (paste a dossier) and GET /api/sample.
  uv run python -m vestigium.serve        then open http://127.0.0.1:8000/  (overview) or /app.html  (the app)
Gemini keys stay server-side (.env); the browser never sees them.
"""
import base64, json, pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .dossier import dossier
from .generator import all_cases
from .intake import analyze
from .scan import scan_analyze, render_scan, TIERS

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
        if u.path == "/api/scan_sample":      # render a synthetic scan of a built-in case, read it, and return the result with the photo
            q = parse_qs(u.query); cid = q.get("case", ["prop-014"])[0]; tier = q.get("tier", ["phone"])[0]
            if cid not in CASES or tier not in TIERS: return self._json({"error": "unknown sample"}, 404)
            files, _ = render_scan(dossier(CASES[cid], "clean"), tier, seed=1)
            try: out = scan_analyze(files)
            except Exception as e: return self._json({"error": f"The scanner is unavailable right now ({str(e)[:80]}). Try again in a minute."})
            if not out.get("error") and files[0][1] == "image/jpeg": out["preview"] = "data:image/jpeg;base64," + base64.b64encode(files[0][2]).decode()
            return self._json(out)
        if u.path == "/api/ping": return self._json({"ok": True})
        super().do_GET()

    def _scan(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > 20_000_000: return self._json({"error": "upload too large (max about 14 MB)"}, 413)
        try:
            body = json.loads(self.rfile.read(n)); files = []
            for f in body.get("files", [])[:12]:
                raw = base64.b64decode(f["data"], validate=True)
                ok = (raw[:5] == b"%PDF-" and f.get("mime") == "application/pdf") or (raw[:3] == b"\xff\xd8\xff" and f.get("mime") == "image/jpeg") or \
                     (raw[:8] == b"\x89PNG\r\n\x1a\n" and f.get("mime") == "image/png") or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" and f.get("mime") == "image/webp")
                if not ok: return self._json({"error": f"{str(f.get('name'))[:40]} is not a PDF, JPEG, PNG or WebP file"}, 400)
                files.append((str(f.get("name", "file"))[:60], f["mime"], raw))
        except Exception: return self._json({"error": "bad request"}, 400)
        if not files: return self._json({"error": "Choose a PDF or photos first."}, 400)
        try: self._json(scan_analyze(files))
        except Exception as e: self._json({"error": f"The scanner is unavailable right now ({str(e)[:80]}). Try again in a minute."})

    def do_POST(self):
        if urlparse(self.path).path == "/api/scan": return self._scan()
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
    print("Vestigium: http://127.0.0.1:8000/  (overview)  ·  http://127.0.0.1:8000/app.html  (the app)  ·  Ctrl+C to stop")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
