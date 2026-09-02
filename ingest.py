"""
ingest.py — kleine HTTP-ontvanger voor de verzuim-data van de bookmarklet.

Draait in een achtergrond-thread binnen hetzelfde proces als de Streamlit-app,
op een aparte poort. De bookmarklet (op de magister.net-origin) POST't hier de
opgehaalde verzuim-JSON naartoe; de Streamlit-pagina haalt hem daarna uit het
geheugen op via take().

Overgenomen uit `mentoruur/verzuim_ingest.py`; alleen de limieten zijn hier
ruimer, omdat een teamleider een hele afdeling ophaalt in plaats van één
mentorgroep.

Bewaart data alleen kort in het geheugen (TTL) — niets op schijf.

Let op: dit deelt geheugen met de Streamlit-reruns omdat het hetzelfde proces is.
Bij meerdere Streamlit-workers/replica's moet dit vervangen worden door een
gedeelde store (Redis/db).
"""

import time
import json
import threading
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_TTL         = 900                 # seconden dat een payload geldig blijft (ophalen duurt langer)
_MAX_BYTES   = 25 * 1024 * 1024    # 25 MB veiligheidslimiet
_STORE       = {}                  # token -> (payload, timestamp)
_STORE_LOCK  = threading.Lock()
_START_LOCK  = threading.Lock()
_started_port = None


def put(token, payload):
    with _STORE_LOCK:
        _STORE[token] = (payload, time.time())
        _prune_locked()


def take(token):
    """Haal (en verwijder) de payload voor dit token, indien vers genoeg."""
    with _STORE_LOCK:
        item = _STORE.pop(token, None)
    if not item:
        return None
    payload, ts = item
    if time.time() - ts > _TTL:
        return None
    return payload


def _prune_locked():
    now = time.time()
    for k in [k for k, (_, ts) in _STORE.items() if now - ts > _TTL]:
        _STORE.pop(k, None)


class _Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        token = (parse_qs(urlparse(self.path).query).get('token') or [''])[0]
        length = int(self.headers.get('Content-Length', 0) or 0)
        if not token or length <= 0 or length > _MAX_BYTES:
            self._reply(400, {'ok': False, 'error': 'bad request'})
            return
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            self._reply(400, {'ok': False, 'error': 'invalid json'})
            return
        put(token, payload)
        n = len(payload.get('students', [])) if isinstance(payload, dict) else 0
        self._reply(200, {'ok': True, 'students': n})

    def _reply(self, code, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def log_message(self, *args):
        pass  # geen console-spam


def ensure_server(port):
    """Start de ontvanger één keer per proces (idempotent)."""
    global _started_port
    with _START_LOCK:
        if _started_port is not None:
            return _started_port
        srv = ThreadingHTTPServer(('0.0.0.0', port), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _started_port = port
        return port
