"""
ingest.py — kleine HTTP-server tussen de app en de bladwijzer.

Draait in een achtergrond-thread binnen hetzelfde proces als de Streamlit-app,
op een aparte poort, achter nginx. Hij ontvangt **geen verzuim**: dat blijft in
de browser (zie bookmarklet.py en rapport.py). Wat hij wel doet:

- GET  .../rapport.html            het rapportvenster (statische code)
- GET  ...?token=<t>               voor de bladwijzer: instellingen (codes,
                                   mentornamen, grenzen), de leerlingnummers van
                                   de coördinator en klaargezette logboeknotities
- POST ...?token=<t>&schrijf=1     per notitie of het schrijven in Magister lukte

Het token is per gebruiker (afgeleid van het eckid, zie app._token), zodat
niemand bij de lijst of wachtrij van een ander kan.

Alles staat alleen in het geheugen. Bij meerdere Streamlit-workers/replica's
moet dit vervangen worden door een gedeelde store.
"""

import json
import threading
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rapport

_MAX_BYTES   = 64 * 1024           # alleen schrijfuitslagen komen hier binnen
_LIJSTEN     = {}                  # token -> [leerling-ids] voor de coördinator
_SCHRIJF     = {}                  # token -> [logboekopdrachten die nog weg moeten]
_UITSLAG     = {}                  # token -> [uitslag per opdracht van de laatste ronde]
_CONFIG      = {}                  # token -> instellingen uit de zijbalk van de app
_STORE_LOCK  = threading.Lock()
_START_LOCK  = threading.Lock()
_started_port = None
_standaard   = lambda: {}          # gedeelde instellingen (codes, mentoren); zet de app

# Het rapportvenster mag zelf niets versturen; de meta-CSP in de pagina zegt
# hetzelfde, maar als header geldt hij ook als iemand de pagina anders opent.
_RAPPORT_HEADERS = {
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Security-Policy': ("default-src 'none'; script-src 'unsafe-inline'; "
                                "style-src 'unsafe-inline'; img-src data:; "
                                "form-action 'none'; base-uri 'none'"),
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-cache',
    # Bewust géén Cross-Origin-Opener-Policy: dan verliest het venster de
    # koppeling met het Magister-tabblad (window.opener).
}


def zet_standaard(functie):
    """Functie die de gedeelde instellingen levert (codes.json, mentoren.json).

    Wordt bij elke vraag opnieuw aangeroepen, zodat een wijziging in de app
    meteen bij de bladwijzer is — ook na een herstart, voordat iemand de app
    heeft geopend.
    """
    global _standaard
    _standaard = functie


def config_zet(token, config):
    """Instellingen uit de zijbalk van deze gebruiker (grenzen, selectie, ...)."""
    with _STORE_LOCK:
        _CONFIG[token] = dict(config)


def config_lees(token):
    try:
        uit = dict(_standaard() or {})
    except Exception:
        uit = {}
    with _STORE_LOCK:
        uit.update(_CONFIG.get(token, {}))
    return uit


def lijst_zet(token, ids):
    """Leerlingnummers klaarzetten die de bladwijzer bij elke klik ophaalt.

    Zo hoeft de knop niet opnieuw geïnstalleerd te worden als de lijst wijzigt.
    """
    with _STORE_LOCK:
        _LIJSTEN[token] = [int(i) for i in ids]


def lijst_lees(token):
    with _STORE_LOCK:
        return list(_LIJSTEN.get(token, []))


def schrijf_zet(token, opdrachten):
    """Logboekopdrachten klaarzetten die de bladwijzer moet wegschrijven.

    Elke opdracht heeft een sleutel; de bladwijzer meldt per sleutel terug of
    het gelukt is, zodat een tweede ronde niets dubbel schrijft.
    """
    with _STORE_LOCK:
        _SCHRIJF[token] = list(opdrachten)


def schrijf_lees(token):
    with _STORE_LOCK:
        return list(_SCHRIJF.get(token, []))


def schrijf_meld(token, geschreven):
    """Uitslag van de bladwijzer verwerken, meteen bij binnenkomst.

    Gelukte opdrachten gaan uit de wachtrij; mislukte blijven staan met de
    foutmelding erbij. Dit gebeurt hier en niet pas als de Streamlit-pagina
    herlaadt — anders schrijft een tweede ronde dezelfde notities nog een keer.
    """
    per_sleutel = {g.get('sleutel'): g for g in geschreven if isinstance(g, dict)}
    with _STORE_LOCK:
        rest = []
        for o in _SCHRIJF.get(token, []):
            g = per_sleutel.get(o.get('sleutel'))
            if g and g.get('ok'):
                continue
            if g:
                o = dict(o, fout=str(g.get('fout') or 'onbekende fout')[:200])
            rest.append(o)
        _SCHRIJF[token] = rest
        _UITSLAG[token] = [{'sleutel': g.get('sleutel'), 'ok': bool(g.get('ok')),
                            'fout': str(g.get('fout') or '')[:200]}
                           for g in per_sleutel.values()]


def schrijf_uitslag(token):
    """Haal (en verwijder) de laatste uitslag, om hem één keer te tonen."""
    with _STORE_LOCK:
        return _UITSLAG.pop(token, None)


class _Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.rstrip('/').endswith('/rapport.html'):
            self._rapport()
            return
        token = (parse_qs(url.query).get('token') or [''])[0]
        if not token:
            self._reply(400, {'ok': False, 'error': 'bad request'})
            return
        self._reply(200, {'ok': True, 'ids': lijst_lees(token),
                          'schrijf': schrijf_lees(token),
                          'config': config_lees(token)})

    def do_POST(self):
        vraag = parse_qs(urlparse(self.path).query)
        token = (vraag.get('token') or [''])[0]
        length = int(self.headers.get('Content-Length', 0) or 0)
        if (not token or (vraag.get('schrijf') or [''])[0] != '1'
                or length <= 0 or length > _MAX_BYTES):
            self._reply(400, {'ok': False, 'error': 'bad request'})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            self._reply(400, {'ok': False, 'error': 'invalid json'})
            return
        geschreven = payload.get('geschreven') if isinstance(payload, dict) else None
        if not isinstance(geschreven, list):
            self._reply(400, {'ok': False, 'error': 'bad request'})
            return
        schrijf_meld(token, geschreven)
        self._reply(200, {'ok': True, 'rest': len(schrijf_lees(token))})

    def _rapport(self):
        try:
            body = rapport.bouw().encode('utf-8')
        except Exception:
            self._reply(500, {'ok': False, 'error': 'rapport niet te bouwen'})
            return
        self.send_response(200)
        for k, v in _RAPPORT_HEADERS.items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def log_message(self, *args):
        pass  # geen console-spam, en geen tokens in de log


def ensure_server(port, host='127.0.0.1'):
    """Start de server één keer per proces (idempotent).

    Standaard alleen op localhost: op een server staat nginx ervoor, dus de
    poort hoeft niet van buiten bereikbaar te zijn.
    """
    global _started_port
    with _START_LOCK:
        if _started_port is not None:
            return _started_port
        srv = ThreadingHTTPServer((host, port), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _started_port = port
        return port
